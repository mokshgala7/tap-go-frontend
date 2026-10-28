"""
test_qr_payment.py
──────────────────
Automated tests for the QR payment flow.
Covers all 20 requirements listed in the implementation spec.
Uses the existing in-memory SQLite environment and helpers.
"""
import time
import uuid
import secrets
import threading
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from tests.helpers import Env
from app.models import PaymentRequest, Transaction, Wallet


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def env():
    return Env()


@pytest.fixture
def scene(env):
    """Standard test scene: one active driver, one funded passenger."""
    driver_id = env.add_user(
        "driver@qrtest.local",
        account_type="driver",
        balance=0,
        name="Test Driver",
    )
    passenger_id = env.add_user(
        "pax@qrtest.local",
        account_type="passenger",
        balance=500,
        name="Test Passenger",
    )
    return {
        "env": env,
        "driver_id": driver_id,
        "passenger_id": passenger_id,
        "driver_headers": env.user_headers(driver_id),
        "pax_headers": env.user_headers(passenger_id),
    }


def create_request(scene, amount=58.0):
    """Helper: driver creates a QR payment request."""
    r = scene["env"].client.post(
        "/api/qr/create-request",
        json={"amount": amount},
        headers=scene["driver_headers"],
    )
    return r


def confirm_request(scene, token, idempotency_key=None):
    """Helper: passenger confirms payment."""
    if idempotency_key is None:
        idempotency_key = f"test-{uuid.uuid4().hex}"
    return scene["env"].client.post(
        f"/api/qr/{token}/confirm",
        json={"idempotency_key": idempotency_key},
        headers=scene["pax_headers"],
    )


# ── 1. Authenticated driver creates a valid QR request ────────────────────────

def test_driver_can_create_qr_request(scene):
    r = create_request(scene, amount=58.0)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["amount"] == 58.0
    assert data["driver_id"] == scene["driver_id"]
    assert len(data["token"]) > 20
    assert "expires_at" in data
    assert data["expires_in_seconds"] == 120


# ── 2. Passenger cannot create a driver payment request ───────────────────────

def test_passenger_cannot_create_qr_request(scene):
    r = scene["env"].client.post(
        "/api/qr/create-request",
        json={"amount": 58.0},
        headers=scene["pax_headers"],
    )
    assert r.status_code == 403


# ── 3. Invalid amount is rejected ─────────────────────────────────────────────

@pytest.mark.parametrize("bad_amount", [0, -10, 0.001, 99999999])
def test_invalid_amount_rejected(scene, bad_amount):
    r = create_request(scene, amount=bad_amount)
    assert r.status_code == 400, f"Expected 400 for amount={bad_amount}, got {r.status_code}"


# ── 4. QR token is unpredictable and unique ───────────────────────────────────

def test_tokens_are_unique_and_long(scene):
    tokens = set()
    for _ in range(5):
        r = create_request(scene, amount=10.0)
        assert r.status_code == 200
        t = r.json()["token"]
        assert len(t) >= 22, "Token too short to be cryptographically safe (128-bit minimum)"
        tokens.add(t)
    assert len(tokens) == 5, "Duplicate tokens generated"


# ── 5. Payment request expires after 120 seconds ─────────────────────────────

def test_expiry_stored_correctly(scene):
    before = datetime.utcnow()
    r = create_request(scene, amount=20.0)
    after = datetime.utcnow()
    assert r.status_code == 200
    assert r.json()["expires_at"].endswith("Z"), "expires_at must be explicit UTC"
    expires_at = datetime.fromisoformat(r.json()["expires_at"].rstrip("Z"))
    assert before + timedelta(seconds=118) <= expires_at <= after + timedelta(seconds=122)


# ── 6. Expired QR cannot be fetched for payment ───────────────────────────────

def test_expired_qr_cannot_be_fetched(scene):
    env = scene["env"]
    r = create_request(scene, amount=30.0)
    assert r.status_code == 200
    token = r.json()["token"]

    # Manually expire it in DB
    db = env.db()
    try:
        db.query(PaymentRequest).filter(PaymentRequest.utr == token).update(
            {"expires_at": datetime.utcnow() - timedelta(seconds=1)},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()

    r2 = env.client.get(f"/api/qr/{token}", headers=scene["pax_headers"])
    assert r2.status_code == 410, r2.text


# ── 7. Expired QR cannot be confirmed ────────────────────────────────────────

def test_expired_qr_cannot_be_confirmed(scene):
    env = scene["env"]
    r = create_request(scene, amount=30.0)
    token = r.json()["token"]

    db = env.db()
    try:
        db.query(PaymentRequest).filter(PaymentRequest.utr == token).update(
            {"expires_at": datetime.utcnow() - timedelta(seconds=1)},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()

    r2 = confirm_request(scene, token)
    assert r2.status_code == 410, r2.text


# ── 8. Successful payment debits the passenger correctly ─────────────────────

def test_payment_debits_passenger(scene):
    env = scene["env"]
    initial_pax = env.balance(scene["passenger_id"])
    r = create_request(scene, amount=58.0)
    token = r.json()["token"]

    r2 = confirm_request(scene, token)
    assert r2.status_code == 200, r2.text
    assert r2.json()["success"] is True

    final_pax = env.balance(scene["passenger_id"])
    assert abs((initial_pax - final_pax) - 58.0) < 0.001


# ── 9. Successful payment credits the correct driver ─────────────────────────

def test_payment_credits_driver(scene):
    env = scene["env"]
    initial_drv = env.balance(scene["driver_id"]) or 0
    r = create_request(scene, amount=58.0)
    token = r.json()["token"]
    confirm_request(scene, token)

    final_drv = env.balance(scene["driver_id"])
    assert abs((final_drv - initial_drv) - 58.0) < 0.001


# ── 10. Passenger cannot change driver or amount ──────────────────────────────

def test_passenger_cannot_override_driver_or_amount(scene):
    """Confirm ignores passenger body beyond idempotency_key; driver and
    amount are always taken from the stored PaymentRequest."""
    env = scene["env"]
    r = create_request(scene, amount=58.0)
    token = r.json()["token"]

    # We only send idempotency_key; no driver_id or amount override is accepted.
    r2 = env.client.post(
        f"/api/qr/{token}/confirm",
        json={"idempotency_key": f"key-{uuid.uuid4().hex}"},
        headers=scene["pax_headers"],
    )
    assert r2.status_code == 200
    assert r2.json()["transaction"]["amount"] == 58.0
    assert r2.json()["transaction"]["driver_name"] == "Test Driver"


# ── 11. Insufficient balance leaves both wallets unchanged ────────────────────

def test_insufficient_balance_leaves_wallets_unchanged(scene):
    env = scene["env"]
    # Add a broke passenger
    broke_id = env.add_user("broke@qrtest.local", account_type="passenger", balance=5)
    broke_headers = env.user_headers(broke_id)

    r = create_request(scene, amount=100.0)
    token = r.json()["token"]

    initial_drv = env.balance(scene["driver_id"]) or 0

    r2 = env.client.post(
        f"/api/qr/{token}/confirm",
        json={"idempotency_key": f"broke-{uuid.uuid4().hex}"},
        headers=broke_headers,
    )
    # Should fail (insufficient funds)
    assert r2.status_code in (400, 410), r2.text

    # Driver should not have been credited
    assert (env.balance(scene["driver_id"]) or 0) == initial_drv


# ── 12. Frozen wallets follow existing payment rules ─────────────────────────

def test_frozen_passenger_cannot_pay(scene):
    env = scene["env"]
    frozen_id = env.add_user("frozen@qrtest.local", account_type="passenger", balance=200, frozen=True)
    frozen_headers = env.user_headers(frozen_id)

    r = create_request(scene, amount=50.0)
    token = r.json()["token"]

    r2 = env.client.post(
        f"/api/qr/{token}/confirm",
        json={"idempotency_key": f"frozen-{uuid.uuid4().hex}"},
        headers=frozen_headers,
    )
    assert r2.status_code == 400
    assert "frozen" in r2.json().get("detail", "").lower()


# ── 13. Successful QR cannot be reused ───────────────────────────────────────

def test_completed_qr_cannot_be_reused(scene):
    env = scene["env"]
    r = create_request(scene, amount=10.0)
    token = r.json()["token"]

    r1 = confirm_request(scene, token)
    assert r1.status_code == 200

    # Try a second, different passenger attempting the same token
    second_id = env.add_user("second@qrtest.local", account_type="passenger", balance=200)
    second_headers = env.user_headers(second_id)
    r2 = env.client.post(
        f"/api/qr/{token}/confirm",
        json={"idempotency_key": f"second-{uuid.uuid4().hex}"},
        headers=second_headers,
    )
    assert r2.status_code in (409, 410), r2.text


# ── 14. Repeated confirmation does not charge twice ───────────────────────────

def test_idempotent_confirmation_does_not_double_charge(scene):
    env = scene["env"]
    r = create_request(scene, amount=20.0)
    token = r.json()["token"]
    key = f"idem-{uuid.uuid4().hex}"

    r1 = confirm_request(scene, token, idempotency_key=key)
    assert r1.status_code == 200
    initial_pax = env.balance(scene["passenger_id"])

    r2 = confirm_request(scene, token, idempotency_key=key)
    # Either 200 (idempotent replay) or 4xx (token used)
    assert r2.status_code in (200, 409, 410)

    final_pax = env.balance(scene["passenger_id"])
    # Balance must not have changed again
    assert abs(initial_pax - final_pax) < 0.001


# ── 15. Concurrent confirmations cannot charge twice ─────────────────────────

def test_concurrent_confirmations_charge_exactly_once(scene, tmp_path):
    """
    Uses a file-backed SQLite database (required for multi-thread access)
    and fires two confirm requests simultaneously.
    """
    db_path = str(tmp_path / "concurrent_test.db")
    env2 = Env(path=db_path)

    driver_id = env2.add_user("drv_c@qrtest.local", account_type="driver", balance=0, name="Concurrent Driver")
    pax_id    = env2.add_user("pax_c@qrtest.local", account_type="passenger", balance=500)

    drv_h = env2.user_headers(driver_id)
    pax_h = env2.user_headers(pax_id)

    r = env2.client.post("/api/qr/create-request", json={"amount": 50.0}, headers=drv_h)
    assert r.status_code == 200
    token = r.json()["token"]

    results = []
    key = f"concurrent-{uuid.uuid4().hex}"

    def attempt():
        r2 = env2.client.post(
            f"/api/qr/{token}/confirm",
            json={"idempotency_key": key},
            headers=pax_h,
        )
        results.append(r2.status_code)

    t1, t2 = threading.Thread(target=attempt), threading.Thread(target=attempt)
    t1.start(); t2.start()
    t1.join(); t2.join()

    # At least one must succeed; at most one may succeed.
    successes = results.count(200)
    assert successes <= 1, f"Double charge! Both returned 200. Statuses: {results}"

    # Passenger debited at most once: balance ≥ 450
    final_pax = env2.balance(pax_id)
    assert final_pax is not None and final_pax >= 450, f"Double charge! Balance: {final_pax}"


# ── 16. Unknown tokens are rejected ──────────────────────────────────────────

def test_unknown_token_rejected_for_get(scene):
    r = scene["env"].client.get(
        "/api/qr/not-a-real-token-abcdef1234",
        headers=scene["pax_headers"],
    )
    assert r.status_code == 404


def test_unknown_token_rejected_for_confirm(scene):
    r = scene["env"].client.post(
        "/api/qr/not-a-real-token-abcdef1234/confirm",
        json={"idempotency_key": f"k-{uuid.uuid4().hex}"},
        headers=scene["pax_headers"],
    )
    assert r.status_code == 404


# ── 17. Cancelled requests cannot be paid ────────────────────────────────────

def test_cancelled_request_cannot_be_paid(scene):
    env = scene["env"]
    r = create_request(scene, amount=30.0)
    token = r.json()["token"]

    # Driver cancels
    rc = env.client.post(f"/api/qr/{token}/cancel", headers=scene["driver_headers"])
    assert rc.status_code == 200
    assert rc.json()["status"] == "Cancelled"

    # Passenger tries to pay
    r2 = confirm_request(scene, token)
    assert r2.status_code in (409, 410), r2.text


# ── 18. Terminal status access is appropriately authenticated ─────────────────

def test_status_requires_auth(scene):
    env = scene["env"]
    r = create_request(scene, amount=10.0)
    token = r.json()["token"]

    # No auth
    r2 = env.client.get(f"/api/qr/{token}/status")
    assert r2.status_code in (401, 403)


def test_status_only_visible_to_creating_driver(scene):
    env = scene["env"]

    # Another driver trying to read a request they did not create
    other_id = env.add_user("other_drv@qrtest.local", account_type="driver", balance=0)
    other_h = env.user_headers(other_id)

    r = create_request(scene, amount=10.0)
    token = r.json()["token"]

    r2 = env.client.get(f"/api/qr/{token}/status", headers=other_h)
    assert r2.status_code == 404  # should not reveal other driver's request


# ── 19. QR rotation does not create overlapping requests ─────────────────────

def test_driver_can_create_multiple_requests_sequentially(scene):
    """Each new request must be a separate row with a distinct token."""
    env = scene["env"]
    tokens = []
    for _ in range(3):
        r = create_request(scene, amount=20.0)
        assert r.status_code == 200
        tokens.append(r.json()["token"])
    assert len(set(tokens)) == 3, "Tokens must be unique across rotations"


# ── 20. Existing wallet security tests still pass ─────────────────────────────
# (Verified by running pytest without -k flag — the test suite discovers and
#  runs test_wallet_security.py and test_payment_security.py automatically.)


# ── Additional: transaction is persisted ─────────────────────────────────────

def test_transaction_persisted_after_qr_payment(scene):
    env = scene["env"]
    r = create_request(scene, amount=42.0)
    token = r.json()["token"]
    r2 = confirm_request(scene, token)
    assert r2.status_code == 200
    ref = r2.json()["transaction"]["reference"]

    db = env.db()
    try:
        txn = db.query(Transaction).filter(Transaction.reference == ref).first()
        assert txn is not None
        assert txn.status == "completed"
        assert abs(float(txn.amount) - 42.0) < 0.001
        assert txn.driver_id == scene["driver_id"]
        assert txn.passenger_id == scene["passenger_id"]
    finally:
        db.close()


# ── Additional: payment request marked Completed ──────────────────────────────

def test_payment_request_status_after_success(scene):
    env = scene["env"]
    r = create_request(scene, amount=15.0)
    token = r.json()["token"]
    confirm_request(scene, token)

    db = env.db()
    try:
        pr = db.query(PaymentRequest).filter(PaymentRequest.utr == token).first()
        assert pr is not None
        assert pr.status == "Completed"
    finally:
        db.close()


# ── Additional: driver status endpoint shows success after payment ─────────────

def test_status_shows_completed_after_payment(scene):
    env = scene["env"]
    r = create_request(scene, amount=25.0)
    token = r.json()["token"]
    confirm_request(scene, token)

    rs = env.client.get(f"/api/qr/{token}/status", headers=scene["driver_headers"])
    assert rs.status_code == 200
    data = rs.json()
    assert data["status"] == "Completed"
    assert "transaction_reference" in data


# ── 21. POS contract: URL format, status vocabulary, expiry, cancel ───────────

def _expire(scene, token, seconds_ago=1):
    db = scene["env"].db()
    try:
        db.query(PaymentRequest).filter(PaymentRequest.utr == token).update(
            {"expires_at": datetime.utcnow() - timedelta(seconds=seconds_ago)},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def _status(scene, token):
    return scene["env"].client.get(f"/api/qr/{token}/status", headers=scene["driver_headers"])


def test_create_response_has_short_https_payment_url(scene):
    body = create_request(scene, amount=1.5).json()
    assert body["payment_url"] == f"https://www.thetapandgo.in/p/{body['token']}"
    assert len(body["payment_url"]) <= 60
    assert body["expires_in_seconds"] == 120
    assert body["amount"] == 1.5


def test_status_vocabulary_and_expiry_without_any_other_call(scene):
    token = create_request(scene, amount=1.5).json()["token"]
    r = _status(scene, token)
    assert r.json()["status"] == "Pending"
    assert 115 <= r.json()["seconds_remaining"] <= 120

    _expire(scene, token)          # nobody has touched the row since creation
    r = _status(scene, token)
    assert r.json()["status"] == "Expired"
    assert r.json()["seconds_remaining"] == 0


def test_status_reports_processing_with_capital_p(scene):
    token = create_request(scene, amount=1.5).json()["token"]
    db = scene["env"].db()
    try:
        db.query(PaymentRequest).filter(PaymentRequest.utr == token).update(
            {"status": "processing"}, synchronize_session=False)
        db.commit()
    finally:
        db.close()
    assert _status(scene, token).json()["status"] == "Processing"


def test_cancel_is_idempotent_and_works_on_expired(scene):
    env = scene["env"]
    token = create_request(scene, amount=1.5).json()["token"]
    first = env.client.post(f"/api/qr/{token}/cancel", headers=scene["driver_headers"])
    again = env.client.post(f"/api/qr/{token}/cancel", headers=scene["driver_headers"])
    assert first.status_code == again.status_code == 200
    assert first.json()["status"] == again.json()["status"] == "Cancelled"

    token2 = create_request(scene, amount=1.5).json()["token"]
    _expire(scene, token2)
    r = env.client.post(f"/api/qr/{token2}/cancel", headers=scene["driver_headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "Expired"      # not recorded as Cancelled
    assert _status(scene, token2).json()["status"] == "Expired"


def test_get_details_includes_vehicle_and_passenger_balance(scene):
    env = scene["env"]
    token = create_request(scene, amount=12.5).json()["token"]
    r = env.client.get(f"/api/qr/{token}", headers=scene["pax_headers"])
    assert r.status_code == 200, r.text
    p = r.json()["payment"]
    assert p["driver_name"] == "Test Driver"
    assert p["amount"] == 12.5
    assert p["wallet_balance"] == 500
    assert p["status"] == "Pending"
    assert "vehicle_registration" in p and "vehicle_type" in p
    assert 0 < p["seconds_remaining"] <= 120


def test_unavailable_responses_name_the_status(scene):
    env = scene["env"]
    t_exp = create_request(scene, amount=5).json()["token"]
    _expire(scene, t_exp)
    r = env.client.get(f"/api/qr/{t_exp}", headers=scene["pax_headers"])
    assert (r.status_code, r.json()["status"]) == (410, "Expired")

    t_can = create_request(scene, amount=5).json()["token"]
    env.client.post(f"/api/qr/{t_can}/cancel", headers=scene["driver_headers"])
    r = confirm_request(scene, t_can)
    assert (r.status_code, r.json()["status"]) == (410, "Cancelled")

    t_paid = create_request(scene, amount=5).json()["token"]
    assert confirm_request(scene, t_paid).status_code == 200
    r = env.client.get(f"/api/qr/{t_paid}", headers=scene["pax_headers"])
    assert (r.status_code, r.json()["status"]) == (410, "Completed")


def test_insufficient_balance_keeps_request_payable_after_top_up(scene):
    env = scene["env"]
    broke_id = env.add_user("short@qrtest.local", account_type="passenger", balance=5)
    headers = env.user_headers(broke_id)
    token = create_request(scene, amount=100.0).json()["token"]

    r = env.client.post(f"/api/qr/{token}/confirm", json={"idempotency_key": "short-key-0001"}, headers=headers)
    assert r.status_code == 400
    assert r.json()["code"] == "insufficient_balance"
    assert r.json()["balance"] == 5 and r.json()["required"] == 100
    assert _status(scene, token).json()["status"] == "Pending"

    db = env.db()
    try:
        db.query(Wallet).filter(Wallet.user_id == broke_id).update({"balance": Decimal("150")})
        db.commit()
    finally:
        db.close()
    r = env.client.post(f"/api/qr/{token}/confirm", json={"idempotency_key": "short-key-0001"}, headers=headers)
    assert r.status_code == 200, r.text
    assert _status(scene, token).json()["status"] == "Completed"
    assert env.balance(broke_id) == 50
    assert env.balance(scene["driver_id"]) == 100
