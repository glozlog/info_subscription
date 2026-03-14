$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Port = 8501
$Url = "http://localhost:$Port/"

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

function Test-PortOpen {
  param([int]$Port)
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect("127.0.0.1", $Port)
    $client.Close()
    return $true
  } catch {
    return $false
  }
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

try {
  & $PythonExe -c "import streamlit, pandas, psutil" | Out-Null
} catch {
  Write-Host "Python environment is missing required packages (streamlit/pandas/psutil)."
  Write-Host "Python: $PythonExe"
  exit 1
}

if (-not (Test-PortOpen -Port $Port)) {
  $logDir = Join-Path $ProjectRoot "logs"
  if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
  $ts = Get-Date -Format "yyyyMMdd_HHmmss"
  $outLog = Join-Path $logDir "streamlit_${ts}.out.log"
  $errLog = Join-Path $logDir "streamlit_${ts}.err.log"

  $p = Start-Process -FilePath $PythonExe -ArgumentList @(
    "-m", "streamlit", "run", "web_app.py",
    "--server.headless", "true",
    "--server.port", "$Port"
  ) -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog

  Start-Sleep -Milliseconds 800
  if ($p -and $p.HasExited) {
    Write-Host "Failed to start Streamlit (process exited immediately)."
    Write-Host "Logs:"
    Write-Host "  $outLog"
    Write-Host "  $errLog"
    exit 2
  }

  $deadline = (Get-Date).AddSeconds(60)
  while ((Get-Date) -lt $deadline) {
    if (Test-PortOpen -Port $Port) {
      if (Test-HttpReady -Url $Url) { break }
    }
    Start-Sleep -Milliseconds 500
  }
}

if (-not (Test-HttpReady -Url $Url)) {
  Write-Host "Streamlit is not responding on $Url"
  exit 3
}

Start-Process $Url | Out-Null
