<#
.SYNOPSIS
  Development mode: FastAPI with auto-reload on :8000 and the Vite dev server on :5173
  (which proxies /api to the backend). Open http://localhost:5173.
  Run scripts/start.ps1 once first so dependencies and the database exist.
#>
param([int]$ApiPort = 8000)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Run scripts/start.ps1 once first to create .venv" }

Push-Location (Join-Path $Root "backend")
& $venvPy -m app.cli migrate
Pop-Location

$api = Start-Process -FilePath $venvPy -PassThru -NoNewWindow -ArgumentList @(
  "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--reload", "--reload-dir", "backend",
  "--host", "127.0.0.1", "--port", "$ApiPort") -WorkingDirectory $Root
try {
  Push-Location (Join-Path $Root "frontend")
  & npm run dev
} finally {
  Pop-Location
  if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force }
}
