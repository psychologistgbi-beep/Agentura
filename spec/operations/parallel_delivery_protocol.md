# Parallel Delivery Protocol

**Owner:** Technical Lead  
**Effective date:** 2026-02-15  
**Applies to:** all roles in `AGENTS.md`

## 1. Purpose

Define safe parallel execution rules so the team can run multiple task lanes at once without violating authority boundaries, quality gates, or release integrity.

## 2. Parallelism model

The team may run multiple concurrent lanes when lane dependencies and file ownership allow it.

Lane types:
- **A: Requirements/Architecture lane** (PO, SA, CA)
- **B: Implementation lane** (EA)
- **C: Quality lane** (QA/SET)
- **D: Operations lane** (DevOps/SRE)
- **E: Orchestration lane** (TL, SM)

Maximum recommended active lanes per sprint batch: **4**.

## 3. Session and terminal rules

- One active lane should map to one dedicated terminal/session context.
- Multiple terminal sessions are allowed and expected for independent lanes.
- Every lane session must start with a valid preflight stamp from `spec/templates/PREFLIGHT_STAMP_TEMPLATE.md`.
- Session role must match lane owner role.

## 4. Lane readiness rules (parallel entry gate)

A lane can start only if all are true:
- task id is assigned and in approved baseline;
- lane owner role is explicit;
- dependencies are marked (`none`, `soft`, `hard`);
- target files are listed;
- acceptance checks are listed.

## 5. File overlap and lock rules

- Parallel execution is allowed for disjoint file sets.
- If two lanes need the same high-risk file, TL assigns a **file lock owner**.
- High-risk files include:
  - `AGENTS.md`
  - `spec/AGENT_RUNTIME.md`
  - `spec/AGENT_RUNTIME_ADAPTERS.md`
  - `apps/executive-cli/src/executive_cli/models.py`
  - `apps/executive-cli/src/executive_cli/cli.py`
- Non-owner lane touching a locked file is blocked until lock release or TL override.

## 6. Dependency scheduling rules

- Hard dependency: downstream lane waits for accepted commit from upstream lane.
- Soft dependency: downstream may proceed with assumptions tagged `[ASSUMPTION]` and must reconcile before merge.
- No dependency: lanes run in parallel with independent acceptance.

## 7. Integration and acceptance rules

- Each lane must produce its own gate report (7 sections).
- TL maintains acceptance ledger with verdict per lane commit.
- Accepted commits integrate in this order unless baseline explicitly overrides:
  1. Architecture/requirements lane
  2. Implementation lane
  3. Quality lane
  4. Operations lane
- Push is allowed only for commits with accepted verdicts and passed quality gates.

## 8. Conflict and rollback rules

- Merge conflict on shared files triggers TL conflict resolution.
- TL can reject one lane commit and keep the other to minimize blast radius.
- Rejected lane must rebase on latest accepted state before resubmission.
- Rollback uses atomic commit revert; never revert unrelated accepted scope.

## 9. Monitoring and cadence

Minimum sync cadence for active parallel batch:
- lane heartbeat every 2 hours (`status`, `blockers`, `next step`);
- one daily synchronization checkpoint across all lane owners;
- explicit blocked-state escalation to TL and SM.

## 10. Parallel anti-patterns

- Starting implementation lanes before requirement acceptance criteria exist.
- Running two lanes on same locked file without TL lock owner.
- Accepting commits without lane-level gate reports.
- Pushing mixed accepted/rejected commit ranges.
- Using parallelism to bypass architecture or security approvals.
