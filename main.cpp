#include <hpx/algorithm.hpp>
#include <hpx/execution.hpp>
#include <hpx/init.hpp>

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <random>
#include <string>
#include <vector>

#include <limits>
#include <stdexcept>

using namespace hpx::parallel::detail;
using hpx::execution::parallel_executor;

namespace
{
    // Top-level configuration values for a single benchmark run.
    // These are the command-line knobs that control how much work is sorted,
    // how often we repeat the timed measurement, and whether we validate the
    // output or emit CSV text instead of a human-friendly summary.
    struct benchmark_config
    {
#if defined(HPX_DEBUG)
        // In debug builds we intentionally keep the dataset smaller so that the
        // sort can be debugged quickly without spending large amounts of time in
        // repeated execution.
        std::uint64_t size = 1'000'000;
#else
        // Production-style benchmark default: large enough to make the parallel
        // sort work economically meaningful while still being tractable for an
        // automated sweep over many thread counts and input sizes.
        std::uint64_t size = 100'000'000;
#endif
        int trials = 5;
        int warmup = 1;
        unsigned int seed = std::random_device{}();
        std::string distribution = "shuffle";
        bool verify = true;
        bool baseline = true;
        bool csv = false;
    };

    // Captures the timing results for one algorithm on one dataset.
    // We store the raw per-trial speeds because they are useful for both
    // statistical summaries and for debugging outlier behavior.
    struct benchmark_summary
    {
        std::string name;
        std::vector<double> trial_speed;
        double min_speed = 0.0;
        double max_speed = 0.0;
        double mean_speed = 0.0;
        double median_speed = 0.0;
    };

    // HPX accepts a thread count in a few different syntactic forms:
    //   --threads=40
    //   --threads 40
    // The benchmarking script passes the count as a CLI argument and wants the
    // runtime to map that to hpx.os_threads, so we normalize here.
    std::string parse_os_threads_arg(int argc, char* argv[])
    {
        for (int i = 1; i < argc; ++i)
        {
            std::string arg = argv[i];
            if (arg.rfind("--threads=", 0) == 0)
            {
                return arg.substr(std::string("--threads=").size());
            }

            if (arg == "--threads" && i + 1 < argc)
            {
                return argv[i + 1];
            }
        }

        // If the benchmark caller never specified a thread count, let HPX decide
        // from the machine defaults.
        return "all";
    }

    // Builds the raw dataset that will be sorted.
    // This is intentionally not a "real world" dataset like a file or DB dump;
    // it is a structured synthetic input so the benchmark is reproducible and so
    // we can compare distributions without external noise.
    std::vector<std::uint64_t> make_input(std::uint64_t size,
        std::string const& distribution, std::mt19937_64& rng)
    {
        std::vector<std::uint64_t> values(size);

        if (distribution == "shuffle")
        {
            // The standard benchmark pattern: a full permutation of [0, size)
            // so that the sort is operating on uniformly random inputs.
            std::iota(values.begin(), values.end(), std::uint64_t{0});
            std::shuffle(values.begin(), values.end(), rng);
            return values;
        }

        if (distribution == "uniform")
        {
            // Draw values from the full uint64_t domain using a uniform
            // distribution. This creates less structure than a permutation and is
            // useful for seeing how the algorithm behaves under very noisy data.
            std::uniform_int_distribution<std::uint64_t> dist;
            for (auto& v : values)
            {
                v = dist(rng);
            }
            return values;
        }

        if (distribution == "sorted")
        {
            // Already sorted, making the benchmark easy to verify and letting us
            // see the lower bound of how fast the sort can run on a favorable
            // input layout.
            std::iota(values.begin(), values.end(), std::uint64_t{0});
            return values;
        }

        if (distribution == "reverse")
        {
            // Descending values are a classic adversarial pattern for some sort
            // implementations and can expose poor partitioning behavior.
            for (std::uint64_t i = 0; i < size; ++i)
            {
                values[i] = size - i;
            }
            return values;
        }

        if (distribution == "few_unique")
        {
            // A highly skewed dataset with only a small number of distinct keys.
            // This is useful for testing performance on repetitive or clustered
            // data, which is common in real workloads.
            std::uniform_int_distribution<std::uint64_t> dist(0, 255);
            for (auto& v : values)
            {
                v = dist(rng);
            }
            return values;
        }

        throw std::runtime_error(
            "invalid --distribution value, use one of: shuffle, uniform, sorted, reverse, few_unique");
    }

    // Runs one benchmark configuration for a single algorithm.
    // We accept a generic sorter callable so the same harness can benchmark both
    // HPX sample_sort and the standard library baseline with almost no code
    // duplication.
    template <typename SortFn>
    benchmark_summary run_benchmark(std::string name,
        std::vector<std::uint64_t> const& base_input, int warmup, int trials,
        bool verify, SortFn&& sorter)
    {
        benchmark_summary summary;
        summary.name = std::move(name);
        summary.trial_speed.reserve(static_cast<std::size_t>(trials));

        // We report throughput as elements sorted per millisecond.
        // That means larger numbers are better, and the metric makes sense for
        // comparing different thread counts or different input sizes.
        auto const size = static_cast<double>(base_input.size());

        // Warmup runs are not included in the measurement, but they help the
        // runtime settle in and reduce one-time startup/cache effects.
        for (int i = 0; i < warmup; ++i)
        {
            std::vector<std::uint64_t> data = base_input;
            sorter(data);
            if (verify && !std::is_sorted(data.begin(), data.end()))
            {
                throw std::runtime_error("sort verification failed during warmup");
            }
        }

        // Repeated timed trials allow us to smooth out jitter and noise from the
        // OS scheduler or cache effects. We record each per-trial throughput.
        for (int t = 0; t < trials; ++t)
        {
            std::vector<std::uint64_t> data = base_input;

            auto const start = std::chrono::steady_clock::now();
            sorter(data);
            auto const end = std::chrono::steady_clock::now();

            if (verify && !std::is_sorted(data.begin(), data.end()))
            {
                throw std::runtime_error("sort verification failed in timed trial");
            }

            std::chrono::duration<double, std::milli> const elapsed = end - start;
            // This is a throughput metric, not a latency metric. The value says
            // how many elements are processed per millisecond.
            summary.trial_speed.push_back(size / elapsed.count());
        }

        // Summary statistics for the distribution of trial speeds.
        summary.min_speed = *std::min_element(summary.trial_speed.begin(), summary.trial_speed.end());
        summary.max_speed = *std::max_element(summary.trial_speed.begin(), summary.trial_speed.end());
        summary.mean_speed =
            std::accumulate(summary.trial_speed.begin(), summary.trial_speed.end(), 0.0) /
            static_cast<double>(summary.trial_speed.size());

        // Median is robust against outlier runs and is often more informative
        // than the mean for benchmarking, especially when the machine is noisy.
        std::vector<double> sorted = summary.trial_speed;
        std::sort(sorted.begin(), sorted.end());
        auto const mid = sorted.size() / 2;
        if (sorted.size() % 2 == 0)
        {
            summary.median_speed = (sorted[mid - 1] + sorted[mid]) / 2.0;
        }
        else
        {
            summary.median_speed = sorted[mid];
        }

        return summary;
    }

    // Human-readable output for a benchmark result.
    // This is the simpler mode used when the benchmark is run interactively.
    void print_summary(benchmark_summary const& summary)
    {
        std::cout << std::fixed << std::setprecision(3);
        std::cout << summary.name << "\n";
        std::cout << "  trials(elements/ms): ";
        for (std::size_t i = 0; i < summary.trial_speed.size(); ++i)
        {
            std::cout << summary.trial_speed[i];
            if (i + 1 < summary.trial_speed.size())
            {
                std::cout << ", ";
            }
        }
        std::cout << "\n";
        std::cout << "  min/median/mean/max(elements/ms): " << summary.min_speed << " / "
                  << summary.median_speed << " / " << summary.mean_speed << " / "
                  << summary.max_speed << "\n";
    }

    // CSV mode produces machine-readable output that the Python plotting script can
    // parse. This is especially important because the Python driver expects a fixed
    // column layout and filters rows by algorithm name.
    void print_csv(std::vector<benchmark_summary> const& all)
    {
        std::cout << "name,trial_idx,trial_speed,min_speed,median_speed,mean_speed,max_speed\n";
        for (auto const& summary : all)
        {
            for (std::size_t i = 0; i < summary.trial_speed.size(); ++i)
            {
                std::cout << summary.name << ',' << i << ',' << summary.trial_speed[i]
                          << ',' << summary.min_speed << ',' << summary.median_speed << ','
                          << summary.mean_speed << ',' << summary.max_speed << '\n';
            }
        }
    }
}    // namespace

// The actual benchmark entry point called by HPX after initialization.
// All the runtime options have already been parsed by the HPX framework, and this
// function is responsible for translating them into our benchmark_config and
// invoking the sort functions.
int hpx_main(hpx::program_options::variables_map& vm)
{
    benchmark_config cfg;

    // Read each option from the command-line variable map and store it in the
    // benchmark_config container.
    cfg.size = vm["size"].as<std::uint64_t>();
    cfg.trials = vm["trials"].as<int>();
    cfg.warmup = vm["warmup"].as<int>();
    cfg.seed = vm["seed"].as<unsigned int>();
    cfg.distribution = vm["distribution"].as<std::string>();
    cfg.verify = vm["verify"].as<bool>();
    cfg.baseline = vm["baseline"].as<bool>();
    cfg.csv = vm["csv"].as<bool>();

    // Defensive validation: benchmark parameters must be physically meaningful.
    if (cfg.size == 0)
    {
        throw std::runtime_error("--size must be > 0");
    }
    if (cfg.trials <= 0)
    {
        throw std::runtime_error("--trials must be > 0");
    }
    if (cfg.warmup < 0)
    {
        throw std::runtime_error("--warmup must be >= 0");
    }

    // Create a reproducible dataset for the selected distribution and size.
    std::mt19937_64 rng(cfg.seed);
    auto const input = make_input(cfg.size, cfg.distribution, rng);

    // The benchmark is printing a concise configuration summary before the sort
    // begins so the user can see exactly what workload was measured.
    std::cout << "Benchmark config\n";
    std::cout << "  size        : " << cfg.size << "\n";
    std::cout << "  distribution: " << cfg.distribution << "\n";
    std::cout << "  warmup      : " << cfg.warmup << "\n";
    std::cout << "  trials      : " << cfg.trials << "\n";
    std::cout << "  seed        : " << cfg.seed << "\n";
    std::cout << "  verify      : " << (cfg.verify ? "true" : "false") << "\n";
    std::cout << "  baseline    : " << (cfg.baseline ? "true" : "false") << "\n";

    // Store all results in one vector so the CSV / summary code can process them
    // uniformly regardless of whether we benchmark one algorithm or both.
    std::vector<benchmark_summary> all;

    // Benchmark the HPX parallel sample sort. This is the main target of the
    // repository: measure how quickly the parallel algorithm can sort data on a
    // given thread count and dataset size.
    all.push_back(run_benchmark("hpx::sample_sort", input, cfg.warmup, cfg.trials,
        cfg.verify, [](std::vector<std::uint64_t>& data) {
            // In this project, sample_sort is exposed through the HPX detail
            // namespace, so this lambda is the point where the actual parallel
            // sort is invoked.
            sample_sort(parallel_executor{}, data.begin(), data.end());
        }));

    // If the user requests a baseline, we also run the standard library sort on
    // the same data to compare the specialized parallel sort against the serial
    // reference implementation.
    if (cfg.baseline)
    {
        all.push_back(run_benchmark("std::sort", input, cfg.warmup, cfg.trials,
            cfg.verify, [](std::vector<std::uint64_t>& data) {
                std::sort(data.begin(), data.end());
            }));
    }

    // Output mode is chosen here. CSV is preferred by the plotting script because
    // it can parse rows and compute per-thread / per-size medians without relying
    // on brittle text parsing.
    if (cfg.csv)
    {
        print_csv(all);
    }
    else
    {
        for (auto const& s : all)
        {
            print_summary(s);
        }
    }

    // Return control to HPX after the benchmark is complete.
    return hpx::local::finalize();
}

// Main entry point for the benchmark binary.
// This is where HPX is initialized and where the default configuration values are
// registered as command-line options. The action of this function is to parse the
// benchmarking arguments, set hpx.os_threads, and then invoke hpx_main.
int main(int argc, char* argv[])
{
    using namespace hpx::program_options;
    options_description desc_commandline(
        "Usage: " HPX_APPLICATION_STRING " [options]");

    // These defaults are important because they represent the standard settings
    // used by the rest of the project. Changing them here changes the default
    // behavior of the benchmark binary for every invocation.
    benchmark_config defaults;
    desc_commandline.add_options()("size,n",
        value<std::uint64_t>()->default_value(defaults.size),
        "number of elements to sort")(
        "trials,t", value<int>()->default_value(defaults.trials),
        "number of timed benchmark trials")(
        "warmup,w", value<int>()->default_value(defaults.warmup),
        "number of untimed warmup runs")(
        "seed,s", value<unsigned int>()->default_value(defaults.seed),
        "random seed for reproducible input generation")(
        "distribution,d",
        value<std::string>()->default_value(defaults.distribution),
        "input distribution: shuffle|uniform|sorted|reverse|few_unique")(
        "verify", value<bool>()->default_value(defaults.verify),
        "verify output is sorted")(
        "baseline", value<bool>()->default_value(defaults.baseline),
        "also run std::sort baseline")(
        "csv", value<bool>()->default_value(defaults.csv),
        "print CSV output instead of text summary")(
        "threads", value<std::string>()->default_value("all"),
        "HPX OS thread count (for convenience, mapped to hpx.os_threads)");

    // The script appends --threads=<N> to the benchmark command line, and we
    // convert that into the HPX runtime configuration below.
    std::string const requested_threads = parse_os_threads_arg(argc, argv);
    std::vector<std::string> const cfg = {
        std::string("hpx.os_threads=") + requested_threads};

    // The HPX runtime is initialized with a configuration vector that sets the
    // number of OS threads. This is the crucial hook that lets the Python sweep
    // vary the concurrency level without changing the C++ source.
    hpx::local::init_params init_args;
    init_args.desc_cmdline = desc_commandline;
    init_args.cfg = cfg;

    return hpx::local::init(hpx_main, argc, argv, init_args);
}