# Scrum Metrics Operations

## Purpose

Track sprint throughput and code quality using a single command.

## Command

```bash
cd /Users/gaidabura/Agentura/apps/executive-cli
uv run execas review scrum-metrics --start YYYY-MM-DD --end YYYY-MM-DD
```

## Default behavior

- Computes throughput/carry-over/lead-time from task data.
- Runs quality snapshot (`pytest -q` + coverage gate).
- Saves a snapshot record to `.data/scrum_metrics_history.json`.

## Options

- `--no-run-quality` to skip test/coverage snapshot.
- `--no-save` to print metrics without appending history.
- Omit `--start` / `--end` to use the latest 14-day window.

## Output fields

- `throughput_done_count`
- `throughput_done_estimate_min`
- `backlog_at_start_count`
- `carry_over_count`
- `carry_over_rate`
- `lead_time_avg_hours`
- `lead_time_p85_hours`
- `quality_tests_passed`
- `quality_coverage_gate_passed`
- `quality_coverage_percent`
