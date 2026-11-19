# One-command setup (PowerShell 5.1+).
#
#   powershell -ExecutionPolicy Bypass -File setup.ps1
#
# Creates a virtualenv if there is anything to install, then runs the provider
# wizard. The template itself has zero dependencies - the venv step is skipped
# automatically when requirements.txt is empty.
#
#   setup.ps1 -Preset groq
#   setup.ps1 -SkipProvider          # configure later
#   setup.ps1 -NoVenv                # use system Python

param(
  [string]$Python = "",
  [string]$Preset = "",
  [string]$BaseUrl = "",
  [string]$ApiKey = "",
  [string]$Model = "",
  [switch]$NoVenv,
  [switch]$SkipProvider,
  [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

function Find-Python {
  param([string]$Preferred)
  if ($Preferred) { return $Preferred }
  foreach ($cmd in @("python", "py", "python3")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
      try {
        if ($cmd -eq "py") { & py -3 --version *> $null; if ($LASTEXITCODE -eq 0) { return "py -3" } }
        else { & $cmd --version *> $null; if ($LASTEXITCODE -eq 0) { return $cmd } }
      } catch { }
    }
  }
  return $null
}

$pyCmd = Find-Python -Preferred $Python
if (-not $pyCmd) {
  Write-Host "Python 3 not found. Install it from https://www.python.org/downloads/ (tick 'Add to PATH')." -ForegroundColor Red
  exit 1
}
Write-Step "Python: $pyCmd"

# ------------------------------------------------------------- dependencies
$requirements = Join-Path $PSScriptRoot "requirements.txt"
$hasDeps = $false
if ((Test-Path $requirements) -and -not $SkipDeps) {
  $lines = Get-Content $requirements | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") }
  if ($lines) { $hasDeps = $true }
}

$pythonExe = "python"
if ($hasDeps) {
  if ($NoVenv) {
    Write-Step "Installing dependencies into system Python"
    & $pyCmd -m pip install -r $requirements
  } else {
    if (-not (Test-Path ".venv")) {
      Write-Step "Creating virtualenv .venv"
      Invoke-Expression "$pyCmd -m venv .venv"
      if ($LASTEXITCODE -ne 0) { Write-Warn "venv creation failed, using system Python"; $NoVenv = $true }
    }
    if (-not $NoVenv) { $pythonExe = Join-Path $PSScriptRoot ".venv\Scripts\python.exe" }
    Write-Step "Installing dependencies"
    & $pythonExe -m pip install -r $requirements
  }
  if ($LASTEXITCODE -ne 0) { Write-Warn "pip reported errors - the provider wizard still works" }
  else { Write-Ok "dependencies installed" }
} else {
  Write-Ok "no dependencies to install"
}

# ------------------------------------------------------------- provider
if (-not $SkipProvider) {
  Write-Step "AI provider setup"
  $providerArgs = @($pythonExe, "scripts\setup_provider.py")
  if ($Preset) { $providerArgs += @("--preset", $Preset) }
  if ($BaseUrl) { $providerArgs += @("--base-url", $BaseUrl) }
  if ($ApiKey)  { $providerArgs += @("--api-key", $ApiKey) }
  if ($Model)   { $providerArgs += @("--model", $Model) }
  & $pythonExe @providerArgs
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  python scripts\local_ai.py     # check the provider and ping it"
Write-Host "  python examples\hello_local_ai.py"
Write-Host "  python scripts\setup_provider.py --check"
