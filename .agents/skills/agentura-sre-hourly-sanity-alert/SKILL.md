---
name: agentura-sre-hourly-sanity-alert
description: Harden recurring sync operations with weekday sanity checks and alerting rules for empty critical result sets.
---

# Agentura SRE Hourly Sanity Alert

## Purpose

Ensure scheduled sync operations are observable and raise actionable alerts when data quality degrades.

## Use this skill when

- Defining or updating recurring sync runbooks.
- Preparing release readiness for scheduler-driven integrations.
- Validating degraded-mode recovery and alert behavior.

## Do not use this skill when

- Task is pure feature coding without ops impact.

## Inputs

- `/Users/gaidabura/Agentura/AGENTS.md`
- `/Users/gaidabura/Agentura/agents/devops_sre/SKILL.md`
- `/Users/gaidabura/Agentura/spec/operations/hourly_sync.md`

## Workflow

1. Verify runbook has sync command, exit-code semantics, and degraded-mode actions.
2. Ensure post-sync sanity check exists:
   - `uv run execas calendar next-week --source yandex_caldav`
3. Ensure weekday alert rule is documented:
   - alert when status is `ok` but next-week result is empty for 2 consecutive runs.
4. Ensure suppression policy exists for maintenance or declared degraded incidents.
5. Record operational readiness verdict and residual risk.

## Output

- Updated runbook section in `/Users/gaidabura/Agentura/spec/operations/hourly_sync.md`.
- TL-facing operational verdict with monitoring notes.

## Guardrails

- Do not weaken security or redaction policies.
- Do not request/store credentials.
