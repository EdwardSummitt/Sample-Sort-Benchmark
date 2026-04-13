#!/usr/bin/env bash
set -euo pipefail

THREADS=(1 2 4 8 16 17 18 19 20 21 22)

EXE_PATH="${1:-./build/test_hpx}"
OUT_CSV="${2:-thread_scaling_summary.csv}"

SIZE="${SIZE:-100000000}"
TRIALS="${TRIALS:-5}"
WARMUP="${WARMUP:-1}"
DISTRIBUTION="${DISTRIBUTION:-shuffle}"
BASELINE="${BASELINE:-true}"
VERIFY="${VERIFY:-true}"

if [[ ! -f "$EXE_PATH" ]]; then
    echo "Error: executable not found at '$EXE_PATH'" >&2
    echo "Usage: $0 [path_to_test_hpx] [output_csv]" >&2
    exit 1
fi

echo "thread,name,min_ms,max_ms,mean_ms,median_ms" > "$OUT_CSV"

for t in "${THREADS[@]}"; do
    echo "Running thread=$t" >&2

    run_output="$($EXE_PATH \
        --threads="$t" \
        --size="$SIZE" \
        --trials="$TRIALS" \
        --warmup="$WARMUP" \
        --distribution="$DISTRIBUTION" \
        --baseline="$BASELINE" \
        --verify="$VERIFY" \
        --csv=true)"

    # Input CSV format from benchmark:
    # name,trial_idx,trial_ms,min_ms,median_ms,mean_ms,max_ms
    # Values are repeated for each trial, so we keep trial_idx==0 as the summary row.
    echo "$run_output" | awk -F',' -v thread="$t" '
        NR == 1 { next }
        $2 == 0 {
            printf "%s,%s,%s,%s,%s,%s\n", thread, $1, $4, $7, $6, $5
        }
    ' >> "$OUT_CSV"
done

echo "Done. Wrote summary to $OUT_CSV" >&2
