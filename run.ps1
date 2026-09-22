$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv311\Scripts\python.exe')) {
    py -3.11 -m venv .venv311
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& .\.venv311\Scripts\python.exe -m pip install -r requirements-lock.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv311\Scripts\python.exe -m exile_worth
