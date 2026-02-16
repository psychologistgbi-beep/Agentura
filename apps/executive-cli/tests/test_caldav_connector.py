from __future__ import annotations

from datetime import datetime, timezone
from urllib.error import HTTPError, URLError

import pytest

from executive_cli.connectors.caldav import (
    CalDavConnector,
    CalendarConnectorError,
    RemoteCalendarEvent,
    _build_sync_window,
    _decode_ical_text,
    _parse_ical_events,
    _parse_ical_time_fragment,
)


class _ResponseStub:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


def test_from_env_requires_all_credentials(monkeypatch) -> None:
    monkeypatch.delenv("EXECAS_CALDAV_URL", raising=False)
    monkeypatch.delenv("EXECAS_CALDAV_USERNAME", raising=False)
    monkeypatch.delenv("EXECAS_CALDAV_PASSWORD", raising=False)
    monkeypatch.setattr("executive_cli.connectors.caldav.load_password_from_keychain", lambda **kwargs: None)

    with pytest.raises(CalendarConnectorError, match="not configured"):
        CalDavConnector.from_env()


def test_from_env_rejects_http_url(monkeypatch) -> None:
    monkeypatch.setenv("EXECAS_CALDAV_URL", "http://calendar.example/dav")
    monkeypatch.setenv("EXECAS_CALDAV_USERNAME", "alice")
    monkeypatch.setenv("EXECAS_CALDAV_PASSWORD", "secret")

    with pytest.raises(CalendarConnectorError, match="https://"):
        CalDavConnector.from_env()


def test_from_env_loads_password_from_keychain_when_env_missing(monkeypatch) -> None:
    monkeypatch.setenv("EXECAS_CALDAV_URL", "https://caldav.example.com")
    monkeypatch.setenv("EXECAS_CALDAV_USERNAME", "alice@example.com")
    monkeypatch.delenv("EXECAS_CALDAV_PASSWORD", raising=False)
    monkeypatch.setattr(
        "executive_cli.connectors.caldav.load_password_from_keychain",
        lambda **kwargs: "secret-from-keychain",
    )

    connector = CalDavConnector.from_env()
    assert connector.password == "secret-from-keychain"


def test_build_sync_window_uses_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("EXECAS_CALDAV_SYNC_LOOKBACK_DAYS", "7")
    monkeypatch.setenv("EXECAS_CALDAV_SYNC_LOOKAHEAD_DAYS", "21")

    window_start, window_end = _build_sync_window()
    now_utc = datetime.now(timezone.utc)

    assert abs((now_utc - window_start).total_seconds() - (7 * 86400)) < 120
    assert abs((window_end - now_utc).total_seconds() - (21 * 86400)) < 120


def test_build_sync_window_invalid_env_falls_back_to_defaults(monkeypatch) -> None:
    monkeypatch.setenv("EXECAS_CALDAV_SYNC_LOOKBACK_DAYS", "-5")
    monkeypatch.setenv("EXECAS_CALDAV_SYNC_LOOKAHEAD_DAYS", "bad-value")

    window_start, window_end = _build_sync_window()
    now_utc = datetime.now(timezone.utc)

    assert abs((now_utc - window_start).total_seconds() - (30 * 86400)) < 120
    assert abs((window_end - now_utc).total_seconds() - (365 * 86400)) < 120


def test_fetch_events_short_circuits_when_ctag_unchanged(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://calendar.example/dav",
        username="alice",
        password="secret",
    )
    monkeypatch.setattr(CalDavConnector, "_resolve_collection_urls", lambda self: [self.base_url])
    monkeypatch.setattr(
        CalDavConnector,
        "_fetch_collection_props",
        lambda self, *, collection_url=None: {"ctag": "ctag-1"},
    )

    def _unexpected(
        self,
        *,
        timezone_name: str,
        window_start=None,
        window_end=None,
        external_id_prefix: str = "",
        collection_url: str | None = None,
    ):
        del collection_url, window_start, window_end, external_id_prefix
        raise AssertionError(f"full snapshot should not be called for {timezone_name}")

    monkeypatch.setattr(CalDavConnector, "_fetch_full_snapshot", _unexpected)

    batch = connector.fetch_events(
        calendar_slug="primary",
        cursor="https://calendar.example/dav::ctag-1",
        cursor_kind="ctag",
        timezone_name="Europe/Moscow",
    )

    assert batch.events == []
    assert batch.cursor == "https://calendar.example/dav::ctag-1"
    assert batch.cursor_kind == "ctag"
    assert batch.full_snapshot is False


def test_fetch_events_returns_full_snapshot_when_needed(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://calendar.example/dav",
        username="alice",
        password="secret",
    )
    monkeypatch.setattr(CalDavConnector, "_resolve_collection_urls", lambda self: [self.base_url])
    monkeypatch.setattr(
        CalDavConnector,
        "_fetch_collection_props",
        lambda self, *, collection_url=None: {"ctag": "ctag-2"},
    )
    monkeypatch.setattr(
        CalDavConnector,
        "_fetch_full_snapshot",
        lambda self, *, timezone_name, window_start=None, window_end=None, external_id_prefix="", collection_url=None: [
            RemoteCalendarEvent(
                external_id=f"{external_id_prefix}uid-1",
                start_dt=datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc),
                end_dt=datetime(2026, 2, 20, 11, 0, tzinfo=timezone.utc),
                title="Meeting",
                external_etag="e1",
                external_modified_at="2026-02-20T09:00:00+00:00",
            )
        ],
    )

    batch = connector.fetch_events(
        calendar_slug="primary",
        cursor="ctag-1",
        cursor_kind="ctag",
        timezone_name="Europe/Moscow",
    )
    assert len(batch.events) == 1
    assert batch.cursor == "https://calendar.example/dav::ctag-2"
    assert batch.cursor_kind == "ctag"
    assert batch.full_snapshot is True
    assert batch.coverage_start is not None
    assert batch.coverage_end is not None


def test_fetch_events_resolves_collection_from_root_endpoint(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://caldav.yandex.ru",
        username="alice",
        password="secret",
    )
    expected_collection_url = "https://caldav.yandex.ru/calendars/alice/events/"
    monkeypatch.setattr(CalDavConnector, "_resolve_collection_urls", lambda self: [expected_collection_url])

    observed_collection_urls: list[str] = []

    def _props(self, *, collection_url=None):
        assert collection_url is not None
        observed_collection_urls.append(collection_url)
        return {"ctag": "ctag-9"}

    def _snapshot(
        self,
        *,
        timezone_name: str,
        window_start=None,
        window_end=None,
        external_id_prefix: str = "",
        collection_url: str | None = None,
    ):
        del timezone_name, window_start, window_end, external_id_prefix
        assert collection_url is not None
        observed_collection_urls.append(collection_url)
        return []

    monkeypatch.setattr(CalDavConnector, "_fetch_collection_props", _props)
    monkeypatch.setattr(CalDavConnector, "_fetch_full_snapshot", _snapshot)

    batch = connector.fetch_events(
        calendar_slug="primary",
        cursor="ctag-old",
        cursor_kind="ctag",
        timezone_name="Europe/Moscow",
    )

    assert batch.full_snapshot is True
    assert observed_collection_urls == [expected_collection_url, expected_collection_url]


def test_resolve_collection_url_discovers_events_collection(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://caldav.yandex.ru",
        username="alice",
        password="secret",
    )
    discovery_payload = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:propstat>
      <d:status>HTTP/1.1 200 OK</d:status>
      <d:prop>
        <d:current-user-principal>
          <d:href>/principals/users/alice/</d:href>
        </d:current-user-principal>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>
"""
    principal_payload = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:propstat>
      <d:status>HTTP/1.1 200 OK</d:status>
      <d:prop>
        <c:calendar-home-set>
          <d:href>/calendars/alice/</d:href>
        </c:calendar-home-set>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>
"""
    calendars_payload = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/calendars/alice/work/</d:href>
    <d:propstat>
      <d:status>HTTP/1.1 200 OK</d:status>
      <d:prop>
        <d:resourcetype><d:collection /><c:calendar /></d:resourcetype>
        <d:displayname>Work</d:displayname>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/calendars/alice/events/</d:href>
    <d:propstat>
      <d:status>HTTP/1.1 200 OK</d:status>
      <d:prop>
        <d:resourcetype><d:collection /><c:calendar /></d:resourcetype>
        <d:displayname>Primary</d:displayname>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>
"""

    def _request(self, url: str, *, method: str, depth: str, body: str):
        del method, body
        if url == "https://caldav.yandex.ru" and depth == "0":
            return discovery_payload
        if url == "https://caldav.yandex.ru/principals/users/alice/" and depth == "0":
            return principal_payload
        if url == "https://caldav.yandex.ru/calendars/alice/" and depth == "1":
            return calendars_payload
        raise AssertionError(f"Unexpected request: {url} depth={depth}")

    monkeypatch.setattr(CalDavConnector, "_request_xml_url", _request)

    collection_url = connector._resolve_collection_url()
    assert collection_url == "https://caldav.yandex.ru/calendars/alice/events/"


def test_resolve_collection_urls_prefers_vevent_supported_collections(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://caldav.yandex.ru",
        username="alice",
        password="secret",
    )
    monkeypatch.setattr(
        CalDavConnector,
        "_discover_calendar_home_url",
        lambda self, root_url: "https://caldav.yandex.ru/calendars/alice/",
    )
    monkeypatch.setattr(
        CalDavConnector,
        "_discover_calendar_collections",
        lambda self, home: [
            "https://caldav.yandex.ru/calendars/alice/events-main/",
            "https://caldav.yandex.ru/calendars/alice/events-personal/",
        ],
    )

    urls = connector._resolve_collection_urls()
    assert urls == [
        "https://caldav.yandex.ru/calendars/alice/events-main/",
        "https://caldav.yandex.ru/calendars/alice/events-personal/",
    ]


def test_fetch_collection_props_parses_ctag_and_sync_token(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://calendar.example/dav",
        username="alice",
        password="secret",
    )
    payload = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:" xmlns:cs="http://calendarserver.org/ns/">
  <d:response>
    <d:propstat>
      <d:status>HTTP/1.1 200 OK</d:status>
      <d:prop>
        <cs:getctag>ctag-99</cs:getctag>
        <d:sync-token>token-abc</d:sync-token>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>
"""
    monkeypatch.setattr(
        CalDavConnector,
        "_request_xml",
        lambda self, *, method, depth, body: payload,
    )

    props = connector._fetch_collection_props()
    assert props == {"ctag": "ctag-99", "sync_token": "token-abc"}


def test_fetch_full_snapshot_parses_events(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://calendar.example/dav",
        username="alice",
        password="secret",
    )
    payload = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:propstat>
      <d:status>HTTP/1.1 200 OK</d:status>
      <d:prop>
        <d:getetag>"etag-1"</d:getetag>
        <c:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid-1
DTSTART;TZID=Europe/Moscow:20260220T100000
DTEND;TZID=Europe/Moscow:20260220T110000
SUMMARY:Plan\\, sync
LAST-MODIFIED:20260220T070000Z
END:VEVENT
BEGIN:VEVENT
UID:uid-2
RECURRENCE-ID:20260221T100000Z
DTSTART:20260221T100000Z
DTEND:20260221T110000Z
SUMMARY:Recurring
DTSTAMP:20260220T060000Z
END:VEVENT
END:VCALENDAR</c:calendar-data>
      </d:prop>
    </d:propstat>
  </d:response>
  <d:response>
    <d:propstat>
      <d:status>HTTP/1.1 404 Not Found</d:status>
      <d:prop>
        <d:getetag>"ignored"</d:getetag>
        <c:calendar-data>BEGIN:VCALENDAR</c:calendar-data>
      </d:prop>
    </d:propstat>
  </d:response>
</d:multistatus>
"""
    monkeypatch.setattr(
        CalDavConnector,
        "_request_xml",
        lambda self, *, method, depth, body: payload,
    )

    events = connector._fetch_full_snapshot(timezone_name="Europe/Moscow")
    assert [event.external_id for event in events] == ["uid-1", "uid-2;20260221T100000Z"]
    assert events[0].title == "Plan, sync"
    assert events[0].external_etag == '"etag-1"'
    assert events[1].external_modified_at == "2026-02-20T06:00:00+00:00"


def test_parse_ical_events_handles_unfolding_and_fallback_end() -> None:
    calendar_data = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid-3
DTSTART;VALUE=DATE:20260222
SUMMARY:Long\\ntext
  continued
END:VEVENT
END:VCALENDAR
"""
    events = _parse_ical_events(calendar_data=calendar_data, default_timezone=timezone.utc)
    assert len(events) == 1
    assert events[0].external_id == "uid-3"
    assert events[0].start_dt.isoformat() == "2026-02-22T00:00:00+00:00"
    assert events[0].end_dt.isoformat() == "2026-02-23T00:00:00+00:00"
    assert events[0].title == "Long\ntext continued"


def test_parse_ical_events_expands_weekly_rrule_in_window() -> None:
    calendar_data = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid-weekly
DTSTART:20260209T080000Z
DTEND:20260209T083000Z
SUMMARY:YFlow
RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;INTERVAL=1
END:VEVENT
END:VCALENDAR
"""
    events = _parse_ical_events(
        calendar_data=calendar_data,
        default_timezone=timezone.utc,
        window_start=datetime(2026, 2, 16, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 2, 23, 0, 0, tzinfo=timezone.utc),
    )

    assert [event.external_id for event in events] == [
        "uid-weekly;20260216T080000Z",
        "uid-weekly;20260218T080000Z",
        "uid-weekly;20260220T080000Z",
    ]
    assert [event.title for event in events] == ["YFlow", "YFlow", "YFlow"]


def test_parse_ical_events_rrule_respects_exdate() -> None:
    calendar_data = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:uid-exdate
DTSTART:20260216T093000Z
DTEND:20260216T100000Z
SUMMARY:Текучка
RRULE:FREQ=DAILY;INTERVAL=1
EXDATE:20260217T093000Z
END:VEVENT
END:VCALENDAR
"""
    events = _parse_ical_events(
        calendar_data=calendar_data,
        default_timezone=timezone.utc,
        window_start=datetime(2026, 2, 16, 0, 0, tzinfo=timezone.utc),
        window_end=datetime(2026, 2, 19, 0, 0, tzinfo=timezone.utc),
    )

    assert [event.external_id for event in events] == [
        "uid-exdate;20260216T093000Z",
        "uid-exdate;20260218T093000Z",
    ]


def test_parse_ical_events_skips_invalid_or_missing_uid() -> None:
    calendar_data = """BEGIN:VCALENDAR
BEGIN:VEVENT
DTSTART:20260220T120000Z
DTEND:20260220T110000Z
SUMMARY:Bad interval
END:VEVENT
BEGIN:VEVENT
DTSTART:20260220T120000Z
DTEND:20260220T130000Z
END:VEVENT
END:VCALENDAR
"""
    events = _parse_ical_events(calendar_data=calendar_data, default_timezone=timezone.utc)
    assert events == []


def test_parse_ical_time_fragment_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="Unsupported iCal datetime value"):
        _parse_ical_time_fragment("2026-02-20 10:00")


def test_decode_ical_text_unescapes_sequences() -> None:
    assert _decode_ical_text(r"Line1\nLine2\,x\;y\\z") == "Line1\nLine2,x;y\\z"


def test_request_xml_maps_transport_errors(monkeypatch) -> None:
    connector = CalDavConnector(
        base_url="https://calendar.example/dav",
        username="alice",
        password="secret",
    )

    monkeypatch.setattr(
        "executive_cli.connectors.caldav.urlopen",
        lambda request, timeout: _ResponseStub(b"<ok/>"),
    )
    assert connector._request_xml(method="PROPFIND", depth="0", body="<x/>") == b"<ok/>"

    def _raise_401(request, timeout):
        raise HTTPError(request.full_url, 401, "unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("executive_cli.connectors.caldav.urlopen", _raise_401)
    with pytest.raises(CalendarConnectorError, match="authentication failed"):
        connector._request_xml(method="PROPFIND", depth="0", body="<x/>")

    def _raise_500(request, timeout):
        raise HTTPError(request.full_url, 500, "server error", hdrs=None, fp=None)

    monkeypatch.setattr("executive_cli.connectors.caldav.urlopen", _raise_500)
    with pytest.raises(CalendarConnectorError, match="HTTP 500"):
        connector._request_xml(method="PROPFIND", depth="0", body="<x/>")

    monkeypatch.setattr(
        "executive_cli.connectors.caldav.urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("down")),
    )
    with pytest.raises(CalendarConnectorError, match="unreachable"):
        connector._request_xml(method="PROPFIND", depth="0", body="<x/>")

    monkeypatch.setattr(
        "executive_cli.connectors.caldav.urlopen",
        lambda request, timeout: (_ for _ in ()).throw(TimeoutError("slow")),
    )
    with pytest.raises(CalendarConnectorError, match="timed out"):
        connector._request_xml(method="PROPFIND", depth="0", body="<x/>")
