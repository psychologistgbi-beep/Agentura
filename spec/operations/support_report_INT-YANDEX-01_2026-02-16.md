# SUPPORT INCIDENT REPORT

Incident ID: INT-YANDEX-01-DATA-GAP  
Date: 2026-02-16  
Owner: Technical Lead  
Status: partially_resolved

1) Business impact
- `execas calendar next-week --source yandex_caldav` returned empty output while user had real meetings in the same week.

2) Root cause
- CalDAV connector treated `https://caldav.yandex.ru` as a ready calendar collection and did not perform calendar-home/collection discovery for root endpoint.
- Result: sync could finish without auth error but import no relevant events for target week.

3) Corrective actions
- Implemented CalDAV root endpoint discovery in connector:
  - discover `calendar-home-set` from root/principal;
  - discover calendar collection from calendar-home;
  - select primary/events-like collection deterministically.
- Added regression tests for root endpoint discovery and collection resolution path.
- Re-ran quality gates for the CLI test suite and coverage.

4) Verification evidence
- Commands:
  - `cd apps/executive-cli && uv run pytest -q`
  - `cd apps/executive-cli && uv run pytest --cov=executive_cli --cov-report=term-missing --cov-fail-under=80`
  - `cd apps/executive-cli && uv run execas sync hourly --retries 2 --backoff-sec 5`
  - `cd apps/executive-cli && uv run execas calendar next-week --source yandex_caldav --anchor-date 2026-02-15`
- Results:
  - tests: `87 passed`
  - coverage: `89.54%` (threshold 80% passed)
  - hourly sync: `calendar sync ok`, `mail sync ok`, status `ok`
  - next-week: non-empty, `Count: 7`

5) Agents involved (mandatory)
- Executive Assistant (implementation + retry run)
- Technical Lead (incident workflow/orchestration rules and closure format)

6) Parallel execution metrics (mandatory)
- configured parallel lanes: 2
- observed max parallel lanes: 2

7) Residual risks
- Some recurring meetings may still be underrepresented if provider recurrence patterns are not fully expanded into weekly instances.
- Keep incident in monitoring mode until week output matches expected operational view.

8) EA retry instruction
- retry command(s):
  - `cd apps/executive-cli && uv run execas sync hourly --retries 2 --backoff-sec 5`
  - `cd apps/executive-cli && uv run execas calendar next-week --source yandex_caldav`
- expected business result:
  - non-empty next-week meeting set for active work week with `status=ok`.
