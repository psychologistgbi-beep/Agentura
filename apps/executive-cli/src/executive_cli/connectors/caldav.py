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

logger = logging.getLogger(__name__)


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

        if not base_url or not username or not password:
            raise CalendarConnectorError(
                "CalDAV connector is not configured. Set EXECAS_CALDAV_URL, EXECAS_CALDAV_USERNAME, EXECAS_CALDAV_PASSWORD."
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
        collection_url = self._resolve_collection_url()
        collection_props = self._fetch_collection_props(collection_url=collection_url)
        ctag = collection_props.get("ctag")

        if ctag and cursor and cursor_kind == "ctag" and cursor == ctag:
            return CalendarSyncBatch(
                events=[],
                cursor=ctag,
                cursor_kind="ctag",
                full_snapshot=False,
            )

        events = self._fetch_full_snapshot(collection_url=collection_url, timezone_name=timezone_name)
        return CalendarSyncBatch(
            events=events,
            cursor=ctag,
            cursor_kind="ctag" if ctag else cursor_kind,
            full_snapshot=True,
        )

    def _resolve_collection_url(self) -> str:
        parsed = urlparse(self.base_url)
        # If caller passed a concrete path, treat it as a collection URL.
        if parsed.path and parsed.path != "/":
            return self.base_url

        calendar_home_url = self._discover_calendar_home_url(self.base_url)
        if calendar_home_url is None:
            raise CalendarConnectorError(
                "CalDAV calendar-home-set discovery failed. Check endpoint settings."
            )

        collection_url = self._discover_primary_collection_url(calendar_home_url)
        if collection_url is None:
            raise CalendarConnectorError("CalDAV calendar collection discovery failed.")
        return collection_url

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
        body = """<?xml version="1.0" encoding="utf-8"?>
<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:prop>
    <d:resourcetype />
    <d:displayname />
  </d:prop>
</d:propfind>
"""
        payload = self._request_xml_url(calendar_home_url, method="PROPFIND", depth="1", body=body)
        root = self._parse_xml(payload)

        candidates: list[tuple[str, str]] = []
        for response in root.findall(f".//{{{self._NS_DAV}}}response"):
            href = (response.findtext(f"{{{self._NS_DAV}}}href") or "").strip()
            if not href:
                continue

            is_calendar = False
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

            if not is_calendar:
                continue
            candidates.append((urljoin(calendar_home_url, href), display_name))

        if not candidates:
            return None

        def _rank(item: tuple[str, str]) -> tuple[int, int, str]:
            url, display_name = item
            path = urlparse(url).path.rstrip("/").lower()
            display_norm = display_name.strip().lower()
            prefer_events_path = 0 if path.endswith("/events") else 1
            prefer_primary_name = 0 if display_norm in {"primary", "default", "main"} else 1
            return (prefer_events_path, prefer_primary_name, path)

        return sorted(candidates, key=_rank)[0][0]

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

        events_by_external_id: dict[str, RemoteCalendarEvent] = {}
        for response in root.findall(f".//{{{self._NS_DAV}}}response"):
            etag, calendar_data = self._extract_event_payload(response)
            if calendar_data is None:
                continue

            for item in _parse_ical_events(calendar_data=calendar_data, default_timezone=default_timezone):
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


def _parse_ical_events(*, calendar_data: str, default_timezone: ZoneInfo | timezone) -> list[_ParsedEvent]:
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
            parsed = _parse_single_event(current_lines, default_timezone=default_timezone)
            if parsed is not None:
                events.append(parsed)
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


def _parse_single_event(
    lines: list[str],
    *,
    default_timezone: ZoneInfo | timezone,
) -> _ParsedEvent | None:
    values: dict[str, tuple[dict[str, str], str]] = {}
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
        values[name] = (params, raw_value)

    uid = (values.get("UID", ({}, ""))[1] or "").strip()
    if not uid:
        return None

    dtstart = _parse_ical_dt(values.get("DTSTART"), default_timezone=default_timezone)
    if dtstart is None:
        return None
    dtend = _parse_ical_dt(values.get("DTEND"), default_timezone=default_timezone)
    if dtend is None:
        dtend = _fallback_end_dt(values.get("DTSTART"), dtstart)
    if dtstart >= dtend:
        return None

    recurrence_id_raw = (values.get("RECURRENCE-ID", ({}, ""))[1] or "").strip()
    external_id = uid if not recurrence_id_raw else f"{uid};{recurrence_id_raw}"

    title_raw = values.get("SUMMARY", ({}, ""))[1].strip()
    title = _decode_ical_text(title_raw) if title_raw else None

    modified = _parse_ical_dt(values.get("LAST-MODIFIED"), default_timezone=default_timezone)
    if modified is None:
        modified = _parse_ical_dt(values.get("DTSTAMP"), default_timezone=default_timezone)
    modified_iso = modified.astimezone(timezone.utc).isoformat() if modified is not None else None

    return _ParsedEvent(
        external_id=external_id,
        start_dt=dtstart,
        end_dt=dtend,
        title=title,
        external_modified_at=modified_iso,
    )


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
