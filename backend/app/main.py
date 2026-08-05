import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.config import settings
from app.database import engine, Base
from app.routes import admin, auth, wallet, payment


def ensure_demo_users(db):
    """
    Create permanent demo accounts for PayU Integration Team review.
    Accounts are NEVER duplicated — safe to call on every startup.

    Demo Credentials:
      Admin:      payuadmin@tapandgo.com  / 123
      Passenger:  passenger@tapandgo.com  / 123
      Driver:     driver@tapandgo.com     / 123
    """
    from app.models import User, Wallet, Admin
    from app.utils.security import hash_password

    # ── Demo Admin ────────────────────────────────────────────────────────────
    admin_email = "payuadmin@tapandgo.com"
    if not db.query(Admin).filter(Admin.email == admin_email).first():
        demo_admin = Admin(
            email=admin_email,
            password_hash=hash_password("123"),
            name="PayU Demo Admin",
        )
        db.add(demo_admin)
        db.commit()
        print(f"[Demo] Created admin in Admin table: {admin_email}")

    if not db.query(User).filter(User.email == admin_email).first():
        demo_admin_user = User(
            account_type="admin",
            name="PayU Demo Admin",
            email=admin_email,
            phone="9000000000",
            password_hash=hash_password("123"),
            status="active",
        )
        db.add(demo_admin_user)
        db.commit()
        print(f"[Demo] Created admin in User table: {admin_email}")

    # ── Helper: create user + wallet ──────────────────────────────────────────
    def _create_demo_user(email, phone, name, account_type):
        if db.query(User).filter(User.email == email).first():
            # Ensure wallet exists even for previously created users
            user = db.query(User).filter(User.email == email).first()
            if not db.query(Wallet).filter(Wallet.user_id == user.id).first():
                db.add(Wallet(user_id=user.id, balance=0))
                db.commit()
                print(f"[Demo] Created wallet for existing user: {email}")
            return
        user = User(
            account_type=account_type,
            name=name,
            email=email,
            phone=phone,
            password_hash=hash_password("123"),
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(Wallet(user_id=user.id, balance=500 if account_type == "passenger" else 0))
        db.commit()
        print(f"[Demo] Created {account_type}: {email}")

    _create_demo_user(
        email="passenger@tapandgo.com",
        phone="9000000001",
        name="Demo Passenger",
        account_type="passenger",
    )
    _create_demo_user(
        email="driver@tapandgo.com",
        phone="9000000002",
        name="Demo Driver",
        account_type="driver",
    )


# Auto-create tables if database exists.  Existing installations keep their
# current data; the migration below adds any columns that models.py defines
# but the original schema.sql may not include.
try:
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("users")}
        # Every (column_name, SQL_definition) pair is tried independently so
        # pre-existing columns are silently skipped.
        migrations = [
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
            ("bank_locked", "INT DEFAULT 0"),
            ("bank_request_status", "VARCHAR(20) DEFAULT 'none'"),
            ("doc_request_status", "VARCHAR(20) DEFAULT 'none'"),
            ("phone_request_status", "VARCHAR(20) DEFAULT 'none'"),
        ]
        with engine.begin() as connection:
            for col_name, col_def in migrations:
                if col_name not in columns:
                    try:
                        connection.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                        print(f"[Migration] Added column users.{col_name}")
                    except Exception:
                        pass  # column may already exist from a previous partial run

    if "transactions" in inspector.get_table_names():
        txn_columns = {column["name"] for column in inspector.get_columns("transactions")}
        txn_migrations = [
            ("transaction_type", "VARCHAR(30) NULL"),
            ("description", "TEXT NULL"),
            ("balance_after", "DECIMAL(12, 2) NULL"),
            ("idempotency_key", "VARCHAR(128) NULL"),
            ("related_transaction_id", "INT NULL"),
            ("provider", "VARCHAR(30) NULL"),
            ("provider_transaction_id", "VARCHAR(128) NULL"),
            ("utr", "VARCHAR(128) NULL"),
            ("payer_name", "VARCHAR(120) NULL"),
            ("payment_request_id", "INT NULL"),
            ("payment_source", "VARCHAR(50) NULL"),
            ("email_received_at", "DATETIME NULL"),
            ("raw_email_id", "VARCHAR(255) NULL"),
            ("updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        ]
        with engine.begin() as connection:
            for col_name, col_def in txn_migrations:
                if col_name not in txn_columns:
                    try:
                        connection.execute(text(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_def}"))
                        print(f"[Migration] Added column transactions.{col_name}")
                    except Exception:
                        pass

    from app.database import SessionLocal
    from app.routes.admin import ensure_default_admin
    with SessionLocal() as db:
        ensure_default_admin(db)
        # Seed PayU demo accounts when PAYU_REVIEW_MODE is enabled
        if settings.PAYU_REVIEW_MODE:
            ensure_demo_users(db)
except Exception as e:
    print(f"[Warning] Could not auto-create database tables on startup: {e}")


app = FastAPI(title="Tap&Go API", version="1.0.0")


# Configure CORS Middleware
# When ALLOWED_ORIGINS contains "*", browsers require allow_credentials=False
_origins = settings.ALLOWED_ORIGINS
_use_wildcard = "*" in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _use_wildcard else _origins,
    allow_credentials=False if _use_wildcard else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directories exist and mount static route
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOADS_DIR = os.path.join(
    BASE_DIR,
    "reviewer_seed/uploads" if settings.REVIEW_DEMO_MODE else "uploads",
)
for folder in ["profile", "rc", "licence", "insurance", "signatures", "id_documents"]:
    os.makedirs(os.path.join(UPLOADS_DIR, folder), exist_ok=True)

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Include Routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(wallet.router)
app.include_router(payment.router)
app.include_router(payment.debug_router)

@app.get("/")
def root():
    """Root endpoint for status check."""
    return {"message": "Tap&Go Backend Running", "review_mode": settings.PAYU_REVIEW_MODE}
