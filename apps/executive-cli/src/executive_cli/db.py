from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlmodel import Session, create_engine, select

from executive_cli.models import Calendar, Settings

DEFAULT_SETTINGS: dict[str, str] = {
    "timezone": "Europe/Moscow",
    "planning_start": "07:00",
    "planning_end": "19:00",
    "lunch_start": "12:00",
    "lunch_duration_min": "60",
    "min_focus_block_min": "30",
    "buffer_min": "5",
}
PRIMARY_CALENDAR_SLUG = "primary"
PRIMARY_CALENDAR_NAME = "Primary"


# /apps/executive-cli/src/executive_cli/db.py -> /apps/executive-cli
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / ".data" / "execas.sqlite"


def get_db_path() -> Path:
    db_path_env = os.getenv("EXECAS_DB_PATH")
    if not db_path_env:
        return DEFAULT_DB_PATH

    candidate = Path(db_path_env).expanduser()
    if candidate.is_absolute():
        return candidate
    return (Path.cwd() / candidate).resolve()


def ensure_db_directory() -> Path:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_database_url(*, ensure_directory: bool = False) -> str:
    db_path = ensure_db_directory() if ensure_directory else get_db_path()
    return f"sqlite:///{db_path}"


def get_engine(*, ensure_directory: bool = False):
    return create_engine(
        get_database_url(ensure_directory=ensure_directory),
        connect_args={"check_same_thread": False},
    )


def apply_migrations() -> None:
    ensure_db_directory()

    alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", get_database_url(ensure_directory=True))
    command.upgrade(alembic_cfg, "head")


def seed_defaults() -> None:
    engine = get_engine(ensure_directory=True)

    with Session(engine) as session:
        for key, value in DEFAULT_SETTINGS.items():
            existing = session.get(Settings, key)
            if existing is None:
                session.add(Settings(key=key, value=value))

        timezone_setting = session.get(Settings, "timezone")
        timezone = timezone_setting.value if timezone_setting is not None else DEFAULT_SETTINGS["timezone"]

        primary_calendar = session.exec(
            select(Calendar).where(Calendar.slug == PRIMARY_CALENDAR_SLUG)
        ).first()
        if primary_calendar is None:
            session.add(
                Calendar(
                    slug=PRIMARY_CALENDAR_SLUG,
                    name=PRIMARY_CALENDAR_NAME,
                    timezone=timezone,
                )
            )

        session.commit()


def initialize_database() -> Path:
    apply_migrations()
    seed_defaults()
    return get_db_path()
