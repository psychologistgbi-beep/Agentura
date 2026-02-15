# TL Plan: Yandex Read-Only Integration (Calendar + Mail)

**Owner:** Technical Lead  
**Date:** 2026-02-15  
**Objective:** integrate Agentura with user's real Yandex Calendar and Yandex Mail in strict read-only mode.

## Confirmed constraints (user-approved)

- Calendar provider: **Yandex CalDAV**.
- Mail provider: **Yandex IMAP**.
- Access scope: **read-only only**.
- Mail scope: **INBOX only**.

## Delivery posture

Current codebase already contains CalDAV/IMAP connectors, sync services, security guardrails, hourly orchestration, and tests.
This batch focuses on **production integration readiness** (configuration, live-path validation, observability, and acceptance), not greenfield implementation.

## Applied changes since baseline lock

Already implemented and available before live credential run:
- EA secure integration scenarios: `spec/operations/ea_yandex_integration_scenarios.md`
- Acceptance checklist artifact: `spec/operations/integration_acceptance_yandex.md`
- Secure helper for EA setup/smoke checks: `scripts/ea-yandex-check`
- Security env naming synchronized with connector runtime (`EXECAS_*` in `SECURITY.md`)
- Next-week import verification command: `uv run execas calendar next-week --source yandex_caldav`

## Baseline scope (`INT-YANDEX-01`)

1. `INT-DISC-01` (System Analyst + Product Owner + TL)
   - Finalize acceptance criteria for business outcome.
   - Produce environment checklist (required env vars, expected values format).

2. `INT-ARCH-01` (Chief Architect)
   - Confirm read-only and INBOX-only compliance against policy.
   - Validate risk controls and fallback behavior.

3. `INT-EXEC-01` (Executive Assistant)
   - Run integration verification flow on real endpoints.
   - Implement minimal fixes if any runtime mismatch appears.

4. `INT-QA-01` (QA/SET)
   - Execute regression + integration checks.
   - Produce release-quality verdict and residual risk notes.

5. `INT-OPS-01` (DevOps/SRE + TL)
   - Validate hourly sync operational setup and runbook completeness.
   - Verify metrics command (`review scrum-metrics`) is included in operations routine.

## Estimation (compressed, capacity-based)

- Batch A (discovery + architecture lock): **done (artifact stage complete)**
- Batch B (execution + fixes): **2.0-3.5h**
- Batch C (QA + ops + acceptance): **1.0-1.5h**

**Remaining target:** **3.0-5.0h** (same-day target, assuming credentials/endpoints are ready).

## Calibration rule (agreed)

Initial estimate is provisional. Next estimates are derived from actual throughput and lead-time observed in the first integration batch using:
- `execas review scrum-metrics`
- acceptance ledger cycle time
- defect escape / rework counts

## Acceptance criteria (business)

- Calendar sync works against user's Yandex CalDAV endpoint without policy violations.
- Mail sync works against user's Yandex IMAP INBOX only.
- Read-only constraints preserved end-to-end.
- Next-week meetings are visible in local SQLite via `calendar next-week`.
- Hourly sync runbook and fallback steps are validated.
- Quality gates pass before release acceptance.

## Out of scope

- Any write-back to external calendar/mail.
- Any mailbox scope beyond INBOX.
- Any relaxation of security policy for credentials.

## Status board

- INT-DISC-01: completed (prep artifacts delivered)
- INT-ARCH-01: completed (architecture review artifact delivered)
- INT-EXEC-01: completed for readiness, pending live credentials run
- INT-QA-01: completed (quality verdict + gates passed)
- INT-OPS-01: completed (runbook/tooling includes next-week verification)
