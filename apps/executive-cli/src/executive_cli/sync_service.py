from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as _utc_tz
import json
import logging

from sqlmodel import Session, select

from executive_cli.connectors.caldav import CalendarConnector
from executive_cli.connectors.imap import MailConnector
from executive_cli.db import PRIMARY_CALENDAR_SLUG
from executive_cli.models import BusyBlock, Calendar, Email, SyncState
from executive_cli.timeutil import dt_to_db

logger = logging.getLogger(__name__)

CALDAV_SOURCE = "yandex_caldav"
CALDAV_SCOPE_PRIMARY = "primary"
IMAP_SOURCE = "yandex_imap"
IMAP_SCOPE_INBOX = "INBOX"
IMAP_CURSOR_KIND_UID = "uidvalidity_uidnext"


@dataclass(frozen=True)
class CalendarSyncResult:
    inserted: int
    updated: int
    skipped: int
    soft_deleted: int
    cursor: str | None
    cursor_kind: str | None


@dataclass(frozen=True)
class MailSyncResult:
    inserted: int
    updated: int
    cursor: str
    cursor_kind: str


def sync_calendar_primary(
    session: Session,
    *,
    connector: CalendarConnector,
) -> CalendarSyncResult:
    logger.info(
        "calendar_sync_started source=%s scope=%s",
        CALDAV_SOURCE,
        CALDAV_SCOPE_PRIMARY,
    )
    calendar = session.exec(select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)).first()
    if calendar is None:
        raise ValueError("Primary calendar is not initialized. Run 'execas init' first.")

    state = session.exec(
        select(SyncState)
        .where(SyncState.source == CALDAV_SOURCE)
        .where(SyncState.scope == CALDAV_SCOPE_PRIMARY)
    ).first()
    cursor = state.cursor if state is not None else None
    cursor_kind = state.cursor_kind if state is not None else None

    try:
        batch = connector.fetch_events(
            calendar_slug=calendar.slug,
            cursor=cursor,
            cursor_kind=cursor_kind,
            timezone_name=calendar.timezone,
        )
    except Exception:
        logger.error(
            "calendar_sync_failed source=%s scope=%s stage=fetch",
            CALDAV_SOURCE,
            CALDAV_SCOPE_PRIMARY,
        )
        raise

    existing_rows = session.exec(
        select(BusyBlock)
        .where(BusyBlock.calendar_id == calendar.id)
        .where(BusyBlock.source == CALDAV_SOURCE)
    ).all()
    existing_by_external_id = {
        row.external_id: row for row in existing_rows if row.external_id is not None
    }

    inserted = 0
    updated = 0
    skipped = 0
    soft_deleted = 0
    seen_external_ids: set[str] = set()

    try:
        for event in batch.events:
            if event.start_dt >= event.end_dt:
                raise ValueError(f"Invalid interval for event {event.external_id}: start_dt >= end_dt")

            seen_external_ids.add(event.external_id)
            existing = existing_by_external_id.get(event.external_id)
            if existing is None:
                row = BusyBlock(
                    calendar_id=calendar.id,
                    start_dt=dt_to_db(event.start_dt),
                    end_dt=dt_to_db(event.end_dt),
                    title=event.title,
                    source=CALDAV_SOURCE,
                    external_id=event.external_id,
                    external_etag=event.external_etag,
                    external_modified_at=event.external_modified_at,
                    is_deleted=0,
                )
                session.add(row)
                existing_by_external_id[event.external_id] = row
                inserted += 1
                continue

            if existing.external_etag == event.external_etag and existing.is_deleted == 0:
                skipped += 1
                continue

            existing.start_dt = dt_to_db(event.start_dt)
            existing.end_dt = dt_to_db(event.end_dt)
            existing.title = event.title
            existing.external_etag = event.external_etag
            existing.external_modified_at = event.external_modified_at
            existing.is_deleted = 0
            session.add(existing)
            updated += 1

        if batch.full_snapshot:
            for row in existing_rows:
                if row.external_id is None:
                    continue
                if row.external_id in seen_external_ids:
                    continue
                if row.is_deleted == 0:
                    row.is_deleted = 1
                    session.add(row)
                    soft_deleted += 1
        else:
            for external_id in batch.deleted_external_ids:
                row = existing_by_external_id.get(external_id)
                if row is None:
                    continue
                if row.is_deleted == 1:
                    continue
                row.is_deleted = 1
                session.add(row)
                soft_deleted += 1

        updated_at = datetime.now(_utc_tz.utc).isoformat()
        if state is None:
            state = SyncState(
                source=CALDAV_SOURCE,
                scope=CALDAV_SCOPE_PRIMARY,
                cursor=batch.cursor,
                cursor_kind=batch.cursor_kind,
                updated_at=updated_at,
            )
            session.add(state)
        else:
            state.cursor = batch.cursor
            state.cursor_kind = batch.cursor_kind
            state.updated_at = updated_at
            session.add(state)

        session.commit()
    except Exception:
        session.rollback()
        logger.error(
            "calendar_sync_failed source=%s scope=%s",
            CALDAV_SOURCE,
            CALDAV_SCOPE_PRIMARY,
        )
        raise

    logger.info(
        "calendar_sync_completed source=%s scope=%s inserted=%s updated=%s skipped=%s soft_deleted=%s",
        CALDAV_SOURCE,
        CALDAV_SCOPE_PRIMARY,
        inserted,
        updated,
        skipped,
        soft_deleted,
    )

    return CalendarSyncResult(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        soft_deleted=soft_deleted,
        cursor=batch.cursor,
        cursor_kind=batch.cursor_kind,
    )


def sync_mailbox(
    session: Session,
    *,
    connector: MailConnector,
    mailbox: str = IMAP_SCOPE_INBOX,
) -> MailSyncResult:
    scope = mailbox.strip() or IMAP_SCOPE_INBOX
    logger.info("mail_sync_started source=%s scope=%s", IMAP_SOURCE, scope)
    state = session.exec(
        select(SyncState)
        .where(SyncState.source == IMAP_SOURCE)
        .where(SyncState.scope == scope)
    ).first()
    cursor_uidvalidity, cursor_uidnext = _parse_uid_cursor(state.cursor if state is not None else None)

    try:
        batch = connector.fetch_headers(
            mailbox=scope,
            cursor_uidvalidity=cursor_uidvalidity,
            cursor_uidnext=cursor_uidnext,
        )
    except Exception:
        logger.error("mail_sync_failed source=%s scope=%s stage=fetch", IMAP_SOURCE, scope)
        raise
    if cursor_uidvalidity is not None and cursor_uidvalidity != batch.uidvalidity:
        logger.warning(
            "mail_sync_uidvalidity_changed source=%s scope=%s",
            IMAP_SOURCE,
            scope,
        )
    new_cursor = f"{batch.uidvalidity}:{batch.uidnext}"
    now_iso = datetime.now(_utc_tz.utc).isoformat()

    existing_rows = session.exec(
        select(Email)
        .where(Email.source == IMAP_SOURCE)
    ).all()
    existing_by_external_id = {row.external_id: row for row in existing_rows}

    # If a provider serves duplicate Message-ID entries in one batch, keep the latest UID.
    deduped_messages = {
        message.external_id: message
        for message in sorted(batch.messages, key=lambda message: message.mailbox_uid)
        if message.external_id
    }

    inserted = 0
    updated = 0
    try:
        for message in deduped_messages.values():
            if message.mailbox_uid <= 0:
                raise ValueError("Email mailbox UID must be > 0.")

            flags_json = json.dumps(list(message.flags))
            existing = existing_by_external_id.get(message.external_id)
            if existing is None:
                row = Email(
                    source=IMAP_SOURCE,
                    external_id=message.external_id,
                    mailbox_uid=message.mailbox_uid,
                    subject=message.subject,
                    sender=message.sender,
                    received_at=message.received_at,
                    first_seen_at=now_iso,
                    last_seen_at=now_iso,
                    flags_json=flags_json,
                )
                session.add(row)
                existing_by_external_id[message.external_id] = row
                inserted += 1
                continue

            existing.mailbox_uid = message.mailbox_uid
            existing.subject = message.subject
            existing.sender = message.sender
            existing.received_at = message.received_at
            existing.last_seen_at = now_iso
            existing.flags_json = flags_json
            session.add(existing)
            updated += 1

        if state is None:
            state = SyncState(
                source=IMAP_SOURCE,
                scope=scope,
                cursor=new_cursor,
                cursor_kind=IMAP_CURSOR_KIND_UID,
                updated_at=now_iso,
            )
            session.add(state)
        else:
            state.cursor = new_cursor
            state.cursor_kind = IMAP_CURSOR_KIND_UID
            state.updated_at = now_iso
            session.add(state)

        session.commit()
    except Exception:
        session.rollback()
        logger.error("mail_sync_failed source=%s scope=%s", IMAP_SOURCE, scope)
        raise

    logger.info(
        "mail_sync_completed source=%s scope=%s inserted=%s updated=%s",
        IMAP_SOURCE,
        scope,
        inserted,
        updated,
    )

    return MailSyncResult(
        inserted=inserted,
        updated=updated,
        cursor=new_cursor,
        cursor_kind=IMAP_CURSOR_KIND_UID,
    )


def _parse_uid_cursor(cursor: str | None) -> tuple[int | None, int | None]:
    if cursor is None:
        return None, None

    parts = cursor.split(":", maxsplit=1)
    if len(parts) != 2:
        return None, None

    try:
        uidvalidity = int(parts[0])
        uidnext = int(parts[1])
    except ValueError:
        return None, None

    if uidvalidity <= 0 or uidnext <= 0:
        return None, None
    return uidvalidity, uidnext
