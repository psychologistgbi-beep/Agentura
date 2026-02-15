---
name: agentura-tl-acceptance-ledger
description: Perform Technical Lead commit acceptance workflow with scope checks, quality-gate evidence, and dispatch ledger updates before push.
---

# Agentura TL Acceptance Ledger

## Purpose

Standardize TL acceptance decisions for incoming commits and keep traceable acceptance ledgers.

## Use this skill when

- TL receives deliverables from role lanes and must accept/reject.
- Push preparation requires explicit evidence and scope traceability.
- Batch report requires accepted/rejected commit rationale.

## Do not use this skill when

- Task is still in active implementation and no acceptance package exists.

## Inputs

- `/Users/gaidabura/Agentura/AGENTS.md`
- `/Users/gaidabura/Agentura/agents/technical_lead/SKILL.md`
- Relevant dispatch file in `/Users/gaidabura/Agentura/spec/operations/`
- Relevant gate reports and task files.

## Workflow

1. Validate commit is within user-approved baseline scope.
2. Validate role-to-scope match and authority boundaries.
3. Validate quality evidence:
   - `uv run pytest -q`
   - coverage gate
   - migration integrity when applicable.
4. Update acceptance ledger row with verdict and evidence.
5. Approve push only for accepted commit range.

## Output

- Updated dispatch ledger file under `/Users/gaidabura/Agentura/spec/operations/`.
- TL acceptance summary listing accepted/rejected commits and reasons.

## Guardrails

- No push of unaccepted commits.
- No force-push.
- No scope expansion without user re-alignment.
