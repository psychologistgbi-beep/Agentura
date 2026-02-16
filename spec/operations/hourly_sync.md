# Hourly sync runtime (calendar + mail)

## Command

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas sync hourly --retries 2 --backoff-sec 5 --parallel
```

Credential setup helper for EA live checks:
```bash
cd /Users/gaidabura/Agentura
scripts/ea-yandex-check
```

Post-sync verification (next-week meetings in local DB):
```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas calendar next-week --source yandex_caldav
```

Weekday sanity-check rule (operations):
- On Monday-Friday, run post-sync verification after scheduler run.
- If `sync hourly` is `status=ok` and `calendar next-week` returns no meetings for 2 consecutive runs, raise alert.
- Suppress alert when maintenance window or degraded-mode incident is explicitly declared.

Default policy:
- `--retries 2` per source (calendar and mail separately)
- `--backoff-sec 5`
- `--parallel` (default): calendar/mail are executed concurrently with isolated DB sessions.
- backoff formula: `delay = backoff_sec * 2^attempt` (attempt starts from `0` for first retry)

Sequential mode is available when lower external concurrency is preferred:
```bash
uv run execas sync hourly --retries 2 --backoff-sec 5 --sequential
```

Runtime telemetry in CLI output:
- `attempts=<n>` and `elapsed_sec=<seconds>` for each source;
- final line includes `mode=<parallel|sequential>` and total `elapsed_sec`.

CalDAV sync-window tuning (optional, load control):
- `EXECAS_CALDAV_SYNC_LOOKBACK_DAYS` (default `30`)
- `EXECAS_CALDAV_SYNC_LOOKAHEAD_DAYS` (default `365`)

## Exit codes

- `0` - both sources synced successfully
- `2` - degraded mode: only one source synced successfully
- `1` - both sources failed

## Scheduling locally (notebook)

### Cron (Linux/macOS)

```cron
# Every hour at minute 0
0 * * * * cd /Users/gaidabura/Agentura/apps/executive-cli && uv run execas sync hourly --retries 2 --backoff-sec 5 --parallel >> /tmp/execas-hourly-sync.log 2>&1

# Optional sanity check (weekday alert hook to monitoring wrapper)
5 * * * 1-5 cd /Users/gaidabura/Agentura/apps/executive-cli && uv run execas calendar next-week --source yandex_caldav >> /tmp/execas-next-week.log 2>&1
```

### launchd (macOS)

Create a LaunchAgent plist with:
- `StartInterval = 3600`
- `ProgramArguments = ["/usr/bin/env", "uv", "run", "execas", "sync", "hourly", "--retries", "2", "--backoff-sec", "5", "--parallel"]`
- `WorkingDirectory = /Users/gaidabura/Agentura/apps/executive-cli`

### Windows Task Scheduler

Configure an hourly trigger and run:

```powershell
uv run execas sync hourly --retries 2 --backoff-sec 5 --parallel
```

Working directory:
`C:\Users\gaidabura\Agentura\apps\executive-cli`

## Degraded mode handling

If one source fails after retries:
- command prints `degraded` with sanitized reason (no secrets)
- second source still runs
- process exits with code `2`

Recommended ops actions:
1. Check network reachability and endpoint availability.
2. Verify connector env vars are present (without printing secret values).
3. Re-run manually with same retry policy:
   `uv run execas sync hourly --retries 2 --backoff-sec 5 --parallel`
4. Re-check imported meetings:
   `uv run execas calendar next-week --source yandex_caldav`
5. If source remains unavailable, run manual fallback commands below.

If both sources fail:
- process exits with code `1`
- treat as incident requiring connector/service remediation

## Manual fallback commands

### Calendar fallback

```bash
uv run execas busy add --date YYYY-MM-DD --start HH:MM --end HH:MM --title "Manual busy block"
```

### Mail fallback

```bash
uv run execas task capture "Email follow-up" --estimate 30 --priority P2 --status NEXT
```

## Security/observability notes

- Do not print raw exception messages from connectors in operator runbooks/log templates.
- Error output from hourly sync is intentionally sanitized to avoid secret leakage.
- Keep scheduler logs enabled so `0/2/1` outcomes are visible over time.
