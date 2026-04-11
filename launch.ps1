$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'python is required but was not found on PATH.'
}

if (-not (Test-Path '.venv')) {
    Write-Host 'Creating virtual environment in .venv'
    python -m venv .venv
}

$VenvPython = Join-Path $ScriptDir '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    throw 'Virtual environment python executable not found at .venv\Scripts\python.exe'
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

& $VenvPython -m gasp.main
