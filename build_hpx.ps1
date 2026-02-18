# Delete old build folder if it exists
if (Test-Path build) {
    Write-Host "Deleting old build folder..."
    Remove-Item build -Recurse -Force
}

# Configure CMake
Write-Host "Configuring CMake..."
cmake -B build -S . -G "Visual Studio 18 2026" -A x64 `
  -DCMAKE_TOOLCHAIN_FILE=C:/Users/esummi1/vcpkg/scripts/buildsystems/vcpkg.cmake

# Build project
Write-Host "Building project..."
cmake --build build --config Release

Write-Host "Build complete!"

Write-Host "Running..."
.\build\Release\test_hpx.exe
