# TASK TL-POLICY-REFLECTION-01: Reflect Updated Secret/Runtime Policies

**Author:** Technical Lead  
**Date:** 2026-02-16  
**Scope type:** process/runtime policy alignment

## Goal

Synchronize project policy artifacts after the security/runtime policy update:
- credentials may be sourced from environment variables and approved OS secret store (macOS Keychain) for local runtime;
- EA runtime must support on-demand sync with minimal operator friction while preserving least privilege and redaction rules.

## Why now

Recent integration fixes introduced Keychain-based secret lookup and force-full resync workflow. Several docs/templates still contain legacy wording (`env vars only`) and need alignment to avoid policy drift.

## In scope

- Update policy/runtime docs and templates that still describe credentials as env-only.
- Update role skills and integration runbooks to include Keychain-safe path and fallback behavior.
- Ensure wording remains explicit about:
  - no secrets in repository;
  - no secrets in SQLite;
  - read-only CalDAV/IMAP boundaries and IMAP `INBOX` scope.
- Add verification evidence for policy consistency.

## Out of scope

- Schema/migration changes.
- Time model changes.
- Integration connector behavior changes beyond already implemented functionality.

## Required artifacts

- `spec/AGENT_RUNTIME.md`
- `spec/AGENT_RUNTIME_ADAPTERS.md`
- `spec/templates/INTEGRATION_TEMPLATE.md`
- `spec/templates/THREAT_MODEL_TEMPLATE.md`
- `agents/chief_architect/SKILL.md`
- `agents/executive_assistant/SKILL.md` (consistency pass)
- `spec/operations/hourly_sync.md`
- TL dispatch/ledger update in `spec/operations/tl_dispatch_policy_reflection_2026-02-16.md`

## Acceptance checks

- [ ] No authoritative project doc says "credentials in env vars only" unless explicitly scoped to a special case.
- [ ] Security wording remains strict: no plaintext secrets in repo/SQLite/log outputs.
- [ ] Read-only CalDAV + IMAP INBOX constraints remain unchanged.
- [ ] Runtime docs and templates are mutually consistent.
- [ ] Verification evidence includes grep report + quality gates status.

## Verification commands

```bash
cd /Users/gaidabura/Agentura
rg -n "env vars only|environment variables only|credentials.*only" AGENTS.md agents spec scripts -S
cd apps/executive-cli && uv run pytest -q
cd apps/executive-cli && uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
```

## Rollback notes

If policy alignment introduces ambiguity or conflicting guidance, revert only policy-wording edits, keep working implementation unchanged, and re-dispatch with narrowed wording scope.
