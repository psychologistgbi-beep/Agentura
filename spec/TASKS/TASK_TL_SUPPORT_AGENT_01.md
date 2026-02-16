# TASK TL-SUPPORT-AGENT-01: Technical Support Agent Flow

**Author:** Executive Assistant  
**Date:** 2026-02-15  
**Scope type:** process/runtime support orchestration

## Goal

Define and implement a TL-owned support-agent workflow that handles incidents when business result is not achieved, reports elimination status, and triggers EA retry.

## Constraints (hard)

- Keep authority boundaries from `AGENTS.md`.
- No plaintext credentials in artifacts.
- No schema/migration/time-model changes in this task.

## In scope

- TL support workflow definition and dispatch protocol.
- Incident report format using `spec/templates/SUPPORT_INCIDENT_REPORT_TEMPLATE.md`.
- Explicit requirement to report:
  - involved agents;
  - observed max parallel lanes.
- Explicit remediation verdict requirement:
  - `root-cause elimination confirmed: YES|NO`;
  - `EA retry authorized now: YES|NO`.
- Handoff rule: EA must retry business-result attempt after support fix.

## Out of scope

- Feature implementation in product code.
- New external integrations.

## Deliverables

- Update TL operational docs/dispatch so support-agent lane can be assigned immediately.
- Ensure incident closure includes formal report by template.
- Ensure unresolved result loops back to rework automatically.

## Acceptance checks

- [ ] TL workflow explicitly includes support-agent incident handling.
- [ ] Report template with mandatory agent/parallel fields is referenced.
- [ ] Report template requires explicit remediation verdict for EA retry authorization.
- [ ] EA retry-after-fix rule is documented.
- [ ] Rework loop is documented when retry still fails.

## Suggested verification commands

```bash
cd /Users/gaidabura/Agentura
rg -n "support|incident|parallel|Agents involved|EA retry" agents/technical_lead/SKILL.md agents/executive_assistant/SKILL.md spec/templates/SUPPORT_INCIDENT_REPORT_TEMPLATE.md spec/TASKS/TASK_TL_SUPPORT_AGENT_01.md
```
