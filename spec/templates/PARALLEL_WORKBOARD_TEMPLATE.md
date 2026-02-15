# Parallel Workboard Template

Use this template for each parallel delivery batch.

## Batch metadata

- Batch id: `<BATCH-ID>`
- Sprint: `<SPRINT-ID>`
- Date: `<YYYY-MM-DD>`
- TL owner: `<name>`

## Lanes

| Lane | Task ID | Role | Dependency (`none/soft/hard`) | Locked files | Status | Last update |
|---|---|---|---|---|---|---|
| A | `<task>` | `<role>` | `<type>` | `<files>` | `<active/blocked/done>` | `<timestamp>` |
| B | `<task>` | `<role>` | `<type>` | `<files>` | `<active/blocked/done>` | `<timestamp>` |
| C | `<task>` | `<role>` | `<type>` | `<files>` | `<active/blocked/done>` | `<timestamp>` |
| D | `<task>` | `<role>` | `<type>` | `<files>` | `<active/blocked/done>` | `<timestamp>` |

## Acceptance queue

| Commit | Lane | Task | Verdict | Evidence |
|---|---|---|---|---|
| `<sha>` | `<lane>` | `<task>` | `<accepted/rejected/pending>` | `<gate report / checks>` |

## Escalations

- `<issue>` -> owner `<role>` -> ETA `<time>`
