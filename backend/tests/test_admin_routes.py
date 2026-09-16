import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, Admin, SupportTicket, NFCCardOrder, User
from app.utils.security import hash_password
from sqlalchemy.pool import StaticPool

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture
def setup_admin_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    admin = Admin(
        email="admin@thetapandgo.in",
        password_hash=hash_password("AdminPass123!"),
        name="Admin Test",
        is_active=True,
    )
    db.add(admin)

    user = User(
        name="Passenger Test",
        email="passenger@test.com",
        phone="9876543211",
        password_hash=hash_password("Pass123!"),
        account_type="passenger",
    )
    db.add(user)
    db.commit()
    db.refresh(admin)
    db.refresh(user)

    # Add dummy support ticket
    ticket = SupportTicket(
        user_id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        subject="Payment inquiry",
        message="Help with wallet",
        status="open",
        priority="medium",
        category="billing",
    )
    db.add(ticket)

    # Add dummy card order
    order = NFCCardOrder(
        order_reference="NFC-TEST-001",
        user_id=user.id,
        card_type="standard_nfc",
        card_price=50.00,
        delivery_charge=40.00,
        total_amount=90.00,
        recipient_name=user.name,
        phone=user.phone,
        address_line1="123 Main St",
        area="Andheri",
        city="Mumbai",
        state="Maharashtra",
        pincode="400001",
        order_status="processing",
        payment_status="simulated",
        is_demo=True,
    )
    db.add(order)
    db.commit()

    yield {"admin": admin, "user": user, "db": db}
    db.close()

def test_admin_support_all_endpoint_exists_and_returns_200(setup_admin_db):
    data = setup_admin_db
    admin_id = str(data["admin"].id)

    # 1. Test /api/admin/support/admin/all
    res = client.get("/api/admin/support/admin/all", headers={"x-admin-id": admin_id})
    assert res.status_code == 200
    res_json = res.json()
    assert "items" in res_json or "tickets" in res_json

    # 2. Test /api/admin/support/all
    res2 = client.get("/api/admin/support/all", headers={"x-admin-id": admin_id})
    assert res2.status_code == 200

def test_admin_card_order_all_endpoint_exists_and_returns_200(setup_admin_db):
    data = setup_admin_db
    admin_id = str(data["admin"].id)

    # 1. Test /api/admin/card-order/admin/all
    res = client.get("/api/admin/card-order/admin/all", headers={"x-admin-id": admin_id})
    assert res.status_code == 200
    res_json = res.json()
    assert res_json.get("success") is True
    assert "orders" in res_json
    assert len(res_json["orders"]) >= 1

    # 2. Test /api/admin/card-order/all
    res2 = client.get("/api/admin/card-order/all", headers={"x-admin-id": admin_id})
    assert res2.status_code == 200
