<#
.SYNOPSIS
    Builds a standalone, self-elevating EFI-Boot-Entry-Cleaner.exe.

.DESCRIPTION
    Creates a .venv (unless Python is already available), installs PySide6 and
    PyInstaller, generates the icon, and packages the app as a single windowed
    executable with a requireAdministrator (UAC) manifest.

.PARAMETER SkipInstall
    Skip pip install. Use when the environment is already prepared.

.PARAMETER OneDir
    Build a folder (faster startup, many files) instead of a single .exe.

.EXAMPLE
    .\build.ps1
    .\build.ps1 -SkipInstall
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$OneDir
)

$ErrorActionPreference = "Stop"
Push-Location $PSScriptRoot

try {
    $python = if (Test-Path ".venv\Scripts\python.exe") {
        ".venv\Scripts\python.exe"
    } else {
        "python"
    }

    Write-Host "Using: $python" -ForegroundColor Cyan
    & $python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11+ is required'; print('Python', sys.version.split()[0])"
    if ($LASTEXITCODE -ne 0) { throw "Python 3.11+ is required." }

    if (-not $SkipInstall) {
        Write-Host "Installing dependencies..." -ForegroundColor Cyan
        & $python -m pip install --upgrade pip
        & $python -m pip install -r requirements.txt "pyinstaller>=6.6"
    }

    Write-Host "Generating icon..." -ForegroundColor Cyan
    & $python tools\make_icon.py

    $mode = if ($OneDir) { "--onedir" } else { "--onefile" }

    $arguments = @(
        "--noconfirm"
        "--clean"
        $mode
        "--windowed"
        "--uac-admin"
        "--name", "EFI-Boot-Entry-Cleaner"
        "--icon", "assets\app.ico"
        "--add-data", "assets;assets"
        "--version-file", "packaging\windows_version_info.txt"
        "--exclude-module", "tkinter"
        "main.py"
    )

    Write-Host "Running PyInstaller..." -ForegroundColor Cyan
    & $python -m PyInstaller @arguments

    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

    $artifact = if ($OneDir) {
        "dist\EFI-Boot-Entry-Cleaner\EFI-Boot-Entry-Cleaner.exe"
    } else {
        "dist\EFI-Boot-Entry-Cleaner.exe"
    }

    if (-not (Test-Path $artifact)) { throw "Build finished but $artifact is missing." }

    $hash = (Get-FileHash $artifact -Algorithm SHA256).Hash
    $size = [math]::Round((Get-Item $artifact).Length / 1MB, 1)

    Write-Host ""
    Write-Host "Build complete" -ForegroundColor Green
    Write-Host "  File:   $artifact"
    Write-Host "  Size:   $size MB"
    Write-Host "  SHA256: $hash"
    Write-Host ""
    Write-Host "Double-click the .exe - Windows will ask for Administrator rights." -ForegroundColor Yellow
}
finally {
    Pop-Location
}
