$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$ComposeDir = Join-Path $ProjectRoot "wechat2rss"
$ComposeFile = Join-Path $ComposeDir "docker-compose.yml"
$EnvFile = Join-Path $ComposeDir ".env"
$EnvExample = Join-Path $ComposeDir ".env.example"

if (-not (Test-Path $ComposeFile)) {
  Write-Host "Compose file not found: $ComposeFile"
  exit 1
}

if (-not (Test-Path $EnvFile)) {
  if (Test-Path $EnvExample) {
    Copy-Item $EnvExample $EnvFile
  } else {
    New-Item -ItemType File -Path $EnvFile | Out-Null
  }
  Write-Host "Created env file: $EnvFile"
  Write-Host "Please edit it and fill LIC_EMAIL / LIC_CODE / RSS_HOST, then run again."
  notepad $EnvFile
  exit 2
}

$envMap = @{}
Get-Content $EnvFile | ForEach-Object {
  $line = $_.Trim()
  if (-not $line) { return }
  if ($line.StartsWith("#")) { return }
  $parts = $line.Split("=", 2)
  if ($parts.Count -ne 2) { return }
  $k = $parts[0].Trim()
  $v = $parts[1].Trim()
  if ($k) { $envMap[$k] = $v }
}

$missing = @()
foreach ($k in @("LIC_EMAIL", "LIC_CODE", "RSS_HOST")) {
  if (-not $envMap.ContainsKey($k) -or -not $envMap[$k]) {
    $missing += $k
  }
}
if ($missing.Count -gt 0) {
  Write-Host "Missing env values in ${EnvFile}: $($missing -join ', ')"
  exit 3
}

try {
  docker info | Out-Null
} catch {
  Write-Host "Docker daemon is not running. Please start Docker Desktop first."
  exit 1
}

docker compose -f $ComposeFile up -d

$token = ""
$TokenFile = Join-Path $ComposeDir "token.txt"
try {
  $logsText = docker logs wechat2rss 2>$null | Out-String
  if ($logsText) {
    $matches = [regex]::Matches($logsText, 'Token:\s*([A-Za-z0-9_-]+)')
    if ($matches -and $matches.Count -gt 0) {
      $token = $matches[$matches.Count - 1].Groups[1].Value
    }
  }
} catch {
}

if (-not $token -and (Test-Path $TokenFile)) {
  try {
    $token = (Get-Content $TokenFile -ErrorAction SilentlyContinue | Select-Object -First 1).Trim()
  } catch {
  }
}

if ($token) {
  try { Set-Clipboard -Value $token } catch { }
  try { $token | Out-File -FilePath $TokenFile -Encoding utf8 -Force } catch { }
  Write-Host ""
  Write-Host "Wechat2RSS Token: $token"
  Write-Host "Token copied to clipboard."
}

Start-Sleep -Seconds 1
Start-Process "http://localhost:8080" | Out-Null
