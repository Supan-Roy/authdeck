Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$innoScript = Join-Path $projectRoot 'installer\AuthDeck.iss'
if (-not (Test-Path $innoScript)) {
  throw "Inno Setup script not found: $innoScript"
}

$isccCandidates = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)

$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
  throw "ISCC.exe not found. Install Inno Setup 6 first."
}

& $iscc $innoScript
if ($LASTEXITCODE -ne 0) {
  throw "Installer build failed"
}

Write-Host "Installer build complete. Check installer/output." -ForegroundColor Green
