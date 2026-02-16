# TL Dispatch: SUPPORT-AGENT-01

**Owner:** Technical Lead  
**Date:** 2026-02-15  
**Baseline source:** `spec/TASKS/TASK_TL_SUPPORT_AGENT_01.md`

## Scope lock

- Incident support orchestration only.
- No product feature changes.
- No schema/ADR/time-model changes.

## Dispatch brief

### TL-SUPPORT-AGENT-01 (Technical Lead)

Goal:
- Stand up a repeatable support-agent execution lane for incidents where business result is not reached.
- Enforce incident report form and EA retry loop.

Required artifacts:
- `spec/TASKS/TASK_TL_SUPPORT_AGENT_01.md`
- `spec/templates/SUPPORT_INCIDENT_REPORT_TEMPLATE.md`
- Updated TL/EA workflow references:
  - `agents/technical_lead/SKILL.md`
  - `agents/executive_assistant/SKILL.md`

Acceptance:
- Incident handling includes mandatory report with:
  - involved agents;
  - configured and observed max parallel lanes.
- EA retry-after-fix is mandatory.
- If retry still fails, incident status must return to rework.

## Support lane activation gate

Before support execution starts, TL records:

1. Incident ID and blocked business result statement.
2. Lane owner role and backup reviewer role.
3. Dependency type and file scope.
4. SLA/checkpoint timestamp for next update.
5. Initial evidence artifact link (escalation, logs, command output).

## Incident handoff protocol (mandatory)

1. EA opens incident -> assigns TL.
2. TL creates support lane/agent assignment in this dispatch.
3. TL returns support incident report using `spec/templates/SUPPORT_INCIDENT_REPORT_TEMPLATE.md`:
   - section `5) Agents involved (mandatory)`;
   - section `6) Parallel execution metrics (mandatory)`;
   - section `9) Remediation verdict (mandatory)` with explicit `root-cause elimination confirmed` and `EA retry authorized now`.
4. EA retries business result using retry instructions from report section `8) EA retry instruction`.
5. EA retry is allowed only if section `9` verdict is `YES/YES`.
6. If retry succeeds -> incident state is `resolved` or `partially_resolved`.
7. If retry fails -> incident state is `rework_required`, EA attaches updated evidence, TL reopens support lane.

## Dispatch execution ledger (2026-02-15)

| Item | Owner | Verdict | Evidence |
|---|---|---|---|
| TL support lane workflow activation | Technical Lead | implemented | incident handling protocol and activation gate defined in this dispatch |
| Mandatory report template enforcement | Technical Lead | implemented | `spec/templates/SUPPORT_INCIDENT_REPORT_TEMPLATE.md` referenced in protocol step 3 |
| EA retry/rework loop enforcement | Technical Lead + Executive Assistant | implemented | protocol steps 4-6 + EA/TL role skill updates |

## Implementation status

- Status: `implemented`
- Date: `2026-02-15`
- Scope note: process/runtime support orchestration only; no product/schema/ADR/time-model changes.
