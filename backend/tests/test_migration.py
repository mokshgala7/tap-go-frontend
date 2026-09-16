import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine, inspect, text
from app.main import run_database_migrations, _exec_safe


def test_migration_upgrades_legacy_email_otps():
    """Verify that a legacy email_otps table (only id, email, otp, created_at, expires_at)
    is cleanly upgraded with reason, purpose, attempts, is_verified, used, and otp_metadata,
    and existing rows are preserved with correct defaults."""
    engine = create_engine("sqlite:///:memory:")

    # 1. Create legacy email_otps table mimicking older production Supabase schema
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE email_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(120) NOT NULL,
                otp VARCHAR(10) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO email_otps (email, otp, expires_at)
            VALUES ('legacy@thetapandgo.in', '654321', '2026-12-31 23:59:59')
        """))

    inspector = inspect(engine)
    initial_cols = {col["name"] for col in inspector.get_columns("email_otps")}
    assert initial_cols == {"id", "email", "otp", "created_at", "expires_at"}

    # 2. Run the migration
    run_database_migrations(engine)

    # 3. Verify all required columns now exist
    inspector = inspect(engine)
    migrated_cols = {col["name"] for col in inspector.get_columns("email_otps")}
    required_cols = {"id", "email", "otp", "reason", "purpose", "attempts", "is_verified", "used", "otp_metadata", "created_at", "expires_at"}
    assert required_cols.issubset(migrated_cols), f"Missing columns: {required_cols - migrated_cols}"

    # 4. Verify existing row is preserved and backfilled
    with engine.connect() as conn:
        row = conn.execute(text("SELECT email, otp, reason, purpose, attempts, is_verified, used FROM email_otps WHERE email = 'legacy@thetapandgo.in'")).mappings().first()
        assert row is not None
        assert row["otp"] == "654321"
        assert row["reason"] == "create_account"
        assert row["purpose"] == "create_account"
        assert row["attempts"] == 0
        assert row["is_verified"] in (False, 0)
        assert row["used"] in (False, 0)


def test_migration_is_idempotent():
    """Verify that running the migration multiple times produces no errors and preserves all data."""
    engine = create_engine("sqlite:///:memory:")

    # Run 1 on fresh DB
    run_database_migrations(engine)

    # Insert a test OTP row with current schema
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO email_otps (email, otp, reason, purpose, attempts, is_verified, used, expires_at)
            VALUES ('active@thetapandgo.in', '112233', 'forgot_password', 'forgot_password', 1, 0, 0, '2026-12-31 23:59:59')
        """))

    # Run 2 on already migrated DB
    run_database_migrations(engine)

    # Run 3 again to test repeated execution
    run_database_migrations(engine)

    # Verify data intact
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT email, otp, reason, purpose, attempts FROM email_otps WHERE email = 'active@thetapandgo.in'")).mappings().all()
        assert len(rows) == 1
        assert rows[0]["reason"] == "forgot_password"
        assert rows[0]["purpose"] == "forgot_password"
        assert rows[0]["attempts"] == 1


def test_exec_safe_isolates_statement_failures():
    """Verify that _exec_safe isolates statement failures without leaving connection in aborted state."""
    engine = create_engine("sqlite:///:memory:")
    
    # Executing invalid SQL should fail safely without raising exception
    res_fail = _exec_safe(engine, "SELECT * FROM non_existent_table_xyz", "expected failure test")
    assert res_fail is False

    # Executing valid SQL immediately after should succeed
    res_success = _exec_safe(engine, "SELECT 1", "subsequent success test")
    assert res_success is True


def test_migration_handles_partial_legacy_schema():
    """Simulates production Supabase state where reason/purpose were not added yet,
    verifying that adding columns individually never raises UndefinedColumn errors."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE email_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(120) NOT NULL,
                otp VARCHAR(10) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL
            )
        """))
    # Run migration on partially defined legacy table
    run_database_migrations(engine)

    inspector = inspect(engine)
    cols = {col["name"] for col in inspector.get_columns("email_otps")}
    for col in ["reason", "purpose", "attempts", "is_verified", "used", "otp_metadata"]:
        assert col in cols, f"Column {col} was not created"

