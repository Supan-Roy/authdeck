Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$python = Join-Path $projectRoot '..\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
  throw "Python executable not found at $python"
}

$iconPng = Join-Path $projectRoot 'assets\icon.png'
$iconIco = Join-Path $projectRoot 'assets\icon.ico'
if ((Test-Path $iconPng) -and (-not (Test-Path $iconIco))) {
  & $python -c "from pathlib import Path; from PIL import Image; p=Path('assets/icon.png'); Image.open(p).save('assets/icon.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
}

$pyinstallerArgs = @(
  '--noconfirm'
  '--clean'
  '--noconsole'
  '--onefile'
  '--name', 'AuthDeck'
  '--add-data', 'assets;assets'
  '--add-data', 'data;data'
  '--collect-all', 'pyzbar'
  '--collect-all', 'mss'
)

if (Test-Path $iconIco) {
  $pyinstallerArgs += @('--icon', 'assets/icon.ico')
}

$pyinstallerArgs += 'main.py'

& $python -m PyInstaller @pyinstallerArgs
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed"
}

Write-Host "Build complete: dist/AuthDeck.exe" -ForegroundColor Green
