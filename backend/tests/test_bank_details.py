import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base, User, EditRequest
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
def setup_bank_db():
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    driver = User(
        name="Driver Test",
        email="driver@test.com",
        phone="9876543210",
        password_hash=hash_password("Pass123!"),
        account_type="driver",
        bank_account_holder=None,
        bank_account_number=None,
        bank_ifsc=None,
        bank_upi_id=None,
        bank_locked=0,
        bank_request_status="none"
    )
    passenger = User(
        name="Passenger Test",
        email="passenger@test.com",
        phone="9876543211",
        password_hash=hash_password("Pass123!"),
        account_type="passenger",
        bank_account_holder="",
        bank_account_number="",
        bank_ifsc="",
        bank_upi_id="",
        bank_locked=0,
        bank_request_status="none"
    )
    db.add(driver)
    db.add(passenger)
    db.commit()
    db.refresh(driver)
    db.refresh(passenger)

    login_driver = client.post("/api/auth/login", json={"account": "driver@test.com", "password": "Pass123!"})
    assert login_driver.status_code == 200
    driver_token = login_driver.json()["token"]

    login_passenger = client.post("/api/auth/login", json={"account": "passenger@test.com", "password": "Pass123!"})
    assert login_passenger.status_code == 200
    passenger_token = login_passenger.json()["token"]

    yield {
        "driver": driver,
        "passenger": passenger,
        "driver_token": driver_token,
        "passenger_token": passenger_token,
        "db": db
    }
    db.close()

def test_initial_bank_save_and_lock(setup_bank_db):
    data = setup_bank_db
    token = data["driver_token"]

    # Initial save
    res = client.put(
        "/api/auth/profile",
        json={
            "user_id": data["driver"].id,
            "bank_account_holder": "Driver One",
            "bank_account_number": "123456789012",
            "bank_ifsc": "sbin0001234",
            "bank_upi_id": "driver@okaxis"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success"] is True
    user_info = res_data["user"]
    assert user_info["bank_account_holder"] == "Driver One"
    assert user_info["bank_account_number"] == "123456789012"
    assert user_info["bank_ifsc"] == "SBIN0001234" # uppercased
    assert user_info["bank_upi_id"] == "driver@okaxis"
    assert user_info["bank_locked"] == 1

    # Second direct save should be rejected because bank details are locked
    res_direct = client.put(
        "/api/auth/profile",
        json={
            "user_id": data["driver"].id,
            "bank_account_holder": "Changed Name",
            "bank_account_number": "987654321098",
            "bank_ifsc": "HDFC0001234",
            "bank_upi_id": "changed@okaxis"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res_direct.status_code == 400
    assert "locked" in res_direct.json()["detail"].lower()

def test_admin_change_request(setup_bank_db):
    data = setup_bank_db
    token = data["passenger_token"]
    db = data["db"]

    # 1. Save initial bank details
    res = client.put(
        "/api/auth/profile",
        json={
            "user_id": data["passenger"].id,
            "bank_account_holder": "Passenger Initial",
            "bank_account_number": "111122223333",
            "bank_ifsc": "ICIC0001234",
            "bank_upi_id": "passenger@icici"
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    assert res.json()["user"]["bank_locked"] == 1

    # 2. Submit change request to Admin
    req_res = client.post(
        "/api/auth/request-admin-access",
        json={
            "user_id": data["passenger"].id,
            "request_type": "bank",
            "bank_details": {
                "bank_account_holder": "Passenger New",
                "bank_account_number": "999988887777",
                "bank_ifsc": "HDFC0005678",
                "bank_upi_id": "passengernew@hdfc"
            }
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    assert req_res.status_code == 200
    req_json = req_res.json()
    assert req_json["success"] is True
    assert req_json["user"]["bank_request_status"] == "requested"

    # Verify EditRequest in DB
    edit_req = db.query(EditRequest).filter_by(user_id=data["passenger"].id, field_name="bank").first()
    assert edit_req is not None
    assert edit_req.status == "pending"
    assert "999988887777" in edit_req.new_value
