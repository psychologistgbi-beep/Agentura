from __future__ import annotations

import imaplib
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from datetime import timezone
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from typing import Protocol

logger = logging.getLogger(__name__)


class MailConnectorError(RuntimeError):
    """Raised when mail sync connector cannot read remote headers."""


@dataclass(frozen=True)
class RemoteEmailHeader:
    external_id: str
    mailbox_uid: int
    subject: str | None = None
    sender: str | None = None
    received_at: str | None = None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class MailSyncBatch:
    messages: list[RemoteEmailHeader]
    uidvalidity: int
    uidnext: int


class MailConnector(Protocol):
    def fetch_headers(
        self,
        *,
        mailbox: str,
        cursor_uidvalidity: int | None,
        cursor_uidnext: int | None,
        received_since: date | None = None,
    ) -> MailSyncBatch: ...


@dataclass(frozen=True)
class ImapConnector:
    host: str
    username: str
    password: str
    port: int = 993
    timeout_sec: float = 20.0

    def __post_init__(self) -> None:
        if not self.host or not self.username or not self.password:
            raise MailConnectorError("IMAP connector is not configured.")
        if self.port <= 0:
            raise MailConnectorError("IMAP port is invalid.")

    @classmethod
    def from_env(cls) -> ImapConnector:
        host = os.getenv("EXECAS_IMAP_HOST", "").strip()
        username = os.getenv("EXECAS_IMAP_USERNAME", "").strip()
        password = os.getenv("EXECAS_IMAP_PASSWORD", "").strip()
        port_raw = os.getenv("EXECAS_IMAP_PORT", "993").strip()

        if not host or not username or not password:
            raise MailConnectorError(
                "IMAP connector is not configured. Set EXECAS_IMAP_HOST, EXECAS_IMAP_USERNAME, EXECAS_IMAP_PASSWORD."
            )

        try:
            port = int(port_raw)
        except ValueError as exc:
            raise MailConnectorError("IMAP port is invalid.") from exc
        if port <= 0:
            raise MailConnectorError("IMAP port is invalid.")

        return cls(host=host, username=username, password=password, port=port)

    def fetch_headers(
        self,
        *,
        mailbox: str,
        cursor_uidvalidity: int | None,
        cursor_uidnext: int | None,
        received_since: date | None = None,
    ) -> MailSyncBatch:
        try:
            client = imaplib.IMAP4_SSL(self.host, self.port, timeout=self.timeout_sec)
        except (OSError, TimeoutError):
            raise MailConnectorError("IMAP endpoint is unreachable.") from None

        try:
            try:
                client.login(self.username, self.password)
            except imaplib.IMAP4.error:
                logger.warning("imap_auth_failed mailbox=%s", mailbox)
                raise MailConnectorError("IMAP authentication failed.") from None

            status, _ = client.select(mailbox, readonly=True)
            if status != "OK":
                raise MailConnectorError("IMAP mailbox is unavailable.")

            uidvalidity, uidnext = self._read_uid_state(client, mailbox)
            full_resync = cursor_uidvalidity is None or cursor_uidvalidity != uidvalidity
            since_uid = None if full_resync else cursor_uidnext
            uids = self._search_uids(client, since_uid=since_uid, received_since=received_since)
            messages = [self._fetch_header(client, uid) for uid in uids]

            return MailSyncBatch(
                messages=messages,
                uidvalidity=uidvalidity,
                uidnext=uidnext,
            )
        except MailConnectorError:
            raise
        except imaplib.IMAP4.error:
            raise MailConnectorError("IMAP request failed.") from None
        except (OSError, TimeoutError):
            raise MailConnectorError("IMAP endpoint is unreachable.") from None
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def _read_uid_state(self, client: imaplib.IMAP4_SSL, mailbox: str) -> tuple[int, int]:
        status, payload = client.status(mailbox, "(UIDVALIDITY UIDNEXT)")
        if status != "OK" or not payload or payload[0] is None:
            raise MailConnectorError("IMAP mailbox status request failed.")

        text = _decode_bytes(payload[0])
        uidvalidity = _extract_int_token(text, "UIDVALIDITY")
        uidnext = _extract_int_token(text, "UIDNEXT")
        if uidvalidity is None or uidnext is None:
            raise MailConnectorError("IMAP mailbox status response is invalid.")
        return uidvalidity, uidnext

    def _search_uids(
        self,
        client: imaplib.IMAP4_SSL,
        *,
        since_uid: int | None,
        received_since: date | None,
    ) -> list[int]:
        criteria_parts = ["1:*" if since_uid is None else f"{max(since_uid, 1)}:*"]
        if received_since is not None:
            criteria_parts.append(f"SINCE {received_since.strftime('%d-%b-%Y')}")
        criteria = " ".join(criteria_parts)
        status, payload = client.uid("SEARCH", None, criteria)
        if status != "OK":
            raise MailConnectorError("IMAP search request failed.")
        if not payload or payload[0] is None:
            return []

        uids: set[int] = set()
        for raw in payload[0].split():
            try:
                uid = int(raw)
            except ValueError:
                continue
            if uid > 0:
                uids.add(uid)
        return sorted(uids)

    def _fetch_header(self, client: imaplib.IMAP4_SSL, uid: int) -> RemoteEmailHeader:
        status, payload = client.uid(
            "FETCH",
            str(uid),
            "(UID FLAGS BODY.PEEK[HEADER.FIELDS (MESSAGE-ID SUBJECT FROM DATE)])",
        )
        if status != "OK" or payload is None:
            raise MailConnectorError("IMAP fetch request failed.")

        header_bytes = b""
        parsed_flags: tuple[str, ...] = ()
        for item in payload:
            if isinstance(item, tuple):
                meta = _decode_bytes(item[0])
                flags = _parse_flags(meta)
                if flags:
                    parsed_flags = flags
                value = item[1]
                if isinstance(value, bytes):
                    header_bytes += value
            elif isinstance(item, bytes):
                flags = _parse_flags(_decode_bytes(item))
                if flags:
                    parsed_flags = flags

        parsed = BytesParser(policy=default).parsebytes(header_bytes)
        subject = _decode_header_value(parsed.get("Subject"))
        sender_raw = parsed.get("From")
        sender = parseaddr(sender_raw)[1] if sender_raw else ""
        if not sender:
            sender = sender_raw or ""

        received_at = _parse_received_at(parsed.get("Date"))
        external_id = (parsed.get("Message-ID") or "").strip() or f"uid:{uid}"

        return RemoteEmailHeader(
            external_id=external_id,
            mailbox_uid=uid,
            subject=subject or None,
            sender=sender.strip() or None,
            received_at=received_at,
            flags=parsed_flags,
        )


def _decode_bytes(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _extract_int_token(payload: str, key: str) -> int | None:
    match = re.search(rf"\b{re.escape(key)}\s+(\d+)\b", payload)
    if match is None:
        return None
    return int(match.group(1))


def _parse_flags(fetch_payload_text: str) -> tuple[str, ...]:
    match = re.search(r"FLAGS\s*\(([^)]*)\)", fetch_payload_text)
    if match is None:
        return ()
    raw_flags = match.group(1).strip()
    if not raw_flags:
        return ()
    return tuple(sorted(set(raw_flags.split())))


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except (ValueError, TypeError):
        return value.strip()


def _parse_received_at(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()
