$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$ComposeFile = Join-Path $ProjectRoot "wechat2rss\docker-compose.yml"

Write-Host "== Docker compose ps =="
docker compose -f $ComposeFile ps

Write-Host ""
Write-Host "== Container list (filtered) =="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | Select-String -Pattern "wechat2rss|NAMES" -CaseSensitive:$false

Write-Host ""
Write-Host "== Tail logs (wechat2rss) =="
docker logs --tail 120 wechat2rss

Write-Host ""
Write-Host "== HTTP check http://localhost:8080 =="
try {
  $resp = Invoke-WebRequest -Uri "http://localhost:8080" -TimeoutSec 5 -UseBasicParsing
  Write-Host ("Status: " + $resp.StatusCode)
} catch {
  Write-Host ("HTTP failed: " + $_.Exception.Message)
}
