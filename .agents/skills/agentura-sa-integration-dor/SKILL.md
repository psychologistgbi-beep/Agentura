---
name: agentura-sa-integration-dor
description: Create a complete integration Definition of Ready package before implementation. Use when a task introduces or changes an external integration and requirements must be locked.
---

# Agentura SA Integration DoR

## Purpose

Produce a full integration readiness package that removes ambiguity before implementation starts.

## Use this skill when

- A task involves CalDAV, IMAP, API, or MCP integration design/changes.
- Scope, endpoint, access policy, and acceptance commands must be formalized.
- Technical Lead requests a pre-implementation requirements package.

## Do not use this skill when

- Work is pure implementation with an already approved integration DoR.
- The task is unrelated to external integrations.

## Inputs

- `/Users/gaidabura/Agentura/AGENTS.md`
- `/Users/gaidabura/Agentura/agents/system_analyst/SKILL.md`
- `/Users/gaidabura/Agentura/spec/templates/INTEGRATION_DOR_TEMPLATE.md`
- Relevant task file in `/Users/gaidabura/Agentura/spec/TASKS/`

## Workflow

1. Confirm business objective and in-scope/out-of-scope boundaries.
2. Document provider, protocol, endpoint, and environment.
3. Lock approved access scope and explicitly forbidden actions.
4. Document security constraints, including credential channel and log redaction requirements.
5. Define acceptance commands and expected evidence artifacts.
6. Record dependencies, assumptions, and handoff owners.

## Output

- Create or update a DoR artifact in `/Users/gaidabura/Agentura/spec/operations/`:
  - `dor_<integration_or_task>_<YYYY-MM-DD>.md`
- Provide traceability links to related task and acceptance checklist.

## Guardrails

- Never request or store credentials in plaintext.
- Never redefine role authority from `AGENTS.md`.
- Mark unresolved requirements as `[TBD]` with a concrete default proposal.
