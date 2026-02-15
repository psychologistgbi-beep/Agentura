# Security Baseline for Agentura

This document defines mandatory operational safeguards for local development and CLI usage.

## 1. Secrets handling

- Store secrets only in environment variables or local secure storage (OS keychain when applicable).
- Never store credentials in source code, fixtures, migration files, or markdown examples.
- Do not persist API keys, app passwords, OAuth tokens, or session cookies in SQLite.
- Use explicit variable names and keep them outside git-tracked files.

Recommended env naming:

- `EXECAS_CALDAV_URL`
- `EXECAS_CALDAV_USERNAME`
- `EXECAS_CALDAV_PASSWORD`
- `EXECAS_IMAP_HOST`
- `EXECAS_IMAP_PORT`
- `EXECAS_IMAP_USERNAME`
- `EXECAS_IMAP_PASSWORD`

Note: these names match the active connector implementation in `apps/executive-cli/src/executive_cli/connectors/`.

## 2. Git hygiene

The repository must ignore local secrets and local data artifacts.

Required ignore coverage:

- `.env`
- `.env.*`
- `*.pem`
- `*.key`
- `credentials.*`
- local SQLite artifacts (`*.sqlite`, `*.sqlite3`, and app-local data directories)

## 3. Logging policy

Forbidden in logs:

- credentials, tokens, auth headers
- full email bodies and attachment contents
- raw connector payloads containing sensitive personal data

Allowed in logs:

- redacted error categories
- sync counters and timing
- opaque identifiers when needed for debugging

Redaction rule: replace sensitive values with `***REDACTED***` before rendering any error.

## 4. Least privilege

- Calendar connector scope: read-only events.
- Mail connector scope: read-only inbox metadata.
- No send, delete, move, or write-back permissions in MVP.

## 5. Local storage and retention

- SQLite path: `apps/executive-cli/.data/`.
- Do not store full external content unless explicitly approved by product/security policy.
- Prefer metadata-only ingest for mail.

## 6. Verification checklist

Run before merge:

1. `rg -n "password|token|secret|apikey|authorization" -S` and inspect results for false positives.
2. Confirm `.gitignore` includes required secret patterns.
3. Run tests and coverage gates from `AGENTS.md`.
4. Confirm no sample credentials were introduced in docs.

## 7. Incident response (local)

If a secret is accidentally committed:

1. Revoke/rotate the secret immediately.
2. Remove secret from tracked files and history as needed.
3. Document impact and remediation in commit/PR notes.
4. Re-run verification checklist.
