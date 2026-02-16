# EA Yandex Integration Scenarios

**Owner:** Executive Assistant  
**Date:** 2026-02-15  
**Scope:** Yandex CalDAV + Yandex IMAP (`INBOX`) in read-only mode

## Security baseline

- Credentials are accepted from user only via secure channel.
- Credentials are used via environment variables only.
- Credentials are never written to repository files, markdown examples, or SQLite.
- Mail scope is fixed to `INBOX`.

Required runtime variables:
- `EXECAS_CALDAV_URL`
- `EXECAS_CALDAV_USERNAME`
- `EXECAS_CALDAV_PASSWORD`
- `EXECAS_IMAP_HOST`
- `EXECAS_IMAP_PORT` (default `993`)
- `EXECAS_IMAP_USERNAME`
- `EXECAS_IMAP_PASSWORD`

## Scenario 1: Credential intake and secure session setup

Goal: obtain credentials from user and prepare one secure operator session.

Steps:
1. Receive credentials from user in secure channel.
2. Start a clean terminal session.
3. Set environment variables for current session only.
4. Do not print secret values and do not store them in files.

Recommended command helper:
```bash
cd /Users/gaidabura/Agentura
scripts/ea-yandex-check --only-smoke
```

## Scenario 2: Smoke validation (connectivity + policy)

Goal: verify connectors work with read-only policy before full run.

Commands:
```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas calendar sync
uv run execas mail sync --mailbox INBOX
uv run execas calendar next-week --source yandex_caldav
```

Expected:
- Command exits successfully or returns sanitized, actionable error.
- No secret values are printed.
- No non-INBOX mailbox is used.
- `calendar next-week` prints non-empty result when upcoming meetings exist.
- `calendar next-week` timezone label matches `execas config show` timezone value.

## Scenario 3: First full operational check

Goal: validate full integration path used in production.

Commands:
```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas sync hourly --retries 2 --backoff-sec 5
uv run execas calendar next-week --source yandex_caldav
uv run execas review scrum-metrics --no-run-quality
```

Expected:
- `sync hourly` returns `0` (ok) or `2` (degraded with one source available).
- `calendar next-week` confirms imported meeting set for the target week.
- Metrics command writes/prints snapshot for calibration.
- Any degraded/error output remains sanitized (no credentials or token fragments).

## Scenario 4: Degraded mode handling

Trigger: `sync hourly` returns exit code `1` or repeated `2`.

Actions:
1. Confirm environment variables exist (without printing values).
2. Re-run source-specific checks:
   - `uv run execas calendar sync`
   - `uv run execas mail sync --mailbox INBOX`
   - `uv run execas calendar next-week --source yandex_caldav`
3. If one source remains down, continue with available source and document degraded status.
4. Use manual fallback for critical planning continuity.

Fallback commands:
```bash
uv run execas busy add --date YYYY-MM-DD --start HH:MM --end HH:MM --title "Manual busy block"
uv run execas task capture "Email follow-up" --estimate 30 --priority P2 --status NEXT
```

## Scenario 5: Credential rotation

Trigger: password/app-password rotation or auth failure.

Steps:
1. Request updated credentials from user.
2. Start new secure session and re-export env vars.
3. Run Scenario 2 smoke validation.
4. Run Scenario 3 full check.
5. Confirm old credentials are no longer in any shell profile or local files.

## Scenario 6: Acceptance handoff to TL

EA handoff package must include:
- command list executed;
- exit codes and timestamps;
- degraded incidents (if any) and mitigation;
- explicit statement: read-only policy preserved and INBOX-only scope used.

Use artifacts:
- `spec/operations/integration_acceptance_yandex.md`
- TL acceptance ledger in `spec/operations/tl_dispatch_yandex_integration_2026-02-15.md`

## Scenario 7: On-demand sync by user request

Trigger: user asks `синхронизируй сейчас`.

Actions:
1. Execute immediate sync run:
   - `uv run execas sync hourly --retries 2 --backoff-sec 5`
2. Execute post-sync verification:
   - `uv run execas calendar next-week --source yandex_caldav`
3. Return a compact status report:
   - calendar status (`ok/degraded/failed`);
   - mail status (`ok/degraded/failed`);
   - overall hourly sync status (`ok/degraded/failed`);
   - next-week meeting count and week range.

Notes:
- Keep read-only and `INBOX`-only constraints.
- Do not print secrets.
