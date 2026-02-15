from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.connectors.imap import ImapConnector, MailConnectorError, MailSyncBatch, RemoteEmailHeader
from executive_cli.db import get_engine
from executive_cli.models import Email, SyncState
from executive_cli.sync_service import IMAP_SCOPE_INBOX, IMAP_SOURCE, sync_mailbox


def _create_engine(tmp_path):
    db_path = tmp_path / "mail_sync.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


class FakeConnector:
    def __init__(self, batch: MailSyncBatch):
        self.batch = batch
        self.calls: list[tuple[str, int | None, int | None]] = []

    def fetch_headers(
        self,
        *,
        mailbox: str,
        cursor_uidvalidity: int | None,
        cursor_uidnext: int | None,
    ) -> MailSyncBatch:
        self.calls.append((mailbox, cursor_uidvalidity, cursor_uidnext))
        return self.batch


def test_sync_mailbox_performs_incremental_upsert_and_advances_cursor(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    with Session(engine) as session:
        session.add(
            Email(
                source=IMAP_SOURCE,
                external_id="<m1@example.com>",
                mailbox_uid=10,
                subject="Old",
                sender="old@example.com",
                received_at="2026-02-20T06:00:00+00:00",
                first_seen_at="2026-02-20T07:00:00+00:00",
                last_seen_at="2026-02-20T07:00:00+00:00",
                flags_json='["\\\\Seen"]',
            )
        )
        session.add(
            SyncState(
                source=IMAP_SOURCE,
                scope=IMAP_SCOPE_INBOX,
                cursor="111:11",
                cursor_kind="uidvalidity_uidnext",
                updated_at="2026-02-20T07:00:00+00:00",
            )
        )
        session.commit()

        connector = FakeConnector(
            MailSyncBatch(
                messages=[
                    RemoteEmailHeader(
                        external_id="<m1@example.com>",
                        mailbox_uid=11,
                        subject="Updated",
                        sender="alice@example.com",
                        received_at="2026-02-20T08:00:00+00:00",
                        flags=("\\Flagged", "\\Seen"),
                    ),
                    RemoteEmailHeader(
                        external_id="<m2@example.com>",
                        mailbox_uid=12,
                        subject="New",
                        sender="bob@example.com",
                        received_at="2026-02-20T09:00:00+00:00",
                        flags=("\\Seen",),
                    ),
                ],
                uidvalidity=111,
                uidnext=13,
            )
        )

        result = sync_mailbox(session, connector=connector, mailbox=IMAP_SCOPE_INBOX)
        assert result.inserted == 1
        assert result.updated == 1
        assert result.cursor == "111:13"
        assert connector.calls == [(IMAP_SCOPE_INBOX, 111, 11)]

    with Session(engine) as session:
        rows = session.exec(
            select(Email)
            .where(Email.source == IMAP_SOURCE)
            .order_by(Email.external_id)
        ).all()
        assert [row.external_id for row in rows] == ["<m1@example.com>", "<m2@example.com>"]
        assert rows[0].first_seen_at == "2026-02-20T07:00:00+00:00"
        assert rows[0].last_seen_at != "2026-02-20T07:00:00+00:00"
        assert rows[0].subject == "Updated"
        assert rows[0].flags_json == '["\\\\Flagged", "\\\\Seen"]'

        state = session.exec(
            select(SyncState)
            .where(SyncState.source == IMAP_SOURCE)
            .where(SyncState.scope == IMAP_SCOPE_INBOX)
        ).one()
        assert state.cursor == "111:13"


def test_sync_mailbox_deduplicates_same_external_id_within_batch(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    with Session(engine) as session:
        connector = FakeConnector(
            MailSyncBatch(
                messages=[
                    RemoteEmailHeader(
                        external_id="<dup@example.com>",
                        mailbox_uid=20,
                        subject="Older copy",
                        sender="one@example.com",
                        received_at="2026-02-20T07:00:00+00:00",
                        flags=("\\Seen",),
                    ),
                    RemoteEmailHeader(
                        external_id="<dup@example.com>",
                        mailbox_uid=21,
                        subject="Latest copy",
                        sender="two@example.com",
                        received_at="2026-02-20T08:00:00+00:00",
                        flags=("\\Answered",),
                    ),
                ],
                uidvalidity=222,
                uidnext=22,
            )
        )
        result = sync_mailbox(session, connector=connector)
        assert result.inserted == 1
        assert result.updated == 0

    with Session(engine) as session:
        rows = session.exec(select(Email).where(Email.source == IMAP_SOURCE)).all()
        assert len(rows) == 1
        assert rows[0].mailbox_uid == 21
        assert rows[0].subject == "Latest copy"
        assert rows[0].flags_json == '["\\\\Answered"]'


def test_sync_mailbox_does_not_advance_cursor_on_failure(tmp_path) -> None:
    engine = _create_engine(tmp_path)
    with Session(engine) as session:
        session.add(
            SyncState(
                source=IMAP_SOURCE,
                scope=IMAP_SCOPE_INBOX,
                cursor="333:7",
                cursor_kind="uidvalidity_uidnext",
                updated_at="2026-02-20T05:00:00+00:00",
            )
        )
        session.commit()

        connector = FakeConnector(
            MailSyncBatch(
                messages=[
                    RemoteEmailHeader(
                        external_id="<bad@example.com>",
                        mailbox_uid=0,
                        subject="Broken",
                        sender="bad@example.com",
                        received_at="2026-02-20T09:00:00+00:00",
                        flags=(),
                    )
                ],
                uidvalidity=333,
                uidnext=8,
            )
        )
        with pytest.raises(ValueError):
            sync_mailbox(session, connector=connector)

    with Session(engine) as session:
        state = session.exec(
            select(SyncState)
            .where(SyncState.source == IMAP_SOURCE)
            .where(SyncState.scope == IMAP_SCOPE_INBOX)
        ).one()
        assert state.cursor == "333:7"


def test_mail_sync_command_shows_fallback_on_connector_error(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "mail_cli.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()

    def _raise_from_env(cls):
        raise MailConnectorError("IMAP endpoint is unreachable.")

    monkeypatch.setattr("executive_cli.cli.ImapConnector.from_env", classmethod(_raise_from_env))

    result = runner.invoke(app, ["mail", "sync"])
    assert result.exit_code == 1
    assert "Mail sync failed" in result.output
    assert "Fallback" in result.output
    assert "task capture" in result.output


def test_mail_sync_command_executes_real_sync_flow(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "mail_cli_success.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    runner = CliRunner()
    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0

    connector = FakeConnector(
        MailSyncBatch(
            messages=[
                RemoteEmailHeader(
                    external_id="<ok@example.com>",
                    mailbox_uid=44,
                    subject="Hello",
                    sender="alice@example.com",
                    received_at="2026-02-20T09:00:00+00:00",
                    flags=("\\Seen",),
                )
            ],
            uidvalidity=444,
            uidnext=45,
        )
    )
    monkeypatch.setattr(
        "executive_cli.cli.ImapConnector.from_env",
        classmethod(lambda cls: connector),
    )

    result = runner.invoke(app, ["mail", "sync"])
    assert result.exit_code == 0
    assert "inserted=1" in result.output
    assert "cursor=444:45" in result.output

    with Session(get_engine(ensure_directory=True)) as session:
        rows = session.exec(select(Email).where(Email.source == IMAP_SOURCE)).all()
        assert len(rows) == 1
        assert rows[0].external_id == "<ok@example.com>"

        state = session.exec(
            select(SyncState)
            .where(SyncState.source == IMAP_SOURCE)
            .where(SyncState.scope == IMAP_SCOPE_INBOX)
        ).one()
        assert state.cursor == "444:45"


def test_imap_connector_uses_ssl_and_parses_headers(monkeypatch) -> None:
    monkeypatch.setenv("EXECAS_IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("EXECAS_IMAP_USERNAME", "alice")
    monkeypatch.setenv("EXECAS_IMAP_PASSWORD", "secret")
    connector = ImapConnector.from_env()

    calls: dict[str, str] = {}

    class _ImapStub:
        def __init__(self, host: str, port: int, timeout: float):
            calls["init"] = f"{host}:{port}:{timeout}"

        def login(self, username: str, password: str):
            calls["login"] = f"{username}:{password}"
            return "OK", [b"Logged in"]

        def select(self, mailbox: str, readonly: bool = False):
            calls["select"] = f"{mailbox}:{readonly}"
            return "OK", [b"1"]

        def status(self, mailbox: str, criteria: str):
            calls["status"] = f"{mailbox}:{criteria}"
            return "OK", [b"INBOX (UIDVALIDITY 555 UIDNEXT 102)"]

        def uid(self, command: str, *args):
            if command == "SEARCH":
                return "OK", [b"101"]
            if command == "FETCH":
                return (
                    "OK",
                    [
                        (
                            b'101 (UID 101 FLAGS (\\Seen) BODY[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM DATE)] {126}',
                            (
                                b"Message-ID: <x@example.com>\r\n"
                                b"Subject: =?utf-8?B?VGVzdA==?=\r\n"
                                b"From: Alice <alice@example.com>\r\n"
                                b"Date: Thu, 20 Feb 2026 10:00:00 +0300\r\n\r\n"
                            ),
                        ),
                        b")",
                    ],
                )
            raise AssertionError(command)

        def logout(self):
            calls["logout"] = "1"
            return "BYE", [b"Logged out"]

    monkeypatch.setattr("executive_cli.connectors.imap.imaplib.IMAP4_SSL", _ImapStub)

    batch = connector.fetch_headers(mailbox="INBOX", cursor_uidvalidity=None, cursor_uidnext=None)
    assert calls["init"].startswith("imap.example.com:993:")
    assert calls["select"] == "INBOX:True"
    assert calls["status"] == "INBOX:(UIDVALIDITY UIDNEXT)"
    assert calls["logout"] == "1"
    assert batch.uidvalidity == 555
    assert batch.uidnext == 102
    assert len(batch.messages) == 1
    assert batch.messages[0].external_id == "<x@example.com>"
    assert batch.messages[0].subject == "Test"
    assert batch.messages[0].sender == "alice@example.com"
    assert batch.messages[0].received_at == datetime(2026, 2, 20, 7, 0, tzinfo=timezone.utc).isoformat()
    assert batch.messages[0].flags == ("\\Seen",)
