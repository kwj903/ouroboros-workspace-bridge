$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is required before installing Workspace Terminal Bridge. Install uv, then run this script again."
    exit 1
}

uv sync
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Workspace Terminal Bridge dependencies are installed."
Write-Host ""
Write-Host "Next:"
Write-Host "  uv run woojae setup"
Write-Host ""
Write-Host "This project is intended to run from a repository checkout with:"
Write-Host "  uv run woojae ..."
