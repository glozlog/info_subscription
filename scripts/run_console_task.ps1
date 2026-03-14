$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Port = 8501
$Url = "http://localhost:$Port/"

$PythonExe = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

function Test-HttpReady {
  param([string]$Url)
  try {
    $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
    return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
  } catch {
    return $false
  }
}

if (Test-HttpReady -Url $Url) {
  exit 0
}

$logDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$outLog = Join-Path $logDir "streamlit_task_${ts}.out.log"
$errLog = Join-Path $logDir "streamlit_task_${ts}.err.log"

Start-Process -FilePath $PythonExe -ArgumentList @(
  "-m", "streamlit", "run", "web_app.py",
  "--server.headless", "true",
  "--server.port", "$Port"
) -WorkingDirectory $ProjectRoot -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog | Out-Null

exit 0
