# Memoriq Virtual Environment Setup (Windows)
$ErrorActionPreference = "Stop"

$MEMORIQ_HOME = "$env:USERPROFILE\.memoriq"
$VENV_PATH = "$MEMORIQ_HOME\venv"

Write-Host "[Memoriq] Setting up virtual environment..."

if (-not (Test-Path $VENV_PATH)) {
    python -m venv $VENV_PATH
    Write-Host "[Memoriq] Virtual environment created at $VENV_PATH"
}

& "$VENV_PATH\Scripts\Activate.ps1"

python -m pip install --upgrade pip
python -m pip install -r "$MEMORIQ_HOME\requirements.txt"

Write-Host "[Memoriq] Dependencies installed successfully"
Write-Host "[Memoriq] Virtual environment ready at $VENV_PATH"
