$ErrorActionPreference = "Stop"

$pythonCommands = @(
    @("py", "-3.11"),
    @("py", "-3"),
    @("python")
)

$venvCreated = $false
foreach ($cmd in $pythonCommands) {
    $exe = $cmd[0]
    $args = @()
    if ($cmd.Length -gt 1) {
        $args = $cmd[1..($cmd.Length - 1)]
    }

    try {
        & $exe @args -m venv .venv
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Created .venv using: $exe $($args -join ' ')"
            $venvCreated = $true
            break
        }
    }
    catch {
        # Try next python command.
    }
}

if (-not $venvCreated) {
    throw "Could not create a virtual environment. Install Python 3.11+ and ensure 'py' or 'python' is on PATH."
}

$venvPython = ".\.venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host ""
Write-Host "Environment is ready. Activate with: .\.venv\Scripts\Activate.ps1"
