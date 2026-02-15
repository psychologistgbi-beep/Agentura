from __future__ import annotations

import imaplib
from urllib.error import HTTPError

import pytest
import sqlalchemy as sa
from sqlmodel import Session, SQLModel, create_engine, select
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.connectors.caldav import CalDavConnector, CalendarConnectorError
from executive_cli.connectors.imap import ImapConnector, MailConnectorError, MailSyncBatch, RemoteEmailHeader
from executive_cli.models import Email, SyncState
from executive_cli.sync_service import IMAP_SCOPE_INBOX, IMAP_SOURCE, sync_mailbox


def _create_engine(tmp_path):
    db_path = tmp_path / "security_guardrails.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


class _StaticBatchConnector:
    def __init__(self, batch: MailSyncBatch):
        self.batch = batch

    def fetch_headers(
        self,
        *,
        mailbox: str,
        cursor_uidvalidity: int | None,
        cursor_uidnext: int | None,
    ) -> MailSyncBatch:
        del mailbox, cursor_uidvalidity, cursor_uidnext
        return self.batch


def test_calendar_sync_cli_does_not_echo_secret_on_connector_error(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "calendar_cli_redaction.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    secret = "calendar-secret-123"

    def _raise_from_env(cls):
        raise CalendarConnectorError(f"CalDAV authentication failed. password={secret}")

    monkeypatch.setattr("executive_cli.cli.CalDavConnector.from_env", classmethod(_raise_from_env))

    result = runner.invoke(app, ["calendar", "sync"])
    assert result.exit_code == 1
    assert "Calendar sync failed." in result.output
    assert "Fallback" in result.output
    assert secret not in result.output


def test_mail_sync_cli_does_not_echo_secret_on_connector_error(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "mail_cli_redaction.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    secret = "imap-secret-123"

    def _raise_from_env(cls):
        raise MailConnectorError(f"IMAP authentication failed. password={secret}")

    monkeypatch.setattr("executive_cli.cli.ImapConnector.from_env", classmethod(_raise_from_env))

    result = runner.invoke(app, ["mail", "sync"])
    assert result.exit_code == 1
    assert "Mail sync failed." in result.output
    assert "Fallback" in result.output
    assert secret not in result.output


def test_caldav_auth_error_no_secret_in_exception(monkeypatch) -> None:
    secret = "calendar-pass-123"
    connector = CalDavConnector(base_url="https://calendar.example/dav", username="alice", password=secret)

    def _raise_401(request, timeout):
        del timeout
        raise HTTPError(request.full_url, 401, f"unauthorized password={secret}", hdrs=None, fp=None)

    monkeypatch.setattr("executive_cli.connectors.caldav.urlopen", _raise_401)

    with pytest.raises(CalendarConnectorError, match="authentication failed") as exc_info:
        connector._request_xml(method="PROPFIND", depth="0", body="<x/>")

    assert secret not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_imap_auth_error_no_secret_in_exception(monkeypatch) -> None:
    secret = "imap-pass-123"
    connector = ImapConnector(host="imap.example.com", username="alice", password=secret)

    class _ImapStub:
        def __init__(self, host: str, port: int, timeout: float):
            del host, port, timeout

        def login(self, username: str, password: str):
            del username, password
            raise imaplib.IMAP4.error(f"login rejected password={secret}")

        def logout(self):
            return "BYE", [b"Logged out"]

    monkeypatch.setattr("executive_cli.connectors.imap.imaplib.IMAP4_SSL", _ImapStub)

    with pytest.raises(MailConnectorError, match="authentication failed") as exc_info:
        connector.fetch_headers(mailbox="INBOX", cursor_uidvalidity=None, cursor_uidnext=None)

    assert secret not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_imap_request_error_no_secret_in_exception(monkeypatch) -> None:
    secret = "imap-request-secret"
    connector = ImapConnector(host="imap.example.com", username="alice", password="app-pass")

    class _ImapStub:
        def __init__(self, host: str, port: int, timeout: float):
            del host, port, timeout

        def login(self, username: str, password: str):
            del username, password
            return "OK", [b"Logged in"]

        def select(self, mailbox: str, readonly: bool = False):
            del mailbox, readonly
            raise imaplib.IMAP4.error(f"request failed token={secret}")

        def logout(self):
            return "BYE", [b"Logged out"]

    monkeypatch.setattr("executive_cli.connectors.imap.imaplib.IMAP4_SSL", _ImapStub)

    with pytest.raises(MailConnectorError, match="request failed") as exc_info:
        connector.fetch_headers(mailbox="INBOX", cursor_uidvalidity=None, cursor_uidnext=None)

    assert secret not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_imap_unreachable_error_no_secret_in_exception(monkeypatch) -> None:
    secret = "transport-secret"
    connector = ImapConnector(host="imap.example.com", username="alice", password="app-pass")

    def _raise_unreachable(host: str, port: int, timeout: float):
        del host, port, timeout
        raise OSError(f"connect failed token={secret}")

    monkeypatch.setattr("executive_cli.connectors.imap.imaplib.IMAP4_SSL", _raise_unreachable)

    with pytest.raises(MailConnectorError, match="unreachable") as exc_info:
        connector.fetch_headers(mailbox="INBOX", cursor_uidvalidity=None, cursor_uidnext=None)

    assert secret not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_caldav_rejects_http_url_constructor() -> None:
    with pytest.raises(CalendarConnectorError, match="https://"):
        CalDavConnector(base_url="http://calendar.example/dav", username="alice", password="secret")


def test_imap_uses_ssl_without_plaintext_fallback(monkeypatch) -> None:
    connector = ImapConnector(host="imap.example.com", username="alice", password="secret")
    calls = {"ssl": 0, "plain": 0}

    class _ImapSslStub:
        def __init__(self, host: str, port: int, timeout: float):
            del host, port, timeout
            calls["ssl"] += 1

        def login(self, username: str, password: str):
            del username, password
            return "OK", [b"Logged in"]

        def select(self, mailbox: str, readonly: bool = False):
            del mailbox, readonly
            return "OK", [b"1"]

        def status(self, mailbox: str, criteria: str):
            del mailbox, criteria
            return "OK", [b"INBOX (UIDVALIDITY 42 UIDNEXT 43)"]

        def uid(self, command: str, *args):
            del args
            if command == "SEARCH":
                return "OK", [b""]
            raise AssertionError(command)

        def logout(self):
            return "BYE", [b"Logged out"]

    def _plain_imap(*args, **kwargs):
        del args, kwargs
        calls["plain"] += 1
        raise AssertionError("Plain IMAP must not be used.")

    monkeypatch.setattr("executive_cli.connectors.imap.imaplib.IMAP4", _plain_imap)
    monkeypatch.setattr("executive_cli.connectors.imap.imaplib.IMAP4_SSL", _ImapSslStub)

    batch = connector.fetch_headers(mailbox="INBOX", cursor_uidvalidity=None, cursor_uidnext=None)
    assert batch.uidvalidity == 42
    assert batch.uidnext == 43
    assert calls["ssl"] == 1
    assert calls["plain"] == 0


def test_email_headers_only_policy_no_body_or_recipients_persisted(tmp_path, monkeypatch) -> None:
    body_token = "BODY_TOKEN_SHOULD_NOT_PERSIST"
    recipient = "recipient@example.com"
    connector = ImapConnector(host="imap.example.com", username="alice", password="secret")

    class _ImapStub:
        def __init__(self, host: str, port: int, timeout: float):
            del host, port, timeout

        def login(self, username: str, password: str):
            del username, password
            return "OK", [b"Logged in"]

        def select(self, mailbox: str, readonly: bool = False):
            del mailbox, readonly
            return "OK", [b"1"]

        def status(self, mailbox: str, criteria: str):
            del mailbox, criteria
            return "OK", [b"INBOX (UIDVALIDITY 55 UIDNEXT 56)"]

        def uid(self, command: str, *args):
            if command == "SEARCH":
                return "OK", [b"55"]
            if command == "FETCH":
                del args
                return (
                    "OK",
                    [
                        (
                            b'55 (UID 55 FLAGS (\\Seen) BODY[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM DATE)] {280}',
                            (
                                b"Message-ID: <headers-only@example.com>\r\n"
                                b"Subject: Security check\r\n"
                                b"From: Alice <alice@example.com>\r\n"
                                b"To: Recipient <recipient@example.com>\r\n"
                                b"Cc: Team <team@example.com>\r\n"
                                b"Date: Thu, 20 Feb 2026 10:00:00 +0300\r\n"
                                b"\r\n"
                                b"Attachment: report.pdf\r\n"
                                b"Body: BODY_TOKEN_SHOULD_NOT_PERSIST\r\n"
                            ),
                        ),
                        b")",
                    ],
                )
            raise AssertionError(command)

        def logout(self):
            return "BYE", [b"Logged out"]

    monkeypatch.setattr("executive_cli.connectors.imap.imaplib.IMAP4_SSL", _ImapStub)

    batch = connector.fetch_headers(mailbox="INBOX", cursor_uidvalidity=None, cursor_uidnext=None)
    assert len(batch.messages) == 1
    assert batch.messages[0].sender == "alice@example.com"
    assert recipient not in (batch.messages[0].subject or "")

    engine = _create_engine(tmp_path)
    with Session(engine) as session:
        sync_mailbox(session, connector=_StaticBatchConnector(batch), mailbox="INBOX")

    with Session(engine) as session:
        row = session.exec(select(Email).where(Email.source == IMAP_SOURCE)).one()
        persisted = " ".join(
            [
                row.external_id,
                row.subject or "",
                row.sender or "",
                row.flags_json or "",
                row.received_at or "",
            ]
        )
        assert body_token not in persisted
        assert recipient not in persisted

        columns = [info[1] for info in session.exec(sa.text("PRAGMA table_info(emails)")).all()]
        forbidden_columns = {"body", "body_text", "attachments", "recipient_list", "to", "cc", "bcc"}
        assert forbidden_columns.isdisjoint(set(columns))


def test_sync_service_log_levels_are_safe(tmp_path, monkeypatch) -> None:
    engine = _create_engine(tmp_path)
    log_records: list[tuple[str, str]] = []

    def _record(level: str):
        def _logger(message: str, *args, **kwargs) -> None:
            del kwargs
            text = message % args if args else message
            log_records.append((level, text))

        return _logger

    monkeypatch.setattr("executive_cli.sync_service.logger.info", _record("INFO"))
    monkeypatch.setattr("executive_cli.sync_service.logger.warning", _record("WARNING"))
    monkeypatch.setattr("executive_cli.sync_service.logger.error", _record("ERROR"))

    with Session(engine) as session:
        session.add(
            SyncState(
                source=IMAP_SOURCE,
                scope=IMAP_SCOPE_INBOX,
                cursor="10:11",
                cursor_kind="uidvalidity_uidnext",
                updated_at="2026-02-20T05:00:00+00:00",
            )
        )
        session.commit()

    ok_connector = _StaticBatchConnector(
        MailSyncBatch(
            messages=[
                RemoteEmailHeader(
                    external_id="<safe-log@example.com>",
                    mailbox_uid=11,
                    subject="Safe log",
                    sender="alice@example.com",
                    received_at="2026-02-20T09:00:00+00:00",
                    flags=("\\Seen",),
                )
            ],
            uidvalidity=20,
            uidnext=21,
        )
    )
    with Session(engine) as session:
        sync_mailbox(session, connector=ok_connector, mailbox=IMAP_SCOPE_INBOX)

    levelnames = [level for level, _ in log_records]
    messages = [message for _, message in log_records]
    assert "INFO" in levelnames
    assert "WARNING" in levelnames
    assert any("mail_sync_started" in message for message in messages)
    assert any("mail_sync_completed" in message for message in messages)

    log_records.clear()
    secret = "log-secret-should-not-appear"

    class _FailingConnector:
        def fetch_headers(
            self,
            *,
            mailbox: str,
            cursor_uidvalidity: int | None,
            cursor_uidnext: int | None,
        ) -> MailSyncBatch:
            del mailbox, cursor_uidvalidity, cursor_uidnext
            raise MailConnectorError(f"IMAP authentication failed. token={secret}")

    with Session(engine) as session:
        with pytest.raises(MailConnectorError):
            sync_mailbox(session, connector=_FailingConnector(), mailbox=IMAP_SCOPE_INBOX)

    levelnames = [level for level, _ in log_records]
    assert "ERROR" in levelnames
    assert secret not in " ".join(message for _, message in log_records)
