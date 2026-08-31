$ErrorActionPreference = "Stop"

$vcpkgRoot = if ($env:VCPKG_ROOT) {
  $env:VCPKG_ROOT
} else {
  Join-Path $PSScriptRoot "..\vcpkg"
}
$toolchainFile = Join-Path $vcpkgRoot "scripts\buildsystems\vcpkg.cmake"

if (-not (Test-Path $toolchainFile)) {
  throw "vcpkg toolchain file not found at '$toolchainFile'. Set VCPKG_ROOT to your vcpkg installation directory."
}

# Delete old build folder if it exists
if (Test-Path build) {
    Write-Host "Deleting old build folder..."
    Remove-Item build -Recurse -Force
}

# Configure CMake
Write-Host "Configuring CMake..."
cmake -B build -S . -G "Visual Studio 18 2026" -A x64 `
  -DCMAKE_TOOLCHAIN_FILE="$toolchainFile"

# Build project
Write-Host "Building project..."
cmake --build build --config Release

Write-Host "Build complete!"

Write-Host "Running..."
& .\build\Release\test_hpx.exe
