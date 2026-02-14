from datetime import datetime

from executive_cli.busy_service import MergedBusyBlock, merge_busy_blocks
from executive_cli.models import BusyBlock
from executive_cli.timeutil import MOSCOW_TZ


def busy_block(id: int, start: str, end: str, title: str) -> BusyBlock:
    return BusyBlock(
        id=id,
        calendar_id=1,
        start_dt=start,
        end_dt=end,
        title=title,
    )


def iso_dt(hour: int, minute: int) -> str:
    return datetime(2024, 1, 1, hour, minute, tzinfo=MOSCOW_TZ).isoformat()


def test_merge_overlapping_blocks() -> None:
    blocks = [
        busy_block(1, iso_dt(10, 0), iso_dt(11, 0), "A"),
        busy_block(2, iso_dt(10, 30), iso_dt(12, 0), "B"),
    ]

    merged = merge_busy_blocks(blocks)

    assert merged == [
        MergedBusyBlock(
            start_dt=datetime(2024, 1, 1, 10, 0, tzinfo=MOSCOW_TZ),
            end_dt=datetime(2024, 1, 1, 12, 0, tzinfo=MOSCOW_TZ),
            title_parts=["A", "B"],
        )
    ]
    assert merged[0].title == "A | B"


def test_merge_adjacent_blocks() -> None:
    blocks = [
        busy_block(1, iso_dt(14, 0), iso_dt(14, 30), "X"),
        busy_block(2, iso_dt(14, 30), iso_dt(15, 0), "Y"),
    ]

    merged = merge_busy_blocks(blocks)

    assert merged == [
        MergedBusyBlock(
            start_dt=datetime(2024, 1, 1, 14, 0, tzinfo=MOSCOW_TZ),
            end_dt=datetime(2024, 1, 1, 15, 0, tzinfo=MOSCOW_TZ),
            title_parts=["X", "Y"],
        )
    ]
    assert merged[0].title == "X | Y"


def test_merge_empty_returns_empty_list() -> None:
    assert merge_busy_blocks([]) == []
