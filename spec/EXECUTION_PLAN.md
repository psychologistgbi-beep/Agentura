# Execution Plan — Executive Assistant MVP

## Task Dependency Graph

```
TASK 01 (bootstrap)
  └── TASK 02 (schema + migrations)
        ├── TASK 03 (busy blocks + merge)
        ├── TASK 04 (config commands)
        ├── TASK 05 (areas/projects/commitments)
        │     └── TASK 06 (tasks CRUD)
        │           ├── TASK 07 (plan day)
        │           │     └── TASK 08 (planner tests)
        │           └── TASK 10 (weekly review)
        ├── TASK 09 (people/decisions + FTS5)
        │     └── TASK 12 (FTS tests + smoke)
        └── TASK 11 (MCP stubs)
```

## Execution Order

### Phase 1: Foundation (Milestone 1)

| Step | Task | Verify | Commit message pattern |
|------|------|--------|----------------------|
| 1 | **TASK 01** — Bootstrap CLI | `uv run execas --help`, `uv run execas init` exits 0 | `feat: bootstrap executive-cli project` |
| 2 | **TASK 02** — Schema + migrations | `uv run execas init` creates DB; `sqlite3 <db> ".tables"` shows all tables; settings seeded | `feat: add SQLite schema and migrations` |
| 3 | **TASK 04** — Config show/set | `uv run execas config show` prints 7 keys; `config set buffer_min 10` persists | `feat: implement config show/set` |
| 4 | **TASK 03** — Busy blocks | T06, T07, T08 from TEST_PLAN pass manually | `feat: busy add/list with merge logic` |

### Phase 2: GTD Core (Milestone 2)

| Step | Task | Verify | Commit message pattern |
|------|------|--------|----------------------|
| 5 | **TASK 05** — Areas/Projects/Commitments | T03; `commitment import` creates YC-1..3 | `feat: areas, projects, commitments CRUD` |
| 6 | **TASK 06** — Tasks CRUD | T04, T05; task capture/list/move/done/waiting all work | `feat: GTD task lifecycle` |

### Phase 3: Planning (Milestone 3)

| Step | Task | Verify | Commit message pattern |
|------|------|--------|----------------------|
| 7 | **TASK 07** — Plan day | T09, T10, T11, T12, T13 from TEST_PLAN | `feat: deterministic plan day (3 variants)` |
| 8 | **TASK 08** — Planner unit tests | `uv run pytest` all green | `test: planner and merge unit tests` |

### Phase 4: Knowledge + Integration (Milestones 4-5)

| Step | Task | Verify | Commit message pattern |
|------|------|--------|----------------------|
| 9 | **TASK 09** — People/Decisions + FTS5 | T14, T15 | `feat: people and decisions with FTS5` |
| 10 | **TASK 10** — Weekly review | I1 acceptance; markdown output exists | `feat: weekly review command` |
| 11 | **TASK 11** — MCP stubs | T16, T17; graceful errors | `feat: MCP sync stubs (calendar + email)` |
| 12 | **TASK 12** — FTS tests + smoke | `uv run pytest` all green; E2E smoke passes | `test: FTS and integration smoke tests` |

## Verification Checklist Per Step

After **each commit**, verify:
1. `uv run execas --help` still works (no import errors).
2. `uv run execas init` on fresh DB succeeds.
3. Any existing tests still pass (`uv run pytest` if tests exist).
4. Referenced TEST_PLAN cases pass (manual or automated).

### Phase 5: Architecture Alignment (Post-MVP, Pre-Sync)

| Step | Task | Verify | Commit message pattern |
|------|------|--------|----------------------|
| 13 | **Chief Architect agent** — AGENTS.md, SKILL.md, templates | `AGENTS.md`, `agents/chief_architect/SKILL.md`, `spec/templates/` exist | `feat: add Chief Architect agent` |
| 14 | **ADR-10 Architecture Gate** — Task files, review checklist | `spec/TASKS/TASK_R1_*.md`, `TASK_R2_R4_*.md` exist; SKILL.md has ADR-10 checklist | `arch: ADR-10 architecture gate` |
| 15 | **ARCH-ALIGN-01** — Document alignment | 0 contradictions between TECH_SPEC/EXECUTION_PLAN/ACCEPTANCE/TASK_R2_R4 | `arch: align post-MVP roadmap and agent runtime` |

### Phase 6: External Sync (R1–R4)

**Dependency graph:**
```
Phase 5 (alignment)
  └── R1 (ADR-10 schema migration)
        ├── R2 (calendar incremental sync)
        ├── R3 (mail headers ingest + task-email links)
        └── R4 (security guardrails — validates R2+R3)
```

R2 and R3 are independent of each other. R4 must review R2+R3 code before merge.

| Step | Release | Scope | Verify | Commit message pattern |
|------|---------|-------|--------|----------------------|
| 16 | **R1** | Schema: extend `busy_blocks` (5 cols), create `sync_state`, `emails`, `task_email_links`, partial unique index | See below | `feat: ADR-10 provenance schema migration` |
| 17 | **R2** | CalDAV connector + `calendar sync` command + `busy_service` is_deleted filter | See below | `feat: calendar incremental sync (CalDAV)` |
| 18 | **R3** | IMAP connector + `mail sync` + `task capture --from-email` + `task link-email` | See below | `feat: mail ingest + task-email links` |
| 19 | **R4** | Credential redaction, PII filter, TLS enforcement, structured logging, security tests | See below | `feat: sync security guardrails` |

#### R1 verify commands
```bash
cd apps/executive-cli
rm -f .data/execas.sqlite && uv run execas init
sqlite3 .data/execas.sqlite ".tables"
# Must include: sync_state, emails, task_email_links
sqlite3 .data/execas.sqlite "PRAGMA table_info('busy_blocks');"
# Must include: source, external_id, external_etag, external_modified_at, is_deleted
sqlite3 .data/execas.sqlite "PRAGMA index_list('busy_blocks');"
# Must include: uq_busy_blocks_source_external_id
uv run execas busy add --date 2026-02-20 --start 10:00 --end 11:00 --title "Test"
sqlite3 .data/execas.sqlite "SELECT source, external_id, is_deleted FROM busy_blocks WHERE id=1;"
# Expected: manual||0
uv run pytest --cov=executive_cli --cov-fail-under=80
# Downgrade+upgrade cycle
uv run python -c "
from alembic.config import Config; from alembic import command
cfg = Config('alembic.ini')
command.downgrade(cfg, '-1')
command.upgrade(cfg, 'head')
print('Downgrade+upgrade cycle OK')
"
```

#### R2 verify commands
```bash
cd apps/executive-cli
uv run execas calendar sync  # with mock or real CalDAV
sqlite3 .data/execas.sqlite "SELECT source, external_id, is_deleted FROM busy_blocks WHERE source='yandex_caldav';"
uv run execas busy list --date <sync-date>  # must exclude is_deleted=1 rows
uv run pytest --cov=executive_cli --cov-fail-under=80
```

#### R3 verify commands
```bash
cd apps/executive-cli
uv run execas mail sync  # with mock or real IMAP
sqlite3 .data/execas.sqlite "SELECT source, external_id, subject FROM emails;"
uv run execas task capture "Follow up" --estimate 30 --priority P2 --from-email 1
uv run execas task link-email 1 1 --type reference
sqlite3 .data/execas.sqlite "SELECT * FROM task_email_links;"
uv run pytest --cov=executive_cli --cov-fail-under=80
```

#### R4 verify commands
```bash
cd apps/executive-cli
uv run pytest tests/test_security_guardrails.py -v
# All G1-G4 tests pass
uv run pytest --cov=executive_cli --cov-fail-under=80
```

---

## Risk Notes

- **TASK 07 is the most complex task.** If it takes too long, ship TASK 01-06 + 09 as a usable subset (GTD + knowledge without planning).
- **FTS5 triggers in migrations** can be tricky with Alembic autogenerate. Plan to write FTS migration manually.
- **MCP stubs** (TASK 11) are intentionally late — they don't block anything and can be deferred if time runs out.
- **R2/R3 require external credentials** for integration testing. Unit tests use mocks; real CalDAV/IMAP testing requires Yandex app password in env vars.
- **R4 depends on R2+R3 code** for security review. Can be developed in parallel but final validation requires R2+R3 connector code.

## Definition of Done

### MVP (Phases 1–4)

All 12 tasks committed. The following must hold:
- `uv run pytest` passes.
- TEST_PLAN T01-T17 pass (manual verification documented).
- ACCEPTANCE.md criteria A-L (MVP) met.
- No TBD items remain in TECH_SPEC (all resolved or explicitly deferred with rationale).

### Post-MVP: External Sync (Phase 6)

R1-R4 committed. The following must hold:
- All R1 verify commands pass (schema + migration cycle).
- All R2 verify commands pass (calendar sync dedup + soft delete).
- All R3 verify commands pass (mail ingest + task-email links).
- All R4 verify commands pass (security guardrails G1-G4).
- ACCEPTANCE.md criteria G3-post, K1-post, K2-post met.
- `uv run pytest --cov=executive_cli --cov-fail-under=80` passes.
