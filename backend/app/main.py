import os
import logging
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.config import settings
from app.database import engine, Base
from app.routes import admin, auth, wallet, payment, card_order, support, nfc_security

logger = logging.getLogger("tapgo")


def run_database_migrations(eng):
    """
    Safely ensures all required tables and columns exist across
    PostgreSQL (Supabase), MySQL, and SQLite.
    Operates additively and never drops data or fails the process.
    """
    try:
        inspector = inspect(eng)
        dialect = eng.dialect.name
        table_names = set(inspector.get_table_names())

        # 1. EMAIL OTPS TABLE & COLUMNS
        if "email_otps" in table_names:
            otp_cols = {col["name"] for col in inspector.get_columns("email_otps")}
            with eng.begin() as conn:
                if "purpose" not in otp_cols:
                    try:
                        conn.execute(text("ALTER TABLE email_otps ADD COLUMN purpose VARCHAR(32) DEFAULT 'registration'"))
                        logger.info("[Migration] Added column email_otps.purpose")
                    except Exception as ex:
                        logger.warning(f"[Migration] email_otps.purpose: {ex}")

                if "attempts" not in otp_cols:
                    try:
                        col_type = "INT NOT NULL DEFAULT 0" if dialect == "mysql" else "INTEGER NOT NULL DEFAULT 0"
                        conn.execute(text(f"ALTER TABLE email_otps ADD COLUMN attempts {col_type}"))
                        logger.info("[Migration] Added column email_otps.attempts")
                    except Exception as ex:
                        logger.warning(f"[Migration] email_otps.attempts: {ex}")

                if "is_verified" not in otp_cols:
                    try:
                        col_type = "TINYINT(1) NOT NULL DEFAULT 0" if dialect == "mysql" else ("BOOLEAN NOT NULL DEFAULT FALSE" if dialect == "postgresql" else "BOOLEAN NOT NULL DEFAULT 0")
                        conn.execute(text(f"ALTER TABLE email_otps ADD COLUMN is_verified {col_type}"))
                        logger.info("[Migration] Added column email_otps.is_verified")
                    except Exception as ex:
                        logger.warning(f"[Migration] email_otps.is_verified: {ex}")

                # Metadata column for amount-tied OTP (wallet_topup)
                if "otp_metadata" not in otp_cols:
                    try:
                        conn.execute(text("ALTER TABLE email_otps ADD COLUMN otp_metadata TEXT NULL"))
                        logger.info("[Migration] Added column email_otps.otp_metadata")
                    except Exception as ex:
                        logger.warning(f"[Migration] email_otps.otp_metadata: {ex}")
        else:
            with eng.begin() as conn:
                if dialect == "postgresql":
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS email_otps (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(120) NOT NULL,
                            otp VARCHAR(10) NOT NULL,
                            purpose VARCHAR(32) NOT NULL DEFAULT 'registration',
                            attempts INTEGER NOT NULL DEFAULT 0,
                            is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS idx_email_otps_email ON email_otps(email);
                        CREATE INDEX IF NOT EXISTS idx_email_otps_purpose ON email_otps(purpose);
                    """))
                elif dialect == "mysql":
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS email_otps (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            email VARCHAR(120) NOT NULL,
                            otp VARCHAR(10) NOT NULL,
                            purpose VARCHAR(32) NOT NULL DEFAULT 'registration',
                            attempts INT NOT NULL DEFAULT 0,
                            is_verified TINYINT(1) NOT NULL DEFAULT 0,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            expires_at DATETIME NOT NULL,
                            KEY idx_email (email),
                            KEY idx_purpose (purpose)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """))
                else:  # sqlite
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS email_otps (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            email VARCHAR(120) NOT NULL,
                            otp VARCHAR(10) NOT NULL,
                            purpose VARCHAR(32) NOT NULL DEFAULT 'registration',
                            attempts INTEGER NOT NULL DEFAULT 0,
                            is_verified BOOLEAN NOT NULL DEFAULT 0,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            expires_at DATETIME NOT NULL
                        );
                        CREATE INDEX IF NOT EXISTS ix_email_otps_email ON email_otps(email);
                        CREATE INDEX IF NOT EXISTS ix_email_otps_purpose ON email_otps(purpose);
                    """))
                logger.info("[Migration] Created table email_otps")

        # 2. EMAIL LOGS TABLE
        table_names = set(inspect(eng).get_table_names())
        if "email_logs" not in table_names:
            with eng.begin() as conn:
                if dialect == "postgresql":
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS email_logs (
                            id SERIAL PRIMARY KEY,
                            email_type VARCHAR(50) NOT NULL,
                            recipient VARCHAR(120) NOT NULL,
                            reference VARCHAR(64) NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'SENT',
                            error_message TEXT NULL,
                            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_email_logs_recipient ON email_logs(recipient);
                        CREATE INDEX IF NOT EXISTS idx_email_logs_created_at ON email_logs(created_at);
                    """))
                elif dialect == "mysql":
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS email_logs (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            email_type VARCHAR(50) NOT NULL,
                            recipient VARCHAR(120) NOT NULL,
                            reference VARCHAR(64) NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'SENT',
                            error_message TEXT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            KEY idx_recipient (recipient),
                            KEY idx_created_at (created_at)
                        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """))
                else:  # sqlite
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS email_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            email_type VARCHAR(50) NOT NULL,
                            recipient VARCHAR(120) NOT NULL,
                            reference VARCHAR(64) NULL,
                            status VARCHAR(20) NOT NULL DEFAULT 'SENT',
                            error_message TEXT NULL,
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS ix_email_logs_recipient ON email_logs(recipient);
                        CREATE INDEX IF NOT EXISTS ix_email_logs_created_at ON email_logs(created_at);
                    """))
                logger.info("[Migration] Created table email_logs")

        # 3. USERS TABLE LEGACY COLUMNS
        if "users" in table_names:
            user_cols = {col["name"] for col in inspector.get_columns("users")}
            user_migrations = [
                ("status", "VARCHAR(20) NOT NULL DEFAULT 'active'"),
                ("qr_identifier", "VARCHAR(128) NULL"),
                ("nfc_identifier", "VARCHAR(128) NULL"),
                ("signature_document", "VARCHAR(255) NULL"),
                ("id_document", "VARCHAR(255) NULL"),
                ("state", "VARCHAR(100) NULL"),
                ("emergency_contact_name", "VARCHAR(100) NULL"),
                ("emergency_contact_phone", "VARCHAR(20) NULL"),
                ("bank_account_holder", "VARCHAR(100) NULL"),
                ("bank_account_number", "VARCHAR(50) NULL"),
                ("bank_ifsc", "VARCHAR(20) NULL"),
                ("bank_upi_id", "VARCHAR(50) NULL"),
                ("bank_locked", "INT DEFAULT 0" if dialect == "mysql" else "INTEGER DEFAULT 0"),
                ("bank_request_status", "VARCHAR(20) DEFAULT 'none'"),
                ("doc_request_status", "VARCHAR(20) DEFAULT 'none'"),
                ("phone_request_status", "VARCHAR(20) DEFAULT 'none'"),
            ]
            with eng.begin() as conn:
                for col_name, col_def in user_migrations:
                    if col_name not in user_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                        except Exception:
                            pass

        # 4. TRANSACTIONS TABLE LEGACY COLUMNS
        if "transactions" in table_names:
            txn_cols = {col["name"] for col in inspector.get_columns("transactions")}
            txn_migrations = [
                ("transaction_type", "VARCHAR(30) NULL"),
                ("description", "TEXT NULL"),
                ("balance_after", "DECIMAL(12, 2) NULL"),
                ("idempotency_key", "VARCHAR(128) NULL"),
                ("related_transaction_id", "INT NULL" if dialect == "mysql" else "INTEGER NULL"),
                ("provider", "VARCHAR(30) NULL"),
                ("provider_transaction_id", "VARCHAR(128) NULL"),
                ("utr", "VARCHAR(128) NULL"),
                ("payer_name", "VARCHAR(120) NULL"),
                ("payment_request_id", "INT NULL" if dialect == "mysql" else "INTEGER NULL"),
                ("payment_source", "VARCHAR(50) NULL"),
                ("email_received_at", "DATETIME NULL" if dialect != "postgresql" else "TIMESTAMP WITHOUT TIME ZONE NULL"),
                ("raw_email_id", "VARCHAR(255) NULL"),
            ]
            with eng.begin() as conn:
                for col_name, col_def in txn_migrations:
                    if col_name not in txn_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_def}"))
                        except Exception:
                            pass

        # 5. CREATE ALL REMAINING TABLES FROM MODELS.PY
        try:
            Base.metadata.create_all(bind=eng)
        except Exception as create_ex:
            logger.warning(f"[Warning] Base.metadata.create_all: {create_ex}")

        # 6. ENSURE DEFAULT ADMIN EXISTS
        try:
            from app.database import SessionLocal
            from app.routes.admin import ensure_default_admin
            with SessionLocal() as db:
                ensure_default_admin(db)
        except Exception as admin_ex:
            logger.warning(f"[Warning] ensure_default_admin: {admin_ex}")

        # 7. ENSURE AMAZON REVIEWER USER EXISTS
        try:
            from app.database import SessionLocal
            from app.routes.auth import ensure_amazon_reviewer_user
            with SessionLocal() as db:
                ensure_amazon_reviewer_user(db)
        except Exception as rev_ex:
            logger.warning(f"[Warning] ensure_amazon_reviewer_user: {rev_ex}")

        # 8. SUPPORT TICKETS TABLE
        table_names = set(inspect(eng).get_table_names())
        if "support_tickets" not in table_names:
            with eng.begin() as conn:
                try:
                    if dialect == "postgresql":
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS support_tickets (
                                id SERIAL PRIMARY KEY,
                                user_id INTEGER NOT NULL REFERENCES users(id),
                                name VARCHAR(100) NOT NULL,
                                email VARCHAR(120) NOT NULL,
                                phone VARCHAR(20) NOT NULL,
                                category VARCHAR(50) NOT NULL DEFAULT 'other',
                                priority VARCHAR(20) NOT NULL DEFAULT 'medium',
                                subject VARCHAR(255) NOT NULL,
                                message TEXT NOT NULL,
                                status VARCHAR(30) NOT NULL DEFAULT 'open',
                                admin_reply TEXT NULL,
                                replied_by INTEGER NULL REFERENCES admins(id),
                                replied_at TIMESTAMP WITHOUT TIME ZONE NULL,
                                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS idx_support_tickets_user_id ON support_tickets(user_id);
                            CREATE INDEX IF NOT EXISTS idx_support_tickets_status ON support_tickets(status);
                            CREATE INDEX IF NOT EXISTS idx_support_tickets_created_at ON support_tickets(created_at);
                        """))
                    elif dialect == "mysql":
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS support_tickets (
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                user_id INT NOT NULL,
                                name VARCHAR(100) NOT NULL,
                                email VARCHAR(120) NOT NULL,
                                phone VARCHAR(20) NOT NULL,
                                category VARCHAR(50) NOT NULL DEFAULT 'other',
                                priority VARCHAR(20) NOT NULL DEFAULT 'medium',
                                subject VARCHAR(255) NOT NULL,
                                message TEXT NOT NULL,
                                status VARCHAR(30) NOT NULL DEFAULT 'open',
                                admin_reply TEXT NULL,
                                replied_by INT NULL,
                                replied_at DATETIME NULL,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                                KEY idx_user_id (user_id),
                                KEY idx_status (status),
                                KEY idx_created_at (created_at)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                        """))
                    else:
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS support_tickets (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER NOT NULL,
                                name VARCHAR(100) NOT NULL,
                                email VARCHAR(120) NOT NULL,
                                phone VARCHAR(20) NOT NULL,
                                category VARCHAR(50) NOT NULL DEFAULT 'other',
                                priority VARCHAR(20) NOT NULL DEFAULT 'medium',
                                subject VARCHAR(255) NOT NULL,
                                message TEXT NOT NULL,
                                status VARCHAR(30) NOT NULL DEFAULT 'open',
                                admin_reply TEXT NULL,
                                replied_by INTEGER NULL,
                                replied_at DATETIME NULL,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS ix_support_tickets_user_id ON support_tickets(user_id);
                            CREATE INDEX IF NOT EXISTS ix_support_tickets_status ON support_tickets(status);
                        """))
                    logger.info("[Migration] Created table support_tickets")
                except Exception as ex:
                    logger.warning(f"[Migration] support_tickets: {ex}")

        # 9. NFC CARDS TABLE
        table_names = set(inspect(eng).get_table_names())
        if "nfc_cards" not in table_names:
            with eng.begin() as conn:
                try:
                    if dialect == "postgresql":
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS nfc_cards (
                                id SERIAL PRIMARY KEY,
                                user_id INTEGER NOT NULL REFERENCES users(id),
                                card_reference VARCHAR(64) NOT NULL UNIQUE,
                                card_type VARCHAR(50) NOT NULL DEFAULT 'standard_nfc',
                                status VARCHAR(20) NOT NULL DEFAULT 'active',
                                blocked_reason TEXT NULL,
                                block_requested_at TIMESTAMP WITHOUT TIME ZONE NULL,
                                nfc_order_id INTEGER NULL REFERENCES nfc_card_orders(id),
                                replacement_order_id INTEGER NULL REFERENCES nfc_card_orders(id),
                                issued_at TIMESTAMP WITHOUT TIME ZONE NULL,
                                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS idx_nfc_cards_user_id ON nfc_cards(user_id);
                            CREATE INDEX IF NOT EXISTS idx_nfc_cards_status ON nfc_cards(status);
                            CREATE UNIQUE INDEX IF NOT EXISTS idx_nfc_cards_ref ON nfc_cards(card_reference);
                        """))
                    elif dialect == "mysql":
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS nfc_cards (
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                user_id INT NOT NULL,
                                card_reference VARCHAR(64) NOT NULL UNIQUE,
                                card_type VARCHAR(50) NOT NULL DEFAULT 'standard_nfc',
                                status VARCHAR(20) NOT NULL DEFAULT 'active',
                                blocked_reason TEXT NULL,
                                block_requested_at DATETIME NULL,
                                nfc_order_id INT NULL,
                                replacement_order_id INT NULL,
                                issued_at DATETIME NULL,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                                KEY idx_user_id (user_id),
                                KEY idx_status (status)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                        """))
                    else:
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS nfc_cards (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER NOT NULL,
                                card_reference VARCHAR(64) NOT NULL UNIQUE,
                                card_type VARCHAR(50) NOT NULL DEFAULT 'standard_nfc',
                                status VARCHAR(20) NOT NULL DEFAULT 'active',
                                blocked_reason TEXT NULL,
                                block_requested_at DATETIME NULL,
                                nfc_order_id INTEGER NULL,
                                replacement_order_id INTEGER NULL,
                                issued_at DATETIME NULL,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS ix_nfc_cards_user_id ON nfc_cards(user_id);
                            CREATE INDEX IF NOT EXISTS ix_nfc_cards_status ON nfc_cards(status);
                        """))
                    logger.info("[Migration] Created table nfc_cards")
                except Exception as ex:
                    logger.warning(f"[Migration] nfc_cards: {ex}")

        # 10. WITHDRAWAL REQUESTS TABLE
        table_names = set(inspect(eng).get_table_names())
        if "withdrawal_requests" not in table_names:
            with eng.begin() as conn:
                try:
                    if dialect == "postgresql":
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                                id SERIAL PRIMARY KEY,
                                user_id INTEGER NOT NULL REFERENCES users(id),
                                wallet_id INTEGER NOT NULL REFERENCES wallets(id),
                                hold_transaction_id INTEGER NULL REFERENCES transactions(id),
                                amount NUMERIC(12,2) NOT NULL,
                                destination_desc TEXT NOT NULL,
                                reference VARCHAR(64) NOT NULL UNIQUE,
                                otp_verified BOOLEAN NOT NULL DEFAULT TRUE,
                                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                                admin_id INTEGER NULL REFERENCES admins(id),
                                admin_note TEXT NULL,
                                reviewed_at TIMESTAMP WITHOUT TIME ZONE NULL,
                                paid_at TIMESTAMP WITHOUT TIME ZONE NULL,
                                idempotency_key VARCHAR(128) NULL UNIQUE,
                                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS idx_wr_user_id ON withdrawal_requests(user_id);
                            CREATE INDEX IF NOT EXISTS idx_wr_status ON withdrawal_requests(status);
                            CREATE INDEX IF NOT EXISTS idx_wr_reference ON withdrawal_requests(reference);
                        """))
                    elif dialect == "mysql":
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                user_id INT NOT NULL,
                                wallet_id INT NOT NULL,
                                hold_transaction_id INT NULL,
                                amount DECIMAL(12,2) NOT NULL,
                                destination_desc TEXT NOT NULL,
                                reference VARCHAR(64) NOT NULL UNIQUE,
                                otp_verified TINYINT(1) NOT NULL DEFAULT 1,
                                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                                admin_id INT NULL,
                                admin_note TEXT NULL,
                                reviewed_at DATETIME NULL,
                                paid_at DATETIME NULL,
                                idempotency_key VARCHAR(128) NULL UNIQUE,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                                KEY idx_user_id (user_id),
                                KEY idx_status (status)
                            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                        """))
                    else:
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER NOT NULL,
                                wallet_id INTEGER NOT NULL,
                                hold_transaction_id INTEGER NULL,
                                amount NUMERIC(12,2) NOT NULL,
                                destination_desc TEXT NOT NULL,
                                reference VARCHAR(64) NOT NULL UNIQUE,
                                otp_verified BOOLEAN NOT NULL DEFAULT 1,
                                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                                admin_id INTEGER NULL,
                                admin_note TEXT NULL,
                                reviewed_at DATETIME NULL,
                                paid_at DATETIME NULL,
                                idempotency_key VARCHAR(128) NULL UNIQUE,
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                            );
                            CREATE INDEX IF NOT EXISTS ix_wr_user_id ON withdrawal_requests(user_id);
                            CREATE INDEX IF NOT EXISTS ix_wr_status ON withdrawal_requests(status);
                        """))
                    logger.info("[Migration] Created table withdrawal_requests")
                except Exception as ex:
                    logger.warning(f"[Migration] withdrawal_requests: {ex}")

    except Exception as e:
        logger.error(f"[Database Migration Critical] Startup migration error: {e}")


# Execute migration at startup
run_database_migrations(engine)

app = FastAPI(title="Tap&Go API", version="1.0.0")


# Configure CORS Middleware
_origins = [o.strip() for o in settings.ALLOWED_ORIGINS if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if _origins else ["*"],
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handler for safe debugging & clean JSON responses
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[Unhandled Exception] {request.method} {request.url.path}: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"}
    )

# Ensure upload directories exist and mount static route
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(
    BASE_DIR,
    "reviewer_seed/uploads" if settings.REVIEW_DEMO_MODE else "uploads",
)
for folder in ["profile", "rc", "licence", "insurance", "signatures", "id_documents"]:
    os.makedirs(os.path.join(UPLOADS_DIR, folder), exist_ok=True)

if settings.REVIEW_DEMO_MODE:
    app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


# Include Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(wallet.router)
app.include_router(payment.router)
app.include_router(payment.debug_router)
app.include_router(card_order.router)
app.include_router(support.router)
app.include_router(nfc_security.router)

@app.get("/")
def root():
    """Root endpoint for status check."""
    return {"message": "Tap&Go Backend Running", "demo_mode": settings.DEMO_MODE}
