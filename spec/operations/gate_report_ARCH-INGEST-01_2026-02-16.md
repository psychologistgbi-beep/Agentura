# Gate Report: ARCH-INGEST-01

## 1) Role confirmation

- Acting roles: Chief Architect + System Analyst (combined session).
- Authority basis: `AGENTS.md` section 2 (lines 63–73): ADR (new) requires Chief Architect approval (line 67); integration design is CA-owned (line 70); documentation is self-approved (line 73).
- Task type: Architecture design (docs only, no code/migrations).

## 2) Decisions

1. Adopt four-stage ingestion pipeline: Extract (LLM) → Classify (LLM+heuristic) → Deduplicate (deterministic) → Route (deterministic, confidence-based).
2. Three input channels: C1 meeting protocols, C2 assistant dialogues, C3 incoming email. Unified `IngestSource` protocol for extensibility.
3. Conservative auto-create threshold (0.8); lower-confidence candidates go to human review queue (`task_drafts` table).
4. Email channel (C3) reuses ADR-10 schema (`emails` + `task_email_links`). Only subject + sender sent to LLM — no body (ADR-10 line 236 preserved).
5. LLM isolated in `extractor.py` only; all other pipeline stages deterministic.
6. EA remains single writer (ADR-09); pipeline calls same `task_service.create_task()` code path as `task capture`.
7. Three new tables (`ingest_documents`, `task_drafts`, `ingest_log`). Zero changes to existing tables.
8. ADR-11 authored and added to `spec/ARCH_DECISIONS.md`.

## 3) Artifacts

- `spec/TASKS/TASK_INGEST_PIPELINE_DESIGN.md` — full pipeline design (10 sections, ~350 lines)
- `spec/ARCH_DECISIONS.md` — ADR-11 added (Task Ingestion Pipeline)
- `spec/EXECUTION_PLAN.md` — Phase 7 (I1–I6) with dependency graph and verify commands

## 4) Traceability

- ADR-01 (datetime storage): `spec/ARCH_DECISIONS.md:1–18` — all ingest timestamps via `dt_to_db()`
- ADR-06 (deterministic planning): `spec/ARCH_DECISIONS.md:104–127` — ingestion explicitly non-deterministic, `plan day` unaffected
- ADR-09 (single writer): `spec/ARCH_DECISIONS.md:183–196` — pipeline calls EA's task service
- ADR-10 (sync schema): `spec/ARCH_DECISIONS.md:200–243` — `emails`, `task_email_links` reused for C3
- ADR-10 privacy: `spec/ARCH_DECISIONS.md:236` — no body stored or sent to LLM
- `Task` model: `apps/executive-cli/src/executive_cli/models.py:96–129` — fields mirrored in `task_drafts`
- `Email` model: `apps/executive-cli/src/executive_cli/models.py:202–217` — C3 reads from this table
- `TaskEmailLink` model: `apps/executive-cli/src/executive_cli/models.py:220–230` — auto-created for C3 origin links
- `task capture --from-email`: `spec/TASKS/TASK_R2_R4_SYNC_SECURITY_PLAN.md:118–126`
- AGENTS.md authority table: lines 63–73

## 5) Implementation handoff

Verification commands (docs-only batch — quality gates for existing code):

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run pytest -q
uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80
rm -f .data/execas.sqlite && uv run execas init
```

Observed outcomes:
- full suite: 102 passed
- coverage: 88.36%
- migration integrity: pass

Participation and parallelism metrics:
- configured participating roles: 7
- observed active role sessions: 2 (Chief Architect + System Analyst, combined)
- configured max parallel lanes: 5
- observed max parallel lanes: 1

Next steps for EA implementation:
- R1 (ADR-10 schema) must be merged first — ingestion migration extends the chain.
- R3 (mail sync) must be merged for C3 (email channel) to work.
- LLM API key must be available in `LLM_API_KEY` env var.
- Prompt templates (I2) require Chief Architect review before merge.

## 6) Risks / open questions

1. LLM hallucination rate unknown until real-world prompt calibration (I2).
2. Russian + English mixed content in meeting protocols — multilingual few-shot examples needed.
3. Meeting transcript format not standardized across tools.
4. `ingest_documents` stores file paths, not contents — file must exist at processing time.
5. Embedding-based semantic dedup deferred — string dedup sufficient for initial deployment.
6. No batch LLM call optimization yet — individual document processing only.

## 7) ADR status

- **ADR-11 added** to `spec/ARCH_DECISIONS.md` (Task Ingestion Pipeline Architecture).
- ADR-01 through ADR-10 remain unchanged.
