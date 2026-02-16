from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr
from executive_cli.secret_store import (
    DEFAULT_CALDAV_KEYCHAIN_SERVICE,
    load_password_from_keychain,
)

logger = logging.getLogger(__name__)
_SYNC_LOOKBACK_DAYS = 30
_SYNC_LOOKAHEAD_DAYS = 365


class CalendarConnectorError(RuntimeError):
    """Raised when calendar sync connector cannot read remote events."""


@dataclass(frozen=True)
class RemoteCalendarEvent:
    external_id: str
    start_dt: datetime
    end_dt: datetime
    title: str | None = None
    external_etag: str | None = None
    external_modified_at: str | None = None


@dataclass(frozen=True)
class CalendarSyncBatch:
    events: list[RemoteCalendarEvent]
    cursor: str | None
    cursor_kind: str | None
    full_snapshot: bool
    deleted_external_ids: tuple[str, ...] = ()
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None


class CalendarConnector(Protocol):
    def fetch_events(
        self,
        *,
        calendar_slug: str,
        cursor: str | None,
        cursor_kind: str | None,
        timezone_name: str,
    ) -> CalendarSyncBatch: ...


@dataclass(frozen=True)
class CalDavConnector:
    base_url: str
    username: str
    password: str
    timeout_sec: float = 20.0

    _NS_DAV = "DAV:"
    _NS_CALDAV = "urn:ietf:params:xml:ns:caldav"
    _NS_CALSERVER = "http://calendarserver.org/ns/"

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme.lower() != "https":
            raise CalendarConnectorError("CalDAV URL must use https://")

    @classmethod
    def from_env(cls) -> CalDavConnector:
        base_url = os.getenv("EXECAS_CALDAV_URL", "").strip()
        username = os.getenv("EXECAS_CALDAV_USERNAME", "").strip()
        password = os.getenv("EXECAS_CALDAV_PASSWORD", "").strip()
        if not password and username:
            password = (
                load_password_from_keychain(
                    account=username,
                    env_service_var="EXECAS_CALDAV_KEYCHAIN_SERVICE",
                    default_service=DEFAULT_CALDAV_KEYCHAIN_SERVICE,
                )
                or ""
            )

        if not base_url or not username or not password:
            raise CalendarConnectorError(
                "CalDAV connector is not configured. Set EXECAS_CALDAV_URL, EXECAS_CALDAV_USERNAME and "
                "EXECAS_CALDAV_PASSWORD, or store the password in macOS Keychain via "
                "'execas secret set-caldav'."
            )

        return cls(base_url=base_url, username=username, password=password)

    def fetch_events(
        self,
        *,
        calendar_slug: str,
        cursor: str | None,
        cursor_kind: str | None,
        timezone_name: str,
    ) -> CalendarSyncBatch:
        del calendar_slug
        window_start, window_end = _build_sync_window()
        collection_urls = self._resolve_collection_urls()
        ctag_parts: list[str] = []
        for collection_url in collection_urls:
            collection_props = self._fetch_collection_props(collection_url=collection_url)
            ctag_value = collection_props.get("ctag") or "-"
            ctag_parts.append(f"{collection_url}::{ctag_value}")

        multi_cursor = "|".join(sorted(ctag_parts)) if ctag_parts else None
        multi_cursor_kind = "multi_ctag" if len(collection_urls) > 1 else "ctag"

        if multi_cursor and cursor and cursor_kind == multi_cursor_kind and cursor == multi_cursor:
            return CalendarSyncBatch(
                events=[],
                cursor=multi_cursor,
                cursor_kind=multi_cursor_kind,
                full_snapshot=False,
            )

        events_by_external_id: dict[str, RemoteCalendarEvent] = {}
        for collection_url in collection_urls:
            collection_events = self._fetch_full_snapshot(
                collection_url=collection_url,
                timezone_name=timezone_name,
                window_start=window_start,
                window_end=window_end,
                external_id_prefix=_collection_identity(collection_url),
            )
            for event in collection_events:
                events_by_external_id[event.external_id] = event

        return CalendarSyncBatch(
            events=sorted(events_by_external_id.values(), key=lambda event: event.external_id),
            cursor=multi_cursor,
            cursor_kind=multi_cursor_kind if multi_cursor else cursor_kind,
            full_snapshot=True,
            coverage_start=window_start,
            coverage_end=window_end,
        )

    def _resolve_collection_urls(self) -> list[str]:
        parsed = urlparse(self.base_url)
        if parsed.path and parsed.path != "/":
            return [self.base_url]

        calendar_home_url = self._discover_calendar_home_url(self.base_url)
        if calendar_home_url is None:
            raise CalendarConnectorError(
                "CalDAV calendar-home-set discovery failed. Check endpoint settings."
            )
        collection_urls = self._discover_calendar_collections(calendar_home_url)
        if not collection_urls:
            fallback = self._discover_primary_collection_url(calendar_home_url)
            if fallback is None:
                raise CalendarConnectorError("CalDAV calendar collection discovery failed.")
            return [fallback]
        return collection_urls

    def _resolve_collection_url(self) -> str:
        urls = self._resolve_collection_urls()
        return urls[0]

    def _discover_calendar_home_url(self, root_url: str) -> str | None:
        root_body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:current-user-principal />
    <c:calendar-home-set />
  </d:prop>
</d:propfind>
"""
        payload = self._request_xml_url(root_url, method="PROPFIND", depth="0", body=root_body)
        root = self._parse_xml(payload)

        calendar_home_href = self._extract_first_href(
            root, f"{{{self._NS_CALDAV}}}calendar-home-set/{{{self._NS_DAV}}}href"
        )
        if calendar_home_href:
            return urljoin(root_url, calendar_home_href)

        principal_href = self._extract_first_href(
            root, f"{{{self._NS_DAV}}}current-user-principal/{{{self._NS_DAV}}}href"
        )
        if not principal_href:
            return None

        principal_url = urljoin(root_url, principal_href)
        principal_body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <c:calendar-home-set />
  </d:prop>
</d:propfind>
"""
        principal_payload = self._request_xml_url(
            principal_url, method="PROPFIND", depth="0", body=principal_body
        )
        principal_root = self._parse_xml(principal_payload)
        principal_home_href = self._extract_first_href(
            principal_root, f"{{{self._NS_CALDAV}}}calendar-home-set/{{{self._NS_DAV}}}href"
        )
        if not principal_home_href:
            return None
        return urljoin(principal_url, principal_home_href)

    def _discover_primary_collection_url(self, calendar_home_url: str) -> str | None:
        collections = self._discover_calendar_collections(calendar_home_url)
        if collections:
            return collections[0]

        return None

    def _discover_calendar_collections(self, calendar_home_url: str) -> list[str]:
        body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:resourcetype />
    <d:displayname />
    <c:supported-calendar-component-set />
  </d:prop>
</d:propfind>
"""
        payload = self._request_xml_url(calendar_home_url, method="PROPFIND", depth="1", body=body)
        root = self._parse_xml(payload)

        candidates: list[tuple[str, str, bool]] = []
        for response in root.findall(f".//{{{self._NS_DAV}}}response"):
            href = (response.findtext(f"{{{self._NS_DAV}}}href") or "").strip()
            if not href:
                continue

            is_calendar = False
            supports_vevent = False
            display_name = ""
            for propstat in response.findall(f"{{{self._NS_DAV}}}propstat"):
                status = (propstat.findtext(f"{{{self._NS_DAV}}}status") or "").strip()
                if "200" not in status:
                    continue
                prop = propstat.find(f"{{{self._NS_DAV}}}prop")
                if prop is None:
                    continue

                resource_type = prop.find(f"{{{self._NS_DAV}}}resourcetype")
                if resource_type is not None and resource_type.find(f"{{{self._NS_CALDAV}}}calendar") is not None:
                    is_calendar = True
                if not display_name:
                    display_name = (prop.findtext(f"{{{self._NS_DAV}}}displayname") or "").strip()
                supported = prop.find(f"{{{self._NS_CALDAV}}}supported-calendar-component-set")
                if supported is not None:
                    for comp in supported.findall(f"{{{self._NS_CALDAV}}}comp"):
                        if (comp.attrib.get("name") or "").upper() == "VEVENT":
                            supports_vevent = True

            if not is_calendar:
                continue
            candidates.append((urljoin(calendar_home_url, href), display_name, supports_vevent))

        if not candidates:
            return []

        def _rank(item: tuple[str, str, bool]) -> tuple[int, int, int, str]:
            url, display_name, supports_vevent = item
            path = urlparse(url).path.rstrip("/").lower()
            display_norm = display_name.strip().lower()
            prefer_vevent = 0 if supports_vevent else 1
            prefer_events_path = 0 if path.endswith("/events") else 1
            prefer_primary_name = 0 if display_norm in {"primary", "default", "main"} else 1
            return (prefer_vevent, prefer_events_path, prefer_primary_name, path)

        sorted_candidates = sorted(candidates, key=_rank)
        event_collections = [url for url, _name, supports_vevent in sorted_candidates if supports_vevent]
        if event_collections:
            return event_collections
        return [sorted_candidates[0][0]]

    def _extract_first_href(self, root: ET.Element, path: str) -> str | None:
        for prop in root.findall(f".//{{{self._NS_DAV}}}prop"):
            href = (prop.findtext(path) or "").strip()
            if href:
                return href
        return None

    def _parse_xml(self, payload: bytes) -> ET.Element:
        try:
            return ET.fromstring(payload)
        except ET.ParseError:
            raise CalendarConnectorError("CalDAV response is invalid.") from None

    def _fetch_collection_props(self, *, collection_url: str | None = None) -> dict[str, str]:
        body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:cs="http://calendarserver.org/ns/">
  <d:prop>
    <cs:getctag />
    <d:sync-token />
  </d:prop>
</d:propfind>
"""
        target_url = collection_url or self.base_url
        if target_url == self.base_url:
            payload = self._request_xml(method="PROPFIND", depth="0", body=body)
        else:
            payload = self._request_xml_url(
                target_url,
                method="PROPFIND",
                depth="0",
                body=body,
            )
        root = self._parse_xml(payload)

        ctag: str | None = None
        sync_token: str | None = None
        for prop in root.findall(f".//{{{self._NS_DAV}}}prop"):
            for node in list(prop):
                local_name = node.tag.split("}", maxsplit=1)[-1]
                value = (node.text or "").strip()
                if not value:
                    continue
                if local_name == "getctag":
                    ctag = value
                elif local_name == "sync-token":
                    sync_token = value

        result: dict[str, str] = {}
        if ctag:
            result["ctag"] = ctag
        if sync_token:
            result["sync_token"] = sync_token
        return result

    def _fetch_full_snapshot(
        self,
        *,
        timezone_name: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        external_id_prefix: str = "",
        collection_url: str | None = None,
    ) -> list[RemoteCalendarEvent]:
        body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:getetag />
    <c:calendar-data />
  </d:prop>
</d:propfind>
"""
        target_url = collection_url or self.base_url
        if target_url == self.base_url:
            payload = self._request_xml(method="PROPFIND", depth="1", body=body)
        else:
            payload = self._request_xml_url(
                target_url,
                method="PROPFIND",
                depth="1",
                body=body,
            )
        root = self._parse_xml(payload)

        try:
            default_timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            default_timezone = timezone.utc
        window_start_value = window_start or datetime.min.replace(tzinfo=timezone.utc)
        window_end_value = window_end or datetime.max.replace(tzinfo=timezone.utc)

        events_by_external_id: dict[str, RemoteCalendarEvent] = {}
        for response in root.findall(f".//{{{self._NS_DAV}}}response"):
            etag, calendar_data = self._extract_event_payload(response)
            if calendar_data is None:
                continue

            for item in _parse_ical_events(
                calendar_data=calendar_data,
                default_timezone=default_timezone,
                window_start=window_start_value,
                window_end=window_end_value,
                external_id_prefix=external_id_prefix,
            ):
                event = RemoteCalendarEvent(
                    external_id=item.external_id,
                    start_dt=item.start_dt,
                    end_dt=item.end_dt,
                    title=item.title,
                    external_etag=etag,
                    external_modified_at=item.external_modified_at,
                )
                events_by_external_id[event.external_id] = event

        return sorted(events_by_external_id.values(), key=lambda event: event.external_id)

    def _extract_event_payload(self, response: ET.Element) -> tuple[str | None, str | None]:
        etag: str | None = None
        calendar_data: str | None = None
        for propstat in response.findall(f"{{{self._NS_DAV}}}propstat"):
            status = (propstat.findtext(f"{{{self._NS_DAV}}}status") or "").strip()
            if "200" not in status:
                continue

            prop = propstat.find(f"{{{self._NS_DAV}}}prop")
            if prop is None:
                continue
            etag = (prop.findtext(f"{{{self._NS_DAV}}}getetag") or "").strip() or etag
            calendar_data = (
                (prop.findtext(f"{{{self._NS_CALDAV}}}calendar-data") or "").strip() or calendar_data
            )

        return etag, calendar_data

    def _request_xml(self, *, method: str, depth: str, body: str) -> bytes:
        return self._request_xml_url(self.base_url, method=method, depth=depth, body=body)

    def _request_xml_url(self, url: str, *, method: str, depth: str, body: str) -> bytes:
        auth = base64.b64encode(f"{self.username}:{self.password}".encode("utf-8")).decode("ascii")
        request = Request(
            url,
            data=body.encode("utf-8"),
            method=method,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/xml; charset=utf-8",
                "Depth": depth,
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code in (401, 403):
                logger.warning("caldav_auth_failed status=%s", exc.code)
                raise CalendarConnectorError("CalDAV authentication failed.") from None
            raise CalendarConnectorError(f"CalDAV request failed with HTTP {exc.code}.") from None
        except URLError:
            raise CalendarConnectorError("CalDAV endpoint is unreachable.") from None
        except TimeoutError:
            raise CalendarConnectorError("CalDAV request timed out.") from None


@dataclass(frozen=True)
class _ParsedEvent:
    external_id: str
    start_dt: datetime
    end_dt: datetime
    title: str | None
    external_modified_at: str | None


_FieldValue = tuple[dict[str, str], str]


def _build_sync_window() -> tuple[datetime, datetime]:
    now_utc = datetime.now(timezone.utc)
    return (now_utc - timedelta(days=_SYNC_LOOKBACK_DAYS), now_utc + timedelta(days=_SYNC_LOOKAHEAD_DAYS))


def _parse_ical_events(
    *,
    calendar_data: str,
    default_timezone: ZoneInfo | timezone,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    external_id_prefix: str = "",
) -> list[_ParsedEvent]:
    window_start_value = window_start or datetime.min.replace(tzinfo=timezone.utc)
    window_end_value = window_end or datetime.max.replace(tzinfo=timezone.utc)
    lines = _unfold_ical_lines(calendar_data)
    events: list[_ParsedEvent] = []
    in_event = False
    current_lines: list[str] = []

    for line in lines:
        upper = line.strip().upper()
        if upper == "BEGIN:VEVENT":
            in_event = True
            current_lines = []
            continue
        if upper == "END:VEVENT":
            events.extend(
                _parse_event_instances(
                    current_lines,
                    default_timezone=default_timezone,
                    window_start=window_start_value,
                    window_end=window_end_value,
                    external_id_prefix=external_id_prefix,
                )
            )
            in_event = False
            current_lines = []
            continue
        if in_event:
            current_lines.append(line)

    return events


def _unfold_ical_lines(calendar_data: str) -> list[str]:
    raw_lines = calendar_data.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []
    for line in raw_lines:
        if not line:
            continue
        if line[0] in {" ", "\t"} and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_event_fields(lines: list[str]) -> dict[str, list[_FieldValue]]:
    values: dict[str, list[_FieldValue]] = {}
    for line in lines:
        if ":" not in line:
            continue
        raw_name, raw_value = line.split(":", maxsplit=1)
        parts = raw_name.split(";")
        name = parts[0].upper()
        params: dict[str, str] = {}
        for item in parts[1:]:
            if "=" not in item:
                continue
            key, value = item.split("=", maxsplit=1)
            params[key.upper()] = value.strip('"')
        values.setdefault(name, []).append((params, raw_value))
    return values


def _first_field(values: dict[str, list[_FieldValue]], name: str) -> _FieldValue | None:
    options = values.get(name.upper())
    if not options:
        return None
    return options[0]


def _all_fields(values: dict[str, list[_FieldValue]], name: str) -> list[_FieldValue]:
    return values.get(name.upper(), [])


def _parse_event_instances(
    lines: list[str],
    *,
    default_timezone: ZoneInfo | timezone,
    window_start: datetime,
    window_end: datetime,
    external_id_prefix: str = "",
) -> list[_ParsedEvent]:
    values = _parse_event_fields(lines)

    uid_field = _first_field(values, "UID")
    uid = (uid_field[1] if uid_field else "").strip()
    if not uid:
        return []

    dtstart_field = _first_field(values, "DTSTART")
    dtstart = _parse_ical_dt(dtstart_field, default_timezone=default_timezone)
    if dtstart is None:
        return []
    dtend = _parse_ical_dt(_first_field(values, "DTEND"), default_timezone=default_timezone)
    if dtend is None:
        dtend = _fallback_end_dt(dtstart_field, dtstart)
    if dtstart >= dtend:
        return []

    title_field = _first_field(values, "SUMMARY")
    title_raw = title_field[1].strip() if title_field else ""
    title = _decode_ical_text(title_raw) if title_raw else None

    modified = _parse_ical_dt(_first_field(values, "LAST-MODIFIED"), default_timezone=default_timezone)
    if modified is None:
        modified = _parse_ical_dt(_first_field(values, "DTSTAMP"), default_timezone=default_timezone)
    modified_iso = modified.astimezone(timezone.utc).isoformat() if modified is not None else None

    recurrence_id_field = _first_field(values, "RECURRENCE-ID")
    if recurrence_id_field is not None:
        recurrence_id = _parse_ical_dt(recurrence_id_field, default_timezone=default_timezone)
        recurrence_component = (
            _format_recurrence_component(recurrence_id)
            if recurrence_id is not None
            else recurrence_id_field[1].strip()
        )
        instance = _ParsedEvent(
            external_id=f"{external_id_prefix}{uid};{recurrence_component}",
            start_dt=dtstart,
            end_dt=dtend,
            title=title,
            external_modified_at=modified_iso,
        )
        return [instance] if _is_overlapping_window(instance.start_dt, instance.end_dt, window_start, window_end) else []

    rrule_field = _first_field(values, "RRULE")
    rdate_fields = _all_fields(values, "RDATE")
    if rrule_field is None and not rdate_fields:
        instance = _ParsedEvent(
            external_id=f"{external_id_prefix}{uid}",
            start_dt=dtstart,
            end_dt=dtend,
            title=title,
            external_modified_at=modified_iso,
        )
        return [instance] if _is_overlapping_window(instance.start_dt, instance.end_dt, window_start, window_end) else []

    duration = dtend - dtstart
    excluded_occurrences_utc = {
        ex.astimezone(timezone.utc).replace(microsecond=0)
        for field in _all_fields(values, "EXDATE")
        for ex in _parse_ical_dt_list(field, default_timezone=default_timezone)
    }

    instances_by_external_id: dict[str, _ParsedEvent] = {}

    if rrule_field is not None:
        rule_text = rrule_field[1].strip()
        if rule_text:
            try:
                rule = rrulestr(rule_text, dtstart=dtstart)
                occurrence_starts = rule.between(window_start - duration, window_end, inc=True)
                for occurrence_start in occurrence_starts:
                    if _is_excluded_occurrence(occurrence_start, excluded_occurrences_utc):
                        continue
                    occurrence_end = occurrence_start + duration
                    if not _is_overlapping_window(occurrence_start, occurrence_end, window_start, window_end):
                        continue
                    external_id = f"{external_id_prefix}{uid};{_format_recurrence_component(occurrence_start)}"
                    instances_by_external_id[external_id] = _ParsedEvent(
                        external_id=external_id,
                        start_dt=occurrence_start,
                        end_dt=occurrence_end,
                        title=title,
                        external_modified_at=modified_iso,
                    )
            except Exception:
                logger.warning("caldav_rrule_parse_failed uid=%s", uid)

    for field in rdate_fields:
        for occurrence_start in _parse_ical_dt_list(field, default_timezone=default_timezone):
            if _is_excluded_occurrence(occurrence_start, excluded_occurrences_utc):
                continue
            occurrence_end = occurrence_start + duration
            if not _is_overlapping_window(occurrence_start, occurrence_end, window_start, window_end):
                continue
            external_id = f"{external_id_prefix}{uid};{_format_recurrence_component(occurrence_start)}"
            instances_by_external_id[external_id] = _ParsedEvent(
                external_id=external_id,
                start_dt=occurrence_start,
                end_dt=occurrence_end,
                title=title,
                external_modified_at=modified_iso,
            )

    return sorted(instances_by_external_id.values(), key=lambda item: item.start_dt)


def _parse_ical_dt_list(
    field: _FieldValue,
    *,
    default_timezone: ZoneInfo | timezone,
) -> list[datetime]:
    params, raw_value = field
    values: list[datetime] = []
    for chunk in raw_value.split(","):
        dt = _parse_ical_dt((params, chunk), default_timezone=default_timezone)
        if dt is not None:
            values.append(dt)
    return values


def _is_overlapping_window(start_dt: datetime, end_dt: datetime, window_start: datetime, window_end: datetime) -> bool:
    return end_dt > window_start and start_dt < window_end


def _is_excluded_occurrence(occurrence_start: datetime, excluded_utc: set[datetime]) -> bool:
    return occurrence_start.astimezone(timezone.utc).replace(microsecond=0) in excluded_utc


def _format_recurrence_component(occurrence_start: datetime) -> str:
    return occurrence_start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _collection_identity(collection_url: str) -> str:
    path = urlparse(collection_url).path.rstrip("/")
    return f"{path}|"


def _parse_ical_dt(
    field: tuple[dict[str, str], str] | None,
    *,
    default_timezone: ZoneInfo | timezone,
) -> datetime | None:
    if field is None:
        return None
    params, raw_value = field
    value = raw_value.strip()
    if not value:
        return None

    if "T" not in value:
        local_date = datetime.strptime(value, "%Y%m%d").date()
        return datetime.combine(local_date, time.min, tzinfo=default_timezone)

    if value.endswith("Z"):
        dt = _parse_ical_time_fragment(value[:-1])
        return dt.replace(tzinfo=timezone.utc)

    dt = _parse_ical_time_fragment(value)
    tzid = params.get("TZID")
    if tzid:
        try:
            return dt.replace(tzinfo=ZoneInfo(tzid))
        except ZoneInfoNotFoundError:
            return dt.replace(tzinfo=default_timezone)
    return dt.replace(tzinfo=default_timezone)


def _parse_ical_time_fragment(value: str) -> datetime:
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported iCal datetime value: {value}")


def _fallback_end_dt(
    dtstart_field: tuple[dict[str, str], str] | None,
    start_dt: datetime,
) -> datetime:
    if dtstart_field is None:
        return start_dt + timedelta(hours=1)
    raw_value = dtstart_field[1].strip()
    if "T" not in raw_value:
        return start_dt + timedelta(days=1)
    return start_dt + timedelta(hours=1)


def _decode_ical_text(raw: str) -> str:
    value = raw.replace("\\n", "\n").replace("\\N", "\n")
    value = value.replace("\\,", ",").replace("\\;", ";")
    value = value.replace("\\\\", "\\")
    return value
