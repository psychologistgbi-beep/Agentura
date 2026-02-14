# Threat Model: <Feature / Component>

**Date:** YYYY-MM-DD

**Author:** Chief Architect

**Scope:** What system, feature, or integration is being modeled.

---

## 1. Assets

What are we protecting?

| Asset | Description | Sensitivity |
|---|---|---|
| SQLite database | Task data, schedule, people, decisions | High (personal productivity data) |
| Credentials | API keys, app passwords for integrations | Critical |
| User schedule | Day plans, busy blocks, time allocation | Medium |
| ... | ... | ... |

## 2. Trust boundaries

```
[User] <--> [CLI process] <--> [SQLite file]
                |
                v
         [MCP connector] <--> [External service]
```

- **Boundary 1:** CLI process <-> SQLite (local filesystem permissions)
- **Boundary 2:** CLI process <-> MCP connector (IPC)
- **Boundary 3:** MCP connector <-> External service (network, TLS)

## 3. Threat enumeration

### T1: Credential exposure
- **Vector:** Credentials committed to repo, logged in error output, or stored in DB
- **Likelihood:** Medium (common developer mistake)
- **Impact:** Critical (account compromise)
- **Mitigation:**
  - Credentials only in env vars (Security Policy in AGENTS.md)
  - `.gitignore` includes `.env`, `*.pem`, `*.key`, `credentials.*`
  - Error messages never include credential values
  - Pre-commit hook (future) to scan for secrets
- **Status:** Mitigated / Accepted / Open

### T2: SQL injection via CLI input
- **Vector:** Malicious input in CLI arguments passed to raw SQL
- **Likelihood:** Low (SQLModel/SQLAlchemy use parameterized queries)
- **Impact:** High (data corruption or extraction)
- **Mitigation:**
  - All queries use SQLModel ORM (parameterized by default)
  - FTS queries use `:q` parameter binding, not string formatting
  - No raw SQL in application code (migrations are admin-only)
- **Status:** Mitigated

### T3: Unauthorized data access
- **Vector:** Another local user or process reads the SQLite file
- **Likelihood:** Low (single-user CLI)
- **Impact:** Medium (schedule and personal data exposure)
- **Mitigation:**
  - SQLite file in `.data/` with standard filesystem permissions
  - No network listener (pure CLI)
  - Future: optional encryption at rest
- **Status:** Accepted (single-user context)

### T4: MCP connector over-privilege
- **Vector:** Connector requests write access when only read is needed
- **Likelihood:** Medium (easy to over-scope during development)
- **Impact:** Medium (unintended mutations on external services)
- **Mitigation:**
  - Integration template requires explicit scope documentation
  - Chief Architect review required for all integration PRs
  - Connector Protocol interfaces enforce read-only by default
- **Status:** Mitigated

### T5: <Add more threats specific to the feature>
- **Vector:** ...
- **Likelihood:** ...
- **Impact:** ...
- **Mitigation:** ...
- **Status:** ...

## 4. Risk matrix

| Threat | Likelihood | Impact | Risk (L x I) | Status |
|---|---|---|---|---|
| T1: Credential exposure | Medium | Critical | High | Mitigated |
| T2: SQL injection | Low | High | Medium | Mitigated |
| T3: Unauthorized access | Low | Medium | Low | Accepted |
| T4: MCP over-privilege | Medium | Medium | Medium | Mitigated |

## 5. Residual risks

Risks that are accepted and not further mitigated:
- Single-user local file access (T3): acceptable for MVP CLI tool
- ...

## 6. Review schedule

- This threat model should be reviewed when:
  - A new integration is added
  - The deployment model changes (e.g., CLI -> server)
  - A security incident occurs
  - Annually as a baseline
