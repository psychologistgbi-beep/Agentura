# Architecture Review: SPEED-COST-01

**Role:** Chief Architect  
**Date:** 2026-02-16  
**Scope:** speed and service-load optimization for local sync runtime

## Context

User requested higher project speed and lower avoidable service load, with emphasis on keeping algorithmic paths for calendar/mail sync and avoiding unnecessary agentic/LLM overhead.

## Candidate verdict matrix

| Candidate | Verdict | Rationale | Approval boundary |
|---|---|---|---|
| Parallel hourly execution of calendar/mail sync | approved now | Preserves deterministic per-source retry semantics while reducing wall time. No schema/time-model changes. | within existing architecture authority |
| CalDAV sync-token incremental REPORT priority | defer | Requires protocol-path extension and additional failure-mode coverage; should be dispatched as dedicated integration change set. | approval-gated; architecture review required before implementation |
| Bounded CalDAV sync window controls | approved now | Runtime tuning via env variables reduces payload/parse cost without changing data model. | within existing architecture authority |
| Sync-service DB access optimization (reduce full-table scans) | approved now | Local query shaping only; no behavioral contract change expected. | within existing architecture authority |
| Hourly runtime telemetry (elapsed seconds/mode) | approved now | Improves ops visibility, no sensitive data expansion. | within existing architecture authority |

## Security and policy impact

- Read-only external boundaries remain unchanged (CalDAV/IMAP pull-only).
- Secrets handling remains unchanged (env/Keychain); no new secret paths.
- No schema, migration, or timezone model changes.

## Risks

1. Parallel mode increases concurrent external requests per run. Mitigation: keep `--sequential` fallback and bounded retries.
2. Window tuning may omit long-horizon events if set too low. Mitigation: conservative defaults retained (`30/365`) and explicit operator override.
3. Deferred sync-token work can leave some avoidable full snapshots. Mitigation: track as next optimization lane.

## ADR status

No ADR amendment required for approved-now changes in this batch.

