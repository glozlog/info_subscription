$ErrorActionPreference = "Continue"

$TaskName = "InfoSubscriptionConsole"

try {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
  Write-Host "Removed Task Scheduler task: $TaskName"
} catch {
  Write-Host "Task not found or could not remove: $TaskName"
}
