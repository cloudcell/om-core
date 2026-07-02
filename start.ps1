#!/usr/bin/env pwsh
# OpenModeling launcher - runtime-first, then clients.
#
# Architecture:
#   1. Runtime (engine + bus + command service + transport) starts first.
#   2. Clients (GUI with splash, REPL, etc.) connect separately.
#   3. Default: GUI + TUI both start. GUI gets the splash screen.
#
# Requires uv. Install from https://docs.astral.sh/uv.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = (Get-Location).Path

# Resolve uv.
function Find-Uv {
    $candidates = @(
        Join-Path $ProjectDir "venv\Scripts\uv.exe"
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
    Write-Host "OM Core uses uv to manage its Python environment." -ForegroundColor Yellow
    Write-Host "uv is not installed or not on your PATH." -ForegroundColor Yellow
    $answer = Read-Host "Install uv automatically now? [Y/n]"
    if (-not $answer) { $answer = "Y" }
    if ($answer.Substring(0, 1).ToUpper() -ne "Y") {
        Write-Error "uv is required. Install it from https://docs.astral.sh/uv"
        exit 1
    }
    Invoke-RestMethod -Uri https://astral.sh/uv/install.ps1 | Invoke-Expression
    $Uv = Find-Uv
    if (-not $Uv) {
        Write-Error "Installation finished, but uv was not found. Restart your shell and retry."
        exit 1
    }
}

# Ensure a project-compatible Python interpreter is installed.
function Ensure-Python {
    $pySpec = "3.12"
    $pyprojectPath = Join-Path $ProjectDir "pyproject.toml"
    if (Test-Path $pyprojectPath) {
        $line = Get-Content $pyprojectPath | Select-String '^requires-python' | Select-Object -First 1
        if ($line -match '([0-9]+\.[0-9]+)') {
            $pySpec = $matches[1]
        }
    }
    & $Uv python find $pySpec | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Python $pySpec not found; installing via uv..."
        & $Uv python install $pySpec
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to install Python $pySpec via uv."
            exit 1
        }
    }
}
Ensure-Python

$Python = "$Uv run python"

function Invoke-OpenM {
    param([string]$Mode)
    switch ($Mode) {
        "--runtime"       { Write-Host "Starting OM runtime host...";       & $Uv run python -O main.py --runtime }
        "--gui"           { Write-Host "Starting OM GUI client...";       & $Uv run python -O main.py --gui }
        "--gui-only"      { Write-Host "Starting OM runtime + GUI...";    & $Uv run python -O main.py --gui-only }
        "--repl"          { Write-Host "Starting OM REPL client...";     & $Uv run python -O main.py --repl }
        "--tui"           { Write-Host "Starting OM TUI client...";      & $Uv run python -O main.py --tui }
        "--gui-with-repl" { Write-Host "Starting OM GUI + REPL...";     & $Uv run python -O main.py --gui-with-repl }
        default {
            Write-Error "Unknown mode: $Mode"
            exit 1
        }
    }
}

$arg = $args[0]

if ($arg -eq "--batch") {
    if ($args.Length -lt 2) {
        Write-Error "Usage: start.ps1 --batch <script>"
        exit 1
    }
    Write-Host "Running OM in batch mode: $($args[1])"
    & $Uv run python -O main.py --batch $args[1]
    exit $LASTEXITCODE
}

if ($arg -and $arg -ne "--batch") {
    Invoke-OpenM -Mode $arg
    exit $LASTEXITCODE
}

# DEFAULT: runtime + GUI (detached), plus TUI in a separate terminal.
$answer = Read-Host "Open a TUI in a separate terminal? [Y/n]"
if (-not $answer) { $answer = "Y" }
$openTui = ($answer.Substring(0, 1).ToUpper() -eq "Y")

Write-Host "Starting OM runtime + GUI..."

# Launch GUI in a detached, minimized process.
Start-Process -FilePath $Uv -ArgumentList "run", "python", "-O", "main.py", "--gui-only" -WindowStyle Minimized

Start-Sleep -Seconds 1

if ($openTui) {
    Write-Host "Opening TUI in a separate terminal..."
    $tuiArgs = "run", "python", "-O", "main.py", "--tui"
    Start-Process -FilePath $Uv -ArgumentList $tuiArgs -WorkingDirectory $ProjectDir
} else {
    Write-Host "TUI not opened. Run 'start.ps1 --tui' later if you want a command line."
}
