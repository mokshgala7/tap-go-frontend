"""The repair script for the obsolete edit-request status 'rejectd'.

Runs only against throw-away SQLite files created here; never against a real database.
"""
import importlib.util
import json
import os

import pytest
from sqlalchemy import create_engine, text

from app.models import Base

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "repair_rejectd_edit_requests.py")
spec = importlib.util.spec_from_file_location("repair_rejectd_edit_requests", SCRIPT)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "snapshot.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id, account_type, name, email, phone, password_hash, status) VALUES (1,'passenger','P','p@example.com','9000000001','x','active')"))
        statuses = ["pending", "approved", "rejected", "rejectd", "approved", "rejectd", "REJECTD", "rejectd ", "Rejected", ""]
        for i, st in enumerate(statuses, start=1):
            c.execute(text("INSERT INTO edit_requests (id, user_id, field_name, status) VALUES (:i, 1, 'phone', :st)"), {"i": i, "st": st})
    return f"sqlite:///{path}", engine


def run(capsys, *argv):
    code = repair.main(list(argv))
    out = capsys.readouterr().out
    return code, json.loads(out)


def statuses(engine):
    with engine.connect() as c:
        return {r[0]: r[1] for r in c.execute(text("SELECT id, status FROM edit_requests"))}


def test_dry_run_reports_the_exact_rows_and_changes_nothing(db, capsys):
    url, engine = db
    before = statuses(engine)
    code, out = run(capsys, "--database-url", url)
    assert code == 0 and out["mode"].startswith("dry-run")
    assert out["rows_with_obsolete_status"] == 2 and out["ids"] == [4, 6]   # exact spelling only
    assert statuses(engine) == before
    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM sqlite_master WHERE name='edit_requests_rejectd_repair_log'")).scalar() == 0


def test_apply_needs_a_backup_flag(db, capsys):
    url, engine = db
    before = statuses(engine)
    code, out = run(capsys, "--database-url", url, "--apply")
    assert code == 2 and out["ok"] is False
    assert statuses(engine) == before


def test_apply_touches_only_the_exact_obsolete_status_and_logs_the_ids(db, capsys):
    url, engine = db
    before = statuses(engine)
    code, out = run(capsys, "--database-url", url, "--apply", "--i-have-a-backup")
    assert code == 0 and out["repaired"] == 2 and out["ids"] == [4, 6]
    after = statuses(engine)
    assert after[4] == after[6] == "rejected"
    # nothing else moved: other spellings, pending, approved and empty rows are untouched
    assert {k: v for k, v in after.items() if k not in (4, 6)} == {k: v for k, v in before.items() if k not in (4, 6)}
    with engine.connect() as c:
        assert [r[0] for r in c.execute(text("SELECT edit_request_id FROM edit_requests_rejectd_repair_log ORDER BY 1"))] == [4, 6]


def test_apply_twice_is_harmless(db, capsys):
    url, engine = db
    run(capsys, "--database-url", url, "--apply", "--i-have-a-backup")
    once = statuses(engine)
    code, out = run(capsys, "--database-url", url, "--apply", "--i-have-a-backup")
    assert code == 0 and out["repaired"] == 0 and statuses(engine) == once


def test_rollback_restores_exactly_the_logged_rows(db, capsys):
    url, engine = db
    before = statuses(engine)
    run(capsys, "--database-url", url, "--apply", "--i-have-a-backup")
    code, out = run(capsys, "--database-url", url, "--rollback")
    assert code == 0 and out["restored"] == 2
    assert statuses(engine) == before


def test_rollback_leaves_alone_a_request_an_administrator_changed_since(db, capsys):
    url, engine = db
    run(capsys, "--database-url", url, "--apply", "--i-have-a-backup")
    with engine.begin() as c:
        c.execute(text("UPDATE edit_requests SET status='approved' WHERE id=6"))   # admin acted after the repair
    code, out = run(capsys, "--database-url", url, "--rollback")
    after = statuses(engine)
    assert code == 0 and out["restored"] == 1 and out["left_alone"] == 1
    assert after[4] == "rejectd" and after[6] == "approved"


def test_rollback_without_a_log_does_nothing(db, capsys):
    url, engine = db
    before = statuses(engine)
    code, out = run(capsys, "--database-url", url, "--rollback")
    assert code == 2 and out["ok"] is False and statuses(engine) == before


def test_a_server_database_needs_the_matching_host_before_anything_runs(capsys):
    # No connection is attempted: the guard fails first.
    code, out = run(capsys, "--database-url", "postgresql://user:pw@db.example.com/app", "--apply", "--i-have-a-backup")
    assert code == 2 and "confirm-host" in out["error"]
    code, out = run(capsys, "--database-url", "postgresql://user:pw@db.example.com/app", "--rollback", "--confirm-host", "other.example.com")
    assert code == 2 and "confirm-host" in out["error"]


def test_the_database_url_is_mandatory():
    with pytest.raises(SystemExit):
        repair.main([])
