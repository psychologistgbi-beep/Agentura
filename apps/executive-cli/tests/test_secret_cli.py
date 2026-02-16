from __future__ import annotations

from typer.testing import CliRunner

from executive_cli.cli import app


def test_secret_set_caldav_stores_password(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, str] = {}

    monkeypatch.setattr("executive_cli.cli.getpass.getpass", lambda prompt: "secret")

    def _store(*, service: str, account: str, password: str) -> None:
        captured["service"] = service
        captured["account"] = account
        captured["password"] = password

    monkeypatch.setattr("executive_cli.cli.store_keychain_password", _store)

    result = runner.invoke(app, ["secret", "set-caldav", "--username", "alice@example.com"])
    assert result.exit_code == 0
    assert "CalDAV password stored in Keychain" in result.output
    assert captured["account"] == "alice@example.com"
    assert captured["password"] == "secret"


def test_secret_status_reports_presence(monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.setenv("EXECAS_CALDAV_USERNAME", "alice@example.com")
    monkeypatch.setenv("EXECAS_IMAP_USERNAME", "alice@example.com")

    def _exists(*, service: str, account: str) -> bool:
        del account
        return service == "execas.caldav.password"

    monkeypatch.setattr("executive_cli.cli.keychain_password_exists", _exists)

    result = runner.invoke(app, ["secret", "status"])
    assert result.exit_code == 0
    assert "caldav_keychain" in result.output
    assert "present=true" in result.output
    assert "imap_keychain" in result.output
    assert "present=false" in result.output
