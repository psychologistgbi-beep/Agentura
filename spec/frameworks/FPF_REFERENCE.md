# FPF Reference Baseline for System Analyst

## Purpose
This document defines how Agentura System Analyst uses FPF as the primary planning framework for requirements and task-plan preparation.

Canonical upstream reference: https://github.com/ailev/FPF

## Policy status
- FPF is mandatory for System Analyst planning sessions.
- The framework is treated as a context artifact (RAG/reference file), not as a static long prompt.
- If this file is missing, System Analyst planning is `NOT READY TO EXECUTE`.

## Required FPF artifacts in every SA plan package
1. Problem frame:
   - target business outcome;
   - scope boundaries (in-scope/out-of-scope);
   - constraints and non-functional limits.
2. Assumptions and uncertainty register:
   - explicit assumptions;
   - unknowns that can invalidate the plan;
   - proposed default decisions for unresolved items.
3. Options and decision rationale:
   - at least one alternative considered;
   - selected option with tradeoff rationale.
4. Evidence links:
   - references to spec/backlog/runtime policy files;
   - verification commands or acceptance checks tied to scope.

## Minimum handoff template (SA -> delivery)
```text
FPF PLAN PACKAGE
- Business outcome:
- Problem frame:
- Scope boundaries:
- Assumptions and unknowns:
- Options considered and chosen option:
- Acceptance criteria:
- Verification commands:
- Traceability links (objective -> story -> task -> verification):
```
