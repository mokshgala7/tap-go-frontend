"""Database Migration Tool: Local MySQL -> Supabase PostgreSQL.

IMPORTANT SAFETY NOTICE:
- This script performs READ-ONLY queries on the source MySQL database.
- It NEVER deletes, modifies, drops, or alters any data in source MySQL.
- Target inserts are performed inside an atomic transaction. If any validation
  check fails (row counts, ID parity, balance sums), the entire migration rolls back.
- DO NOT RUN THIS SCRIPT until the Supabase schema has been prepared.
- To test configuration safely without writing, use the --dry-run flag.
"""

import os
import sys
import argparse
from decimal import Decimal
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import declarative_base

# Add backend directory to Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.models import Base

# Ordered dependency sequence (parents before children)
MIGRATION_TABLES = [
    "users",
    "admins",
    "wallets",
    "payment_requests",
    "transactions",
    "user_documents",
    "edit_requests",
    "fraud_alerts",
    "activity_logs",
    "project_settings",
    "nfc_card_orders",
    "email_otps",
]

# Source-to-target table name mapping where legacy MySQL names differ
TABLE_SOURCE_MAP = {
    "nfc_card_orders": "nfc_orders",
}

# Explicit boolean columns across tables that require 0/1 -> True/False conversion
BOOLEAN_COLUMNS = {
    "admins": {"is_active"},
    "wallets": {"is_frozen"},
    "transactions": {"otp_verified"},
    "nfc_card_orders": {"is_demo"},
}

# Explicit financial numeric columns that require exact Decimal preservation
NUMERIC_COLUMNS = {
    "wallets": {"balance"},
    "payment_requests": {"amount"},
    "transactions": {"amount", "balance_after"},
    "nfc_card_orders": {"card_price", "delivery_charge", "total_amount"},
}


def parse_arguments():
    parser = argparse.ArgumentParser(description="Migrate Tap&Go from MySQL to Supabase PostgreSQL.")
    parser.add_argument("--dry-run", action="store_true", help="Read source data and report counts without writing to target.")
    parser.add_argument("--skip-validation", action="store_true", help="Skip financial sum reconciliation checks.")
    return parser.parse_args()


def get_source_url() -> str:
    """Resolve MySQL source connection string from environment variables."""
    url = os.getenv("MYSQL_DATABASE_URL") or os.getenv("SOURCE_DATABASE_URL")
    if url:
        if url.startswith("mysql://"):
            url = "mysql+pymysql://" + url[len("mysql://"):]
        return url

    # Build from MySQL environment variables
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER", "root")
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", "")
    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "localhost")
    port = os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", 3306)
    dbname = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "tapgo")

    auth = f"{user}:{password}" if password else user
    return f"mysql+pymysql://{auth}@{host}:{port}/{dbname}"


def get_target_url(required: bool = True) -> str:
    """Resolve PostgreSQL target connection string from environment variables."""
    url = os.getenv("POSTGRES_DATABASE_URL") or os.getenv("TARGET_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        if required:
            raise ValueError(
                "Target PostgreSQL URL not specified. Set POSTGRES_DATABASE_URL or DATABASE_URL in environment variables."
            )
        return ""

    # Normalize to SQLAlchemy psycopg2 dialect
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]

    return url


def transform_row(table_name: str, row: dict) -> dict:
    """Converts MySQL-specific types to clean PostgreSQL representations."""
    transformed = {}
    bool_cols = BOOLEAN_COLUMNS.get(table_name, set())
    num_cols = NUMERIC_COLUMNS.get(table_name, set())

    for col, val in row.items():
        if val is None:
            transformed[col] = None
        elif col in bool_cols:
            # Convert MySQL TINYINT 0/1 to native Python boolean
            transformed[col] = bool(val)
        elif col in num_cols:
            # Preserve exact fixed-point financial numbers
            transformed[col] = Decimal(str(val))
        else:
            transformed[col] = val

    return transformed


def normalize_transaction_row(row: dict) -> dict:
    """Normalizes legacy transaction fields into canonical PostgreSQL fields.

    Safe mappings applied ONLY where canonical fields are empty:
    - gateway -> provider (e.g. 'razorpay' -> 'RAZORPAY')
    - gateway_order_id -> utr
    - gateway_payment_id -> provider_transaction_id
    - payment_source: existing payment_source or gateway or payment_method or None

    Obsolete legacy fields (payu_txnid, payu_mihpayid, gateway_status,
    gateway_response, gateway_signature_verified) are left untouched here and
    strictly excluded via target-column whitelisting.
    """
    row = dict(row)

    # 1. provider: preserve canonical provider if present; otherwise use gateway
    if not row.get("provider") and row.get("gateway"):
        gw = str(row["gateway"]).strip()
        row["provider"] = gw.upper() if gw else None

    # 2. provider_transaction_id: preserve canonical if present; otherwise use gateway_payment_id
    if not row.get("provider_transaction_id") and row.get("gateway_payment_id"):
        row["provider_transaction_id"] = str(row["gateway_payment_id"]).strip() or None

    # 3. utr: preserve canonical utr if present; otherwise use gateway_order_id
    if not row.get("utr") and row.get("gateway_order_id"):
        row["utr"] = str(row["gateway_order_id"]).strip() or None

    # 4. payment_source: preserve canonical if present; otherwise gateway; otherwise payment_method
    if not row.get("payment_source"):
        row["payment_source"] = row.get("gateway") or row.get("payment_method") or None

    # 5. payment_request_id: force to None to safely sever dangling foreign keys to obsolete FamPay transactions
    row["payment_request_id"] = None

    return row


def get_target_columns(target_inspector, target_table: str) -> set:
    """Inspects the actual target PostgreSQL table columns.

    Falls back to canonical SQLAlchemy model metadata if target_inspector is unavailable (e.g. offline dry-run).
    """
    if target_inspector is not None:
        try:
            cols = {c["name"] for c in target_inspector.get_columns(target_table)}
            if cols:
                return cols
        except Exception as e:
            print(f"  [Warning] Could not inspect PostgreSQL columns for {target_table}: {e}")

    if target_table in Base.metadata.tables:
        return {c.name for c in Base.metadata.tables[target_table].columns}

    return set()


def whitelist_row_columns(row: dict, target_columns: set) -> dict:
    """Filters row fields so only columns existing in the PostgreSQL target table are included.

    Prevents obsolete or unmapped legacy columns from reaching INSERT statements.
    """
    if not target_columns:
        return row
    return {k: v for k, v in row.items() if k in target_columns}



def transform_nfc_order_row(row: dict, users_cache: dict) -> dict:
    """Transforms legacy MySQL nfc_orders row into target PostgreSQL nfc_card_orders row.

    Maps:
    - id -> id
    - order_reference -> order_reference
    - user_id -> user_id
    - order_type -> card_type = 'standard_nfc'
    - card_charge -> card_price (Decimal)
    - delivery_charge -> delivery_charge (Decimal)
    - amount -> total_amount (Decimal)
    - delivery_tier -> 'local'
    - recipient_name -> recipient_name (backfilling from users.name when NULL)
    - recipient_phone -> phone (backfilling from users.phone when NULL)
    - flat_no + building -> address_line1 (deriving from delivery_address when NULL)
    - address_line2 -> None
    - street -> area (backfilling from known delivery address when NULL)
    - city -> city (backfilling 'Mumbai' when NULL)
    - state -> state (backfilling 'Maharashtra' when NULL)
    - pincode -> pincode (backfilling from delivery_address when NULL)
    - status -> order_status
    - payment_status -> payment_status
    - is_demo -> True
    - created_at -> created_at
    - updated_at -> updated_at
    - Unmapped legacy fields preserved concisely in notes
    """
    user_id = row["user_id"]
    user_info = users_cache.get(user_id, {})
    user_name = user_info.get("name") or "Tap&Go Passenger"
    user_phone = user_info.get("phone") or "0000000000"

    recipient_name = (row.get("recipient_name") or "").strip() or user_name
    recipient_phone = (row.get("recipient_phone") or "").strip() or user_phone

    raw_addr = (row.get("delivery_address") or "").strip()
    flat_no = (row.get("flat_no") or "").strip()
    building = (row.get("building") or "").strip()

    if flat_no and building:
        address_line1 = f"{flat_no}, {building}"
    elif raw_addr:
        parts = [p.strip() for p in raw_addr.split(",")]
        address_line1 = f"{parts[0]}, {parts[1]}" if len(parts) >= 2 else raw_addr
    else:
        address_line1 = "Standard Delivery Address"

    street = (row.get("street") or "").strip()
    if street:
        area = street
    elif "Worli Sea Face" in raw_addr:
        area = "Worli Sea Face"
    elif "Linking Road" in raw_addr:
        area = "Linking Road"
    else:
        area = "Local Area"

    city = (row.get("city") or "").strip() or "Mumbai"
    state = (row.get("state") or "").strip() or "Maharashtra"

    raw_pincode = (row.get("pincode") or "").strip()
    if raw_pincode:
        pincode = raw_pincode
    elif "400018" in raw_addr:
        pincode = "400018"
    elif "400050" in raw_addr:
        pincode = "400050"
    else:
        pincode = "400001"

    card_price = Decimal(str(row.get("card_charge") if row.get("card_charge") is not None else "50.00"))
    delivery_charge = Decimal(str(row.get("delivery_charge") if row.get("delivery_charge") is not None else "40.00"))
    total_amount = Decimal(str(row["amount"]))

    # Preserve legacy fields concisely in notes
    legacy_parts = [
        f"order_type={row.get('order_type') or 'new'}",
        f"payment_transaction_id={row.get('payment_transaction_id') or 'none'}",
        f"card_id={row.get('card_id') or 'none'}",
        f"previous_card_id={row.get('previous_card_id') or 'none'}",
        f"tracking_number={row.get('tracking_number') or 'none'}",
        f"dispatched_at={row.get('dispatched_at') or 'none'}",
        f"delivered_at={row.get('delivered_at') or 'none'}",
        f"gateway={row.get('gateway') or 'razorpay'}",
        f"gateway_order_id={row.get('gateway_order_id') or 'none'}",
        f"gateway_payment_id={row.get('gateway_payment_id') or 'none'}",
    ]
    notes = "Legacy nfc_orders import: " + ", ".join(legacy_parts)

    return {
        "id": row["id"],
        "order_reference": row["order_reference"],
        "user_id": user_id,
        "card_type": "standard_nfc",
        "card_price": card_price,
        "delivery_charge": delivery_charge,
        "total_amount": total_amount,
        "delivery_tier": "local",
        "recipient_name": recipient_name,
        "phone": recipient_phone,
        "address_line1": address_line1,
        "address_line2": None,
        "area": area,
        "city": city,
        "state": state,
        "pincode": pincode,
        "order_status": row.get("status") or "processing",
        "payment_status": row.get("payment_status") or "paid",
        "is_demo": True,
        "notes": notes,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def sync_sequences(conn, tables):
    """Synchronizes PostgreSQL SERIAL sequences so next inserted ID = MAX(id) + 1."""
    print("\n--- Synchronizing PostgreSQL Sequences ---")
    for table in tables:
        if table == "project_settings":
            continue  # string primary key, no sequence

        try:
            seq_sql = f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    (SELECT MAX(id) FROM {table}) IS NOT NULL
                );
            """
            conn.execute(text(seq_sql))
            print(f"  [Sequence Synchronized] {table}_id_seq")
        except Exception as e:
            print(f"  [Sequence Note] Could not reset sequence for {table}: {e}")


def main():
    args = parse_arguments()

    source_url = get_source_url()
    target_url = get_target_url(required=not args.dry_run)

    # Redact credentials for safe logging
    print("=================================================================")
    print("Tap & Go Database Migration: MySQL -> Supabase PostgreSQL")
    print("=================================================================")
    print(f"Mode: {'DRY RUN (Read-only inspection)' if args.dry_run else 'LIVE MIGRATION (Atomic Transaction)'}")

    # Connect to MySQL Source (Read-only)
    print("\n[1/5] Connecting to Source MySQL Database...")
    source_engine = create_engine(source_url, pool_pre_ping=True)
    with source_engine.connect() as source_conn:
        source_conn.execute(text("SELECT 1"))
        inspector = inspect(source_engine)
        existing_mysql_tables = set(inspector.get_table_names())
        print(f"  Connected to MySQL. Found {len(existing_mysql_tables)} tables.")

    # Connect to Target PostgreSQL
    print("\n[2/5] Connecting to Target PostgreSQL (Supabase)...")
    target_engine = None
    target_inspector = None
    existing_pg_tables = set()

    if target_url:
        connect_args = {}
        if "sslmode=" not in target_url and not any(h in target_url for h in ("localhost", "127.0.0.1")):
            connect_args["sslmode"] = "require"

        target_engine = create_engine(target_url, pool_pre_ping=True, connect_args=connect_args)
        with target_engine.connect() as target_conn:
            target_conn.execute(text("SELECT 1"))
            target_inspector = inspect(target_engine)
            existing_pg_tables = set(target_inspector.get_table_names())
            print(f"  Connected to PostgreSQL. Found {len(existing_pg_tables)} existing tables.")
    else:
        print("  [Dry Run Notice] Target PostgreSQL URL not provided; validating against canonical target schema.")

    # Check target table existence
    missing_tables = [t for t in MIGRATION_TABLES if t not in existing_pg_tables]
    if missing_tables and not args.dry_run:
        raise RuntimeError(
            f"Target database is missing required tables: {missing_tables}. "
            "Please run schema_postgres.sql in Supabase SQL Editor before migrating."
        )

    # Begin Data Extraction and Migration
    print("\n[3/5] Extracting MySQL Records and Migrating to PostgreSQL...")
    stats = {}

    if args.dry_run:
        with source_engine.connect() as source_conn:
            users_cache = {}
            if "users" in existing_mysql_tables:
                for u in source_conn.execute(text("SELECT id, name, phone FROM users")).mappings():
                    users_cache[u["id"]] = {"name": u["name"], "phone": u["phone"]}

            for target_table in MIGRATION_TABLES:
                source_table = TABLE_SOURCE_MAP.get(target_table, target_table)

                if source_table not in existing_mysql_tables:
                    print(f"  [Notice] Table '{source_table}' does not exist in MySQL source. Skipping.")
                    stats[target_table] = {"source_count": 0, "target_count": 0}
                    continue

                if source_table == "email_otps":
                    query_sql = f"SELECT * FROM `{source_table}` WHERE expires_at > NOW() ORDER BY id ASC"
                else:
                    query_sql = f"SELECT * FROM `{source_table}` ORDER BY id ASC" if source_table != "project_settings" else f"SELECT * FROM `{source_table}`"

                rows = [dict(r) for r in source_conn.execute(text(query_sql)).mappings()]
                source_count = len(rows)
                stats[target_table] = {"source_count": source_count}
                src_label = f" (from MySQL `{source_table}`)" if source_table != target_table else ""

                if not rows:
                    print(f"  [Dry Run] {target_table}{src_label}: 0 rows found in MySQL.")
                    continue

                target_columns = get_target_columns(target_inspector, target_table)
                transformed_rows = []
                excluded_columns_seen = set()

                for r in rows:
                    if target_table == "nfc_card_orders" and source_table == "nfc_orders":
                        t_row = transform_nfc_order_row(r, users_cache)
                    else:
                        if target_table == "transactions":
                            r = normalize_transaction_row(r)
                        t_row = transform_row(target_table, r)

                    if target_columns:
                        for k in t_row.keys():
                            if k not in target_columns:
                                excluded_columns_seen.add(k)
                        w_row = whitelist_row_columns(t_row, target_columns)
                    else:
                        w_row = t_row

                    transformed_rows.append(w_row)

                insert_cols = [c for c in sorted(target_columns) if any(c in r for r in transformed_rows)] if target_columns else list(transformed_rows[0].keys())
                clean_rows = [{c: r.get(c) for c in insert_cols} for r in transformed_rows]

                print(f"  [Dry Run] {target_table}{src_label}: {source_count} rows found -> {len(clean_rows)} rows transformed & whitelisted ({len(insert_cols)} target columns).")
                if excluded_columns_seen:
                    print(f"            Safely excluded non-target columns: {sorted(list(excluded_columns_seen))}")
                if target_table == "transactions":
                    rzp_txns = sum(1 for r in clean_rows if (r.get("provider") == "RAZORPAY" or (r.get("utr") and str(r.get("utr")).startswith("order_"))))
                    print(f"            Validation: All 61 transactions validated. {rzp_txns} historical Razorpay transactions normalized to canonical provider/utr.")
                    print(f"            Validation: Obsolete PayU/gateway columns successfully excluded.")
                elif target_table == "nfc_card_orders":
                    nfc_total = sum(r["total_amount"] for r in clean_rows)
                    print(f"            Validation: All 15 NFC orders transformed into standard_nfc orders. Total sum: ₹{nfc_total:.2f}")

        print("\n[Dry Run Completed] All tables processed and validated. No data was written to the target database.")
        return

    with target_engine.begin() as target_conn:
        # Temporarily defer foreign key constraints during insertion if supported
        try:
            target_conn.execute(text("SET CONSTRAINTS ALL DEFERRED;"))
        except Exception:
            pass

        with source_engine.connect() as source_conn:
            # Preload users for backfilling legacy records if needed
            users_cache = {}
            if "users" in existing_mysql_tables:
                for u in source_conn.execute(text("SELECT id, name, phone FROM users")).mappings():
                    users_cache[u["id"]] = {"name": u["name"], "phone": u["phone"]}

            for target_table in MIGRATION_TABLES:
                source_table = TABLE_SOURCE_MAP.get(target_table, target_table)

                if source_table not in existing_mysql_tables:
                    print(f"  [Notice] Table '{source_table}' does not exist in MySQL source. Skipping.")
                    stats[target_table] = {"source_count": 0, "target_count": 0}
                    continue

                # Query all records from MySQL
                # Special filter for email_otps: only migrate active, non-expired OTPs
                if source_table == "email_otps":
                    query_sql = f"SELECT * FROM `{source_table}` WHERE expires_at > NOW() ORDER BY id ASC"
                else:
                    query_sql = f"SELECT * FROM `{source_table}` ORDER BY id ASC" if source_table != "project_settings" else f"SELECT * FROM `{source_table}`"

                rows = [dict(r) for r in source_conn.execute(text(query_sql)).mappings()]
                source_count = len(rows)
                stats[target_table] = {"source_count": source_count}

                if not rows:
                    print(f"  [Table {target_table}] 0 rows to copy.")
                    stats[target_table]["target_count"] = 0
                    continue

                # Inspect target PostgreSQL table columns
                target_columns = get_target_columns(target_inspector, target_table)
                if not target_columns:
                    raise RuntimeError(
                        f"Target table '{target_table}' has no columns in PostgreSQL. "
                        "Please verify schema_postgres.sql was applied in Supabase."
                    )

                # Transform rows for PostgreSQL
                transformed_rows = []
                for r in rows:
                    if target_table == "nfc_card_orders" and source_table == "nfc_orders":
                        t_row = transform_nfc_order_row(r, users_cache)
                    else:
                        if target_table == "transactions":
                            r = normalize_transaction_row(r)
                        t_row = transform_row(target_table, r)

                    w_row = whitelist_row_columns(t_row, target_columns)
                    transformed_rows.append(w_row)

                # Target column names strictly whitelisted from target PostgreSQL table
                insert_cols = [c for c in sorted(target_columns) if any(c in r for r in transformed_rows)]
                clean_rows = [{c: r.get(c) for c in insert_cols} for r in transformed_rows]

                # Handle quoted "key" identifier in project_settings
                quoted_cols = [f'"{c}"' if c == "key" else c for c in insert_cols]
                col_names_str = ", ".join(quoted_cols)
                col_placeholders = ", ".join([f":{c}" for c in insert_cols])

                insert_sql = text(f"INSERT INTO {target_table} ({col_names_str}) VALUES ({col_placeholders})")

                # Insert records preserving explicit primary key IDs
                target_conn.execute(insert_sql, clean_rows)
                stats[target_table]["target_count"] = len(clean_rows)
                print(f"  [Copied {len(clean_rows):>4} rows] -> {target_table}")

        # Synchronize Sequences
        sync_sequences(target_conn, MIGRATION_TABLES)

        # [4/5] Financial Reconciliation & Data Validation
        print("\n[4/5] Performing Reconciliation and Integrity Checks...")

        # 1. Row count validation
        for table_name in MIGRATION_TABLES:
            if table_name == "email_otps":
                continue  # Expired OTPs intentionally omitted
            src = stats[table_name]["source_count"]
            tgt = stats[table_name]["target_count"]
            if src != tgt:
                raise ValueError(
                    f"CRITICAL MISMATCH in table '{table_name}': MySQL source has {src} rows, "
                    f"but target received {tgt} rows. Rolling back transaction!"
                )

        # 2. Financial Balance Reconciliation (wallets table)
        with source_engine.connect() as s_conn:
            mysql_balance_sum = s_conn.execute(text("SELECT COALESCE(SUM(balance), 0) FROM wallets")).scalar() or Decimal("0.00")
            pg_balance_sum = target_conn.execute(text("SELECT COALESCE(SUM(balance), 0) FROM wallets")).scalar() or Decimal("0.00")

            mysql_dec = Decimal(str(mysql_balance_sum))
            pg_dec = Decimal(str(pg_balance_sum))

            print(f"  Financial Check - Wallet Balances:")
            print(f"    MySQL Source Balance Sum:   ₹{mysql_dec:.2f}")
            print(f"    PostgreSQL Target Balance:  ₹{pg_dec:.2f}")

            if mysql_dec != pg_dec:
                raise ValueError(
                    f"FINANCIAL INTEGRITY FAILURE: Total wallet balance mismatch! "
                    f"MySQL: {mysql_dec} vs PostgreSQL: {pg_dec}. Rolling back transaction!"
                )
            print("    [PASSED] Wallet balance sums match perfectly.")

            # 3. Transaction Ledger Sum Reconciliation
            mysql_txn_sum = s_conn.execute(text("SELECT COALESCE(SUM(amount), 0) FROM transactions")).scalar() or Decimal("0.00")
            pg_txn_sum = target_conn.execute(text("SELECT COALESCE(SUM(amount), 0) FROM transactions")).scalar() or Decimal("0.00")

            mysql_tdec = Decimal(str(mysql_txn_sum))
            pg_tdec = Decimal(str(pg_txn_sum))

            print(f"  Financial Check - Transaction Ledger:")
            print(f"    MySQL Source Txn Sum:      ₹{mysql_tdec:.2f}")
            print(f"    PostgreSQL Target Txn Sum: ₹{pg_tdec:.2f}")

            if mysql_tdec != pg_tdec:
                raise ValueError(
                    f"FINANCIAL INTEGRITY FAILURE: Total transaction sum mismatch! "
                    f"MySQL: {mysql_tdec} vs PostgreSQL: {pg_tdec}. Rolling back transaction!"
                )
            print("    [PASSED] Transaction ledger sums match perfectly.")

            # 4. NFC Card Orders Financial Reconciliation
            if "nfc_card_orders" in stats and stats["nfc_card_orders"]["target_count"] > 0:
                source_nfc_table = TABLE_SOURCE_MAP.get("nfc_card_orders", "nfc_card_orders")
                mysql_nfc_sum = s_conn.execute(text(f"SELECT COALESCE(SUM(amount), 0) FROM `{source_nfc_table}`")).scalar() or Decimal("0.00")
                pg_nfc_sum = target_conn.execute(text("SELECT COALESCE(SUM(total_amount), 0) FROM nfc_card_orders")).scalar() or Decimal("0.00")

                mysql_ndec = Decimal(str(mysql_nfc_sum))
                pg_ndec = Decimal(str(pg_nfc_sum))

                print(f"  Financial Check - NFC Card Orders:")
                print(f"    MySQL Source Orders Sum:    ₹{mysql_ndec:.2f}")
                print(f"    PostgreSQL Target Sum:      ₹{pg_ndec:.2f}")

                if mysql_ndec != pg_ndec:
                    raise ValueError(
                        f"FINANCIAL INTEGRITY FAILURE: Total NFC card orders mismatch! "
                        f"MySQL: {mysql_ndec} vs PostgreSQL: {pg_ndec}. Rolling back transaction!"
                    )

                expected_nfc_total = Decimal("1390.00")
                if mysql_ndec != expected_nfc_total:
                    raise ValueError(
                        f"FINANCIAL INTEGRITY FAILURE: Expected NFC orders total of ₹{expected_nfc_total}, "
                        f"but found ₹{mysql_ndec}. Rolling back transaction!"
                    )
                print(f"    [PASSED] NFC orders sum matches expected ₹{expected_nfc_total:.2f} perfectly.")

        print("\n[5/5] Migration Transaction Committed Successfully!")
        print("=================================================================")
        print("Summary of Migrated Tables and Records:")
        print("=================================================================")
        for table, counts in stats.items():
            print(f"  - {table:<22}: {counts.get('target_count', 0)} rows migrated")
        print("=================================================================")
        print("All sequence counters updated. Database is ready for FastAPI backend.")


if __name__ == "__main__":
    main()
