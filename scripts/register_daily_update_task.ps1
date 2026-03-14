$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$TaskName = "InfoSubscriptionDailyUpdate"
$Time = "07:00"

$PythonExe = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"
if (-not (Test-Path $PythonExe)) {
  $PythonExe = "python"
}

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "-u main.py --run-3days" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At ([DateTime]::ParseExact($Time, "HH:mm", $null))
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
} catch {
}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null

Write-Host "Created/updated Task Scheduler task: $TaskName"
Write-Host "Runs daily at: $Time"
Write-Host "Command: $PythonExe -u main.py --run-3days"
