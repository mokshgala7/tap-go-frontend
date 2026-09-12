import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, User, UserSession, Admin
from datetime import datetime, timedelta
import hashlib
from app.utils.security import hash_password

from sqlalchemy.pool import StaticPool

client = TestClient(app)

# Use in-memory SQLite for tests
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    
    # Create test user A
    user_a = User(
        name="User A",
        email="usera@example.com",
        phone="1111111111",
        password_hash=hash_password("password123"),
        account_type="passenger",
        id_document="id_documents/a.pdf"
    )
    # Create test user B
    user_b = User(
        name="User B",
        email="userb@example.com",
        phone="2222222222",
        password_hash=hash_password("password123"),
        account_type="driver",
        rc_document="rc/b.jpg"
    )
    # Create Admin
    admin = Admin(
        name="Admin",
        email="admin@example.com",
        password_hash=hash_password("admin123")
    )
    db.add_all([user_a, user_b, admin])
    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)
    db.refresh(admin)
    return db, user_a, user_b, admin

def test_login_creates_session(setup_db):
    db, user_a, user_b, admin = setup_db
    
    res = client.post("/api/auth/login", json={"account": "usera@example.com", "password": "password123"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "token" in data
    
    token = data["token"]
    
    # Check that session exists in DB
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    session = db.query(UserSession).filter_by(token_hash=token_hash).first()
    assert session is not None
    assert session.user_id == user_a.id
    assert session.revoked_at is None

def test_authenticated_profile(setup_db):
    db, user_a, user_b, admin = setup_db
    res = client.post("/api/auth/login", json={"account": "usera@example.com", "password": "password123"})
    token = res.json()["token"]
    
    # Authenticated fetch User A
    res2 = client.get(f"/api/auth/profile/{user_a.id}", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 200
    data = res2.json()["user"]
    assert "Requires Auth" not in (data.get("id_document") or "")

def test_missing_and_invalid_token(setup_db):
    db, user_a, user_b, admin = setup_db
    res = client.get(f"/api/auth/profile/{user_a.id}")
    assert res.status_code == 401
    
    res2 = client.get(f"/api/auth/profile/{user_a.id}", headers={"Authorization": "Bearer invalidtoken"})
    assert res2.status_code == 401

def test_user_cannot_access_other_user(setup_db):
    db, user_a, user_b, admin = setup_db
    res = client.post("/api/auth/login", json={"account": "usera@example.com", "password": "password123"})
    token = res.json()["token"]
    
    res2 = client.get(f"/api/auth/profile/{user_b.id}", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 403

def test_logout_revokes_session(setup_db):
    db, user_a, user_b, admin = setup_db
    res = client.post("/api/auth/login", json={"account": "usera@example.com", "password": "password123"})
    token = res.json()["token"]
    
    # Logout
    client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    
    # Profile fetch should now fail
    res2 = client.get(f"/api/auth/profile/{user_a.id}", headers={"Authorization": f"Bearer {token}"})
    assert res2.status_code == 401

def test_expired_session(setup_db):
    db, user_a, user_b, admin = setup_db
    token = "test_token"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    session = UserSession(
        user_id=user_a.id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() - timedelta(days=1)
    )
    db.add(session)
    db.commit()
    
    res = client.get(f"/api/auth/profile/{user_a.id}", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
