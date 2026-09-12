import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, User, Wallet
from app.routes.auth import ensure_amazon_reviewer_user
from sqlalchemy.pool import StaticPool

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
client = TestClient(app)

def test_amazon_reviewer_provisioning_and_login():
    app.dependency_overrides[get_db] = override_get_db
    db = TestingSessionLocal()
    user = ensure_amazon_reviewer_user(db)
    assert user.email == "amazon.review@thetapandgo.in"
    assert user.account_type == "passenger"
    assert user.status == "active"

    # Verify wallet was created and funded
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    assert wallet is not None
    assert float(wallet.balance) >= 500.0

    # Idempotency check: running again shouldn't fail or create duplicate
    user2 = ensure_amazon_reviewer_user(db)
    assert user2.id == user.id

    # Test login via API endpoint
    response = client.post("/api/auth/login", json={
        "account": "amazon.review@thetapandgo.in",
        "password": "TapGo@2026Review"
    })
    data = response.json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["user"]["email"] == "amazon.review@thetapandgo.in"
    assert data["user"]["account_type"] == "passenger"
    assert "token" in data
    db.close()
