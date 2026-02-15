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

- Batch A (discovery + architecture lock): **1.5-2.0h**
- Batch B (execution + fixes): **2.5-4.0h**
- Batch C (QA + ops + acceptance): **1.5-2.0h**

**Total target:** **5.5-8.0h** (same-day target, assuming credentials/endpoints are ready).

## Calibration rule (agreed)

Initial estimate is provisional. Next estimates are derived from actual throughput and lead-time observed in the first integration batch using:
- `execas review scrum-metrics`
- acceptance ledger cycle time
- defect escape / rework counts

## Acceptance criteria (business)

- Calendar sync works against user's Yandex CalDAV endpoint without policy violations.
- Mail sync works against user's Yandex IMAP INBOX only.
- Read-only constraints preserved end-to-end.
- Hourly sync runbook and fallback steps are validated.
- Quality gates pass before release acceptance.

## Out of scope

- Any write-back to external calendar/mail.
- Any mailbox scope beyond INBOX.
- Any relaxation of security policy for credentials.
