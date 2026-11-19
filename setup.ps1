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

function Resolve-Python {
  # Returns the full path of a working Python 3 interpreter, or $null.
  # Resolving to sys.executable means "py -3" and the Microsoft Store alias
  # never have to be invoked as a multi-word command later on.
  param([string]$Preferred)
  $candidates = @()
  if ($Preferred) { $candidates += ,@($Preferred) }
  $candidates += ,@("python"); $candidates += ,@("py", "-3"); $candidates += ,@("python3")
  foreach ($c in $candidates) {
    $exe = $c[0]
    $pre = @($c | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    try {
      $out = & $exe @pre -c "import sys; assert sys.version_info[0] == 3; print(sys.executable)" 2>$null
      if ($LASTEXITCODE -eq 0 -and $out) {
        $path = ($out | Select-Object -Last 1).Trim()
        if ($path -and (Test-Path $path)) { return $path }
      }
    } catch { }
  }
  return $null
}

$sysPython = Resolve-Python -Preferred $Python
if (-not $sysPython) {
  Write-Host "Python 3 not found. Install it from https://www.python.org/downloads/ (tick 'Add to PATH')." -ForegroundColor Red
  exit 1
}
Write-Step "Python: $sysPython"

# ------------------------------------------------------------- dependencies
$requirements = Join-Path $PSScriptRoot "requirements.txt"
$hasDeps = $false
if ((Test-Path $requirements) -and -not $SkipDeps) {
  $lines = Get-Content $requirements | Where-Object { $_.Trim() -and -not $_.Trim().StartsWith("#") }
  if ($lines) { $hasDeps = $true }
}

$pythonExe = $sysPython
if ($hasDeps) {
  if ($NoVenv) {
    Write-Step "Installing dependencies into system Python"
    & $pythonExe -m pip install -r $requirements
  } else {
    if (-not (Test-Path ".venv")) {
      Write-Step "Creating virtualenv .venv"
      & $sysPython -m venv .venv
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
  $providerArgs = @("scripts\setup_provider.py")
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
