"""Wallet top-up OTP (the code that gates Razorpay order creation).

MOCKED: Razorpay's order API and the Amazon SES hop are replaced by fakes. No account, key or
network is used; these tests prove the server-side rules only.
"""
import json
import os
import threading
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import EmailOTP, PaymentOrder
from app.services.payment.razorpay_service import razorpay_service
from helpers import Env

KEY_ID = "rzp_test_fakefakefake"


class Outbox:
    def __init__(self):
        self.sent, self.fail = [], False

    def __call__(self, to_email, subject, html_content, text_content=None, attachments=None):
        if self.fail:
            return False, "SES rejected the message (simulated)"
        self.sent.append({"to": to_email, "subject": subject, "text": text_content or html_content})
        return True, None


@pytest.fixture
def outbox():
    box = Outbox()
    with patch("app.utils.email_service._send_ses_email", side_effect=box):
        yield box


@pytest.fixture
def cfg():
    with patch.dict(os.environ, {"RAZORPAY_KEY_ID": KEY_ID, "RAZORPAY_KEY_SECRET": "test_only_secret_not_real"}):
        yield


def fake_order(amount_in_rupees, notes=None):
    return {"order_id": f"order_T{int(amount_in_rupees * 100)}", "amount": int(round(amount_in_rupees * 100)),
            "currency": "INR", "key_id": KEY_ID, "is_mock": False}


def request_otp(env, amount=100.0, headers=None):
    return env.client.post("/api/payment/topup/request-otp", json={"amount": amount}, headers=headers or env.h)


def create_order(env, otp, amount=100.0, headers=None):
    return env.client.post("/api/payment/create-order", json={"amount": amount, "otp": otp}, headers=headers or env.h)


def row(env):
    db = env.db()
    try:
        r = db.query(EmailOTP).filter(EmailOTP.reason == "wallet_topup").order_by(EmailOTP.id.desc()).first()
        if r is not None:
            db.expunge(r)
        return r
    finally:
        db.close()


def orders(env):
    db = env.db()
    try:
        return db.query(PaymentOrder).count()
    finally:
        db.close()


def wrong(code):
    return "000000" if code != "000000" else "111111"


@pytest.fixture
def env(cfg):
    e = Env()
    e.uid = e.add_user("payer@example.com", balance=10)
    e.other = e.add_user("other@example.com", balance=10)
    e.h = e.user_headers(e.uid)
    return e


class TestRequestOtp:
    def test_the_code_is_emailed_and_never_returned(self, env, outbox):
        res = request_otp(env)
        assert res.status_code == 200 and res.json()["success"] is True
        code = row(env).otp
        assert len(outbox.sent) == 1 and code in outbox.sent[0]["text"].replace(" ", "")
        assert code not in res.text

    def test_a_failed_send_is_an_error_not_a_success(self, env, outbox):
        outbox.fail = True
        res = request_otp(env)
        assert res.status_code == 500 and res.json().get("success") is not True
        assert "SES" not in res.text and "simulated" not in res.text      # provider text stays in the log
        assert row(env) is not None                                        # the code stays persisted

    def test_resend_cooldown_and_hourly_cap(self, env, outbox):
        assert request_otp(env).status_code == 200
        assert request_otp(env).status_code == 429                         # 60 s cooldown
        for _ in range(4):                                                 # five codes within the hour in total
            db = env.db()
            db.query(EmailOTP).filter(EmailOTP.id == row(env).id).update(
                {"created_at": datetime.utcnow() - timedelta(seconds=61)})
            db.commit()
            db.close()
            assert request_otp(env).status_code == 200
        db = env.db()
        db.query(EmailOTP).filter(EmailOTP.id == row(env).id).update({"created_at": datetime.utcnow() - timedelta(seconds=61)})
        db.commit()
        db.close()
        capped = request_otp(env)
        assert capped.status_code == 429 and "hour" in capped.json()["detail"].lower()
        assert len(outbox.sent) == 5


class TestCreateOrder:
    @pytest.fixture(autouse=True)
    def provider(self):
        with patch.object(razorpay_service, "create_order", side_effect=fake_order) as m:
            self.create_mock = m
            yield m

    def test_the_right_code_creates_one_order_and_is_consumed(self, env, outbox):
        request_otp(env)
        code = row(env).otp
        res = create_order(env, code)
        assert res.status_code == 200 and res.json()["order_id"] == "order_T10000" and res.json()["key_id"] == KEY_ID
        assert row(env).used is True and orders(env) == 1
        replay = create_order(env, code)
        assert replay.status_code == 400 and orders(env) == 1             # the code cannot be used twice

    def test_wrong_codes_count_and_lock_after_five(self, env, outbox):
        request_otp(env)
        code = row(env).otp
        details = [create_order(env, wrong(code)).json()["detail"] for _ in range(5)]
        assert "4 attempts remaining" in details[0] and "Too many incorrect" in details[4]
        assert create_order(env, code).status_code == 400                  # even the right code is dead now
        assert orders(env) == 0

    def test_a_code_for_another_amount_does_not_create_an_order_or_get_consumed(self, env, outbox):
        request_otp(env, 100.0)
        code = row(env).otp
        res = create_order(env, code, amount=999.0)
        assert res.status_code == 400 and "different amount" in res.json()["detail"]
        assert row(env).used is False and orders(env) == 0
        assert create_order(env, code, amount=100.0).status_code == 200    # the right amount still works

    def test_a_code_belongs_to_one_user(self, env, outbox):
        request_otp(env)
        code = row(env).otp
        res = create_order(env, code, headers=env.user_headers(env.other))
        assert res.status_code == 400 and orders(env) == 0

    def test_a_provider_failure_does_not_burn_the_code(self, env, outbox):
        request_otp(env)
        code = row(env).otp
        self.create_mock.side_effect = RuntimeError("provider down")
        res = create_order(env, code)
        assert res.status_code == 500 and "provider down" not in res.text
        assert row(env).used is False and orders(env) == 0
        self.create_mock.side_effect = fake_order                          # the provider recovers
        assert create_order(env, code).status_code == 200

    def test_an_expired_code_is_refused(self, env, outbox):
        request_otp(env)
        code = row(env).otp
        db = env.db()
        db.query(EmailOTP).filter(EmailOTP.id == row(env).id).update({"expires_at": datetime.utcnow() - timedelta(seconds=5)})
        db.commit()
        db.close()
        res = create_order(env, code)
        assert res.status_code == 400 and "expired" in res.json()["detail"].lower() and orders(env) == 0


class TestConcurrency:
    @pytest.fixture(autouse=True)
    def provider(self):
        with patch.object(razorpay_service, "create_order", side_effect=fake_order):
            yield

    def _burst(self, n, fn):
        results, barrier = [], threading.Barrier(n)

        def go():
            barrier.wait()
            results.append(fn())

        threads = [threading.Thread(target=go) for _ in range(n)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return results

    def test_parallel_guesses_cannot_exceed_the_attempt_limit(self, cfg, outbox, tmp_path):
        env = Env(str(tmp_path / "t1.db"))
        env.uid = env.add_user("payer@example.com", balance=10)
        env.h = env.user_headers(env.uid)
        request_otp(env)
        code = row(env).otp
        bad = wrong(code)
        codes = self._burst(20, lambda: create_order(env, bad).status_code)
        assert all(c == 400 for c in codes)
        r = row(env)
        assert r.used is True and r.attempts == 5 and orders(env) == 0

    def test_one_code_creates_exactly_one_order_under_parallel_requests(self, cfg, outbox, tmp_path):
        env = Env(str(tmp_path / "t2.db"))
        env.uid = env.add_user("payer@example.com", balance=10)
        env.h = env.user_headers(env.uid)
        request_otp(env)
        code = row(env).otp
        codes = self._burst(6, lambda: create_order(env, code).status_code)
        assert codes.count(200) == 1, codes
        assert orders(env) == 1
