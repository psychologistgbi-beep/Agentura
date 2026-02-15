from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlmodel import Session, select

from executive_cli.db import PROJECT_ROOT, get_db_path
from executive_cli.models import Task, TaskStatus
from executive_cli.timeutil import db_to_dt

_COVERAGE_RE = re.compile(r"Total coverage:\s*([0-9]+(?:\.[0-9]+)?)%")


@dataclass(frozen=True)
class ScrumMetricsSnapshot:
    start_date: date
    end_date: date
    throughput_done_count: int
    throughput_done_estimate_min: int
    backlog_at_start_count: int
    carry_over_count: int
    carry_over_rate: float
    lead_time_avg_hours: float | None
    lead_time_p85_hours: float | None

    def to_record(self) -> dict[str, object]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "throughput_done_count": self.throughput_done_count,
            "throughput_done_estimate_min": self.throughput_done_estimate_min,
            "backlog_at_start_count": self.backlog_at_start_count,
            "carry_over_count": self.carry_over_count,
            "carry_over_rate": round(self.carry_over_rate, 4),
            "lead_time_avg_hours": None if self.lead_time_avg_hours is None else round(self.lead_time_avg_hours, 2),
            "lead_time_p85_hours": None if self.lead_time_p85_hours is None else round(self.lead_time_p85_hours, 2),
        }


@dataclass(frozen=True)
class CodeQualitySnapshot:
    tests_passed: bool
    coverage_gate_passed: bool
    coverage_percent: float | None

    def to_record(self) -> dict[str, object]:
        return {
            "tests_passed": self.tests_passed,
            "coverage_gate_passed": self.coverage_gate_passed,
            "coverage_percent": None if self.coverage_percent is None else round(self.coverage_percent, 2),
        }


def _window_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_dt_exclusive = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    return start_dt, end_dt_exclusive


def _safe_db_to_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return db_to_dt(value).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = (len(ordered) - 1) * p
    low = math.floor(idx)
    high = math.ceil(idx)
    if low == high:
        return ordered[low]
    weight_high = idx - low
    return ordered[low] * (1 - weight_high) + ordered[high] * weight_high


def compute_scrum_metrics(
    session: Session,
    *,
    start_date: date,
    end_date: date,
) -> ScrumMetricsSnapshot:
    """
    Compute a sprint-window Scrum snapshot from the current task state.

    Notes:
    - Throughput and lead time are computed from tasks currently in DONE status
      with `updated_at` inside the requested window.
    - Carry-over is approximated from tasks created before window start and still
      not DONE/CANCELED in the current snapshot.
    """
    start_dt, end_dt_exclusive = _window_bounds(start_date, end_date)
    tasks = session.exec(select(Task)).all()

    done_in_window: list[Task] = []
    lead_time_hours: list[float] = []

    for task in tasks:
        if TaskStatus(task.status) != TaskStatus.DONE:
            continue
        updated_at = _safe_db_to_utc(task.updated_at)
        if updated_at is None or not (start_dt <= updated_at < end_dt_exclusive):
            continue
        done_in_window.append(task)

        created_at = _safe_db_to_utc(task.created_at)
        if created_at is None or created_at > updated_at:
            continue
        lead_time_hours.append((updated_at - created_at).total_seconds() / 3600.0)

    backlog_at_start: list[Task] = []
    for task in tasks:
        created_at = _safe_db_to_utc(task.created_at)
        if created_at is None:
            continue
        if created_at < start_dt and TaskStatus(task.status) != TaskStatus.CANCELED:
            backlog_at_start.append(task)

    carry_over_count = sum(
        1
        for task in backlog_at_start
        if TaskStatus(task.status) not in {TaskStatus.DONE, TaskStatus.CANCELED}
    )
    backlog_count = len(backlog_at_start)
    carry_over_rate = carry_over_count / backlog_count if backlog_count else 0.0

    throughput_done_estimate_min = sum(task.estimate_min for task in done_in_window)
    lead_time_avg = (sum(lead_time_hours) / len(lead_time_hours)) if lead_time_hours else None
    lead_time_p85 = _percentile(lead_time_hours, 0.85)

    return ScrumMetricsSnapshot(
        start_date=start_date,
        end_date=end_date,
        throughput_done_count=len(done_in_window),
        throughput_done_estimate_min=throughput_done_estimate_min,
        backlog_at_start_count=backlog_count,
        carry_over_count=carry_over_count,
        carry_over_rate=carry_over_rate,
        lead_time_avg_hours=lead_time_avg,
        lead_time_p85_hours=lead_time_p85,
    )


def _run_quality_command(command: list[str], *, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output


def collect_code_quality_snapshot(*, project_root: Path | None = None) -> CodeQualitySnapshot:
    root = project_root or PROJECT_ROOT
    tests_rc, _ = _run_quality_command([sys.executable, "-m", "pytest", "-q"], cwd=root)
    coverage_rc, coverage_output = _run_quality_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=executive_cli",
            "--cov-report=term-missing",
            "--cov-fail-under=80",
        ],
        cwd=root,
    )

    match = _COVERAGE_RE.search(coverage_output)
    coverage_percent = float(match.group(1)) if match else None

    return CodeQualitySnapshot(
        tests_passed=(tests_rc == 0),
        coverage_gate_passed=(coverage_rc == 0),
        coverage_percent=coverage_percent,
    )


def metrics_history_path() -> Path:
    return get_db_path().parent / "scrum_metrics_history.json"


def append_metrics_history(record: dict[str, object]) -> Path:
    path = metrics_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: list[dict[str, object]]
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            existing = payload if isinstance(payload, list) else []
        except json.JSONDecodeError:
            existing = []
    else:
        existing = []

    existing.append(record)
    path.write_text(json.dumps(existing, ensure_ascii=True, indent=2), encoding="utf-8")
    return path
