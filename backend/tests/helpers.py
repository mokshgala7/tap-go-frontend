"""Shared helpers for backend tests."""
import secrets
from datetime import datetime, timedelta
import hashlib

from app.models import AdminSession


def admin_headers(session_factory, admin_id: int) -> dict:
    """Create a real server-side admin session and return its bearer header."""
    token = secrets.token_urlsafe(32)
    db = session_factory()
    try:
        db.add(AdminSession(
            admin_id=int(admin_id),
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        ))
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {token}"}


# ── isolated app + database factory ─────────────────────────────────────────
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Base


class Env:
    """A fresh in-memory database wired into the FastAPI app."""

    def __init__(self, path=None):
        """`path` selects a file-backed SQLite database (needed for tests that use
        several threads); the default is a single shared in-memory connection."""
        if path:
            self.engine = create_engine(
                f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30}
            )
        else:
            self.engine = create_engine(
                "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
            )
        self.Session = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

        def override_get_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

    def db(self):
        return self.Session()

    def add_user(self, email, account_type="passenger", password="Passw0rd!x", phone=None,
                 balance=None, frozen=False, status="active", **extra):
        from app.models import User, Wallet
        from app.utils.security import hash_password
        db = self.db()
        try:
            user = User(
                name=extra.pop("name", email.split("@")[0].title()),
                email=email,
                phone=phone or str(9000000000 + (abs(hash(email)) % 99999999)),
                password_hash=hash_password(password),
                account_type=account_type,
                status=status,
                **extra,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            if balance is not None or frozen:
                from decimal import Decimal
                db.add(Wallet(user_id=user.id, balance=Decimal(str(balance or 0)), is_frozen=frozen))
                db.commit()
            return user.id
        finally:
            db.close()

    def add_admin(self, email="admin@test.local", password="Adm1n-Strong-Pass", active=True):
        from app.models import Admin
        from app.utils.security import hash_password
        db = self.db()
        try:
            admin = Admin(email=email, password_hash=hash_password(password), name="Admin", is_active=active)
            db.add(admin)
            db.commit()
            db.refresh(admin)
            return admin.id
        finally:
            db.close()

    def user_headers(self, user_id):
        """A real user session token for `user_id` (same mechanism as /api/auth/login)."""
        from app.models import UserSession
        token = secrets.token_urlsafe(32)
        db = self.db()
        try:
            db.add(UserSession(
                user_id=user_id,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=datetime.utcnow() + timedelta(days=1),
            ))
            db.commit()
        finally:
            db.close()
        return {"Authorization": f"Bearer {token}"}

    def admin_headers(self, admin_id):
        return admin_headers(self.Session, admin_id)

    def balance(self, user_id):
        from app.models import Wallet
        db = self.db()
        try:
            w = db.query(Wallet).filter(Wallet.user_id == user_id).first()
            return float(w.balance) if w else None
        finally:
            db.close()
