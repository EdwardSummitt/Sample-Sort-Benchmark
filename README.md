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

- Cores: 1, 2, 4, 8, 16, 17, 18, 19, 20
- Input sizes: 9 increments from 1,000,000 to 48,000,000
- Trials per (core, size) pair: 5

The script computes median runtime from trial samples and produces a 3D surface:

- X axis: cores
- Y axis: input size
- Z axis: median time (ms)

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
- `benchmark_3d_surface.png`

## One-Shot Linux Cluster Script

Run everything (vcpkg bootstrap, CMake build, Python venv setup, benchmark sweep, 3D plot) with one command:

```bash
chmod +x ./run_all_linux_cluster.sh
./run_all_linux_cluster.sh
```

Useful overrides:

- `MODULES_TO_LOAD="gcc cmake python/3.11" ./run_all_linux_cluster.sh`
- `BUILD_JOBS=32 ./run_all_linux_cluster.sh`
- `RECREATE_VENV=1 ./run_all_linux_cluster.sh`

Any extra flags are forwarded to `plot_thread_size_surface.py`:

```bash
./run_all_linux_cluster.sh --distribution uniform --warmup 0
```
