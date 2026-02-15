---
name: agentura-sm-lane-sla-wip
description: Enforce Scrum lane-process controls: blocked-lane escalation SLA and concurrent lane WIP limits in parallel delivery batches.
---

# Agentura Scrum Lane SLA and WIP

## Purpose

Keep parallel delivery flow predictable by enforcing blocker escalation and lane WIP policy.

## Use this skill when

- Sprint batch uses parallel lanes.
- Scrum Master is running flow health checks.
- TL requests lane health and blocker status report.

## Do not use this skill when

- Work is single-lane and no process intervention is required.

## Inputs

- `/Users/gaidabura/Agentura/AGENTS.md`
- `/Users/gaidabura/Agentura/agents/scrum_master/SKILL.md`
- `/Users/gaidabura/Agentura/spec/operations/parallel_delivery_protocol.md`
- `/Users/gaidabura/Agentura/spec/templates/PARALLEL_WORKBOARD_TEMPLATE.md`

## Workflow

1. Map active lanes and owners from current batch plan.
2. Check active lane count against WIP limit (`<= 4`) and document exceptions.
3. Identify blocked lanes and start/verify blocker timers.
4. Escalate any unresolved blocker older than 2 hours to TL.
5. Produce flow-health summary and next corrective actions.

## Output

- Updated lane status snapshot using workboard template.
- Scrum process note with escalations and WIP compliance verdict.

## Guardrails

- Do not accept/reject commits (TL authority).
- Do not reprioritize backlog without PO.
