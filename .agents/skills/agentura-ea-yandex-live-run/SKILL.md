---
name: agentura-ea-yandex-live-run
description: Execute the secure EA live integration flow for Yandex CalDAV and IMAP (INBOX only), then verify imported meetings for next week from local SQLite.
---

# Agentura EA Yandex Live Run

## Purpose

Run a production-style, read-only Yandex integration session for Executive Assistant operations.

## Use this skill when

- User is ready to provide Yandex credentials in a secure interactive session.
- The goal is to validate calendar/mail sync and next-week meeting import.
- Integration acceptance evidence is needed for Technical Lead.

## Do not use this skill when

- Credentials are unavailable.
- Task is only documentation or non-live development.

## Inputs

- `/Users/gaidabura/Agentura/AGENTS.md`
- `/Users/gaidabura/Agentura/agents/executive_assistant/SKILL.md`
- `/Users/gaidabura/Agentura/spec/operations/ea_yandex_integration_scenarios.md`
- `/Users/gaidabura/Agentura/spec/operations/integration_acceptance_yandex.md`
- `/Users/gaidabura/Agentura/scripts/ea-yandex-check`

## Workflow

1. Confirm scope constraints: read-only connectors and IMAP `INBOX` only.
2. Start secure interactive flow:
   - `cd /Users/gaidabura/Agentura`
   - `scripts/ea-yandex-check`
3. Record command outcomes and exit codes.
4. Verify next-week meetings output from:
   - `uv run execas calendar next-week --source yandex_caldav`
5. Fill acceptance evidence table and prepare handoff for TL.

## Output

- Completed evidence lines in `/Users/gaidabura/Agentura/spec/operations/integration_acceptance_yandex.md`.
- Short handoff summary for TL: results, incidents, mitigations.

## Guardrails

- Do not request credentials in plain text chat.
- Do not persist credentials to repo files.
- Do not use non-INBOX mailbox scope.
