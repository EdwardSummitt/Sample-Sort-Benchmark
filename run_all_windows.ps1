$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Building HPX benchmark..."
& .\build_hpx.ps1

Write-Host "Preparing Python plotting environment..."
& .\bootstrap.ps1

$python = Join-Path $scriptDir ".venv\Scripts\python.exe"
$executable = Join-Path $scriptDir "build\Release\test_hpx.exe"

if (-not (Test-Path $python)) {
    throw "Python virtual environment was not created at '$python'."
}

if (-not (Test-Path $executable)) {
    throw "Benchmark executable was not created at '$executable'."
}

Write-Host "Running benchmark sweep and generating speed plots..."
& $python .\plot_thread_size_surface.py --exe $executable

Write-Host ""
Write-Host "Complete. Outputs written to:"
Write-Host "  $scriptDir\benchmark_speed_vs_size.png"
Write-Host "  $scriptDir\benchmark_speed_vs_threads.png"
Write-Host "  $scriptDir\benchmark_raw_trials.csv"
Write-Host "  $scriptDir\benchmark_median_summary.csv"
