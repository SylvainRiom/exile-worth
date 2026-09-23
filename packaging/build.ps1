# Builds build\installer\ExileWorth-Setup-<version>.exe and its .sha256.
#   .\packaging\build.ps1              # tests, executable, self-test, installer
#   .\packaging\build.ps1 -SkipTests
param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

$python = if ($env:EXILE_BUILD_PYTHON) { $env:EXILE_BUILD_PYTHON } else { '.\.venv311\Scripts\python.exe' }
function Invoke-Checked { param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') failed ($LASTEXITCODE)" }
}

$version = (Select-String -Path 'exile_worth\__init__.py' -Pattern "__version__ = '([^']+)'").Matches[0].Groups[1].Value
Write-Host "Exile Worth $version"

Invoke-Checked $python @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', 'requirements-lock.txt', '-r', 'requirements-build.txt')
if (-not $SkipTests) {
    Invoke-Checked $python @('-m', 'unittest', 'discover', '-s', 'tests')
}

Invoke-Checked $python @('-m', 'PyInstaller', '--noconfirm', '--distpath', 'build\dist', '--workpath', 'build\work', 'packaging\exile_worth.spec')

# The executable must load its OCR models, catalogue and icons, not just start.
$report = Join-Path $root 'build\self-test.json'
$process = Start-Process -FilePath 'build\dist\ExileWorth\ExileWorth.exe' -ArgumentList @('--self-test', "`"$report`"") -Wait -PassThru
Get-Content $report
if ($process.ExitCode -ne 0) { throw "Self-test of the packaged build failed" }

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) { throw 'Inno Setup 6 not found: winget install JRSoftware.InnoSetup' }
Invoke-Checked $iscc @('/Q', "/DAppVersion=$version", 'packaging\installer.iss')

$setup = "build\installer\ExileWorth-Setup-$version.exe"
$hash = (Get-FileHash -Algorithm SHA256 $setup).Hash.ToLower()
# Same layout as sha256sum: "<hash>  <file name>".
Set-Content -Path "$setup.sha256" -Value "$hash  $(Split-Path -Leaf $setup)" -Encoding ascii -NoNewline
Write-Host "$setup ($([math]::Round((Get-Item $setup).Length / 1MB)) MB)"
Write-Host "sha256 $hash"
