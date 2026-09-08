# Register a daily ADHD Hub indexer task (Windows Task Scheduler)
param(
    [string]$TaskName = "ADHD-Hub-Indexer",
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Time = "09:15"
)

$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) { throw "uv not found on PATH" }

$action = New-ScheduledTaskAction -Execute $uv -Argument "run adhd-hub index" -WorkingDirectory $RepoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Registered task '$TaskName' daily at $Time in $RepoRoot"
