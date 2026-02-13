# TASK 10 — Weekly review command

## Goal
Implement `execas review week --week YYYY-Www` producing prioritised weekly focus items.

## Depends on
- TASK 06 (tasks)
- TASK 05 (commitments)

## In scope
- Ranking algorithm: score = priority_weight + commitment_bonus + due_urgency + waiting_ping_urgency.
  - Candidates: tasks in NOW + NEXT + WAITING (with ping in this week).
  - Top 10 by score.
- Output: markdown list with task title, score rationale, commitment link if any.
- Store summary in DB (new table or reuse day_plans with type='weekly').
- Save markdown to file (documented path, e.g. `outputs/reviews/YYYY-Www.md`).

## Out of scope
- LLM narrative (optional enhancement; not required for MVP acceptance).

## Files to touch (expected)
- apps/executive-cli/src/executive_cli/cli.py (review group)
- apps/executive-cli/src/executive_cli/review.py
- Alembic migration if new table needed (e.g. weekly_reviews)

## Acceptance checks (TEST_PLAN: not explicitly covered; ACCEPTANCE: I1)
- Output contains 5-10 items ranked by score.
- Commitment-linked tasks appear higher.
- Markdown file saved.

## Rollback
- Revert commit.
