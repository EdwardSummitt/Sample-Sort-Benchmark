$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if ($env:PYTHON_BIN) {
    $python = $env:PYTHON_BIN
}
else {
    $venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $python = $venvPython
    }
    else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python 3 was not found. Install Python or set PYTHON_BIN."
        }
        $python = $pythonCommand.Source
    }
}

$executable = $env:EXE_PATH
if (-not $executable) {
    $candidates = @(
        (Join-Path $scriptDir "build\Release\test_hpx.exe"),
        (Join-Path $scriptDir "build\test_hpx.exe"),
        (Join-Path $scriptDir "build\test_hpx")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate -PathType Leaf) {
            $executable = $candidate
            break
        }
    }
}

if (-not $executable -or -not (Test-Path $executable -PathType Leaf)) {
    throw "Benchmark executable not found. Build test_hpx or set EXE_PATH."
}

& $python (Join-Path $scriptDir "plot_thread_scatter.py") --exe $executable @args
if ($LASTEXITCODE -ne 0) {
    throw "Scatter benchmark failed with exit code $LASTEXITCODE."
}
