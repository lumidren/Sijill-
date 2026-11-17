<#
.SYNOPSIS
  One command to run Sijill: installs dependencies, builds the UI, migrates the
  database, seeds the demo clinic (first run only) and serves the app.

.EXAMPLE
  ./scripts/start.ps1                      # demo install on http://127.0.0.1:8000
  ./scripts/start.ps1 -NoDemo              # empty install; create the first admin in the browser
  ./scripts/start.ps1 -DataDir D:\clients\acme -Port 8010   # one install per client organisation
  ./scripts/start.ps1 -ResetDemo           # wipe the database and re-seed the demo
#>
param(
  [string]$DataDir = "",
  [int]$Port = 8000,
  [string]$BindHost = "127.0.0.1",
  [switch]$NoDemo,
  [switch]$ResetDemo,
  [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

# 1. Python 3.12 (64-bit) virtual environment
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
  Step "Creating Python virtual environment (.venv)"
  $created = $false
  if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -eq 0) { $created = $true }
  }
  if (-not $created) { & python -m venv .venv }
  if (-not (Test-Path $venvPy)) { throw "Could not create a virtual environment. Python 3.12 is required." }
}
$bits = & $venvPy -c "import struct; print(struct.calcsize('P')*8)"
if ($bits -ne "64") { Write-Warning "The virtual environment uses 32-bit Python; 64-bit Python 3.12 is recommended." }

# 2. Backend dependencies (re-installed only when requirements.txt changes)
$req = Join-Path $Root "backend\requirements.txt"
$stamp = Join-Path $Root ".venv\.requirements.sha256"
$hash = (Get-FileHash $req -Algorithm SHA256).Hash
if (-not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $hash) {
  Step "Installing backend dependencies"
  & $venvPy -m pip install --disable-pip-version-check -q -r $req
  if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
  Set-Content -Path $stamp -Value $hash -Encoding ascii
}

# 3. Frontend build
if (-not $SkipBuild) {
  Push-Location (Join-Path $Root "frontend")
  try {
    $lock = "package-lock.json"
    $lockStamp = "node_modules\.lock.sha256"
    $lockHash = (Get-FileHash $lock -Algorithm SHA256).Hash
    if (-not (Test-Path "node_modules") -or -not (Test-Path $lockStamp) -or (Get-Content $lockStamp -Raw).Trim() -ne $lockHash) {
      Step "Installing frontend dependencies"
      & npm ci --no-audit --no-fund
      if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
      Set-Content -Path $lockStamp -Value $lockHash -Encoding ascii
    }
    Step "Building the web interface"
    & npx vite build --logLevel warn
    if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
  } finally { Pop-Location }
}

# 4. Database + demo data
if ($DataDir) { $env:PDPL_DATA_DIR = (New-Item -ItemType Directory -Force $DataDir).FullName }
Push-Location (Join-Path $Root "backend")
try {
  Step "Applying database migrations"
  & $venvPy -m app.cli migrate
  if ($LASTEXITCODE -ne 0) { throw "migration failed" }
  if ($ResetDemo) {
    Step "Resetting and seeding the demo clinic"
    & $venvPy -m app.cli seed-demo --reset
  } elseif (-not $NoDemo) {
    Step "Seeding the demo clinic (first run only)"
    & $venvPy -m app.cli seed-demo --if-empty
  }
  if ($LASTEXITCODE -ne 0) { throw "demo seed failed" }
} finally { Pop-Location }

# 5. Serve
Step "Sijill is starting on http://${BindHost}:$Port  (Ctrl+C to stop)"
& $venvPy -m uvicorn app.main:app --app-dir backend --host $BindHost --port $Port
