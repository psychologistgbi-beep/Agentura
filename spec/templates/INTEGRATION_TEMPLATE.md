# Integration Plan: <Service Name>

**Status:** Draft | Approved | Implemented | Deprecated

**Date:** YYYY-MM-DD

**Related ADR:** ADR-NN

---

## 1. Overview

What system are we integrating with? Why?

- **Service:** (e.g., Yandex Calendar via CalDAV, Yandex Mail via IMAP)
- **Protocol:** (e.g., CalDAV/WebDAV, IMAP, REST API, MCP)
- **Direction:** Read-only | Read-write | Bidirectional
- **Trigger:** Manual CLI command | Scheduled | Event-driven

## 2. Data flow

```
[External Service] --(protocol)--> [Connector] --(ORM)--> [SQLite]
```

### Inbound (external -> local)
- What data is fetched?
- How is it mapped to local models?
- Conflict resolution strategy (overwrite / merge / skip)?

### Outbound (local -> external)
- What data is pushed? (MVP: typically none)
- Idempotency guarantees?

## 3. Authentication & credentials

- **Method:** (OAuth2, App Password, API Key, etc.)
- **Storage:** Environment variable names (never in repo)
  - `EXAMPLE_USERNAME`
  - `EXAMPLE_APP_PASSWORD`
- **Rotation:** How are credentials rotated?
- **Fallback:** What happens if credentials are missing or expired?

## 4. MCP connector design (if applicable)

- **Tool name:** `example_fetch_events`
- **Scopes requested:** (minimum necessary)
- **Input schema:**
  ```json
  {
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD"
  }
  ```
- **Output schema:**
  ```json
  [
    {
      "start_dt": "ISO-8601",
      "end_dt": "ISO-8601",
      "title": "string"
    }
  ]
  ```
- **Error handling:** What errors can the MCP tool return? How does the CLI handle each?

## 5. Failure modes

| Failure | Detection | Impact | Mitigation |
|---|---|---|---|
| Service unreachable | Connection timeout | No sync | Print clear error; suggest manual fallback |
| Invalid credentials | 401/403 response | No sync | Print error with reconfiguration instructions |
| Partial data | Incomplete response | Data gap | Log warning; import what was received |
| Rate limiting | 429 response | Delayed sync | Retry with backoff; log warning |

## 6. Manual fallback

When the integration is unavailable, users can:
1. ...
2. ...

## 7. Testing strategy

- **Unit tests:** Mock the connector protocol; verify data mapping
- **Integration test (manual):** Real credentials against test account
- **Verification command:**
  ```bash
  uv run execas <command> sync
  ```

## 8. Security review checklist

- [ ] Credentials stored in env vars only
- [ ] No credentials in logs or error messages
- [ ] Minimum scopes / permissions requested
- [ ] TLS enforced for all connections
- [ ] PII handled per user consent
- [ ] Connector can be disabled without affecting core CLI
