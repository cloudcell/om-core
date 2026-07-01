#!/usr/bin/env pwsh
# OpenModeling test runner for Windows.

$ErrorActionPreference = "Stop"

# Prevent Qt tests from opening visible windows during headless/CI runs.
$env:QT_QPA_PLATFORM = "offscreen"

# Resolve script directory and move there.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Resolve uv.
function Find-Uv {
    $candidates = @(
        Join-Path $ScriptDir "venv\Scripts\uv.exe"
        Join-Path $env:USERPROFILE ".local\bin\uv.exe"
        Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    $inPath = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }
    return $null
}

$Uv = Find-Uv
if (-not $Uv) {
    Write-Error "uv is not installed or not on your PATH. Install it from https://docs.astral.sh/uv"
    exit 1
}

Write-Host "=== Running tests sequentially ==="
& $Uv run python -m pytest tests/

if ($LASTEXITCODE -eq 0) {
    $TS = Get-Date -Format "yyyyMMdd-HHmmss"
    $HASH = (git rev-parse --short HEAD 2>$null)
    if (-not $HASH) { $HASH = "nogit" }
    $Version = "${TS}-${HASH}"
    $Version | Set-Content "version.txt" -Encoding utf8
    Write-Host "Version: $Version"
}

exit $LASTEXITCODE
