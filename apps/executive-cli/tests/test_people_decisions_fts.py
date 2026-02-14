from __future__ import annotations

import sqlalchemy as sa
from sqlmodel import Session, SQLModel, create_engine, select
from typer.testing import CliRunner

from executive_cli.cli import app
from executive_cli.models import Decision, Person

runner = CliRunner()


def _create_engine(tmp_path):
    db_path = tmp_path / "fts_test.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    # FTS5 virtual tables and triggers (mirroring migration)
    with engine.connect() as conn:
        conn.execute(sa.text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS people_fts USING fts5("
            "name, role, context, "
            "content='people', content_rowid='id'"
            ")"
        ))
        conn.execute(sa.text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5("
            "title, body, "
            "content='decisions', content_rowid='id'"
            ")"
        ))
        # people triggers
        conn.execute(sa.text(
            "CREATE TRIGGER IF NOT EXISTS people_ai AFTER INSERT ON people BEGIN "
            "INSERT INTO people_fts(rowid, name, role, context) "
            "VALUES (new.id, new.name, new.role, new.context); "
            "END;"
        ))
        conn.execute(sa.text(
            "CREATE TRIGGER IF NOT EXISTS people_ad AFTER DELETE ON people BEGIN "
            "INSERT INTO people_fts(people_fts, rowid, name, role, context) "
            "VALUES ('delete', old.id, old.name, old.role, old.context); "
            "END;"
        ))
        conn.execute(sa.text(
            "CREATE TRIGGER IF NOT EXISTS people_au AFTER UPDATE ON people BEGIN "
            "INSERT INTO people_fts(people_fts, rowid, name, role, context) "
            "VALUES ('delete', old.id, old.name, old.role, old.context); "
            "INSERT INTO people_fts(rowid, name, role, context) "
            "VALUES (new.id, new.name, new.role, new.context); "
            "END;"
        ))
        # decisions triggers
        conn.execute(sa.text(
            "CREATE TRIGGER IF NOT EXISTS decisions_ai AFTER INSERT ON decisions BEGIN "
            "INSERT INTO decisions_fts(rowid, title, body) "
            "VALUES (new.id, new.title, new.body); "
            "END;"
        ))
        conn.execute(sa.text(
            "CREATE TRIGGER IF NOT EXISTS decisions_ad AFTER DELETE ON decisions BEGIN "
            "INSERT INTO decisions_fts(decisions_fts, rowid, title, body) "
            "VALUES ('delete', old.id, old.title, old.body); "
            "END;"
        ))
        conn.execute(sa.text(
            "CREATE TRIGGER IF NOT EXISTS decisions_au AFTER UPDATE ON decisions BEGIN "
            "INSERT INTO decisions_fts(decisions_fts, rowid, title, body) "
            "VALUES ('delete', old.id, old.title, old.body); "
            "INSERT INTO decisions_fts(rowid, title, body) "
            "VALUES (new.id, new.title, new.body); "
            "END;"
        ))
        conn.commit()
    return engine


def _fts_search_people(session: Session, query: str) -> list[Person]:
    return list(session.exec(
        select(Person).where(
            Person.id.in_(  # type: ignore[union-attr]
                select(sa.column("rowid"))
                .select_from(sa.text("people_fts"))
                .where(sa.text("people_fts MATCH :q"))
            )
        ).params(q=query)
    ).all())


def _fts_search_decisions(session: Session, query: str) -> list[Decision]:
    return list(session.exec(
        select(Decision).where(
            Decision.id.in_(  # type: ignore[union-attr]
                select(sa.column("rowid"))
                .select_from(sa.text("decisions_fts"))
                .where(sa.text("decisions_fts MATCH :q"))
            )
        ).params(q=query)
    ).all())


def test_people_insert_and_fts_search(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        session.add(Person(name="Alice Johnson", role="CTO", context="Leads engineering"))
        session.add(Person(name="Bob Martin", role="Designer", context="UI/UX expert"))
        session.commit()

    with Session(engine) as session:
        results = _fts_search_people(session, "Alice")
        assert len(results) == 1
        assert results[0].name == "Alice Johnson"

        results = _fts_search_people(session, "engineering")
        assert len(results) == 1
        assert results[0].name == "Alice Johnson"

        results = _fts_search_people(session, "Designer")
        assert len(results) == 1
        assert results[0].name == "Bob Martin"

        results = _fts_search_people(session, "nonexistent")
        assert len(results) == 0


def test_decisions_insert_and_fts_search(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        session.add(Decision(
            title="Adopt microservices architecture",
            body="Better scalability for growing team",
        ))
        session.add(Decision(
            title="Use SQLite for MVP",
            body="Simple deployment, sufficient for single-user CLI",
        ))
        session.commit()

    with Session(engine) as session:
        results = _fts_search_decisions(session, "microservices")
        assert len(results) == 1
        assert results[0].title == "Adopt microservices architecture"

        results = _fts_search_decisions(session, "SQLite")
        assert len(results) == 1
        assert results[0].title == "Use SQLite for MVP"

        results = _fts_search_decisions(session, "scalability")
        assert len(results) == 1
        assert results[0].title == "Adopt microservices architecture"

        results = _fts_search_decisions(session, "nonexistent")
        assert len(results) == 0


def test_people_fts_updates_after_update(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        person = Person(name="Charlie Brown", role="Intern", context="Summer program")
        session.add(person)
        session.commit()
        session.refresh(person)
        person_id = person.id

    # Verify initial search works
    with Session(engine) as session:
        results = _fts_search_people(session, "Intern")
        assert len(results) == 1

    # Update role
    with Session(engine) as session:
        person = session.get(Person, person_id)
        person.role = "Senior Engineer"
        session.commit()

    # Old term should no longer match; new term should
    with Session(engine) as session:
        results = _fts_search_people(session, "Intern")
        assert len(results) == 0

        results = _fts_search_people(session, "Senior")
        assert len(results) == 1
        assert results[0].name == "Charlie Brown"


def test_decisions_fts_updates_after_update(tmp_path) -> None:
    engine = _create_engine(tmp_path)

    with Session(engine) as session:
        decision = Decision(title="Use REST API", body="Standard approach")
        session.add(decision)
        session.commit()
        session.refresh(decision)
        decision_id = decision.id

    with Session(engine) as session:
        results = _fts_search_decisions(session, "REST")
        assert len(results) == 1

    # Update title
    with Session(engine) as session:
        decision = session.get(Decision, decision_id)
        decision.title = "Use GraphQL API"
        session.commit()

    with Session(engine) as session:
        results = _fts_search_decisions(session, "REST")
        assert len(results) == 0

        results = _fts_search_decisions(session, "GraphQL")
        assert len(results) == 1
        assert results[0].title == "Use GraphQL API"


# --- CLI flag / backward-compat tests ---


def _init_cli_db(tmp_path, monkeypatch):
    db_path = tmp_path / "cli.sqlite"
    monkeypatch.setenv("EXECAS_DB_PATH", str(db_path))
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0
    return db_path


def test_people_add_via_flag(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["people", "add", "--name", "Flag Person", "--role", "QA"])
    assert result.exit_code == 0
    assert "Flag Person" in result.output


def test_people_add_via_positional(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["people", "add", "Positional Person"])
    assert result.exit_code == 0
    assert "Positional Person" in result.output


def test_people_add_conflict(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["people", "add", "Both", "--name", "Both"])
    assert result.exit_code != 0


def test_people_add_missing(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["people", "add"])
    assert result.exit_code != 0


def test_decision_add_via_flag(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["decision", "add", "--title", "Flag Decision", "--body", "rationale"])
    assert result.exit_code == 0
    assert "Flag Decision" in result.output


def test_decision_add_via_positional(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["decision", "add", "Positional Decision"])
    assert result.exit_code == 0
    assert "Positional Decision" in result.output


def test_decision_add_conflict(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["decision", "add", "Both", "--title", "Both"])
    assert result.exit_code != 0


def test_decision_add_missing(tmp_path, monkeypatch) -> None:
    _init_cli_db(tmp_path, monkeypatch)
    result = runner.invoke(app, ["decision", "add"])
    assert result.exit_code != 0
