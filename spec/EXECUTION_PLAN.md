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

## Risk Notes

- **TASK 07 is the most complex task.** If it takes too long, ship TASK 01-06 + 09 as a usable subset (GTD + knowledge without planning).
- **FTS5 triggers in migrations** can be tricky with Alembic autogenerate. Plan to write FTS migration manually.
- **MCP stubs** (TASK 11) are intentionally late — they don't block anything and can be deferred if time runs out.

## Definition of Done (MVP)

All 12 tasks committed. The following must hold:
- `uv run pytest` passes.
- TEST_PLAN T01-T17 pass (manual verification documented).
- ACCEPTANCE.md criteria A-L met.
- No TBD items remain in TECH_SPEC (all resolved or explicitly deferred with rationale).
