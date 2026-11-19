# One-line installer (PowerShell).
#
#   irm https://raw.githubusercontent.com/itskeshavm-sketch/make-it-local/main/install.ps1 | iex
#
# Downloads the toolkit, then runs setup.ps1 (provider wizard included).
# No git required. Safe to re-run: an existing folder is updated, not wiped.

param(
  [string]$Dir = "",
  [string]$Preset = "",
  [string]$BaseUrl = "",
  [string]$ApiKey = "",
  [string]$Model = "",
  [switch]$SkipDeps,
  [switch]$SkipProvider,
  [switch]$NoVenv
)

$ErrorActionPreference = "Stop"

$Repo = "itskeshavm-sketch/make-it-local"
$Zip = "https://codeload.github.com/$Repo/zip/refs/heads/main"
$Target = if ($Dir) { $Dir } elseif ($env:MAKE_IT_LOCAL_DIR) { $env:MAKE_IT_LOCAL_DIR } else { Join-Path (Get-Location) "make-it-local" }

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }

Write-Step "Installing make-it-local into $Target"

if (Test-Path (Join-Path $Target ".git")) {
  Write-Step "Existing git checkout found - updating"
  try { git -C $Target pull --ff-only | Out-Null; Write-Ok "updated" }
  catch { Write-Warn "git pull failed, continuing with the copy on disk" }
} elseif (Test-Path $Target) {
  Write-Step "Folder exists but is not a git checkout - refreshing it"
  Remove-Item $Target -Recurse -Force
  New-Item -ItemType Directory -Path $Target -Force | Out-Null
} else {
  New-Item -ItemType Directory -Path $Target -Force | Out-Null
}

if (-not (Test-Path (Join-Path $Target ".git"))) {
  $git = Get-Command git -ErrorAction SilentlyContinue
  if ($git) {
    Write-Step "Cloning with git"
    git clone --depth 1 "https://github.com/$Repo.git" $Target | Out-Null
    Write-Ok "cloned"
  } else {
    Write-Step "git not found - downloading the zip instead"
    $tmp = Join-Path $env:TEMP ("mil_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    $zipPath = Join-Path $tmp "repo.zip"
    Invoke-WebRequest -Uri $Zip -OutFile $zipPath -UseBasicParsing
    Expand-Archive -Path $zipPath -DestinationPath $tmp -Force
    $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
    Copy-Item -Path (Join-Path $inner.FullName "*") -Destination $Target -Recurse -Force
    Remove-Item $tmp -Recurse -Force
    Write-Ok "downloaded"
  }
}

$setup = Join-Path $Target "setup.ps1"
if (-not (Test-Path $setup)) {
  Write-Warn "setup.ps1 missing from the download"
  Write-Host "Manual step: cd `"$Target`" ; powershell -ExecutionPolicy Bypass -File setup.ps1" -ForegroundColor Yellow
  exit 1
}

Write-Step "Running setup (provider wizard)"
$setupArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $setup)
if ($SkipDeps)     { $setupArgs += "-SkipDeps" }
if ($SkipProvider) { $setupArgs += "-SkipProvider" }
if ($NoVenv)       { $setupArgs += "-NoVenv" }
if ($Preset)       { $setupArgs += @("-Preset", $Preset) }
if ($BaseUrl)      { $setupArgs += @("-BaseUrl", $BaseUrl) }
if ($ApiKey)       { $setupArgs += @("-ApiKey", $ApiKey) }
if ($Model)        { $setupArgs += @("-Model", $Model) }
& powershell @setupArgs

Write-Host ""
Write-Host "Installed at: $Target" -ForegroundColor Green
Write-Host "cd `"$Target`" ; python scripts\local_ai.py" -ForegroundColor Green
