from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from executive_cli.models import BusyBlock


@dataclass
class MergedBusyBlock:
    start_dt: datetime
    end_dt: datetime
    title_parts: list[str]

    @property
    def title(self) -> str:
        return " | ".join(self.title_parts)


def merge_busy_blocks(rows: list[BusyBlock]) -> list[MergedBusyBlock]:
    parsed_rows = sorted(
        rows,
        key=lambda row: (
            datetime.fromisoformat(row.start_dt),
            row.id if row.id is not None else -1,
        ),
    )

    merged: list[MergedBusyBlock] = []
    for row in parsed_rows:
        start_dt = datetime.fromisoformat(row.start_dt)
        end_dt = datetime.fromisoformat(row.end_dt)
        row_title = row.title or "(untitled)"

        if not merged:
            merged.append(MergedBusyBlock(start_dt=start_dt, end_dt=end_dt, title_parts=[row_title]))
            continue

        current = merged[-1]
        if start_dt <= current.end_dt:
            if end_dt > current.end_dt:
                current.end_dt = end_dt
            current.title_parts.append(row_title)
            continue

        merged.append(MergedBusyBlock(start_dt=start_dt, end_dt=end_dt, title_parts=[row_title]))

    return merged
