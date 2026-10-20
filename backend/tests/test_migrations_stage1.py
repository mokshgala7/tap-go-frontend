"""Stage 1 migration helper: unique provider_transaction_id, duplicate-safe and idempotent."""
import pytest
from sqlalchemy import create_engine, inspect, text

from app.main import ensure_unique_provider_transaction_index


def legacy_engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE transactions (id INTEGER PRIMARY KEY, reference TEXT, provider_transaction_id TEXT NULL)"))
    return eng


def test_no_table(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert ensure_unique_provider_transaction_index(eng) == "no_table"


def test_creates_the_index_when_clean_and_is_idempotent(tmp_path):
    eng = legacy_engine(tmp_path)
    with eng.begin() as c:
        c.execute(text("INSERT INTO transactions (reference, provider_transaction_id) VALUES ('a','p1'),('b','p2'),('c',NULL),('d',NULL)"))
    assert ensure_unique_provider_transaction_index(eng) == "created"
    assert ensure_unique_provider_transaction_index(eng) == "exists"
    assert any(i["unique"] and i["column_names"] == ["provider_transaction_id"] for i in inspect(eng).get_indexes("transactions"))
    with pytest.raises(Exception):
        with eng.begin() as c:
            c.execute(text("INSERT INTO transactions (reference, provider_transaction_id) VALUES ('e','p1')"))


def test_duplicates_are_reported_and_nothing_is_changed(tmp_path):
    eng = legacy_engine(tmp_path)
    with eng.begin() as c:
        c.execute(text("INSERT INTO transactions (reference, provider_transaction_id) VALUES ('a','dup'),('b','dup'),('c','ok')"))
    assert ensure_unique_provider_transaction_index(eng) == "skipped_duplicates"
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM transactions")).scalar() == 3
    assert not any(i["unique"] for i in inspect(eng).get_indexes("transactions"))


def test_startup_migration_adds_the_new_tables_to_an_existing_database(tmp_path):
    """A pre-Stage-1 database (transactions table without the new schema) gains
    admin_sessions + payment_orders and the unique index, keeping its rows."""
    from app.main import run_database_migrations
    eng = legacy_engine(tmp_path)
    with eng.begin() as c:
        c.execute(text("INSERT INTO transactions (reference, provider_transaction_id) VALUES ('keep','p1')"))
    run_database_migrations(eng)
    tables = set(inspect(eng).get_table_names())
    assert {"admin_sessions", "payment_orders"} <= tables
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM transactions WHERE reference='keep'")).scalar() == 1
