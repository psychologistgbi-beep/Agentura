# Agentura Skills Catalog

This directory contains repository-scoped Codex skills for Agentura.

Location is aligned with Codex skill discovery:
- `/Users/gaidabura/Agentura/.agents/skills`

## Skills in this catalog

- `agentura-sa-integration-dor`
- `agentura-ea-yandex-live-run`
- `agentura-qa-timezone-redaction`
- `agentura-sre-hourly-sanity-alert`
- `agentura-tl-acceptance-ledger`
- `agentura-sm-lane-sla-wip`

## Invocation model

- Explicit invocation is preferred for production use (`$skill-name`).
- Some skills allow implicit invocation for low-risk planning/checklist tasks.
- Credentialed or operationally sensitive skills disable implicit invocation via `agents/openai.yaml`.

## Governance

- Global role authority remains in `/Users/gaidabura/Agentura/AGENTS.md`.
- Role profiles remain in `/Users/gaidabura/Agentura/agents/<role>/SKILL.md`.
- These skills provide task-scoped workflows and do not override authority boundaries.
