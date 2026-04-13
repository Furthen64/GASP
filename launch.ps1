$ErrorActionPreference = 'Stop'

# Optional: set this to the folder containing your python.exe if it is not on PATH.
# Example: $PythonPath = 'C:\python312\'
$PythonPath = ''

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if ($PythonPath -ne '') {
    # Resolve python.exe from the user-supplied directory
    $PythonExe = Join-Path $PythonPath 'python.exe'
    if (-not (Test-Path $PythonExe)) {
        throw "python.exe was not found in the specified PythonPath: $PythonPath"
    }
    $PythonCmd = $PythonExe
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = 'python'
} else {
    throw 'python is required but was not found on PATH. Set $PythonPath at the top of launch.ps1 to your Python installation folder.'
}

if (-not (Test-Path '.venv')) {
    Write-Host 'Creating virtual environment in .venv'
    & $PythonCmd -m venv .venv
}

$VenvPython = Join-Path $ScriptDir '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
    throw 'Virtual environment python executable not found at .venv\Scripts\python.exe'
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

& $VenvPython -m gasp.main
