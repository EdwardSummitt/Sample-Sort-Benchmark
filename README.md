# Sample-Sort-Benchmark

## Python plotting environment

This repository includes a basic Python virtual environment setup for plotting benchmark results.

- Recommended Python: 3.11 (3.11+ works)
- Dependencies are tracked in `requirements.txt`
- 3D plotting support comes from `mpl_toolkits.mplot3d`, which is included with `matplotlib`

### Windows (PowerShell)

```powershell
./bootstrap.ps1
.\.venv\Scripts\Activate.ps1
```

### macOS/Linux

```bash
chmod +x bootstrap.sh
./bootstrap.sh
source .venv/bin/activate
```

### Manual setup (any platform)

```bash
python -m venv .venv
# Windows:
# .venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Quick 3D import check

```python
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
```

## Benchmark Sweep + 3D Plot

Use the Python script below to run the benchmark binary across:

- Cores: 1, 2, 4, 6, ..., 40
- Input sizes: 9 increments from 1,000,000 to 48,000,000
- Trials per (core, size) pair: 5

The script computes median speed (elements sorted per ms) from trial samples. Each graph displays speedup by dividing the median speed at each thread count by the median speed from its corresponding one-core run:

- `benchmark_speed_vs_size.png`: X axis is input size, Y axis is parallel-over-sequential speedup, one line per thread count.
- `benchmark_speed_vs_threads.png`: X axis is thread count, Y axis is parallel-over-sequential speedup, one line per input size.

### Example (Windows PowerShell)

```powershell
python .\plot_thread_size_surface.py --exe .\build\Release\test_hpx.exe
```

### Example (macOS/Linux)

```bash
python3 ./plot_thread_size_surface.py --exe ./build/test_hpx
```

Outputs:

- `benchmark_raw_trials.csv`
- `benchmark_median_summary.csv`
- `benchmark_speed_vs_size.png`
- `benchmark_speed_vs_threads.png`

## One-Shot Linux Cluster Script

Run everything (vcpkg bootstrap, CMake build, Python venv setup, benchmark sweep, speed plots) with one command:

```bash
chmod +x ./run_all_linux_cluster.sh
./run_all_linux_cluster.sh
```

Useful overrides:

- `MODULES_TO_LOAD="gcc cmake python/3.11" ./run_all_linux_cluster.sh`
- `BUILD_JOBS=32 ./run_all_linux_cluster.sh`
- `RECREATE_VENV=1 ./run_all_linux_cluster.sh`
- `UPDATE_VCPKG=0 ./run_all_linux_cluster.sh` (pins the current vcpkg/HPX version; by default the script pulls the latest vcpkg on every run and rebuilds HPX only if vcpkg changed)

Any extra flags are forwarded to `plot_thread_size_surface.py`:

```bash
./run_all_linux_cluster.sh --distribution uniform --warmup 0
```

## Thread-Count Scatterplot

After building `test_hpx` and installing the Python plotting requirements, run
the focused sweep using either platform wrapper:

```bash
# Linux/macOS
chmod +x ./run_thread_scatter.sh
./run_thread_scatter.sh

# Windows PowerShell
.\run_thread_scatter.ps1
```

Both wrappers run the shared `plot_thread_scatter.py` driver at one input size
(default 8,000,000 elements) and thread counts 1, 2, 4, ..., 40. By default, each
configuration has one untimed warmup and five timed trials; every timed trial
appears as a scatter point. Override the element count, trial count, warmups, or
output paths with `--size`, `--trials`, `--warmup`, `--output-csv`, and
`--output-plot` (e.g. `./run_thread_scatter.sh --size 16000000`). Set `EXE_PATH` and `PYTHON_BIN`
to select the benchmark executable and Python interpreter. When invoking the
Python driver directly, use `--exe` to select the executable.

Outputs:

- `benchmark_thread_trials.csv`
- `benchmark_thread_scatter.png`
