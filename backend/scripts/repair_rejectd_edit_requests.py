"""Repair edit_requests rows written by the old admin-review bug ("reject" + "d" = "rejectd").

NOT run automatically. NOT run by anyone in the review that produced it. The application never
imports this file; an operator runs it by hand, once, against a database they have backed up.

Safe by design
- Needs an explicit --database-url. It never reads .env or any other configuration.
- Default mode is a read-only DRY RUN: it prints the exact count and ids it would change.
- --apply changes ONLY rows whose status is exactly 'rejectd' (no case folding, no LIKE) and
  refuses to start without --i-have-a-backup.
- Every changed id is first written to a log table, edit_requests_rejectd_repair_log, in the
  same transaction as the UPDATE, so the change can be undone.
- --rollback puts status back to 'rejectd' for exactly the logged ids, and only while they are
  still 'rejected' (a request an administrator has touched since is left alone).
- For a database that is not SQLite, --apply/--rollback also need --confirm-host <host name of
  the URL>, a guard against pasting the wrong connection string.

Examples
    python scripts/repair_rejectd_edit_requests.py --database-url sqlite:////tmp/copy.db
    python scripts/repair_rejectd_edit_requests.py --database-url "$URL" --apply --i-have-a-backup --confirm-host db.example.com
    python scripts/repair_rejectd_edit_requests.py --database-url "$URL" --rollback --confirm-host db.example.com
"""
import argparse
import json
import sys
from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text

OLD = "rejectd"
NEW = "rejected"
LOG_TABLE = "edit_requests_rejectd_repair_log"
USER_STATUS_COLUMNS = ("phone_request_status", "bank_request_status", "doc_request_status")


def _parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--database-url", required=True, help="SQLAlchemy URL of the database to inspect/repair (required)")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="repair the rows (default is a read-only dry run)")
    mode.add_argument("--rollback", action="store_true", help="undo a previous --apply using the log table")
    p.add_argument("--i-have-a-backup", action="store_true", help="required for --apply")
    p.add_argument("--confirm-host", default="", help="host name of the URL; required for --apply/--rollback on non-SQLite databases")
    return p


def _out(**payload):
    print(json.dumps(payload, indent=2, default=str))


def _ids(conn, sql, **params):
    return [row[0] for row in conn.execute(text(sql), params)]


def main(argv=None):
    args = _parser().parse_args(argv)
    url = urlparse(args.database_url)
    is_sqlite = args.database_url.startswith("sqlite")
    changing = args.apply or args.rollback

    if changing and not is_sqlite and (args.confirm_host or "").lower() != (url.hostname or "").lower():
        _out(ok=False, error="--confirm-host must equal the host name in --database-url for a non-SQLite database", mode="refused")
        return 2
    if args.apply and not args.i_have_a_backup:
        _out(ok=False, error="--apply needs --i-have-a-backup (take a backup first)", mode="refused")
        return 2

    engine = create_engine(args.database_url)
    if "edit_requests" not in inspect(engine).get_table_names():
        _out(ok=False, error="no edit_requests table in this database", mode="refused")
        return 2

    if not changing:  # dry run: read-only
        with engine.connect() as conn:
            ids = _ids(conn, "SELECT id FROM edit_requests WHERE status = :old ORDER BY id", old=OLD)
            by_status = [list(r) for r in conn.execute(text("SELECT status, COUNT(*) FROM edit_requests GROUP BY status ORDER BY status"))]
            user_cols = {}
            user_columns = {c["name"] for c in inspect(engine).get_columns("users")} if "users" in inspect(engine).get_table_names() else set()
            for col in USER_STATUS_COLUMNS:
                if col in user_columns:
                    user_cols[col] = conn.execute(text(f"SELECT COUNT(*) FROM users WHERE {col} = :old"), {"old": OLD}).scalar()
        _out(ok=True, mode="dry-run (nothing changed)", obsolete_status=OLD, would_become=NEW,
             rows_with_obsolete_status=len(ids), ids=ids, edit_requests_by_status=by_status,
             users_columns_holding_obsolete_status=user_cols)
        return 0

    with engine.begin() as conn:  # one transaction: all or nothing
        if args.apply:
            conn.execute(text(
                f"CREATE TABLE IF NOT EXISTS {LOG_TABLE} ("
                " edit_request_id INTEGER PRIMARY KEY,"
                " old_status VARCHAR(20) NOT NULL,"
                " repaired_at TIMESTAMP NOT NULL)"
            ))
            ids = _ids(conn, "SELECT id FROM edit_requests WHERE status = :old ORDER BY id", old=OLD)
            conn.execute(text(
                f"INSERT INTO {LOG_TABLE} (edit_request_id, old_status, repaired_at) "
                f"SELECT id, status, :now FROM edit_requests "
                f"WHERE status = :old AND id NOT IN (SELECT edit_request_id FROM {LOG_TABLE})"
            ), {"old": OLD, "now": datetime.utcnow()})
            changed = 0
            if ids:
                changed = conn.execute(text(
                    f"UPDATE edit_requests SET status = :new WHERE status = :old "
                    f"AND id IN (SELECT edit_request_id FROM {LOG_TABLE})"
                ), {"new": NEW, "old": OLD}).rowcount
            _out(ok=True, mode="apply", repaired=changed, ids=ids, undo=f"--rollback restores these ids from {LOG_TABLE}")
            return 0

        if LOG_TABLE not in inspect(engine).get_table_names():
            _out(ok=False, error=f"nothing to roll back: {LOG_TABLE} does not exist", mode="rollback")
            return 2
        logged = _ids(conn, f"SELECT edit_request_id FROM {LOG_TABLE} ORDER BY edit_request_id")
        restored = conn.execute(text(
            f"UPDATE edit_requests SET status = :old WHERE status = :new "
            f"AND id IN (SELECT edit_request_id FROM {LOG_TABLE})"
        ), {"old": OLD, "new": NEW}).rowcount
        conn.execute(text(f"DELETE FROM {LOG_TABLE}"))
        _out(ok=True, mode="rollback", logged_ids=logged, restored=restored,
             left_alone=len(logged) - restored, note="ids an administrator changed after the repair are left alone")
        return 0


if __name__ == "__main__":
    sys.exit(main())
