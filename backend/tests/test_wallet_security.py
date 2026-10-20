"""Wallet, ride payment, withdrawal and admin-transition security
(findings F-01..F-07, F-16, F-17, F-18, F-25). All mocked, no network."""
import json
import threading
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import EmailOTP, Transaction, WithdrawalRequest
from helpers import Env

BANK = dict(bank_account_holder="Rider R", bank_account_number="123456789012",
            bank_ifsc="HDFC0001234", bank_upi_id="rider@hdfc")


@pytest.fixture(autouse=True)
def _no_email():
    with patch("app.routes.wallet.send_withdrawal_otp", return_value=True), \
         patch("app.routes.wallet.send_withdrawal_email", return_value=True), \
         patch("app.routes.wallet.send_ride_passenger_email", return_value=True), \
         patch("app.routes.wallet.send_ride_driver_email", return_value=True), \
         patch("app.routes.admin.send_withdrawal_approved_email", return_value=True), \
         patch("app.routes.admin.send_withdrawal_paid_email", return_value=True), \
         patch("app.routes.admin.send_withdrawal_rejected_email", return_value=True):
        yield


def key():
    return uuid.uuid4().hex


@pytest.fixture
def env():
    e = Env()
    e.p = e.add_user("rider@test.local", balance=500, **BANK)
    e.d = e.add_user("driver@test.local", account_type="driver", balance=0)
    e.other = e.add_user("other@test.local", balance=300)
    e.ph, e.dh, e.oh = e.user_headers(e.p), e.user_headers(e.d), e.user_headers(e.other)
    return e


def pay(env, fare=100, driver=None, headers=None, **extra):
    body = {"driver_id": env.d if driver is None else driver, "fare": fare, "idempotency_key": key(), **extra}
    body = {k: v for k, v in body.items() if v is not ...}
    return env.client.post("/api/wallet/pay", json=body, headers=env.ph if headers is None else headers)


# ───────────────────────────── wallet reads ─────────────────────────────────
class TestWalletReads:
    def test_requires_authentication(self, env):
        for path in (f"/api/wallet/{env.p}", f"/api/wallet/{env.p}/transactions"):
            assert env.client.get(path).status_code == 401

    def test_cross_user_reads_are_forbidden(self, env):
        for path in (f"/api/wallet/{env.p}", f"/api/wallet/{env.p}/transactions"):
            assert env.client.get(path, headers=env.oh).status_code == 403

    def test_owner_can_read(self, env):
        assert env.client.get(f"/api/wallet/{env.p}", headers=env.ph).json()["wallet"]["balance"] == 500
        assert env.client.get(f"/api/wallet/{env.p}/transactions", headers=env.ph).status_code == 200

    def test_refunds_and_driver_deposits_are_labelled_correctly(self, env):
        db = env.db()
        db.add(Transaction(reference="REV-WD-1", driver_id=env.d, amount=50, payment_method="bank_transfer",
                           status="completed", transaction_type="withdrawal_reversal",
                           description="Reversal of rejected withdrawal WD-1"))
        db.add(Transaction(reference="RZP1", driver_id=env.d, amount=75, payment_method="UPI", status="completed",
                           transaction_type="deposit", provider="RAZORPAY", provider_transaction_id="pay_x"))
        db.add(Transaction(reference="WD-1", driver_id=env.d, amount=20, payment_method="bank_transfer",
                           status="pending", transaction_type="withdrawal_hold"))
        db.commit()
        db.close()
        rows = {t["reference"]: t for t in
                env.client.get(f"/api/wallet/{env.d}/transactions", headers=env.dh).json()["transactions"]}
        assert rows["REV-WD-1"]["is_credit"] is True and rows["REV-WD-1"]["type"] == "Withdrawal Reversal"
        assert rows["RZP1"]["is_credit"] is True and rows["RZP1"]["type"].startswith("Add Money")
        assert rows["WD-1"]["is_credit"] is False and rows["WD-1"]["type"] == "Withdrawal"
        assert rows["RZP1"]["transaction_type"] == "deposit"


# ───────────────────────────── POST /pay ────────────────────────────────────
class TestPay:
    def test_requires_authentication(self, env):
        assert pay(env, headers={}).status_code == 401
        assert (env.balance(env.p), env.balance(env.d)) == (500, 0)

    def test_success_moves_money_once_and_returns_a_confirmation(self, env):
        r = pay(env, 120)
        assert r.status_code == 200
        t = r.json()["transaction"]
        assert t["reference"].startswith("TXN") and t["status"] == "completed" and t["amount"] == 120
        assert t["driver_id"] == env.d and t["id"]
        assert r.json()["wallet"]["balance"] == 380
        assert (env.balance(env.p), env.balance(env.d)) == (380, 120)

    def test_forged_passenger_id_is_refused(self, env):
        assert pay(env, passenger_id=env.other).status_code == 403
        assert pay(env, passenger_id=env.p).status_code == 200      # matching id is fine (old clients)
        assert env.balance(env.other) == 300

    def test_attacker_cannot_debit_a_victim_by_naming_them(self, env):
        r = pay(env, passenger_id=env.p, headers=env.oh)
        assert r.status_code == 403
        assert env.balance(env.p) == 500

    def test_driver_id_is_mandatory(self, env):
        body = {"fare": 50, "idempotency_key": key()}
        assert env.client.post("/api/wallet/pay", json=body, headers=env.ph).status_code == 422
        assert (env.balance(env.p), env.balance(env.d)) == (500, 0)

    def test_no_fallback_to_another_driver_when_driver_id_is_null(self, env):
        body = {"driver_id": None, "fare": 50, "idempotency_key": key()}
        assert env.client.post("/api/wallet/pay", json=body, headers=env.ph).status_code == 422
        assert (env.balance(env.p), env.balance(env.d)) == (500, 0)

    @pytest.mark.parametrize("kind", ["unknown", "passenger", "self", "suspended", "pending"])
    def test_recipient_must_be_another_active_driver(self, env, kind):
        target = {
            "unknown": 99999,
            "passenger": env.other,
            "self": env.p,
            "suspended": env.add_user("sus@test.local", account_type="driver", balance=0, status="suspended"),
            "pending": env.add_user("pen@test.local", account_type="driver", balance=0, status="pending"),
        }[kind]
        assert pay(env, driver=target).status_code == 400
        assert env.balance(env.p) == 500

    def test_frozen_recipient_does_not_debit_the_passenger(self, env):
        frozen = env.add_user("frozen@test.local", account_type="driver", balance=0, frozen=True)
        r = pay(env, driver=frozen)
        assert r.status_code == 400
        assert env.balance(env.p) == 500 and env.balance(frozen) == 0

    def test_frozen_or_unfunded_payer_is_refused(self, env):
        fz = env.add_user("fz@test.local", balance=500, frozen=True)
        assert pay(env, headers=env.user_headers(fz)).status_code == 400
        assert env.balance(fz) == 500
        poor = env.add_user("poor@test.local", balance=10)
        r = pay(env, 100, headers=env.user_headers(poor))
        assert r.status_code == 400 and "Insufficient" in r.json()["detail"]
        assert env.balance(poor) == 10 and env.balance(env.d) == 0

    @pytest.mark.parametrize("fare", [0, -5, 0.001, 12.345, 1e9, 50001, "abc", None])
    def test_invalid_amounts_change_nothing(self, env, fare):
        assert pay(env, fare).status_code in (400, 422)
        assert (env.balance(env.p), env.balance(env.d)) == (500, 0)

    def test_nan_and_infinity_are_rejected(self, env):
        for raw in ("NaN", "Infinity"):
            body = f'{{"driver_id": {env.d}, "fare": {raw}, "idempotency_key": "{key()}"}}'
            r = env.client.post("/api/wallet/pay", content=body, headers={**env.ph, "Content-Type": "application/json"})
            assert r.status_code in (400, 422)
        assert env.balance(env.p) == 500

    def test_only_active_passengers_can_pay(self, env):
        assert pay(env, headers=env.dh).status_code == 403            # a driver cannot pay as passenger
        sus = env.add_user("sp@test.local", balance=100, status="suspended")
        assert pay(env, headers=env.user_headers(sus)).status_code == 403

    def test_idempotency_key_is_mandatory_and_well_formed(self, env):
        for k in (..., "", "short"):
            body = {"driver_id": env.d, "fare": 10}
            if k is not ...:
                body["idempotency_key"] = k
            assert env.client.post("/api/wallet/pay", json=body, headers=env.ph).status_code in (400, 422)
        assert env.balance(env.p) == 500

    def test_replay_returns_the_original_payment_without_a_second_debit(self, env):
        k = key()
        a = env.client.post("/api/wallet/pay", json={"driver_id": env.d, "fare": 40, "idempotency_key": k}, headers=env.ph)
        b = env.client.post("/api/wallet/pay", json={"driver_id": env.d, "fare": 40, "idempotency_key": k}, headers=env.ph)
        assert a.status_code == b.status_code == 200
        assert a.json()["transaction"]["reference"] == b.json()["transaction"]["reference"]
        assert b.json()["idempotent"] is True
        assert (env.balance(env.p), env.balance(env.d)) == (460, 40)

    def test_reusing_a_key_for_a_different_payment_is_refused(self, env):
        k = key()
        assert env.client.post("/api/wallet/pay", json={"driver_id": env.d, "fare": 40, "idempotency_key": k}, headers=env.ph).status_code == 200
        r = env.client.post("/api/wallet/pay", json={"driver_id": env.d, "fare": 90, "idempotency_key": k}, headers=env.ph)
        assert r.status_code == 409
        assert env.balance(env.p) == 460

    def test_another_users_key_is_not_a_replay_and_leaks_nothing(self, env):
        k = key()
        env.client.post("/api/wallet/pay", json={"driver_id": env.d, "fare": 40, "idempotency_key": k}, headers=env.ph)
        r = env.client.post("/api/wallet/pay", json={"driver_id": env.d, "fare": 40, "idempotency_key": k}, headers=env.oh)
        assert r.status_code == 200 and r.json().get("idempotent") is not True
        assert r.json()["wallet"]["user_id"] == env.other
        assert (env.balance(env.p), env.balance(env.other)) == (460, 260)

    def test_concurrent_duplicate_requests_debit_once(self, tmp_path):
        e = Env(str(tmp_path / "p.db"))
        p = e.add_user("rider@test.local", balance=500)
        d = e.add_user("driver@test.local", account_type="driver", balance=0)
        h = e.user_headers(p)
        k = key()
        codes = []

        def go():
            codes.append(e.client.post("/api/wallet/pay", json={"driver_id": d, "fare": 100, "idempotency_key": k}, headers=h).status_code)

        ts = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert all(c == 200 for c in codes), codes
        assert (e.balance(p), e.balance(d)) == (400, 100)
        db = e.db()
        assert db.query(Transaction).filter(Transaction.transaction_type == "ride_payment").count() == 1

    def test_concurrent_payments_cannot_overdraw(self, tmp_path):
        e = Env(str(tmp_path / "o.db"))
        p = e.add_user("rider@test.local", balance=100)
        d = e.add_user("driver@test.local", account_type="driver", balance=0)
        h = e.user_headers(p)
        codes = []

        def go():
            codes.append(e.client.post("/api/wallet/pay", json={"driver_id": d, "fare": 100, "idempotency_key": key()}, headers=h).status_code)

        ts = [threading.Thread(target=go) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert codes.count(200) == 1, codes
        assert (e.balance(p), e.balance(d)) == (0, 100)

    def test_money_is_conserved(self, env):
        before = sum(env.balance(u) for u in (env.p, env.d, env.other))
        for fare in (10, 20.5, 300, 5000):                      # the last one fails (insufficient)
            pay(env, fare)
        assert sum(env.balance(u) for u in (env.p, env.d, env.other)) == before


# ───────────────────────────── withdrawals ──────────────────────────────────
def otp_for(env, email="rider@test.local"):
    db = env.db()
    try:
        row = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.reason == "withdraw_balance").order_by(EmailOTP.id.desc()).first()
        return row.otp, row.id
    finally:
        db.close()


def request_otp(env, amount=100, headers=None, **extra):
    return env.client.post("/api/wallet/withdraw/request-otp", json={"amount": amount, **extra},
                           headers=env.ph if headers is None else headers)


def withdraw(env, amount=100, otp=None, headers=None, k=None, **extra):
    body = {"amount": amount, "otp": otp, **extra}
    if k is not False:
        body["idempotency_key"] = k or key()
    return env.client.post("/api/wallet/withdraw", json=body, headers=env.ph if headers is None else headers)


class TestWithdrawalOtp:
    def test_requires_authentication_and_ownership(self, env):
        assert request_otp(env, headers={}).status_code == 401
        assert request_otp(env, user_id=env.other).status_code == 403
        assert request_otp(env, headers=env.oh, user_id=env.p).status_code == 403

    def test_needs_a_saved_payout_destination(self, env):
        assert request_otp(env, headers=env.oh).status_code == 400

    def test_otp_is_bound_to_user_and_amount_and_never_returned(self, env):
        r = request_otp(env, 150)
        assert r.status_code == 200
        otp, _ = otp_for(env)
        assert otp not in r.text
        db = env.db()
        row = db.query(EmailOTP).filter_by(reason="withdraw_balance").first()
        meta = json.loads(row.otp_metadata)
        assert meta == {"amount": "150.00", "user_id": env.p}

    def test_cooldown_returns_429(self, env):
        assert request_otp(env).status_code == 200
        assert request_otp(env).status_code == 429

    @pytest.mark.parametrize("amount", [0, -1, 0.001, 999999])
    def test_invalid_or_unaffordable_amounts(self, env, amount):
        assert request_otp(env, amount).status_code == 400


class TestWithdrawSubmit:
    def ready(self, env, amount=100):
        assert request_otp(env, amount).status_code == 200
        return otp_for(env)[0]

    def test_requires_authentication_and_ownership(self, env):
        otp = self.ready(env)
        assert withdraw(env, otp=otp, headers={}).status_code == 401
        assert withdraw(env, otp=otp, user_id=env.other).status_code == 403
        assert withdraw(env, otp=otp, headers=env.oh).status_code == 400      # other user has no bank/OTP
        assert env.balance(env.p) == 500

    def test_success_reserves_funds_and_records_the_request(self, env):
        otp = self.ready(env, 100)
        r = withdraw(env, 100, otp)
        assert r.status_code == 200
        b = r.json()
        assert b["request_status"] == "pending" and b["wallet"]["balance"] == 400 and b["reference"].startswith("WD-")
        db = env.db()
        wr = db.query(WithdrawalRequest).one()
        hold = db.get(Transaction, wr.hold_transaction_id)
        assert (float(wr.amount), wr.status, hold.status, hold.transaction_type) == (100, "pending", "pending", "withdrawal_hold")
        assert env.balance(env.p) == 400

    def test_otp_for_another_amount_is_rejected_and_counts_as_an_attempt(self, env):
        otp = self.ready(env, 10)
        r = withdraw(env, 400, otp)
        assert r.status_code == 400 and "not issued for this withdrawal amount" in r.json()["detail"]
        assert env.balance(env.p) == 500
        db = env.db()
        assert db.query(EmailOTP).filter_by(reason="withdraw_balance").first().attempts == 1

    def test_otp_replay_is_rejected(self, env):
        otp = self.ready(env, 100)
        assert withdraw(env, 100, otp).status_code == 200
        assert withdraw(env, 100, otp).status_code == 400
        assert env.balance(env.p) == 400

    def test_wrong_purpose_otp_is_rejected(self, env):
        db = env.db()
        db.add(EmailOTP(email="rider@test.local", otp="111111", reason="wallet_topup", purpose="wallet_topup",
                        expires_at=datetime.utcnow() + timedelta(minutes=5),
                        otp_metadata=json.dumps({"amount": "100.00", "user_id": env.p})))
        db.commit()
        assert withdraw(env, 100, "111111").status_code == 400
        assert env.balance(env.p) == 500

    def test_legacy_otp_without_metadata_is_rejected(self, env):
        db = env.db()
        db.add(EmailOTP(email="rider@test.local", otp="222222", reason="withdraw_balance", purpose="withdraw_balance",
                        expires_at=datetime.utcnow() + timedelta(minutes=5)))
        db.commit()
        assert withdraw(env, 100, "222222").status_code == 400
        assert env.balance(env.p) == 500

    def test_expired_otp_and_attempt_limit(self, env):
        otp = self.ready(env, 100)
        db = env.db()
        row = db.query(EmailOTP).filter_by(reason="withdraw_balance").first()
        row.expires_at = datetime.utcnow() - timedelta(minutes=10)
        db.commit()
        assert withdraw(env, 100, otp).status_code == 400
        # attempts: after 5 wrong guesses even the right code is refused
        row.expires_at = datetime.utcnow() + timedelta(minutes=5)
        row.used = False
        row.attempts = 0
        db.commit()
        for _ in range(5):
            assert withdraw(env, 100, "000000").status_code == 400
        assert withdraw(env, 100, otp).status_code == 400
        assert env.balance(env.p) == 500

    def test_missing_otp_and_missing_bank(self, env):
        assert withdraw(env, 100, None).status_code == 400
        assert withdraw(env, 100, "123456", headers=env.oh).status_code == 400

    def test_frozen_wallet_and_insufficient_funds(self, env):
        otp = self.ready(env, 100)
        db = env.db()
        from app.models import Wallet
        db.query(Wallet).filter_by(user_id=env.p).update({"balance": 50})
        db.commit()
        r = withdraw(env, 100, otp)
        assert r.status_code == 400
        assert env.balance(env.p) == 50
        # OTP stays usable because nothing was consumed
        db.query(Wallet).filter_by(user_id=env.p).update({"balance": 500, "is_frozen": True})
        db.commit()
        assert withdraw(env, 100, otp).status_code == 400
        assert env.balance(env.p) == 500

    def test_idempotent_replay_returns_the_same_request(self, env):
        otp = self.ready(env, 100)
        k = key()
        a = withdraw(env, 100, otp, k=k)
        b = withdraw(env, 100, otp, k=k)
        assert a.status_code == b.status_code == 200
        assert a.json()["request_id"] == b.json()["request_id"] and b.json()["idempotent"] is True
        assert env.balance(env.p) == 400
        assert withdraw(env, 250, otp, k=k).status_code == 409           # same key, different amount

    def test_idempotency_keys_are_scoped_to_the_user(self, env):
        env.bank = env.add_user("rider2@test.local", balance=500, **{**BANK, "bank_account_number": "999988887777"})
        h2 = env.user_headers(env.bank)
        k = key()
        otp1 = self.ready(env, 100)
        assert withdraw(env, 100, otp1, k=k).status_code == 200
        assert request_otp(env, 100, headers=h2).status_code == 200
        otp2 = otp_for(env, "rider2@test.local")[0]
        r = withdraw(env, 100, otp2, headers=h2, k=k)
        assert r.status_code == 200 and r.json().get("idempotent") is not True
        assert env.balance(env.bank) == 400

    def test_concurrent_submissions_with_one_otp_withdraw_once(self, tmp_path):
        e = Env(str(tmp_path / "w.db"))
        p = e.add_user("rider@test.local", balance=500, **BANK)
        h = e.user_headers(p)
        e.client.post("/api/wallet/withdraw/request-otp", json={"amount": 100}, headers=h)
        otp = otp_for(e)[0]
        codes = []

        def go():
            codes.append(e.client.post("/api/wallet/withdraw", json={"amount": 100, "otp": otp, "idempotency_key": key()}, headers=h).status_code)

        ts = [threading.Thread(target=go) for _ in range(6)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert codes.count(200) == 1, codes
        assert e.balance(p) == 400
        db = e.db()
        assert db.query(WithdrawalRequest).count() == 1

    def test_history_is_private_to_the_owner(self, env):
        otp = self.ready(env, 100)
        withdraw(env, 100, otp)
        assert env.client.get("/api/wallet/withdraw/history").status_code == 401
        mine = env.client.get("/api/wallet/withdraw/history", headers=env.ph).json()["withdrawal_requests"]
        theirs = env.client.get("/api/wallet/withdraw/history", headers=env.oh).json()["withdrawal_requests"]
        assert len(mine) == 1 and mine[0]["status"] == "pending" and theirs == []


# ───────────────────────── admin withdrawal transitions ─────────────────────
class TestAdminTransitions:
    def make_request(self, env, amount=100):
        db0 = env.db()
        db0.query(EmailOTP).update({"created_at": datetime.utcnow() - timedelta(minutes=5)})   # skip the 60 s cooldown
        db0.commit()
        db0.close()
        assert request_otp(env, amount).status_code == 200
        assert withdraw(env, amount, otp_for(env)[0]).status_code == 200
        db = env.db()
        wr_id = db.query(WithdrawalRequest).order_by(WithdrawalRequest.id.desc()).first().id
        db.close()
        if not hasattr(env, 'ah'):
            env.ah = env.admin_headers(env.add_admin())
        return wr_id

    def act(self, env, wr, action, **kw):
        return env.client.patch(f"/api/admin/withdrawal-requests/{wr}/{action}", headers=env.ah, **kw)

    def test_happy_path_pending_approved_paid(self, env):
        wr = self.make_request(env)
        assert self.act(env, wr, "approve").json()["withdrawal_request"]["status"] == "approved"
        assert self.act(env, wr, "pay").json()["withdrawal_request"]["status"] == "paid"
        assert env.balance(env.p) == 400                          # nothing refunded
        db = env.db()
        assert db.query(Transaction).filter_by(transaction_type="withdrawal").count() == 1

    def test_pay_requires_approval_first(self, env):
        wr = self.make_request(env)
        assert self.act(env, wr, "pay").status_code == 400

    def test_reject_refunds_once_and_labels_the_refund(self, env):
        wr = self.make_request(env)
        r = self.act(env, wr, "reject", json={"admin_note": "bank mismatch"})
        assert r.json()["withdrawal_request"]["status"] == "rejected"
        assert env.balance(env.p) == 500
        again = self.act(env, wr, "reject", json={})
        assert again.status_code == 200 and "already rejected" in again.json()["message"]
        assert env.balance(env.p) == 500                          # no second refund
        rows = {t["reference"]: t for t in env.client.get(f"/api/wallet/{env.p}/transactions", headers=env.ph).json()["transactions"]}
        rev = [t for ref, t in rows.items() if ref.startswith("REV-")][0]
        assert rev["is_credit"] is True and rev["type"] == "Withdrawal Reversal"

    def test_cannot_reject_after_approval_or_approve_after_rejection(self, env):
        wr = self.make_request(env)
        self.act(env, wr, "approve")
        assert self.act(env, wr, "reject", json={}).status_code == 400
        wr2 = self.make_request(env)
        self.act(env, wr2, "reject", json={})
        assert "already in status 'rejected'" in self.act(env, wr2, "approve").json()["message"]
        assert self.act(env, wr2, "pay").status_code == 400

    def test_unknown_request_is_404(self, env):
        env.ah = env.admin_headers(env.add_admin())
        assert self.act(env, 9999, "approve").status_code == 404

    def test_concurrent_approve_and_reject_have_exactly_one_outcome(self, tmp_path):
        e = Env(str(tmp_path / "t.db"))
        p = e.add_user("rider@test.local", balance=500, **BANK)
        h = e.user_headers(p)
        e.client.post("/api/wallet/withdraw/request-otp", json={"amount": 100}, headers=h)
        e.client.post("/api/wallet/withdraw", json={"amount": 100, "otp": otp_for(e)[0], "idempotency_key": key()}, headers=h)
        ah = e.admin_headers(e.add_admin())
        outcomes = []

        def go(action):
            r = e.client.patch(f"/api/admin/withdrawal-requests/1/{action}", headers=ah, json={})
            outcomes.append((action, r.status_code, r.json().get("withdrawal_request", {}).get("status")))

        ts = [threading.Thread(target=go, args=(a,)) for a in ["approve", "reject"] * 3]
        [t.start() for t in ts]
        [t.join() for t in ts]
        db = e.db()
        final = db.get(WithdrawalRequest, 1).status
        assert final in ("approved", "rejected")
        refunds = db.query(Transaction).filter_by(transaction_type="withdrawal_reversal").count()
        if final == "rejected":
            assert refunds == 1 and e.balance(p) == 500
        else:
            assert refunds == 0 and e.balance(p) == 400
