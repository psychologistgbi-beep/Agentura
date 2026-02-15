from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone as _utc_tz

from sqlmodel import Session, select

from executive_cli.connectors.caldav import CalendarConnector
from executive_cli.db import PRIMARY_CALENDAR_SLUG
from executive_cli.models import BusyBlock, Calendar, SyncState
from executive_cli.timeutil import dt_to_db

CALDAV_SOURCE = "yandex_caldav"
CALDAV_SCOPE_PRIMARY = "primary"


@dataclass(frozen=True)
class CalendarSyncResult:
    inserted: int
    updated: int
    skipped: int
    soft_deleted: int
    cursor: str | None
    cursor_kind: str | None


def sync_calendar_primary(
    session: Session,
    *,
    connector: CalendarConnector,
) -> CalendarSyncResult:
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

    batch = connector.fetch_events(
        calendar_slug=calendar.slug,
        cursor=cursor,
        cursor_kind=cursor_kind,
        timezone_name=calendar.timezone,
    )

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
        raise

    return CalendarSyncResult(
        inserted=inserted,
        updated=updated,
        skipped=skipped,
        soft_deleted=soft_deleted,
        cursor=batch.cursor,
        cursor_kind=batch.cursor_kind,
    )

