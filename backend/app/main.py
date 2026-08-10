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
    Create permanent demo accounts for demonstration and evaluation.
    Accounts are NEVER duplicated — safe to call on every startup.

    Demo Credentials:
      Admin:          admin@tapandgo.com      / 123
      Passenger:      passenger@tapandgo.com  / 123
      Driver (Punya): diymr070@gmail.com      / Punya@123
    """
    from app.models import User, Wallet, Admin
    from app.utils.security import hash_password

    # ── Demo Admin ────────────────────────────────────────────────────────────
    for admin_email in ["admin@tapandgo.com"]:
        if not db.query(Admin).filter(Admin.email == admin_email).first():
            demo_admin = Admin(
                email=admin_email,
                password_hash=hash_password("123"),
                name="Tap&Go Demo Admin",
            )
            db.add(demo_admin)
            db.commit()
            print(f"[Demo] Created admin in Admin table: {admin_email}")

        if not db.query(User).filter(User.email == admin_email).first():
            demo_admin_user = User(
                account_type="admin",
                name="Tap&Go Demo Admin",
                email=admin_email,
                phone="9000000000",
                password_hash=hash_password("123"),
                status="active",
            )
            db.add(demo_admin_user)
            db.commit()
            print(f"[Demo] Created admin in User table: {admin_email}")

    # ── Helper: create user + wallet ──────────────────────────────────────────
    def _create_demo_user(email, phone, name, account_type, password="123", **details):
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                account_type=account_type,
                name=name,
                email=email,
                phone=phone,
                password_hash=hash_password(password),
                status="active",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        user.name = name
        user.phone = phone
        user.account_type = account_type
        user.password_hash = hash_password(password)
        user.status = "active"

        for k, v in details.items():
            if hasattr(user, k) and v is not None:
                setattr(user, k, v)

        db.commit()

        # Ensure wallet exists (never overwrite existing balance if wallet already exists)
        if not db.query(Wallet).filter(Wallet.user_id == user.id).first():
            db.add(Wallet(user_id=user.id, balance=500 if account_type == "passenger" else 0))
            db.commit()
            print(f"[Demo] Created wallet for {account_type}: {email}")

    _create_demo_user(
        email="passenger@tapandgo.com",
        phone="9000000001",
        name="Demo Passenger",
        account_type="passenger",
        password="123",
        address="Flat 402, A-Wing, Navrang CHS, Link Road, Santacruz West",
        city="Mumbai",
        state="Maharashtra",
        pincode="400054",
        aadhaar="987654321012",
        pan="ABCDE1234F",
        emergency_contact_name="Ramesh Gala",
        emergency_contact_phone="9820123456",
        bank_account_holder="Demo Passenger",
        bank_account_number="98765432109876",
        bank_ifsc="HDFC0001234",
        bank_upi_id="passenger@upi",
        bank_locked=1,
        id_document="uploads/id_documents/847013a7631f4f93be44f105531cce42_aadhar.jpeg",
        signature_document="uploads/signatures/4d2ba0cb5bf645e095dbb2b3643a741d_digital_signature.png",
        profile_photo="uploads/profile/e8b039c2086f4ff184751f4a294a25b4_profile_photo.png",
    )
    # Real driver account from existing database
    _create_demo_user(
        email="diymr070@gmail.com",
        phone="9820123456",
        name="Punya Gala",
        account_type="driver",
        password="Punya@123",
        address="702, SV Road, Vile Parle West",
        city="Mumbai",
        state="Maharashtra",
        pincode="400056",
        aadhaar="123456789012",
        pan="AOPPH2176B",
        emergency_contact_name="Moksh Gala",
        emergency_contact_phone="9820745564",
        bank_account_holder="Punya Gala",
        bank_account_number="575072740999",
        bank_ifsc="HDFC0001234",
        bank_upi_id="punya@upi",
        bank_locked=1,
        bank_request_status="approved",
        doc_request_status="approved",
        vehicle_type="Taxi",
        vehicle_registration="MH01AB1234",
        vehicle_make="Tata",
        vehicle_model="Nexon EV",
        driving_licence_number="MH0187977554546",
        rc_document="uploads/rc/076010e8f4304cefa1c8dee87ba556ac_rc book.jpeg",
        licence_document="uploads/licence/e895e731df7447d8ab4dbc3f22ec875b_license.jpg",
        insurance_document="uploads/insurance/9ae9aad1e89a4e1cbcdceaaf9a1d00ec_insurance.jpg",
        signature_document="uploads/signatures/4d2ba0cb5bf645e095dbb2b3643a741d_digital_signature.png",
        id_document="uploads/id_documents/847013a7631f4f93be44f105531cce42_aadhar.jpeg",
        profile_photo="uploads/profile/e8b039c2086f4ff184751f4a294a25b4_profile_photo.png",
    )

    # ── Ensure sample transactions exist for demo passenger ───────────────────
    from app.models import Transaction
    demo_p = db.query(User).filter(User.email == "passenger@tapandgo.com").first()
    if demo_p:
        demo_w = db.query(Wallet).filter(Wallet.user_id == demo_p.id).first()
        if demo_w and not db.query(Transaction).filter(Transaction.passenger_id == demo_p.id).first():
            from decimal import Decimal
            sample_txns = [
                Transaction(
                    reference="FAM-DEMO-500",
                    passenger_id=demo_p.id,
                    wallet_id=demo_w.id,
                    amount=Decimal("500.00"),
                    payment_method="FamPay Test",
                    status="completed",
                    otp_verified=True,
                    fraud_status="clear",
                    transaction_type="deposit",
                    description="₹500.00 credited via FamPay Test UPI",
                    balance_after=Decimal("500.00"),
                ),
                Transaction(
                    reference="TXN-RIDE-MH01AB",
                    passenger_id=demo_p.id,
                    wallet_id=demo_w.id,
                    amount=Decimal("58.00"),
                    payment_method="wallet",
                    status="completed",
                    otp_verified=True,
                    fraud_status="clear",
                    transaction_type="ride_payment",
                    description="Auto Ride Fare to Punya Gala (MH 01 AB 1234)",
                    balance_after=Decimal("442.00"),
                ),
                Transaction(
                    reference="FAM-DEMO-100",
                    passenger_id=demo_p.id,
                    wallet_id=demo_w.id,
                    amount=Decimal("100.00"),
                    payment_method="FamPay Test",
                    status="completed",
                    otp_verified=True,
                    fraud_status="clear",
                    transaction_type="deposit",
                    description="₹100.00 credited via UPI",
                    balance_after=Decimal("542.00"),
                ),
                Transaction(
                    reference="WD-DEMO-42",
                    passenger_id=demo_p.id,
                    wallet_id=demo_w.id,
                    amount=Decimal("42.00"),
                    payment_method="bank_transfer",
                    status="completed",
                    otp_verified=True,
                    fraud_status="clear",
                    transaction_type="withdrawal",
                    description="₹42.00 transferred to bank account (XXXX XXXX 9876)",
                    balance_after=Decimal("500.00"),
                ),
            ]
            db.add_all(sample_txns)
            db.commit()
            print("[Demo] Seeded sample transactions for Demo Passenger")


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
        # Seed demo accounts when DEMO_MODE is enabled
        if settings.DEMO_MODE:
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
    return {"message": "Tap&Go Backend Running", "demo_mode": settings.DEMO_MODE}
