# Invocation Conventions

## Day-1 Decoder (interactive)

The Decoder runs inside your normal logged-in Claude Code session via the `/decode` slash
command. No special auth, no `--bare`, no Task Scheduler. Cost is governed by your Claude
subscription window, not per-token charges → effectively $0 marginal.

Deterministic Python helpers (`extract.py`, `ledger.py`) do the fetching, parsing, and state
writes; the model only reasons. Each decode appends a run record to `runs/` for debugging.

## When scheduling is added later (Scout / Conductor — deferred)

These conventions are recorded now so the later, unattended agents are built correctly:

- **Auth (KTD1):** scheduled runs must use the subscription, not the paid API. Run
  `claude setup-token` once to get a long-lived `CLAUDE_CODE_OAUTH_TOKEN`; set ONLY that in the
  Task Scheduler task environment and ensure `ANTHROPIC_API_KEY` is **unset** there (it overrides
  the OAuth token and silently routes to per-token API billing). Verify with `claude /status`
  showing subscription, not API. Record the token's TTL and re-run `setup-token` to renew.
- **Do NOT use `--bare`** for these runs: it reads auth strictly from `ANTHROPIC_API_KEY` /
  apiKeyHelper and never reads the OAuth token, which breaks subscription auth.
- **Invocation shape:** plain `claude -p` with explicit `--allowedTools` and `--permission-mode`
  (so an unattended run never blocks on a prompt), `--output-format json` for the cost/session
  summary, `--output-format stream-json --verbose` for the full trace, context passed via
  `--append-system-prompt-file` / `--add-dir`, and `--json-schema` to shape Ledger writes.
- **Concurrency:** once a second agent can run while another is running, add a file lock around
  every Ledger read-modify-write (Day-1 has a single interactive writer, so no lock yet).
- **Cost guard:** the `total_cost_usd` field in JSON output makes a "halt if today's spend > $X"
  guard trivial; on cap/auth exhaustion, abort the remaining sequence and log the reason.

## Scout go-live (scheduling) — your one-time setup

Scout (`scripts/scout.ps1`) is ready. Three steps, in order. Do a manual run before scheduling.

### 1. Auth — subscription, not API (do this yourself; it's credentials)
- Confirm you're on the subscription: `claude /status` should show your plan, **not** API.
  If not, run `claude login` (interactive) once.
- Make sure `ANTHROPIC_API_KEY` is **not** set as a user/system environment variable — it
  overrides subscription auth and silently bills per-token. Check: `echo $env:ANTHROPIC_API_KEY`
  (should be empty).
- Headless/token alternative (only if `claude -p` won't use your login): `claude setup-token`,
  then `setx CLAUDE_CODE_OAUTH_TOKEN "<token>"` once. Note this stores the token in your user
  registry — keep the repo private and don't export it.

### 2. Manual test (prove it before automating)
```powershell
cd "C:\Users\User\Documents\Personal Projects\ai-learning-fleet"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\scout.ps1
```
Expect a brief at `briefs\<today>.md` and a line in `runs\scout.log`. If `claude` isn't on PATH
in this context, set `$env:AILF_CLAUDE = "C:\path\to\claude.exe"` and retry.

### 3. Register the daily task — one command
This machine's Windows account has **no password**, and Windows will not run a task "whether
logged on or not" for a passwordless account (blank-password accounts are barred from batch
logon). So Scout uses **Interactive logon** — it runs while you're logged in. The installer sets
this up:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-scout-task.ps1   # optional: -At 08:00
```
It registers `AILF-Scout` to run daily at 07:30 with `-StartWhenAvailable` (runs at next logon if
the machine was off/logged out at the trigger) and `-WakeToRun` (wakes from sleep while you're
logged in). For a daily morning brief that's effectively always-on.

**True logged-out running** requires a Windows account password: set one, then re-run with the
principal switched to `-LogonType Password` — Task Scheduler stores the password (encrypted) so it
can load your profile and read your Claude login. `S4U` (passwordless logged-out) cannot read the
credential store, so it is not used.

Inspect / test / remove:
`Get-ScheduledTask AILF-Scout` · `Start-ScheduledTask -TaskName AILF-Scout` ·
`Unregister-ScheduledTask -TaskName AILF-Scout -Confirm:$false`. Status also shows in
`python scripts\doctor.py`.
