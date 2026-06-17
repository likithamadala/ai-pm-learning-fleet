<#
Registers the daily Conductor task and removes the Scout-only task (Conductor now runs Scout).
Interactive logon (runs while you're logged in) - correct for a passwordless account; no password.

  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-conductor-task.ps1 [-At 07:30]

Remove:  Unregister-ScheduledTask -TaskName AILF-Conductor -Confirm:$false
#>
param(
  [string]$At = "07:30",
  [string]$TaskName = "AILF-Conductor"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\conductor.ps1"
if (-not (Test-Path $script)) { throw "conductor.ps1 not found at $script" }

# Conductor runs Scout itself, so retire the standalone Scout task to avoid a double run.
try { Unregister-ScheduledTask -TaskName "AILF-Scout" -Confirm:$false -ErrorAction Stop; Write-Host "Removed old AILF-Scout task." } catch {}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings `
  -Description "AI Learning Fleet - daily orchestrated run (Scout + sync)" -Force | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
Write-Host "Registered '$TaskName' - daily at $At (runs while you're logged in)."
Write-Host "Next run: $($info.NextRunTime)"
Write-Host "Test now: Start-ScheduledTask -TaskName $TaskName"
Write-Host "Remove:   Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
