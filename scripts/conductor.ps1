# conductor.ps1 - the daily orchestrated run (one scheduled task; replaces AILF-Scout).
# Runs the fleet's scheduled steps with failure isolation, writes a consolidated run log, and
# syncs the Ledger + briefs to the private GitHub repo nightly so the repo self-maintains.
# ASCII only (PS 5.1 reads no-BOM .ps1 as cp1252). Subscription auth; ANTHROPIC_API_KEY unset.
# Do NOT set $ErrorActionPreference = "Stop" - native stderr would abort before logging.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$today = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $root "runs\conductor.log"
function Log($m) { "$([DateTime]::UtcNow.ToString('o')) $m" | Out-File -Append -Encoding utf8 $log }
$status = [ordered]@{ date = $today; ts = [DateTime]::UtcNow.ToString('o') }

# Step 1: Scout - news brief + map pointer + due footer (its own subprocess = failure isolation).
try {
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "scripts\scout.ps1")
  $status.scout = "exit $LASTEXITCODE"
} catch {
  $status.scout = "error: $($_.Exception.Message)"
}
Log "scout: $($status.scout)"

# (Extension point: Showcase weekly drafts slot in here once built. If Scout failed with an
#  auth/rate-limit exhaustion, a future step should skip rather than retry into the same wall.)

# Step 2: Sync - commit + push Ledger + briefs to the private repo (the self-maintaining piece).
try {
  git add ledger briefs
  git diff --cached --quiet
  if ($LASTEXITCODE -ne 0) {
    git commit -q -m "chore(daily): fleet run $today"
    git push -q origin main
    $status.sync = "pushed"
  } else {
    $status.sync = "no changes"
  }
} catch {
  $status.sync = "error: $($_.Exception.Message)"
}
Log "sync: $($status.sync)"

# Consolidated per-run record (local; runs/ is git-ignored).
$status | ConvertTo-Json -Compress | Out-File -Append -Encoding utf8 (Join-Path $root "runs\daily-$today.jsonl")
Log "daily run complete"
