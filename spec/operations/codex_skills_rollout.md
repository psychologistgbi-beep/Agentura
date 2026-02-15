# Codex Skills Rollout Plan (Agentura)

**Owner:** Technical Lead  
**Date:** 2026-02-15  
**Reference:** [OpenAI Codex Skills](https://developers.openai.com/codex/skills/)

## Objective

Adopt repository-scoped Codex skills to increase agent execution quality while preserving Agentura role governance.

## Catalog baseline

Skills root:
- `/Users/gaidabura/Agentura/.agents/skills`

Initial wave:
- `agentura-sa-integration-dor`
- `agentura-ea-yandex-live-run`
- `agentura-qa-timezone-redaction`
- `agentura-sre-hourly-sanity-alert`
- `agentura-tl-acceptance-ledger`
- `agentura-sm-lane-sla-wip`

## Rollout phases

### Phase 1: Explicit pilot (recommended)

- Use explicit skill invocation (`$skill-name`) in production tasks.
- Keep sensitive skills non-implicit:
  - `agentura-ea-yandex-live-run`
  - `agentura-sre-hourly-sanity-alert`
- Validate trigger precision and output quality via sprint reports.

### Phase 2: Selective implicit invocation

- Keep implicit only for low-risk workflow/checklist skills:
  - `agentura-sa-integration-dor`
  - `agentura-qa-timezone-redaction`
  - `agentura-tl-acceptance-ledger`
  - `agentura-sm-lane-sla-wip`
- Review false positives weekly and tighten descriptions if needed.

### Phase 3: Scale and hardening

- Extend catalog only after two clean sprint cycles.
- Add task-specific scripts/assets only where deterministic automation is needed.
- Keep one skill per clear outcome to avoid overlap.

## Config governance (`~/.codex/config.toml`)

Per Codex documentation, skill enablement is controlled by `[[skills.config]]`.
Recommended starter profile:

```toml
[[skills.config]]
name = "agentura-sa-integration-dor"
enabled = true

[[skills.config]]
name = "agentura-ea-yandex-live-run"
enabled = true

[[skills.config]]
name = "agentura-qa-timezone-redaction"
enabled = true

[[skills.config]]
name = "agentura-sre-hourly-sanity-alert"
enabled = true

[[skills.config]]
name = "agentura-tl-acceptance-ledger"
enabled = true

[[skills.config]]
name = "agentura-sm-lane-sla-wip"
enabled = true
```

Note:
- Keep implicit policy in each skill metadata (`agents/openai.yaml`).
- Re-run role preflight after config changes.

## Success metrics

Measure per sprint:
- Skill invocation precision (correct trigger ratio).
- Rework rate on role handoffs.
- Lead time from ready to accepted.
- Quality gate pass rate on first attempt.
- Degraded-incident response time for integration lanes.

## Risks and controls

1. Risk: implicit over-triggering.
Control: tighten `description` scope, disable implicit where needed.

2. Risk: role-policy bypass via generic skill text.
Control: keep role authority in `AGENTS.md`; skills are additive and scoped.

3. Risk: credentials exposure in live flows.
Control: keep credentialed skills non-implicit and interactive-only.
