#!/usr/bin/env python3
"""Run HPX benchmark sweeps and generate speedup line plots.

This script is the orchestration layer between the compiled HPX benchmark binary
and the final plots that summarize its performance. It does four main things:

1. It locates the benchmark executable.
2. It runs a Cartesian sweep over several input sizes and thread counts.
3. It converts the raw CSV output into median speeds and speedup ratios.
4. It saves CSV files and plots for later analysis.

The end result is a pair of charts showing how performance changes as either the
input size or the thread count varies.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt


# The benchmark intentionally sweeps a specific set of thread counts.
# The list begins with 1 and then includes every even value up to 40.
# This means the set is: 1, 2, 4, 6, 8, ..., 40.
# This is useful because it produces a smooth enough curve to reveal scaling
# behavior without exploding the number of benchmark executions.
THREAD_COUNTS = [1, *range(2, 41, 2)]

# Nine input sizes are used to span a wide dynamic range while keeping the total
# runtime manageable. The sizes grow by roughly powers of two and a few mixed
# intermediate values so the benchmark covers both small and large workloads.
INPUT_SIZES = [
    1_000_000,
    2_000_000,
    4_000_000,
    8_000_000,
    12_000_000,
    16_000_000,
    24_000_000,
    32_000_000,
    48_000_000,
]

# This is the exact CSV header emitted by the C++ benchmark for each row.
# The Python script relies on this exact string to identify where the useful data
# starts inside the benchmark output, because the program prints other text first.
CSV_HEADER = "name,trial_idx,trial_speed,min_speed,median_speed,mean_speed,max_speed"


def resolve_default_executable() -> Path:
    """Find a likely benchmark executable in the repository.

    The project may build the binary under different paths depending on the OS,
    generator, or build configuration. This function checks a short list of common
    locations and returns the first one that exists.
    """
    candidates = [
        Path("build/Release/test_hpx.exe"),
        Path("build/test_hpx.exe"),
        Path("build/test_hpx"),
        Path("./test_hpx.exe"),
        Path("./test_hpx"),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return candidates[0]


def extract_csv_rows(output: str) -> list[dict[str, str]]:
    """Parse benchmark output and extract the CSV rows that contain timed results.

    The C++ benchmark prints a text banner and then emits a CSV section beginning
    with a fixed header. This function scans the output line by line, locates the
    header, and then feeds the remainder into Python's csv.DictReader.
    """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    start_idx = -1
    for idx, line in enumerate(lines):
        if line == CSV_HEADER:
            start_idx = idx
            break

    if start_idx == -1:
        raise RuntimeError("Could not find CSV header in benchmark output.")

    csv_lines = lines[start_idx:]
    reader = csv.DictReader(csv_lines)
    return list(reader)


def run_one_benchmark(
    exe_path: Path,
    threads: int,
    size: int,
    trials: int,
    warmup: int,
    distribution: str,
    verify: bool,
    algorithm_name: str,
    hpx_bind_none: bool,
    print_bind: bool = False,
    binding_mode: str | None = None,
) -> list[float]:
    """Execute one benchmark configuration and return the raw measured trial speeds.

    The benchmark binary itself is responsible for sorting the data and measuring
    throughput. This function just assembles the correct CLI arguments for that
    process and extracts the timing results from its CSV output.
    """
    cmd = [
        str(exe_path),
        f"--threads={threads}",
        f"--size={size}",
        f"--trials={trials}",
        f"--warmup={warmup}",
        f"--distribution={distribution}",
        "--baseline=false",
        f"--verify={'true' if verify else 'false'}",
        "--csv=true",
    ]
    if binding_mode is not None:
        cmd.append(f"--hpx:bind={binding_mode}")
    elif hpx_bind_none:
        cmd.append("--hpx:bind=none")
    if print_bind:
        cmd.append("--hpx:print-bind")

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "Benchmark command failed.\n"
            f"Command: {' '.join(cmd)}\n"
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    rows = extract_csv_rows(result.stdout)
    trial_speeds = [
        float(row["trial_speed"])
        for row in rows
        if row.get("name") == algorithm_name and row.get("trial_speed")
    ]

    if len(trial_speeds) != trials:
        raise RuntimeError(
            f"Expected {trials} trial rows for '{algorithm_name}', got {len(trial_speeds)} "
            f"for threads={threads}, size={size}."
        )

    return trial_speeds


def write_raw_csv(path: Path, rows: list[dict[str, float]]) -> None:
    """Save all raw trial measurements to a CSV file.

    This is the most granular data artifact produced by the benchmark. It keeps
    every measured trial speed at every thread count and input size, which is
    useful for further analysis or debugging outliers.
    """
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["threads", "size", "trial_index", "trial_speed"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_median_csv(path: Path, rows: list[dict[str, float]]) -> None:
    """Save the median throughput for each (threads, size) pair.

    This is the main file used for plotting. It represents the central tendency of
    each benchmark configuration while reducing the impact of noisy outlier runs.
    """
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["threads", "size", "median_speed"],
        )
        writer.writeheader()
        writer.writerows(rows)


def plot_speedup_vs_size(
    output_path: Path,
    thread_counts: list[int],
    input_sizes: list[int],
    speedups_by_size_thread: list[list[float]],
) -> None:
    """Plot speedup as a function of input size, one line per thread count.

    The speedups_by_size_thread matrix is organized as [size_idx][thread_idx]. For
    each thread count, we take the speedup values across all sizes and plot them on
    the same chart. This lets us see how much the parallel algorithm improves over
    the one-thread baseline as the dataset grows.
    """
    fig, ax = plt.subplots(figsize=(10, 7))

    for thread_idx, threads in enumerate(thread_counts):
        y = [speedups_by_size_thread[size_idx][thread_idx] for size_idx in range(len(input_sizes))]
        ax.plot(input_sizes, y, marker="o", label=f"{threads} threads")

    ax.set_xlabel("Input size (N)")
    ax.set_ylabel("Speedup (parallel / sequential)")
    ax.set_title("HPX Sample Sort Speedup vs Input Size")
    ax.legend(title="Cores (threads)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_speedup_vs_threads(
    output_path: Path,
    thread_counts: list[int],
    input_sizes: list[int],
    speedups_by_size_thread: list[list[float]],
) -> None:
    """Plot speedup as a function of thread count, one line per input size.

    This is the more traditional performance-scaling plot. Each series represents
    a fixed problem size; the x-axis is concurrency and the y-axis is the speedup
    relative to the single-thread baseline for that same input size.
    """
    fig, ax = plt.subplots(figsize=(10, 7))

    for size_idx, size in enumerate(input_sizes):
        y = speedups_by_size_thread[size_idx]
        ax.plot(thread_counts, y, marker="o", label=f"N={size:,}")

    ax.set_xlabel("Cores (threads)")
    ax.set_ylabel("Speedup (parallel / sequential)")
    ax.set_title("HPX Sample Sort Speedup vs Thread Count")
    ax.legend(title="Input size")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def build_arg_parser() -> argparse.ArgumentParser:
    """Define the command-line interface for the benchmark driver.

    The benchmark is intentionally flexible: it can run a full sweep, a focused
    debug case, or any custom input size/thread count combination. This parser is
    the public interface for that functionality.
    """
    parser = argparse.ArgumentParser(
        description="Run core/input-size sweeps and generate parallel-over-sequential speedup plots."
    )
    parser.add_argument(
        "--exe",
        type=Path,
        default=resolve_default_executable(),
        help="Path to benchmark executable (default: build/Release/test_hpx.exe if present).",
    )
    parser.add_argument("--trials", type=int, default=5, help="Timed trials per combo.")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs per combo.")
    parser.add_argument(
        "--distribution",
        type=str,
        default="shuffle",
        choices=["shuffle", "uniform", "sorted", "reverse", "few_unique"],
        help="Input distribution passed to benchmark binary.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=False,
        help="Enable sorted-output verification during benchmark runs.",
    )
    parser.add_argument(
        "--algorithm",
        type=str,
        default="hpx::sample_sort",
        help="Algorithm name to extract from CSV output.",
    )
    parser.add_argument(
        "--hpx-bind-none",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass --hpx:bind=none to permit oversubscription-style thread counts.",
    )
    parser.add_argument(
        "--print-bind",
        action="store_true",
        default=False,
        help="Print HPX thread binding information for each benchmark run.",
    )
    parser.add_argument(
        "--debug-40",
        action="store_true",
        default=False,
        help="Run only the 40-thread configuration and print the HPX bind layout.",
    )
    parser.add_argument(
        "--raw-csv",
        type=Path,
        default=Path("benchmark_raw_trials.csv"),
        help="Output CSV for all trial samples.",
    )
    parser.add_argument(
        "--median-csv",
        type=Path,
        default=Path("benchmark_median_summary.csv"),
        help="Output CSV for median per (threads,size).",
    )
    parser.add_argument(
        "--plot-vs-size",
        type=Path,
        default=Path("benchmark_speedup_vs_size.png"),
        help="Output PNG for speedup-vs-input-size line plot (one line per thread count).",
    )
    parser.add_argument(
        "--plot-vs-threads",
        type=Path,
        default=Path("benchmark_speedup_vs_threads.png"),
        help="Output PNG for speedup-vs-thread-count line plot (one line per input size).",
    )
    return parser


def main() -> int:
    """Run the full benchmark sweep and generate the summary plots.

    This is the core control loop of the script. For each input size, it loops over
    the requested thread counts, invokes the benchmark executable, stores the raw
    measurements, computes the median, converts the medians into speedups relative
    to the single-thread baseline, and finally writes the output files.
    """
    parser = build_arg_parser()
    args = parser.parse_args()

    exe_path = args.exe
    if not exe_path.is_file():
        parser.error(
            f"Benchmark executable not found at '{exe_path}'. "
            "Build first or pass --exe <path>."
        )

    raw_rows: list[dict[str, float]] = []
    median_rows: list[dict[str, float]] = []
    speedups_by_size_thread: list[list[float]] = []

    # The debug mode intentionally overrides the full sweep and only exercises the
    # 40-thread benchmark. This is useful when investigating outliers or scheduler
    # placement effects at a single concurrency point.
    thread_counts = [40] if args.debug_40 else THREAD_COUNTS
    total_runs = len(INPUT_SIZES) * len(thread_counts)
    run_idx = 0

    binding_mode = None
    if args.debug_40:
        print("Debug 40-thread mode: running only the 40-thread configuration with print-bind enabled.")

    for size in INPUT_SIZES:
        medians_for_size: list[float] = []
        for threads in thread_counts:
            run_idx += 1
            print(
                f"[{run_idx}/{total_runs}] Running size={size}, threads={threads}...",
                flush=True,
            )

            trial_speeds = run_one_benchmark(
                exe_path=exe_path,
                threads=threads,
                size=size,
                trials=args.trials,
                warmup=args.warmup,
                distribution=args.distribution,
                verify=args.verify,
                algorithm_name=args.algorithm,
                hpx_bind_none=args.hpx_bind_none,
                print_bind=args.print_bind or args.debug_40,
                binding_mode=binding_mode,
            )

            # The median is the most stable single-number summary for noisy timing
            # data. A single poor scheduling decision or a transient OS artifact can
            # distort the mean, but the median is much less sensitive to those
            # extremes.
            median_speed = float(statistics.median(trial_speeds))
            medians_for_size.append(median_speed)

            for trial_index, trial_speed in enumerate(trial_speeds):
                raw_rows.append(
                    {
                        "threads": threads,
                        "size": size,
                        "trial_index": trial_index,
                        "trial_speed": trial_speed,
                    }
                )

            median_rows.append(
                {
                    "threads": threads,
                    "size": size,
                    "median_speed": median_speed,
                }
            )

        # Speedup is computed relative to the single-thread median for the same
        # input size. This makes the plots comparable across different input sizes,
        # because each series is normalized to its own baseline rather than to an
        # arbitrary absolute reference.
        sequential_median = medians_for_size[0]
        speedups_by_size_thread.append(
            [median_speed / sequential_median for median_speed in medians_for_size]
        )

    # Save the raw per-trial data and the median summary before plotting. These
    # CSV files are valuable because they preserve all measured data for later
    # examination or replotting without rerunning the benchmark.
    write_raw_csv(args.raw_csv, raw_rows)
    write_median_csv(args.median_csv, median_rows)
    plot_speedup_vs_size(args.plot_vs_size, thread_counts, INPUT_SIZES, speedups_by_size_thread)
    plot_speedup_vs_threads(
        args.plot_vs_threads, thread_counts, INPUT_SIZES, speedups_by_size_thread
    )

    print("\nFinished benchmark sweep.")
    print(f"Raw trials CSV      : {args.raw_csv}")
    print(f"Median CSV          : {args.median_csv}")
    print(f"Speed vs size plot  : {args.plot_vs_size}")
    print(f"Speed vs threads plot: {args.plot_vs_threads}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
