<#
Registers (or updates) the daily Scout task.

Uses Interactive logon (runs while you're logged in) - the correct mode for a passwordless
Windows account, which cannot run tasks "whether logged on or not". No password required.

  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-scout-task.ps1 [-At 07:30] [-TaskName AILF-Scout]

Settings:
  -StartWhenAvailable  -> if the machine was off/logged out at the trigger, run at next logon
  -WakeToRun           -> wake from sleep to run (when you're logged in)

Remove:  Unregister-ScheduledTask -TaskName AILF-Scout -Confirm:$false
#>
param(
  [string]$At = "07:30",
  [string]$TaskName = "AILF-Scout"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\scout.ps1"
if (-not (Test-Path $script)) { throw "scout.ps1 not found at $script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings `
  -Description "AI Learning Fleet - daily Scout brief" -Force | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
Write-Host "Registered '$TaskName' - daily at $At (runs while you're logged in)."
Write-Host "Next run: $($info.NextRunTime)"
Write-Host "Test now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "Remove:   Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
