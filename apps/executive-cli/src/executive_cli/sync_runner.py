from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from dataclasses import dataclass
import logging
import time

from executive_cli.connectors.caldav import CalendarConnectorError
from executive_cli.connectors.imap import MailConnectorError

logger = logging.getLogger(__name__)

SyncOperation = Callable[[], object]
SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class SourceSyncOutcome:
    source: str
    success: bool
    attempts: int
    reason: str | None = None
    elapsed_sec: float = 0.0


@dataclass(frozen=True)
class HourlySyncOutcome:
    calendar: SourceSyncOutcome
    mail: SourceSyncOutcome
    elapsed_sec: float = 0.0

    @property
    def exit_code(self) -> int:
        if self.calendar.success and self.mail.success:
            return 0
        if self.calendar.success or self.mail.success:
            return 2
        return 1


def run_hourly_sync(
    *,
    run_calendar: SyncOperation,
    run_mail: SyncOperation,
    retries: int = 2,
    backoff_sec: int = 5,
    sleep_fn: SleepFn = time.sleep,
    parallel: bool = True,
) -> HourlySyncOutcome:
    if retries < 0:
        raise ValueError("--retries must be >= 0.")
    if backoff_sec < 0:
        raise ValueError("--backoff-sec must be >= 0.")

    started_at = time.perf_counter()
    if parallel:
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="execas-sync") as pool:
            calendar_future = pool.submit(
                _run_source,
                source="calendar",
                operation=run_calendar,
                retries=retries,
                backoff_sec=backoff_sec,
                sleep_fn=sleep_fn,
            )
            mail_future = pool.submit(
                _run_source,
                source="mail",
                operation=run_mail,
                retries=retries,
                backoff_sec=backoff_sec,
                sleep_fn=sleep_fn,
            )
            calendar_outcome = calendar_future.result()
            mail_outcome = mail_future.result()
    else:
        calendar_outcome = _run_source(
            source="calendar",
            operation=run_calendar,
            retries=retries,
            backoff_sec=backoff_sec,
            sleep_fn=sleep_fn,
        )
        mail_outcome = _run_source(
            source="mail",
            operation=run_mail,
            retries=retries,
            backoff_sec=backoff_sec,
            sleep_fn=sleep_fn,
        )
    return HourlySyncOutcome(
        calendar=calendar_outcome,
        mail=mail_outcome,
        elapsed_sec=time.perf_counter() - started_at,
    )


def _run_source(
    *,
    source: str,
    operation: SyncOperation,
    retries: int,
    backoff_sec: int,
    sleep_fn: SleepFn,
) -> SourceSyncOutcome:
    started_at = time.perf_counter()
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            operation()
            return SourceSyncOutcome(
                source=source,
                success=True,
                attempts=attempt + 1,
                elapsed_sec=time.perf_counter() - started_at,
            )
        except Exception as exc:
            last_error = exc
            logger.warning(
                "hourly_sync_source_attempt_failed source=%s attempt=%s retries=%s error_type=%s",
                source,
                attempt + 1,
                retries,
                exc.__class__.__name__,
            )
            if attempt == retries:
                break
            delay_sec = backoff_sec * (2**attempt)
            logger.info(
                "hourly_sync_source_retrying source=%s next_attempt=%s backoff_sec=%s",
                source,
                attempt + 2,
                delay_sec,
            )
            sleep_fn(float(delay_sec))

    assert last_error is not None
    return SourceSyncOutcome(
        source=source,
        success=False,
        attempts=retries + 1,
        reason=_sanitize_reason(source=source, error=last_error),
        elapsed_sec=time.perf_counter() - started_at,
    )


def _sanitize_reason(*, source: str, error: Exception) -> str:
    if isinstance(error, CalendarConnectorError):
        return "calendar connector unavailable"
    if isinstance(error, MailConnectorError):
        return "mail connector unavailable"
    if isinstance(error, ValueError):
        return f"{source} validation failed"
    return f"{source} unexpected {error.__class__.__name__}"
