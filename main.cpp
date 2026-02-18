#include <hpx/algorithm.hpp>
#include <hpx/execution.hpp>
#include <hpx/init.hpp>

#include <algorithm>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <iostream>
#include <random>
#include <string>
#include <vector>

using namespace hpx::parallel::detail;
using hpx::execution::parallel_executor;


////////////////////////////////////////////////////////////////////////////
unsigned int seed = std::random_device{}();
std::mt19937 gen(seed);

void sample_sort_benchmark(void)
{
    typedef std::less<std::uint64_t> compare_t;
#if defined(HPX_DEBUG)
    constexpr std::uint32_t NELEM = 1000000;
#else
    constexpr std::uint32_t NELEM = 100000000;
#endif

    std::vector<uint64_t> A;
    A.reserve(NELEM);
    
    for (std::uint64_t i = 0; i < NELEM; ++i)
    {
        A.emplace_back(i);
    }
    std::shuffle(A.begin(), A.end(), gen);

    auto start = std::chrono::high_resolution_clock::now();

    sample_sort(parallel_executor{}, A.begin(), A.end());

    auto end = std::chrono::high_resolution_clock::now();

    std::chrono::duration<long unsigned, std::nano> nanotime1 = end - start;
    std::cout << "hpx::sample_sort: " << (nanotime1.count() / 1000000)
              << std::endl;
}

int hpx_main(hpx::program_options::variables_map& vm)
{
    sample_sort_benchmark();

    return hpx::local::finalize();
}

int main(int argc, char* argv[])
{
    // add command line option which controls the random number generator seed
    using namespace hpx::program_options;
    options_description desc_commandline(
        "Usage: " HPX_APPLICATION_STRING " [options]");

    desc_commandline.add_options()("seed,s", value<unsigned int>(),
        "the random number generator seed to use for this run");

    // By default this test should run on all available cores
    std::vector<std::string> const cfg = {"hpx.os_threads=all"};

    // Initialize and run HPX
    hpx::local::init_params init_args;
    init_args.desc_cmdline = desc_commandline;
    init_args.cfg = cfg;

    return hpx::local::init(hpx_main, argc, argv, init_args);
}