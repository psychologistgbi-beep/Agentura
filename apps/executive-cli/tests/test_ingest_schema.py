from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
import sqlalchemy as sa


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _migrated_engine(tmp_path, monkeypatch):
    db_path = tmp_path / "ingest_schema.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")

    return sa.create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )


def test_ingest_tables_present_with_expected_columns(tmp_path, monkeypatch) -> None:
    engine = _migrated_engine(tmp_path, monkeypatch)
    inspector = sa.inspect(engine)

    table_names = set(inspector.get_table_names())
    assert "ingest_documents" in table_names
    assert "task_drafts" in table_names
    assert "ingest_log" in table_names

    ingest_doc_columns = {col["name"] for col in inspector.get_columns("ingest_documents")}
    assert {"channel", "source_ref", "status", "items_extracted", "created_at", "processed_at"}.issubset(
        ingest_doc_columns
    )

    draft_columns = {col["name"] for col in inspector.get_columns("task_drafts")}
    assert {"confidence", "source_channel", "source_document_id", "source_email_id", "dedup_flag"}.issubset(
        draft_columns
    )

    ingest_log_columns = {col["name"] for col in inspector.get_columns("ingest_log")}
    assert {"document_id", "action", "task_id", "draft_id", "details_json"}.issubset(ingest_log_columns)

    with engine.connect() as conn:
        uq_sql = conn.execute(
            sa.text(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type='index' AND name='sqlite_autoindex_ingest_documents_1'
                """
            )
        ).scalar_one_or_none()
    assert uq_sql is None or "ingest_documents" in uq_sql
