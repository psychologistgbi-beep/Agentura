# Hourly sync runtime (calendar + mail)

## Command

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas sync hourly --retries 2 --backoff-sec 5
```

Default policy:
- `--retries 2` per source (calendar and mail separately)
- `--backoff-sec 5`
- backoff formula: `delay = backoff_sec * 2^attempt` (attempt starts from `0` for first retry)

## Exit codes

- `0` - both sources synced successfully
- `2` - degraded mode: only one source synced successfully
- `1` - both sources failed

## Scheduling locally (notebook)

### Cron (Linux/macOS)

```cron
# Every hour at minute 0
0 * * * * cd /Users/gaidabura/Agentura/apps/executive-cli && uv run execas sync hourly --retries 2 --backoff-sec 5 >> /tmp/execas-hourly-sync.log 2>&1
```

### launchd (macOS)

Create a LaunchAgent plist with:
- `StartInterval = 3600`
- `ProgramArguments = ["/usr/bin/env", "uv", "run", "execas", "sync", "hourly", "--retries", "2", "--backoff-sec", "5"]`
- `WorkingDirectory = /Users/gaidabura/Agentura/apps/executive-cli`

### Windows Task Scheduler

Configure an hourly trigger and run:

```powershell
uv run execas sync hourly --retries 2 --backoff-sec 5
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
   `uv run execas sync hourly --retries 2 --backoff-sec 5`
4. If source remains unavailable, run manual fallback commands below.

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
