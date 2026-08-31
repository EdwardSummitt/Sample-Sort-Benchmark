#!/usr/bin/env python3
"""Run HPX benchmark sweeps and generate median-speed line plots.

This script runs the benchmark executable across a fixed thread-count list and
input-size list, performs 5 trials per combination, computes the median from
raw trial samples, and writes:

1) raw trial CSV
2) median summary CSV
3) speed-vs-size line plot (one line per thread count)
4) speed-vs-threads line plot (one line per input size)
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt


THREAD_COUNTS = [1, 2, 4, 8, 16, 17, 18, 19, 20]

# Nine input-size increments chosen to span small -> large while keeping runtime manageable.
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

CSV_HEADER = "name,trial_idx,trial_speed,min_speed,median_speed,mean_speed,max_speed"


def resolve_default_executable() -> Path:
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
) -> list[float]:
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
    if hpx_bind_none:
        cmd.append("--hpx:bind=none")

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
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["threads", "size", "trial_index", "trial_speed"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_median_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["threads", "size", "median_speed"],
        )
        writer.writeheader()
        writer.writerows(rows)


def plot_speed_vs_size(
    output_path: Path,
    thread_counts: list[int],
    input_sizes: list[int],
    medians_by_size_thread: list[list[float]],
) -> None:
    # medians_by_size_thread is indexed [size_idx][thread_idx]
    fig, ax = plt.subplots(figsize=(10, 7))

    for thread_idx, threads in enumerate(thread_counts):
        y = [medians_by_size_thread[size_idx][thread_idx] for size_idx in range(len(input_sizes))]
        ax.plot(input_sizes, y, marker="o", label=f"{threads} threads")

    ax.set_xlabel("Input size (N)")
    ax.set_ylabel("Median speed (elements/ms)")
    ax.set_title("HPX Sample Sort Speed vs Input Size")
    ax.legend(title="Cores (threads)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_speed_vs_threads(
    output_path: Path,
    thread_counts: list[int],
    input_sizes: list[int],
    medians_by_size_thread: list[list[float]],
) -> None:
    # medians_by_size_thread is indexed [size_idx][thread_idx]
    fig, ax = plt.subplots(figsize=(10, 7))

    for size_idx, size in enumerate(input_sizes):
        y = medians_by_size_thread[size_idx]
        ax.plot(thread_counts, y, marker="o", label=f"N={size:,}")

    ax.set_xlabel("Cores (threads)")
    ax.set_ylabel("Median speed (elements/ms)")
    ax.set_title("HPX Sample Sort Speed vs Thread Count")
    ax.legend(title="Input size")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run core/input-size sweeps and generate median speed line plots."
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
        default=Path("benchmark_speed_vs_size.png"),
        help="Output PNG for speed-vs-input-size line plot (one line per thread count).",
    )
    parser.add_argument(
        "--plot-vs-threads",
        type=Path,
        default=Path("benchmark_speed_vs_threads.png"),
        help="Output PNG for speed-vs-thread-count line plot (one line per input size).",
    )
    return parser


def main() -> int:
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
    medians_by_size_thread: list[list[float]] = []

    total_runs = len(INPUT_SIZES) * len(THREAD_COUNTS)
    run_idx = 0

    for size in INPUT_SIZES:
        medians_for_size: list[float] = []
        for threads in THREAD_COUNTS:
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
            )

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

        medians_by_size_thread.append(medians_for_size)

    write_raw_csv(args.raw_csv, raw_rows)
    write_median_csv(args.median_csv, median_rows)
    plot_speed_vs_size(args.plot_vs_size, THREAD_COUNTS, INPUT_SIZES, medians_by_size_thread)
    plot_speed_vs_threads(args.plot_vs_threads, THREAD_COUNTS, INPUT_SIZES, medians_by_size_thread)

    print("\nFinished benchmark sweep.")
    print(f"Raw trials CSV      : {args.raw_csv}")
    print(f"Median CSV          : {args.median_csv}")
    print(f"Speed vs size plot  : {args.plot_vs_size}")
    print(f"Speed vs threads plot: {args.plot_vs_threads}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
