$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$TaskName = "InfoSubscriptionConsole"

$PsExe = "powershell.exe"
$Script = Join-Path $ProjectRoot "scripts\\run_console_task.ps1"
if (-not (Test-Path $Script)) {
  Write-Host "Script not found: $Script"
  exit 1
}

$Args = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$Action = New-ScheduledTaskAction -Execute $PsExe -Argument $Args -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\\$env:USERNAME"
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -Hidden
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {
}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null

Write-Host "Created/updated Task Scheduler task: $TaskName"
Write-Host "Trigger: AtLogOn ($env:USERDOMAIN\\$env:USERNAME)"
Write-Host "Command: $PsExe $Args"
