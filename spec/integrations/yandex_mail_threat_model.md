# Threat Model: Yandex Mail Ingest

**Status:** Draft

**Date:** 2026-02-14

**Related integration:** `spec/integrations/yandex_mail.md`

## 1. Assets

- IMAP credentials / app password
- Email metadata (`Message-ID`, sender, subject, timestamps)
- Local task graph and task-email links
- Sync cursor/state
- CLI logs and error traces

## 2. Trust boundaries

1. User laptop runtime (trusted, local process)
2. Connector boundary (network + parser)
3. Yandex Mail server (external service)
4. Local SQLite storage (`apps/executive-cli/.data/`)
5. Terminal/log sink (potentially shared)

## 3. Threats and mitigations

| Threat | Vector | Likelihood | Impact | Risk | Mitigation |
|---|---|---:|---:|---:|---|
| Credential exposure | env dump, exception traces | Medium | High | High | redact secrets in errors; never log auth params; optional keychain/env-only policy |
| Unauthorized mailbox scope | connector granted write scopes | Low | High | Medium | enforce read-only scopes; assert capabilities at startup |
| PII over-collection | fetching/storing full body by default | Medium | High | High | headers-first ingest only; body disabled by default; retention limits |
| Injection via headers | malformed header used in CLI/SQL | Medium | Medium | Medium | strict parsing/normalization; parameterized SQL; output escaping |
| Correlation leakage | task-email links reveal sensitive graph | Low | Medium | Low | local-only storage; user-controlled export; no telemetry |
| Replay/duplication | repeated fetch causes duplicate rows | High | Low | Medium | canonical external id + UPSERT; unique constraints |

## 4. Security requirements (must-pass)

- [ ] Read-only access confirmed at connector layer
- [ ] Credentials never written to repository or SQLite
- [ ] No raw body/attachment persistence in MVP
- [ ] Logs redact sensitive fields
- [ ] Dedup constraints implemented in schema (ADR-10)
- [ ] Manual fallback available when connector disabled

## 5. Residual risk

Main residual risk is metadata sensitivity (subject/sender). Residual mitigation is user consent, clear retention defaults, and optional purge command in future iteration.
