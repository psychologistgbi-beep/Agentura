# Test Plan — Executive Assistant MVP (v0.1)

All tests assume timezone = Europe/Moscow unless otherwise stated.
Unless explicitly noted, tests are manual CLI checks (MVP stage).
If automated tests are implemented, they must cover at least the core cases below.

## Conventions
- DB path: use whatever the implementation documents; tests assume a fresh DB can be created.
- Replace `<TASK_ID>` with actual IDs returned by the CLI.
- Dates use ISO format YYYY-MM-DD.

---

## T01 — Bootstrap / init idempotency
**Goal:** `execas init` creates DB, applies migrations, and is safe to run twice.

**Steps:**
1) Delete existing DB file (or use a temp path per docs).
2) Run: `execas init`
3) Run again: `execas init`

**Expected:**
- First run creates DB, migrations applied, seeds primary calendar and baseline settings.
- Second run exits successfully without duplicating primary calendar or corrupting settings.
- `execas --help` works.

---

## T02 — Config show/set roundtrip
**Goal:** settings are persisted and visible with correct defaults.

**Steps:**
1) `execas config show`
2) Change a setting, e.g.: `execas config set buffer_min 10`
3) `execas config show`

**Expected:**
- All required keys exist with defaults: timezone=Europe/Moscow, planning_start=07:00, planning_end=19:00, lunch_start=12:00, lunch_duration_min=60, min_focus_block_min=30, buffer_min=5.
- After step 2, buffer_min shows 10.
- No silent resets.

---

## T03 — Create area/project as reference data
**Goal:** areas/projects exist as lookup tables, not free-text.

**Steps:**
1) Create area: `execas area add "Work"`
2) Create project: `execas project add "Agentura" --area "Work"`
3) List: `execas area list`, `execas project list`

**Expected:**
- Area and project are created and listed.
- Project references the correct area.

---

## T04 — Task capture requires estimate & priority
**Goal:** Task creation enforces required fields.

**Steps:**
1) Try: `execas task capture "Test missing fields"`
2) Then: `execas task capture "Task A" --estimate 30 --priority P2 --project "Agentura"`

**Expected:**
- Step (1) fails with a clear error indicating missing required flags.
- Step (2) succeeds and returns an ID.

---

## T05 — WAITING task requires waiting_on and ping_at
**Goal:** WAITING tasks capture dependency and reminder time.

**Steps:**
1) Create: `execas task capture "Waiting task" --estimate 30 --priority P2`
2) Move to waiting without required fields (or create as waiting):  
   `execas task move <TASK_ID> --status WAITING`
3) Set waiting properly:  
   `execas task waiting <TASK_ID> --on "Ivan / Legal" --ping "2026-02-14 10:00"`

**Expected:**
- Step (2) fails or prompts for missing waiting_on/ping_at.
- Step (3) succeeds; task shows status WAITING and stores dependency + ping time.

---

## T06 — Busy block manual add/list
**Goal:** busy blocks can be created and listed for a day.

**Steps:**
1) `execas busy add --date 2026-02-15 --start 10:00 --end 11:00 --title "Meet A"`
2) `execas busy list --date 2026-02-15`

**Expected:**
- Busy list includes the event with correct timestamps in Europe/Moscow.
- Duration positive and correct.

---

## T07 — Busy blocks merging (overlap)
**Goal:** overlapping busy blocks merge deterministically on read (ADR-03).

**Setup:**
- Add:
  - 10:00–11:00 "Meet A"
  - 10:30–12:00 "Meet B"

**Steps:**
1) Add both busy blocks.
2) `execas busy list --date 2026-02-15`

**Expected:**
- Result shows a single merged busy interval 10:00–12:00 with title "Meet A | Meet B".
- No overlap remains.
- Raw DB still contains 2 separate rows (merge is on read).

---

## T08 — Busy blocks merging (adjacent)
**Goal:** adjacent busy blocks merge per ADR-03 (adjacency = merge).

**Setup:**
- Add:
  - 14:00–14:30 "Block X"
  - 14:30–15:00 "Block Y"

**Steps:**
1) Add both busy blocks.
2) `execas busy list --date <date>`

**Expected:**
- Merged into 14:00–15:00 with title "Block X | Block Y".
- No gaps/overlaps introduced.

---

## T09 — Plan day minimal variant (basic)
**Goal:** produce a time-blocked plan, stored in DB, respecting constraints.

**Setup:**
- Ensure planning window is 07:00–19:00, lunch enabled (12:00, 60m), min_focus_block=30.
- Add busy: 10:00–11:00.
- Add tasks in NOW:
  - Task1 (estimate 60, P1)
  - Task2 (estimate 30, P2)
  - Task3 (estimate 90, P3)

**Steps:**
1) `execas plan day --date 2026-02-16 --variant minimal`

**Expected:**
- Output includes:
  - busy block 10:00–11:00
  - lunch block near 12:00 for 60m (not overlapping busy)
  - at least one focus block scheduled using NOW tasks, preferably highest value (P1 and/or commitment-linked).
- No focus block shorter than 30 minutes.
- Plan stored (day_plans + time_blocks exist).

---

## T10 — Plan day respects “tiny gaps”
**Goal:** gaps smaller than min_focus_block are not used for focus.

**Setup:**
- Busy: 09:00–09:40 and 10:05–11:00 (gap 09:40–10:05 = 25m)
- min_focus_block=30

**Steps:**
1) `execas plan day --date 2026-02-17 --variant realistic`

**Expected:**
- The 25-minute gap is not used for a focus task.
- It becomes buffer/admin (or is ignored), but not focus.

---

## T11 — Lunch conflict handling
**Goal:** lunch moves when default slot conflicts with busy.

**Setup:**
- Lunch default 12:00–13:00.
- Busy: 12:00–12:30 and 13:30–14:00

**Steps:**
1) `execas plan day --date 2026-02-18 --variant realistic`

**Expected:**
- Lunch is scheduled as a 60m block, shifted to the nearest feasible window around mid-day (e.g., 12:30–13:30).
- No overlap with busy.
- Deterministic choice.

---

## T12 — Plan day determinism
**Goal:** same inputs produce same schedule.

**Steps:**
1) Run `execas plan day --date 2026-02-19 --variant realistic` twice without changing inputs.

**Expected:**
- Output schedules are identical (timestamps & selected tasks).
- Stored plans can either be versioned or replaced, but behavior is documented and consistent.

---

## T13 — Full day busy
**Goal:** if day is fully busy, planner does not schedule focus tasks.

**Setup:**
- Busy covers entire planning window 07:00–19:00 (single merged block).

**Steps:**
1) `execas plan day --date 2026-02-20 --variant minimal`

**Expected:**
- Output contains busy blocks (and possibly lunch omitted or irrelevant).
- No focus blocks inserted.
- Output suggests actions: reschedule/carryover list.

---

## T14 — People FTS search
**Goal:** SQLite FTS5 works for People.

**Steps:**
1) `execas people add --name "Andy Petrov" --org "Example" --role "CDO" --notes "met at conference"`
2) `execas people search "Andy"`
3) `execas people search "conference"`

**Expected:**
- Searches return the person record.
- Case-insensitive behavior is acceptable; must be consistent.

---

## T15 — Decisions FTS search
**Goal:** SQLite FTS5 works for Decisions.

**Steps:**
1) `execas decision add --title "Choose SQLite for MVP" --context "fast start" --choice "SQLite" --consequences "migrate later"`
2) `execas decision search "SQLite"`
3) `execas decision search "migrate"`

**Expected:**
- Searches return the decision.
- Index updated immediately after insert.

---

## T16 — MCP Calendar sync stub + fallback
**Goal:** Calendar sync command exists and fails gracefully if MCP not configured.

**Steps:**
1) Run `execas calendar sync` with no MCP configured.

**Expected:**
- Command exits with a clear, actionable error:
  - what is missing (MCP config/credentials)
  - how to proceed (use manual busy add as fallback)
- No partial/corrupt busy blocks.

---

## T17 — MCP Email sync stub + follow-up task
**Goal:** Email sync command exists and supports "create task from email" workflow (at least stubbed).

**Steps:**
1) Run `execas mail sync` with no MCP configured (command name: `mail sync`, not `email sync`).

**Expected:**
- Clear error + fallback instructions.
- If sample/manual email add exists, creating a task from an email creates:
  - a task
  - an email reference record linked to the task