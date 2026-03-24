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
    struct benchmark_config
    {
#if defined(HPX_DEBUG)
        std::uint64_t size = 1'000'000;
#else
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

    struct benchmark_summary
    {
        std::string name;
        std::vector<double> trial_ms;
        double min_ms = 0.0;
        double max_ms = 0.0;
        double mean_ms = 0.0;
        double median_ms = 0.0;
    };

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

        return "all";
    }

    std::vector<std::uint64_t> make_input(std::uint64_t size,
        std::string const& distribution, std::mt19937_64& rng)
    {
        std::vector<std::uint64_t> values(size);

        if (distribution == "shuffle")
        {
            std::iota(values.begin(), values.end(), std::uint64_t{0});
            std::shuffle(values.begin(), values.end(), rng);
            return values;
        }

        if (distribution == "uniform")
        {
            std::uniform_int_distribution<std::uint64_t> dist;
            for (auto& v : values)
            {
                v = dist(rng);
            }
            return values;
        }

        if (distribution == "sorted")
        {
            std::iota(values.begin(), values.end(), std::uint64_t{0});
            return values;
        }

        if (distribution == "reverse")
        {
            for (std::uint64_t i = 0; i < size; ++i)
            {
                values[i] = size - i;
            }
            return values;
        }

        if (distribution == "few_unique")
        {
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

    template <typename SortFn>
    benchmark_summary run_benchmark(std::string name,
        std::vector<std::uint64_t> const& base_input, int warmup, int trials,
        bool verify, SortFn&& sorter)
    {
        benchmark_summary summary;
        summary.name = std::move(name);
        summary.trial_ms.reserve(static_cast<std::size_t>(trials));

        for (int i = 0; i < warmup; ++i)
        {
            std::vector<std::uint64_t> data = base_input;
            sorter(data);
            if (verify && !std::is_sorted(data.begin(), data.end()))
            {
                throw std::runtime_error("sort verification failed during warmup");
            }
        }

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
            summary.trial_ms.push_back(elapsed.count());
        }

        summary.min_ms = *std::min_element(summary.trial_ms.begin(), summary.trial_ms.end());
        summary.max_ms = *std::max_element(summary.trial_ms.begin(), summary.trial_ms.end());
        summary.mean_ms =
            std::accumulate(summary.trial_ms.begin(), summary.trial_ms.end(), 0.0) /
            static_cast<double>(summary.trial_ms.size());

        std::vector<double> sorted = summary.trial_ms;
        std::sort(sorted.begin(), sorted.end());
        auto const mid = sorted.size() / 2;
        if (sorted.size() % 2 == 0)
        {
            summary.median_ms = (sorted[mid - 1] + sorted[mid]) / 2.0;
        }
        else
        {
            summary.median_ms = sorted[mid];
        }

        return summary;
    }

    void print_summary(benchmark_summary const& summary)
    {
        std::cout << std::fixed << std::setprecision(3);
        std::cout << summary.name << "\n";
        std::cout << "  trials(ms): ";
        for (std::size_t i = 0; i < summary.trial_ms.size(); ++i)
        {
            std::cout << summary.trial_ms[i];
            if (i + 1 < summary.trial_ms.size())
            {
                std::cout << ", ";
            }
        }
        std::cout << "\n";
        std::cout << "  min/median/mean/max(ms): " << summary.min_ms << " / "
                  << summary.median_ms << " / " << summary.mean_ms << " / "
                  << summary.max_ms << "\n";
    }

    void print_csv(std::vector<benchmark_summary> const& all)
    {
        std::cout << "name,trial_idx,trial_ms,min_ms,median_ms,mean_ms,max_ms\n";
        for (auto const& summary : all)
        {
            for (std::size_t i = 0; i < summary.trial_ms.size(); ++i)
            {
                std::cout << summary.name << ',' << i << ',' << summary.trial_ms[i]
                          << ',' << summary.min_ms << ',' << summary.median_ms << ','
                          << summary.mean_ms << ',' << summary.max_ms << '\n';
            }
        }
    }
}    // namespace

int hpx_main(hpx::program_options::variables_map& vm)
{
    benchmark_config cfg;

    cfg.size = vm["size"].as<std::uint64_t>();
    cfg.trials = vm["trials"].as<int>();
    cfg.warmup = vm["warmup"].as<int>();
    cfg.seed = vm["seed"].as<unsigned int>();
    cfg.distribution = vm["distribution"].as<std::string>();
    cfg.verify = vm["verify"].as<bool>();
    cfg.baseline = vm["baseline"].as<bool>();
    cfg.csv = vm["csv"].as<bool>();

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

    std::mt19937_64 rng(cfg.seed);
    auto const input = make_input(cfg.size, cfg.distribution, rng);

    std::cout << "Benchmark config\n";
    std::cout << "  size        : " << cfg.size << "\n";
    std::cout << "  distribution: " << cfg.distribution << "\n";
    std::cout << "  warmup      : " << cfg.warmup << "\n";
    std::cout << "  trials      : " << cfg.trials << "\n";
    std::cout << "  seed        : " << cfg.seed << "\n";
    std::cout << "  verify      : " << (cfg.verify ? "true" : "false") << "\n";
    std::cout << "  baseline    : " << (cfg.baseline ? "true" : "false") << "\n";

    std::vector<benchmark_summary> all;
    all.push_back(run_benchmark("hpx::sample_sort", input, cfg.warmup, cfg.trials,
        cfg.verify, [](std::vector<std::uint64_t>& data) {
            // sample_sort is currently in HPX detail namespace in this setup.
            sample_sort(parallel_executor{}, data.begin(), data.end());
        }));

    if (cfg.baseline)
    {
        all.push_back(run_benchmark("std::sort", input, cfg.warmup, cfg.trials,
            cfg.verify, [](std::vector<std::uint64_t>& data) {
                std::sort(data.begin(), data.end());
            }));
    }

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

    return hpx::local::finalize();
}

int main(int argc, char* argv[])
{
    // add command line option which controls the random number generator seed
    using namespace hpx::program_options;
    options_description desc_commandline(
        "Usage: " HPX_APPLICATION_STRING " [options]");

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

    std::string const requested_threads = parse_os_threads_arg(argc, argv);
    std::vector<std::string> const cfg = {
        std::string("hpx.os_threads=") + requested_threads};

    // Initialize and run HPX
    hpx::local::init_params init_args;
    init_args.desc_cmdline = desc_commandline;
    init_args.cfg = cfg;

    return hpx::local::init(hpx_main, argc, argv, init_args);
}