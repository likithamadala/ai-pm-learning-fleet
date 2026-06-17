# scout.ps1 - daily Scout run. Registered as a Windows Task Scheduler task.
# Subscription auth: the run uses your logged-in Claude (run `claude login` once).
# ANTHROPIC_API_KEY must stay UNSET. Plain `claude -p`, never --bare.
#
# NOTE: do NOT set $ErrorActionPreference = "Stop" here. Native tools (python, claude) write
# progress/warnings to stderr, and under "Stop" PowerShell turns that into a fatal error before
# we can log it - which silently kills the task. We gate on explicit exit codes instead.

$root = Split-Path -Parent $PSScriptRoot      # scripts/ -> project root
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

# Resolve claude - prefer claude.cmd (reliable stdin piping); allow override via AILF_CLAUDE.
$claude = $env:AILF_CLAUDE
if (-not $claude) {
  $resolved = Get-Command claude.cmd -ErrorAction SilentlyContinue
  $claude = if ($resolved) { $resolved.Source } else { "claude" }
}

$today = Get-Date -Format "yyyy-MM-dd"
$log = Join-Path $root "runs\scout.log"
function Log($m) { "$([DateTime]::UtcNow.ToString('o')) $m" | Out-File -Append -Encoding utf8 $log }

# 1. Prep - fetch feeds, dedup, rank, extract. stdout = JSON status; we gate on exit code.
$prep = & $py scripts\scout.py prep --top 2
$code = $LASTEXITCODE
if ($code -eq 3) { Log "nothing new today"; exit 0 }
if ($code -ne 0) { Log "prep failed (exit $code): $prep"; exit 1 }

# 2. Reason - scaffold the chosen items into a brief. Prompt via stdin (avoids arg limits).
#    stdout = the brief; stderr (progress) is left to the task host. Gate on exit code.
$promptFile = Join-Path $root "runs\_scout_prompt.txt"
$brief = Get-Content -Raw $promptFile | & $claude -p --append-system-prompt-file agents\scout.md --output-format text
$claudeCode = $LASTEXITCODE

# Failure isolation + cap/auth handling: if the model run failed, do NOT commit - items stay
# unprocessed and retry tomorrow rather than being silently consumed.
if ($claudeCode -ne 0 -or [string]::IsNullOrWhiteSpace($brief)) {
  Log "claude run failed (exit $claudeCode) - not committing; items kept for retry. Is 'claude login' done?"
  exit 1
}

# 3. Write the brief, then append the concept-map pointer (cheap, deterministic - no LLM call).
$briefPath = Join-Path $root "briefs\$today.md"
$brief | Out-File -Encoding utf8 $briefPath
"" | Out-File -Append -Encoding utf8 $briefPath
& $py scripts\cartographer.py pointer | Out-File -Append -Encoding utf8 $briefPath
$due = & $py scripts\schedule.py summary
if ($due) { $due | Out-File -Append -Encoding utf8 $briefPath }

# Weekly refresh (Mondays): re-merge curriculum.json into the concept map.
if ((Get-Date).DayOfWeek -eq 'Monday') { & $py scripts\cartographer.py seed | Out-Null; Log "concept map refreshed" }

# 4. Commit - mark delivered URLs processed, log the run, bump the streak.
& $py scripts\scout.py commit | Out-Null
Log "brief written: $briefPath"
