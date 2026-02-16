from __future__ import annotations

import time
from types import SimpleNamespace

from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.connectors.caldav import CalendarConnectorError
from executive_cli.sync_runner import HourlySyncOutcome, SourceSyncOutcome, run_hourly_sync


def test_sync_hourly_command_success_exit_zero(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXECAS_DB_PATH", str(tmp_path / "sync_hourly_success.sqlite"))
    runner = CliRunner()

    def _stub_run_hourly_sync(**kwargs):
        del kwargs
        return HourlySyncOutcome(
            calendar=SourceSyncOutcome(source="calendar", success=True, attempts=1),
            mail=SourceSyncOutcome(source="mail", success=True, attempts=1),
        )

    monkeypatch.setattr("executive_cli.cli.run_hourly_sync", _stub_run_hourly_sync)

    result = runner.invoke(app, ["sync", "hourly"])
    assert result.exit_code == 0
    assert "Hourly sync complete." in result.output
    assert "status=ok" in result.output


def test_run_hourly_sync_partial_failure_keeps_second_source_and_returns_exit_two() -> None:
    calls: list[str] = []

    def _calendar_fail():
        calls.append("calendar")
        raise RuntimeError("calendar unavailable")

    def _mail_ok():
        calls.append("mail")
        return None

    outcome = run_hourly_sync(
        run_calendar=_calendar_fail,
        run_mail=_mail_ok,
        retries=0,
        backoff_sec=5,
        sleep_fn=lambda _: None,
        parallel=False,
    )

    assert calls == ["calendar", "mail"]
    assert outcome.calendar.success is False
    assert outcome.mail.success is True
    assert outcome.exit_code == 2


def test_run_hourly_sync_both_fail_returns_exit_one() -> None:
    outcome = run_hourly_sync(
        run_calendar=lambda: (_ for _ in ()).throw(RuntimeError("calendar down")),
        run_mail=lambda: (_ for _ in ()).throw(RuntimeError("mail down")),
        retries=0,
        backoff_sec=5,
        sleep_fn=lambda _: None,
        parallel=False,
    )

    assert outcome.calendar.success is False
    assert outcome.mail.success is False
    assert outcome.exit_code == 1


def test_run_hourly_sync_retries_per_source_with_exponential_backoff() -> None:
    calendar_attempts = {"count": 0}
    mail_attempts = {"count": 0}
    backoff_calls: list[float] = []

    def _calendar_flaky():
        calendar_attempts["count"] += 1
        if calendar_attempts["count"] < 3:
            raise RuntimeError("calendar transient")
        return None

    def _mail_flaky():
        mail_attempts["count"] += 1
        if mail_attempts["count"] < 2:
            raise RuntimeError("mail transient")
        return None

    outcome = run_hourly_sync(
        run_calendar=_calendar_flaky,
        run_mail=_mail_flaky,
        retries=2,
        backoff_sec=5,
        sleep_fn=backoff_calls.append,
        parallel=False,
    )

    assert outcome.calendar.success is True
    assert outcome.mail.success is True
    assert outcome.calendar.attempts == 3
    assert outcome.mail.attempts == 2
    assert backoff_calls == [5.0, 10.0, 5.0]


def test_run_hourly_sync_parallel_reduces_wall_time() -> None:
    def _calendar_ok():
        time.sleep(0.2)
        return None

    def _mail_ok():
        time.sleep(0.2)
        return None

    start = time.perf_counter()
    outcome = run_hourly_sync(
        run_calendar=_calendar_ok,
        run_mail=_mail_ok,
        retries=0,
        backoff_sec=5,
        sleep_fn=lambda _: None,
        parallel=True,
    )
    elapsed = time.perf_counter() - start

    assert outcome.exit_code == 0
    # Sequential execution would be around 0.4s; parallel should stay materially lower.
    assert elapsed < 0.35


def test_sync_hourly_cli_does_not_echo_secret_on_degraded_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EXECAS_DB_PATH", str(tmp_path / "sync_hourly_redaction.sqlite"))
    runner = CliRunner()
    secret = "calendar-secret-ops-01"
    mail_calls = {"count": 0}

    monkeypatch.setattr("executive_cli.cli.CalDavConnector.from_env", classmethod(lambda cls: object()))
    monkeypatch.setattr("executive_cli.cli.ImapConnector.from_env", classmethod(lambda cls: object()))

    def _calendar_fail(session, *, connector):
        del session, connector
        raise CalendarConnectorError(f"authentication failed password={secret}")

    def _mail_ok(session, *, connector, mailbox):
        del session, connector, mailbox
        mail_calls["count"] += 1
        return SimpleNamespace(inserted=0, updated=0, cursor_kind="uidvalidity_uidnext", cursor="1:2")

    monkeypatch.setattr("executive_cli.cli.sync_calendar_primary", _calendar_fail)
    monkeypatch.setattr("executive_cli.cli.sync_mailbox", _mail_ok)

    result = runner.invoke(app, ["sync", "hourly", "--retries", "0"])
    assert result.exit_code == 2
    assert "degraded" in result.output
    assert secret not in result.output
    assert mail_calls["count"] == 1
