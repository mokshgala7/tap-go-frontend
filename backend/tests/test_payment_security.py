"""Razorpay top-up security (findings F-08, F-13, F-14, F-15, F-20).

Everything is mocked: no Razorpay account, key or network is used. The HMAC
secret below is a throw-away test value.
"""
import hashlib
import hmac
import json
import os
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import EmailOTP, PaymentOrder, Transaction, Wallet
from app.services.payment.razorpay_service import PaymentsNotConfigured, razorpay_service
from app.utils.security import generate_otp
from helpers import Env

SECRET = "test_only_secret_not_real"
KEY_ID = "rzp_test_fakefakefake"
HOOK_SECRET = "test_only_webhook_secret"


def sign(order_id, payment_id, secret=SECRET):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


@pytest.fixture
def cfg():
    with patch.dict(os.environ, {
        "RAZORPAY_KEY_ID": KEY_ID, "RAZORPAY_KEY_SECRET": SECRET, "RAZORPAY_WEBHOOK_SECRET": HOOK_SECRET,
    }):
        yield


@pytest.fixture
def env(cfg):
    e = Env()
    e.uid = e.add_user("payer@test.local", balance=10)
    e.other = e.add_user("other@test.local", balance=10)
    e.h = e.user_headers(e.uid)
    return e


def add_order(env, user_id=None, amount_paise=10000, order_id="order_ABC1", mock=False, status="created"):
    db = env.db()
    db.add(PaymentOrder(order_id=order_id, user_id=user_id or env.uid, amount_paise=amount_paise,
                        currency="INR", status=status, is_mock=mock))
    db.commit()
    db.close()
    return order_id


def provider(order_id="order_ABC1", amount=10000, status="captured", currency="INR", method="upi"):
    return {"id": "pay_1", "order_id": order_id, "amount": amount, "currency": currency,
            "status": status, "method": method}


def verify(env, order_id="order_ABC1", payment_id="pay_1", headers=None, sig=None, **extra):
    body = {"razorpay_order_id": order_id, "razorpay_payment_id": payment_id,
            "razorpay_signature": sig if sig is not None else sign(order_id, payment_id), **extra}
    return env.client.post("/api/payment/verify-payment", json=body, headers=headers if headers is not None else env.h)


def txns(env, kind="deposit"):
    db = env.db()
    try:
        return db.query(Transaction).filter(Transaction.transaction_type == kind).count()
    finally:
        db.close()


def webhook(env, payload, secret=HOOK_SECRET, sig=True):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if sig:
        headers["X-Razorpay-Signature"] = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return env.client.post("/api/payment/webhook", content=body, headers=headers)


def hook_payload(order_id="order_ABC1", amount=10000, payment_id="pay_1", user_note="1", status="captured"):
    return {"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": payment_id, "order_id": order_id, "amount": amount, "currency": "INR",
        "status": status, "method": "upi", "notes": {"user_id": user_note}}}}}


# ───────────────────────── create-order ─────────────────────────────────────
def topup_otp(env, amount):
    db = env.db()
    db.add(EmailOTP(email="payer@test.local", otp="123456", reason="wallet_topup", purpose="wallet_topup",
                    expires_at=datetime.utcnow() + timedelta(minutes=5),
                    otp_metadata=json.dumps({"amount": amount, "user_id": env.uid})))
    db.commit()
    db.close()


class TestCreateOrder:
    def create(self, env, amount=100.0, headers=None):
        return env.client.post("/api/payment/create-order", json={"amount": amount, "otp": "123456"},
                               headers=headers if headers is not None else env.h)

    def test_requires_authentication(self, env):
        assert self.create(env, headers={}).status_code == 401

    def test_order_is_stored_for_the_authenticated_user_with_the_provider_amount(self, env):
        topup_otp(env, 100.0)
        fake = {"id": "order_NEW1", "order_id": "order_NEW1", "amount": 10000, "currency": "INR",
                "key_id": KEY_ID, "is_mock": False}
        with patch.object(razorpay_service, "create_order", return_value=fake):
            r = self.create(env)
        assert r.status_code == 200 and r.json()["order_id"] == "order_NEW1"
        db = env.db()
        o = db.query(PaymentOrder).filter_by(order_id="order_NEW1").first()
        assert (o.user_id, o.amount_paise, o.currency, o.status, o.is_mock) == (env.uid, 10000, "INR", "created", False)

    def test_without_keys_fails_closed_and_stores_no_order(self, env):
        topup_otp(env, 100.0)
        with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": ""}):
            r = self.create(env)
        assert r.status_code == 503
        db = env.db()
        assert db.query(PaymentOrder).count() == 0

    def test_mock_orders_need_the_explicit_development_flag(self, env):
        with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "", "RAZORPAY_KEY_SECRET": ""}):
            with pytest.raises(PaymentsNotConfigured):
                razorpay_service.create_order(100.0)
            with patch.dict(os.environ, {"ALLOW_MOCK_PAYMENTS": "true"}):
                order = razorpay_service.create_order(100.0)
                assert order["is_mock"] is True and order["order_id"].startswith("order_demo_")
            # never in production, whatever the flag says
            with patch.dict(os.environ, {"ALLOW_MOCK_PAYMENTS": "true", "ENVIRONMENT": "production"}):
                with pytest.raises(PaymentsNotConfigured):
                    razorpay_service.create_order(100.0)

    def test_live_keys_are_allowed_by_default(self, env):
        client = MagicMock()
        client.order.create.return_value = {"id": "order_LIVE1", "amount": 10000, "currency": "INR", "receipt": "r1"}
        with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "rzp_live_xxxxxxxx", "RAZORPAY_KEY_SECRET": "s"}), \
                patch.object(razorpay_service, "get_client", return_value=client):
            os.environ.pop("RAZORPAY_LIVE_ENABLED", None)
            order = razorpay_service.create_order(100.0)
        assert order["order_id"] == "order_LIVE1" and client.order.create.called

    @pytest.mark.parametrize("value", ["false", "0", "no", "off", " False "])
    def test_live_keys_can_be_switched_off(self, env, value):
        with patch.dict(os.environ, {"RAZORPAY_KEY_ID": "rzp_live_xxxxxxxx", "RAZORPAY_KEY_SECRET": "s",
                                     "RAZORPAY_LIVE_ENABLED": value}):
            with pytest.raises(PaymentsNotConfigured):
                razorpay_service.create_order(100.0)

    @pytest.mark.parametrize("amount", [float("nan"), float("inf"), 0.5, -5])
    def test_invalid_amounts_are_rejected(self, env, amount):
        topup_otp(env, 1.0)
        r = env.client.post("/api/payment/create-order", content=json.dumps({"amount": amount, "otp": "123456"}).replace("NaN", "NaN"),
                            headers={**env.h, "Content-Type": "application/json"})
        assert r.status_code in (400, 422)


# ───────────────────────── verify-payment ───────────────────────────────────
class TestVerifyPayment:
    def run(self, env, **kw):
        with patch.object(razorpay_service, "get_payment_details", return_value=kw.pop("prov", provider())):
            return verify(env, **kw)

    def test_requires_authentication(self, env):
        add_order(env)
        assert self.run(env, headers={}).status_code == 401
        assert env.balance(env.uid) == 10

    def test_credits_the_server_side_amount_exactly_once(self, env):
        add_order(env)
        r = self.run(env)
        assert r.status_code == 200 and r.json()["balance"] == 110.0
        assert env.balance(env.uid) == 110.0 and txns(env) == 1

    def test_client_supplied_amount_and_user_are_ignored(self, env):
        add_order(env, amount_paise=100)           # a ₹1 order
        r = self.run(env, prov=provider(amount=100), amount=100000.0, user_id=env.uid)
        assert r.status_code == 200
        assert env.balance(env.uid) == 11.0        # ₹1 credited, not ₹1,00,000

    def test_cannot_verify_for_another_user_or_someone_elses_order(self, env):
        add_order(env)
        assert self.run(env, user_id=env.other).status_code == 403
        theirs = env.user_headers(env.other)
        assert self.run(env, headers=theirs).status_code == 404
        assert (env.balance(env.uid), env.balance(env.other)) == (10, 10)

    def test_unknown_order_is_rejected(self, env):
        assert self.run(env, order_id="order_NOPE").status_code == 404

    def test_invalid_signature_credits_nothing(self, env):
        add_order(env)
        for sig in ("", "deadbeef", sign("order_ABC1", "pay_1", "wrong-secret")):
            r = self.run(env, sig=sig or "x")
            assert r.status_code == 400
        assert env.balance(env.uid) == 10

    @pytest.mark.parametrize("prov", [
        provider(amount=1),                       # amount differs from the order
        provider(status="authorized"),            # not captured
        provider(status="failed"),
        provider(currency="USD"),
        provider(order_id="order_OTHER"),         # payment belongs to another order
        None,                                     # provider unreachable / unknown payment
    ])
    def test_payment_must_match_order_at_the_provider(self, env, prov):
        add_order(env)
        r = self.run(env, prov=prov)
        assert r.status_code == 400
        assert env.balance(env.uid) == 10
        db = env.db()
        assert db.query(PaymentOrder).first().status == "created"   # can be retried

    def test_replay_is_idempotent(self, env):
        add_order(env)
        assert self.run(env).status_code == 200
        r2 = self.run(env)
        assert r2.status_code == 200 and r2.json().get("idempotent") is True
        assert env.balance(env.uid) == 110.0 and txns(env) == 1

    def test_a_paid_order_cannot_be_paid_by_a_different_payment(self, env):
        add_order(env)
        assert self.run(env).status_code == 200
        r = self.run(env, payment_id="pay_2", sig=sign("order_ABC1", "pay_2"), prov={**provider(), "id": "pay_2"})
        assert r.status_code == 409
        assert env.balance(env.uid) == 110.0

    def test_mock_order_requires_dev_flag_at_verification_time(self, env):
        add_order(env, order_id="order_demo_x", mock=True)
        with patch.dict(os.environ, {"RAZORPAY_KEY_SECRET": ""}):
            assert verify(env, order_id="order_demo_x", sig="anything").status_code == 400
        with patch.dict(os.environ, {"RAZORPAY_KEY_SECRET": "", "ALLOW_MOCK_PAYMENTS": "true", "ENVIRONMENT": "production"}):
            assert verify(env, order_id="order_demo_x", sig="anything").status_code == 400
        assert env.balance(env.uid) == 10
        with patch.dict(os.environ, {"RAZORPAY_KEY_SECRET": "", "ALLOW_MOCK_PAYMENTS": "true"}):
            assert verify(env, order_id="order_demo_x", sig="anything").status_code == 200
        assert env.balance(env.uid) == 110.0

    def test_a_real_order_is_not_accepted_with_a_mock_signature_when_secret_missing(self, env):
        add_order(env)
        with patch.dict(os.environ, {"RAZORPAY_KEY_SECRET": "", "ALLOW_MOCK_PAYMENTS": "true"}):
            assert verify(env, sig="sig_mock_123").status_code == 400

    def test_concurrent_verifications_credit_once(self, cfg, tmp_path):
        env = Env(str(tmp_path / "c.db"))
        env.uid = env.add_user("payer@test.local", balance=10)
        env.h = env.user_headers(env.uid)
        add_order(env)
        results = []

        def go():
            with patch.object(razorpay_service, "get_payment_details", return_value=provider()):
                results.append(verify(env).status_code)

        # patch.object is process-wide, so install it once around the threads
        with patch.object(razorpay_service, "get_payment_details", return_value=provider()):
            threads = [threading.Thread(target=lambda: results.append(verify(env).status_code)) for _ in range(8)]
            [t.start() for t in threads]
            [t.join() for t in threads]
        assert all(code == 200 for code in results), results
        assert env.balance(env.uid) == 110.0 and txns(env) == 1

    def test_verify_and_webhook_race_credits_once(self, cfg, tmp_path):
        env = Env(str(tmp_path / "r.db"))
        env.uid = env.add_user("payer@test.local", balance=10)
        env.h = env.user_headers(env.uid)
        add_order(env)
        with patch.object(razorpay_service, "get_payment_details", return_value=provider()):
            ts = [threading.Thread(target=lambda: verify(env)) for _ in range(3)] + \
                 [threading.Thread(target=lambda: webhook(env, hook_payload())) for _ in range(3)]
            [t.start() for t in ts]
            [t.join() for t in ts]
        assert env.balance(env.uid) == 110.0 and txns(env) == 1


# ───────────────────────── webhook ──────────────────────────────────────────
class TestWebhook:
    def test_unsigned_request_is_rejected_and_credits_nothing(self, env):
        add_order(env)
        assert webhook(env, hook_payload(), sig=False).status_code == 400
        assert env.balance(env.uid) == 10

    def test_bad_signature_is_rejected(self, env):
        add_order(env)
        assert webhook(env, hook_payload(), secret="other-secret").status_code == 400
        assert env.balance(env.uid) == 10

    def test_unconfigured_secret_fails_closed(self, env):
        add_order(env)
        with patch.dict(os.environ, {"RAZORPAY_KEY_SECRET": "", "RAZORPAY_WEBHOOK_SECRET": ""}):
            assert webhook(env, hook_payload(), sig=False).status_code == 503
            assert webhook(env, hook_payload()).status_code == 503
        assert env.balance(env.uid) == 10

    def test_forged_event_for_an_unknown_order_is_ignored(self, env):
        r = webhook(env, hook_payload(order_id="order_FORGED", amount=99999900, user_note=str(env.uid)))
        assert r.status_code == 200 and r.json()["status"] == "ignored"
        assert env.balance(env.uid) == 10

    def test_signed_event_credits_the_order_owner_once(self, env):
        add_order(env)
        assert webhook(env, hook_payload(user_note=str(env.other))).status_code == 200   # note is ignored
        assert (env.balance(env.uid), env.balance(env.other)) == (110.0, 10)
        again = webhook(env, hook_payload())
        assert again.json().get("duplicate") is True
        assert env.balance(env.uid) == 110.0 and txns(env) == 1

    @pytest.mark.parametrize("kw", [dict(amount=999999), dict(status="failed")])
    def test_amount_or_status_mismatch_is_ignored(self, env, kw):
        add_order(env)
        assert webhook(env, hook_payload(**kw)).json()["status"] == "ignored"
        assert env.balance(env.uid) == 10

    def test_other_events_are_ignored(self, env):
        add_order(env)
        p = hook_payload()
        p["event"] = "payment.failed"
        assert webhook(env, p).json()["status"] == "ignored"
        assert env.balance(env.uid) == 10

    def test_verify_after_webhook_is_idempotent(self, env):
        add_order(env)
        webhook(env, hook_payload())
        with patch.object(razorpay_service, "get_payment_details", return_value=provider()):
            r = verify(env)
        assert r.status_code == 200 and r.json().get("idempotent") is True
        assert env.balance(env.uid) == 110.0 and txns(env) == 1

    def test_processing_error_returns_non_2xx_so_razorpay_retries(self, env):
        add_order(env)
        with patch("app.routes.payment._credit_order", side_effect=RuntimeError("boom")):
            assert webhook(env, hook_payload()).status_code == 500
        assert env.balance(env.uid) == 10


# ───────────────────────── other hardening ──────────────────────────────────
def test_provider_transaction_id_is_unique_in_the_schema(env):
    db = env.db()
    base = dict(reference="R1", amount=1, payment_method="upi", status="completed", provider_transaction_id="pay_dup")
    db.add(Transaction(**base))
    db.commit()
    db.add(Transaction(**{**base, "reference": "R2"}))
    with pytest.raises(IntegrityError):
        db.commit()


def test_debug_status_requires_an_administrator(env):
    assert env.client.get("/debug/status").status_code == 401
    assert env.client.get("/debug/status", headers=env.h).status_code == 401
    admin = env.add_admin()
    assert env.client.get("/debug/status", headers=env.admin_headers(admin)).status_code == 200


def test_otps_come_from_a_cryptographic_generator():
    assert re.fullmatch(r"\d{6}", generate_otp())
    with patch("app.utils.security.secrets.randbelow", return_value=0):
        assert generate_otp() == "100000"
    with patch("app.utils.security.secrets.randbelow", return_value=899999):
        assert generate_otp() == "999999"
    app_dir = Path(__file__).resolve().parent.parent / "app"
    for f in app_dir.rglob("*.py"):
        assert "random.randint" not in f.read_text(), f
