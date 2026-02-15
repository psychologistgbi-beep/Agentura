---
name: agentura-qa-timezone-redaction
description: Verify timezone correctness for week/date outputs and confirm secret redaction in integration error/degraded paths.
---

# Agentura QA Timezone and Redaction Check

## Purpose

Provide QA evidence that time-window outputs are timezone-correct and connector failures do not leak secrets.

## Use this skill when

- Integration-related CLI output includes week/date windows.
- Changes affect error handling, degraded-mode messaging, or connectors.
- Release verdict requires explicit timezone and redaction checks.

## Do not use this skill when

- Change scope is fully unrelated to time outputs or integration error paths.

## Inputs

- `/Users/gaidabura/Agentura/AGENTS.md`
- `/Users/gaidabura/Agentura/agents/qa_set/SKILL.md`
- `/Users/gaidabura/Agentura/spec/operations/integration_acceptance_yandex.md`
- `/Users/gaidabura/Agentura/spec/operations/qa_verdict_yandex_integration.md`

## Workflow

1. Run baseline regression gate:
   - `cd /Users/gaidabura/Agentura/apps/executive-cli && uv run pytest -q`
2. Validate timezone output consistency:
   - `uv run execas config show`
   - `uv run execas calendar next-week --source yandex_caldav`
3. Validate redaction behavior on failure/degraded path:
   - `uv run execas sync hourly --retries 0 --backoff-sec 1`
   - confirm no credential/token fragments in output.
4. Record pass/fail evidence and residual risks.

## Output

- Updated quality verdict in `/Users/gaidabura/Agentura/spec/operations/qa_verdict_yandex_integration.md`.
- Evidence rows in integration acceptance checklist.

## Guardrails

- Never log or copy any secret value.
- Keep findings reproducible with commands and observed outputs.
