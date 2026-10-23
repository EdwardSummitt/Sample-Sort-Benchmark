#!/usr/bin/env python3
"""Run a fixed-size HPX sample-sort thread sweep and plot every timed trial."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from plot_thread_size_surface import run_one_benchmark


DEFAULT_INPUT_SIZE = 8_000_000
THREAD_COUNTS = [1, *range(2, 41, 2)]
ALGORITHM_NAME = "hpx::sample_sort"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark HPX sample sort at one input size across thread counts 1, 2, 4, ..., 40."
    )
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_INPUT_SIZE,
        help="Number of elements to sort.",
    )
    parser.add_argument(
        "--exe",
        type=Path,
        required=True,
        help="Path to the built test_hpx executable.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=5,
        help="Timed trials per thread count; every timed trial is plotted.",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=1,
        help="Untimed warmup runs per thread count.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("benchmark_thread_trials.csv"),
        help="Output CSV containing every timed trial.",
    )
    parser.add_argument(
        "--output-plot",
        type=Path,
        default=Path("benchmark_thread_scatter.png"),
        help="Output scatterplot image.",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    input_size = args.size
    if input_size <= 0:
        parser.error("--size must be > 0")
    if args.trials <= 0:
        parser.error("--trials must be > 0")
    if args.warmup < 0:
        parser.error("--warmup must be >= 0")
    if not args.exe.is_file():
        parser.error(f"Benchmark executable not found at '{args.exe}'.")

    trial_rows: list[dict[str, float | int]] = []
    for run_index, threads in enumerate(THREAD_COUNTS, start=1):
        print(
            f"[{run_index}/{len(THREAD_COUNTS)}] "
            f"Running size={input_size}, threads={threads}...",
            flush=True,
        )
        speeds = run_one_benchmark(
            exe_path=args.exe,
            threads=threads,
            size=input_size,
            trials=args.trials,
            warmup=args.warmup,
            distribution="shuffle",
            verify=False,
            algorithm_name=ALGORITHM_NAME,
        )
        for trial_index, speed in enumerate(speeds, start=1):
            trial_rows.append(
                {
                    "threads": threads,
                    "size": input_size,
                    "trial_index": trial_index,
                    "trial_speed_elements_per_ms": speed,
                }
            )

    with args.output_csv.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=[
                "threads",
                "size",
                "trial_index",
                "trial_speed_elements_per_ms",
            ],
        )
        writer.writeheader()
        writer.writerows(trial_rows)

    figure, axis = plt.subplots(figsize=(10, 7))
    axis.scatter(
        [row["threads"] for row in trial_rows],
        [row["trial_speed_elements_per_ms"] for row in trial_rows],
        alpha=0.7,
        s=32,
    )
    axis.set_xlabel("HPX OS threads")
    axis.set_ylabel("Throughput (elements/ms)")
    axis.set_title(f"HPX Sample Sort: {input_size:,} Elements")
    axis.set_xticks(THREAD_COUNTS)
    axis.grid(True, alpha=0.3)
    figure.tight_layout()
    figure.savefig(args.output_plot, dpi=180)
    plt.close(figure)

    print(f"\nTimed trials plotted: {len(trial_rows)}")
    print(f"Raw trials CSV      : {args.output_csv}")
    print(f"Scatterplot         : {args.output_plot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
