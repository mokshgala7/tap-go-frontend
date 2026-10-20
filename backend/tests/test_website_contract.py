"""Replays the exact request shapes the (security-patched) website frontend sends,
so the shared backend keeps serving it. Shapes were copied from
frontend/src/{context,components,pages/Admin}. Mocked; no network."""
import hashlib
import hmac
import json
import os
from unittest.mock import patch

import pytest

from app.models import EmailOTP, PaymentOrder
from app.services.payment.razorpay_service import razorpay_service
from helpers import Env

BANK = dict(bank_account_holder="Rider R", bank_account_number="123456789012",
            bank_ifsc="HDFC0001234", bank_upi_id="rider@hdfc")


@pytest.fixture
def env():
    with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "rzp_test_x", "RAZORPAY_KEY_SECRET": "s3cret-test"}), \
         patch("app.routes.wallet.send_withdrawal_otp", return_value=True), \
         patch("app.routes.wallet.send_withdrawal_email", return_value=True), \
         patch("app.routes.wallet.send_ride_passenger_email", return_value=True), \
         patch("app.routes.wallet.send_ride_driver_email", return_value=True), \
         patch("app.routes.payment.send_wallet_topup_email", return_value=True), \
         patch("app.routes.card_order.send_nfc_card_order_email", return_value=True):
        e = Env()
        e.uid = e.add_user("rider@test.local", balance=500, **BANK)
        e.did = e.add_user("driver@test.local", account_type="driver", balance=0)
        e.tok = e.user_headers(e.uid)          # what sessionStorage 'tapgo_token' holds
        yield e


def test_admin_console_flow(env):
    env.add_admin("admin@test.local", "Adm1n-Strong-Pass")
    res = env.client.post("/api/admin/login", json={"email": "admin@test.local", "password": "Adm1n-Strong-Pass"}).json()
    session = res["admin"]                                   # stored as tapgo_admin_session
    assert {"id", "name", "email", "token"} <= set(session)
    auth = {"Authorization": f"Bearer {session['token']}"}   # adminAuthHeaders()
    assert env.client.get("/api/admin/dashboard", headers=auth).status_code == 200
    assert env.client.get("/api/admin/transactions/export", headers=auth).status_code == 200      # CSV export button
    assert env.client.get("/api/admin/card-order/admin/all", headers=auth).status_code == 200     # NFCOrdersAdmin
    assert env.client.get("/api/admin/withdrawal-requests?status=pending", headers=auth).status_code == 200
    assert env.client.post("/api/admin/logout", headers=auth).status_code == 200
    assert env.client.get("/api/admin/dashboard", headers=auth).status_code == 401                # -> website reloads to login


def test_wallet_context_reads(env):
    assert env.client.get(f"/api/wallet/{env.uid}", headers=env.tok).json()["wallet"]["balance"] == 500
    assert env.client.get(f"/api/wallet/{env.uid}/transactions", headers=env.tok).json()["success"] is True


def test_withdraw_modal_flow(env):
    r = env.client.post("/api/wallet/withdraw/request-otp", json={"user_id": env.uid, "amount": 100}, headers=env.tok)
    assert r.status_code == 200 and r.json()["success"] and "message" in r.json()
    db = env.db()
    otp = db.query(EmailOTP).filter_by(reason="withdraw_balance").first().otp
    r = env.client.post("/api/wallet/withdraw", headers=env.tok,
                        json={"user_id": env.uid, "amount": 100, "otp": otp, "idempotency_key": "web-12345678"})
    assert r.status_code == 200 and r.json()["success"] and r.json()["message"]


def test_pay_fare_with_a_driver_id(env):
    r = env.client.post("/api/wallet/pay", headers=env.tok, json={
        "passenger_id": env.uid, "driver_id": env.did, "fare": 58, "payment_method": "QR", "idempotency_key": "web-87654321"})
    body = r.json()
    assert r.status_code == 200 and body["success"] and body["transaction"]["reference"]     # WalletContext uses data.transaction


def test_pay_fare_without_a_driver_is_refused_instead_of_paying_someone_else(env):
    r = env.client.post("/api/wallet/pay", headers=env.tok, json={
        "passenger_id": env.uid, "driver_id": None, "fare": 58, "payment_method": "QR", "idempotency_key": "web-87654321"})
    assert r.status_code == 422
    assert env.balance(env.uid) == 500 and env.balance(env.did) == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_razorpay_modal_verify_payment(env, legacy):
    db = env.db()
    db.add(PaymentOrder(order_id="order_W1", user_id=env.uid, amount_paise=10000, currency="INR", status="created"))
    db.commit()
    sig = hmac.new(b"s3cret-test", b"order_W1|pay_W1", hashlib.sha256).hexdigest()
    body = {"razorpay_order_id": "order_W1", "razorpay_payment_id": "pay_W1", "razorpay_signature": sig, "payment_method": "upi"}
    if legacy:   # an old client still sending user_id and amount
        body.update(user_id=env.uid, amount=1.0)
    prov = {"id": "pay_W1", "order_id": "order_W1", "amount": 10000, "currency": "INR", "status": "captured", "method": "upi"}
    with patch.object(razorpay_service, "get_payment_details", return_value=prov):
        r = env.client.post("/api/payment/verify-payment", json=body, headers=env.tok)
    assert r.status_code == 200 and r.json()["balance"] == 600.0          # onSuccess(verifyData.balance)


def test_card_order_modals(env):
    body = dict(user_id=env.uid, recipient_name="Asha", phone="9876543210", address_line1="12 Main", address_line2=None,
                area="Andheri", city="Mumbai", state="Maharashtra", pincode="400053")
    assert env.client.post("/api/card-order/create", json=body, headers=env.tok).status_code == 200
    assert env.client.get(f"/api/card-order/user/{env.uid}", headers=env.tok).json()["success"] is True
