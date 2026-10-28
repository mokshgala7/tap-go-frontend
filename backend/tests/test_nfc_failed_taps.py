"""
test_nfc_failed_taps.py
───────────────────────
Failed NFC taps: each business failure of POST /api/nfc/pay is stored as a `failed` transaction
(no balance change), replays return the same failure, the card owner gets an email (throttled,
after the response), and money views ignore failed rows.
"""
import asyncio
import json
import threading
import time
import uuid
from unittest.mock import patch

import pytest

from tests.helpers import Env
from app.models import NFCCard, Transaction, User, Wallet
from app.routes import nfc_pay
from app.utils import nfc_failure_email

UID = "04A2B3C4D5E680"
CODES = ["CARD_UNKNOWN", "CARD_BLOCKED", "CARD_LOST", "PASSENGER_INACTIVE",
         "WALLET_FROZEN", "INSUFFICIENT_BALANCE", "AMOUNT_INVALID"]
MAIL = "app.routes.nfc_pay.send_nfc_failure_email"


@pytest.fixture(autouse=True)
def _no_throttle_and_clean_state(monkeypatch):
    monkeypatch.setenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", "0")
    nfc_pay._failure_email_last_sent.clear()
    yield
    nfc_pay._failure_email_last_sent.clear()


@pytest.fixture
def env():
    return Env()


@pytest.fixture
def scene(env):
    driver_id = env.add_user("drv@failtest.local", account_type="driver", balance=0, name="Rakesh Sharma",
                             vehicle_type="Auto", vehicle_registration="MH12AB1234")
    pax_id = env.add_user("pax@failtest.local", account_type="passenger", balance=500, name="Asha Verma")
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax_id, card_reference="NFC-FAIL0001", card_uid=UID, status="active"))
        db.commit()
    finally:
        db.close()
    return {"env": env, "driver_id": driver_id, "pax_id": pax_id,
            "driver_headers": env.user_headers(driver_id), "pax_headers": env.user_headers(pax_id)}


def pay(scene, uid=UID, amount=12.5, key=None, headers=None):
    return scene["env"].client.post(
        "/api/nfc/pay",
        json={"card_uid": uid, "amount": amount, "idempotency_key": key or f"tap-{uuid.uuid4().hex}"},
        headers=headers or scene["driver_headers"],
    )


def rows(scene, **filters):
    db = scene["env"].db()
    try:
        out = db.query(Transaction).filter_by(**filters).order_by(Transaction.id).all()
        for r in out:
            db.expunge(r)
        return out
    finally:
        db.close()


def arrange(scene, code):
    """Put the world into the state that makes `code` happen; returns the kwargs for pay()."""
    db = scene["env"].db()
    try:
        if code == "CARD_BLOCKED":
            db.query(NFCCard).update({"status": "blocked"})
        elif code == "CARD_LOST":
            db.query(NFCCard).update({"status": "lost"})
        elif code == "PASSENGER_INACTIVE":
            db.query(User).filter(User.id == scene["pax_id"]).update({"status": "suspended"})
        elif code == "WALLET_FROZEN":
            db.query(Wallet).filter(Wallet.user_id == scene["pax_id"]).update({"is_frozen": True})
        db.commit()
    finally:
        db.close()
    return {
        "CARD_UNKNOWN": {"uid": "AABBCCDD"},
        "INSUFFICIENT_BALANCE": {"amount": 600},
        "AMOUNT_INVALID": {"amount": -5},
    }.get(code, {})


# ── 1. every failure code records exactly one failed row, no balance change ─────────────

@pytest.mark.parametrize("code", CODES)
def test_each_failure_records_one_failed_row_and_moves_no_money(scene, code):
    kwargs = arrange(scene, code)
    r = pay(scene, key="record-key-0001", **kwargs)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False and body["status"] == "Failed" and body["code"] == code
    assert body["message"] and body["reference"].startswith("TXN")
    assert set(body) <= {"success", "status", "code", "message", "reference"}

    [t] = rows(scene)
    assert t.reference == body["reference"]
    assert (t.status, t.failure_code, t.payment_method, t.transaction_type) == ("failed", code, "NFC", "ride_payment")
    assert (t.fraud_status, t.balance_after) == ("clear", None)
    assert t.driver_id == scene["driver_id"]
    assert t.idempotency_key == f"nfc:{scene['driver_id']}:record-key-0001"
    assert t.description.startswith("NFC payment failed: ")
    if code == "CARD_UNKNOWN":
        assert t.passenger_id is None and t.wallet_id is None
    else:
        assert t.passenger_id == scene["pax_id"] and t.wallet_id is not None
    if code == "AMOUNT_INVALID":
        assert float(t.amount) == 0 and "-5" in t.description
    else:
        assert float(t.amount) == kwargs.get("amount", 12.5)

    env = scene["env"]
    assert env.balance(scene["pax_id"]) == 500 and env.balance(scene["driver_id"]) == 0


def test_over_limit_amount_is_recorded_as_amount_invalid(scene):
    r = pay(scene, amount=99999999)
    assert r.json()["code"] == "AMOUNT_INVALID"
    [t] = rows(scene)
    assert float(t.amount) == 0 and "99999999" in t.description


def test_pos_response_never_leaks_balance_or_contact_details(scene):
    arrange(scene, "INSUFFICIENT_BALANCE")
    text = pay(scene, amount=600).text
    assert "500" not in text and "pax@failtest.local" not in text and "Asha" not in text


# ── 2. cases that are NOT recorded ───────────────────────────────────────────────────────

def test_driver_not_allowed_conflict_unauthenticated_and_bad_key_leave_no_row(scene):
    env = scene["env"]
    assert pay(scene, headers=scene["pax_headers"]).status_code == 403
    susp = env.add_user("susp@failtest.local", account_type="driver", status="suspended", balance=0)
    assert pay(scene, headers=env.user_headers(susp)).status_code == 403
    frozen = env.add_user("fd@failtest.local", account_type="driver", balance=0, frozen=True)
    r = pay(scene, headers=env.user_headers(frozen))
    assert r.status_code == 403 and r.json()["code"] == "DRIVER_NOT_ALLOWED"
    assert env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 5, "idempotency_key": "no-auth-key-1"}).status_code == 401
    for bad in (None, "", "short", "x" * 101):
        r = env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 5, "idempotency_key": bad},
                            headers=scene["driver_headers"])
        assert r.status_code == 400
    assert rows(scene) == []

    pay(scene, amount=10, key="conflict-key-01")                    # completes: 1 row
    assert pay(scene, amount=11, key="conflict-key-01").status_code == 409
    assert len(rows(scene)) == 1


# ── 3. replays ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", CODES)
def test_replay_returns_same_failure_without_new_row_or_email(scene, code):
    kwargs = arrange(scene, code)
    with patch(MAIL, return_value=True) as mail:
        first = pay(scene, key="replay-key-0001", **kwargs).json()
        second = pay(scene, key="replay-key-0001", **kwargs)
    again = second.json()
    assert second.status_code == 200 and again["idempotent"] is True
    assert {k: again[k] for k in ("success", "status", "code", "message", "reference")} == \
           {k: first[k] for k in ("success", "status", "code", "message", "reference")}
    assert len(rows(scene)) == 1
    assert mail.call_count == (0 if code == "CARD_UNKNOWN" else 1)


def test_replay_survives_the_cause_being_fixed(scene):
    arrange(scene, "CARD_BLOCKED")
    first = pay(scene, key="replay-key-0002").json()
    db = scene["env"].db()
    try:
        db.query(NFCCard).update({"status": "active"})
        db.commit()
    finally:
        db.close()
    again = pay(scene, key="replay-key-0002").json()
    assert again["code"] == "CARD_BLOCKED" and again["reference"] == first["reference"]
    assert pay(scene, key="replay-key-0003").json()["success"] is True       # a new tap works


def test_key_reuse_with_a_different_amount_or_card_is_a_conflict_not_a_replay(scene):
    arrange(scene, "INSUFFICIENT_BALANCE")
    pay(scene, amount=600, key="conflict-key-02")
    assert pay(scene, amount=700, key="conflict-key-02").status_code == 409
    assert pay(scene, amount=600, uid="AABBCCDD", key="conflict-key-02").status_code == 409
    assert pay(scene, amount=-1, key="conflict-key-02").status_code == 409
    assert len(rows(scene)) == 1


def test_concurrent_identical_failed_taps_record_one_row_and_one_email(tmp_path):
    env = Env(path=str(tmp_path / "failed_concurrent.db"))
    drv = env.add_user("dc@failtest.local", account_type="driver", balance=0)
    pax = env.add_user("pc@failtest.local", account_type="passenger", balance=5)
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax, card_reference="NFC-CONC9999", card_uid=UID))
        db.commit()
    finally:
        db.close()
    headers = env.user_headers(drv)
    results = []

    def tap():
        results.append(env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 50, "idempotency_key": "double-fail-key-1"},
                                       headers=headers))

    with patch(MAIL, return_value=True) as mail:
        threads = [threading.Thread(target=tap) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert {r.json()["code"] for r in results} == {"INSUFFICIENT_BALANCE"}
    assert len({r.json()["reference"] for r in results}) == 1
    assert mail.call_count == 1
    db = env.db()
    try:
        assert db.query(Transaction).count() == 1
    finally:
        db.close()
    assert env.balance(pax) == 5


# ── 4. the owner's email ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", CODES)
def test_owner_is_emailed_for_every_code_except_unknown_card(scene, code):
    kwargs = arrange(scene, code)
    with patch(MAIL, return_value=True) as mail:
        ref = pay(scene, **kwargs).json()["reference"]
    if code == "CARD_UNKNOWN":
        mail.assert_not_called()
        return
    mail.assert_called_once()
    sent = mail.call_args.kwargs
    assert sent["to_email"] == "pax@failtest.local" and sent["passenger_name"] == "Asha Verma"
    assert sent["code"] == code and sent["reference"] == ref and sent["driver_name"] == "Rakesh Sharma"
    assert (sent["vehicle_type"], sent["vehicle_registration"]) == ("Auto", "MH12AB1234")
    assert sent["created_at"] is not None
    if code == "AMOUNT_INVALID":
        assert sent["fare"] is None
    else:
        assert sent["fare"] == kwargs.get("amount", 12.5)
    # The balance goes into the email only for INSUFFICIENT_BALANCE.
    assert sent["wallet_balance"] == (500.0 if code == "INSUFFICIENT_BALANCE" else None)


@pytest.mark.parametrize("code,reason", [
    ("INSUFFICIENT_BALANCE", "Insufficient wallet balance. Please add money and try again."),
    ("CARD_BLOCKED", "Your card is blocked. If this wasn't you, contact support."),
    ("CARD_LOST", "This card was reported lost. If this wasn't you, contact support."),
    ("WALLET_FROZEN", "Your wallet is frozen. Contact support."),
    ("PASSENGER_INACTIVE", "not active"),
    ("AMOUNT_INVALID", "not valid"),
])
def test_failure_email_content(code, reason):
    with patch.object(nfc_failure_email, "send_email", return_value=True) as send:
        nfc_failure_email.send_nfc_failure_email(
            to_email="pax@failtest.local", passenger_name="Asha Verma", fare=12.5 if code != "AMOUNT_INVALID" else None,
            driver_name="Rakesh Sharma", reference="TXNABC123", code=code, vehicle_type="Auto",
            vehicle_registration="MH12AB1234", wallet_balance=42.0 if code == "INSUFFICIENT_BALANCE" else None)
    kw = send.call_args.kwargs
    html = kw["html_content"].replace("&#x27;", "'")
    assert reason in html and reason.replace("&#x27;", "'") in kw["text_content"]
    for needle in ("Rakesh Sharma", "Auto", "MH12AB1234", "TXNABC123", "FAILED", "Asha"):
        assert needle in html
    assert ("12.50" in html) == (code != "AMOUNT_INVALID")
    assert ("42.00" in html) == (code == "INSUFFICIENT_BALANCE")
    assert kw.get("attachments") is None and kw["email_type"] == "ride_passenger_payment_failed"
    assert kw["reference"] == "TXNABC123" and kw["subject"] == "Tap & Go - Ride Payment Failed"


def test_failure_email_delivery_is_logged_in_email_logs(scene):
    """No credentials in tests, so delivery fails: the attempt must still be logged, like other emails."""
    arrange(scene, "CARD_BLOCKED")
    with patch("app.utils.email_service.log_email_delivery") as log:
        ref = pay(scene).json()["reference"]
    log.assert_called_once()
    assert log.call_args.kwargs["email_type"] == "ride_passenger_payment_failed"
    assert log.call_args.kwargs["recipient"] == "pax@failtest.local" and log.call_args.kwargs["reference"] == ref


def test_email_problems_never_change_the_response_or_the_row(scene):
    arrange(scene, "WALLET_FROZEN")
    with patch(MAIL, side_effect=RuntimeError("ses down")):
        r = pay(scene)
    assert r.status_code == 200 and r.json()["code"] == "WALLET_FROZEN"
    assert len(rows(scene, status="failed")) == 1


# ── 5. throttle ──────────────────────────────────────────────────────────────────────────

def test_default_cooldown_is_300_seconds_and_zero_disables(monkeypatch):
    monkeypatch.delenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", raising=False)
    assert nfc_pay._failure_email_cooldown() == 300
    monkeypatch.setenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", "junk")
    assert nfc_pay._failure_email_cooldown() == 300
    monkeypatch.setenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", "0")
    assert nfc_pay._failure_email_cooldown() == 0


def test_throttle_limits_emails_per_passenger_but_every_failure_is_a_row(scene, monkeypatch):
    monkeypatch.setenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", "300")
    arrange(scene, "CARD_BLOCKED")
    clock = [1000.0]
    monkeypatch.setattr(nfc_pay.time, "monotonic", lambda: clock[0])
    with patch(MAIL, return_value=True) as mail:
        for _ in range(3):
            assert pay(scene).json()["code"] == "CARD_BLOCKED"
        assert mail.call_count == 1 and len(rows(scene, status="failed")) == 3
        clock[0] += 301
        pay(scene)
        assert mail.call_count == 2 and len(rows(scene, status="failed")) == 4


def test_throttle_is_per_passenger_and_zero_means_every_failure_emails(scene, monkeypatch):
    other = scene["env"].add_user("other@failtest.local", account_type="passenger", balance=1)
    db = scene["env"].db()
    try:
        db.add(NFCCard(user_id=other, card_reference="NFC-FAIL0002", card_uid="DEADBEEF"))
        db.commit()
    finally:
        db.close()
    monkeypatch.setenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", "300")
    with patch(MAIL, return_value=True) as mail:
        pay(scene, amount=600)
        pay(scene, uid="DEADBEEF", amount=600)
        pay(scene, amount=600)
    assert mail.call_count == 2
    monkeypatch.setenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", "0")
    with patch(MAIL, return_value=True) as mail:
        for _ in range(3):
            pay(scene, amount=600)
    assert mail.call_count == 3


def test_successful_receipts_are_not_throttled(scene, monkeypatch):
    monkeypatch.setenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", "300")
    with patch("app.routes.nfc_pay.send_ride_passenger_email", return_value=True) as p_mail, \
         patch("app.routes.nfc_pay.send_ride_driver_email", return_value=True):
        for _ in range(3):
            assert pay(scene, amount=10).json()["success"] is True
    assert p_mail.call_count == 3


# ── 6. emails run after the response ─────────────────────────────────────────────────────

def test_response_to_a_failed_tap_does_not_wait_for_the_slow_email(tmp_path):
    from app.main import app

    env = Env(path=str(tmp_path / "failed_timing.db"))
    drv = env.add_user("dt@failtest.local", account_type="driver", balance=0)
    pax = env.add_user("pt@failtest.local", account_type="passenger", balance=1)
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax, card_reference="NFC-TIME9999", card_uid=UID))
        db.commit()
    finally:
        db.close()

    def slow_mail(**kwargs):
        time.sleep(2.0)
        return True

    body = json.dumps({"card_uid": UID, "amount": 50, "idempotency_key": "timing-fail-key"}).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/api/nfc/pay", "raw_path": b"/api/nfc/pay", "query_string": b"", "root_path": "",
        "headers": [(b"host", b"testserver"), (b"authorization", env.user_headers(drv)["Authorization"].encode()),
                    (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
    }
    sent = {"body": b"", "done_at": None}

    async def run():
        started = time.monotonic()
        messages = iter([{"type": "http.request", "body": body, "more_body": False}])

        async def receive():
            try:
                return next(messages)
            except StopIteration:
                await asyncio.sleep(3600)

        async def send(message):
            if message["type"] == "http.response.body":
                sent["body"] += message.get("body", b"")
                if not message.get("more_body"):
                    sent["done_at"] = time.monotonic() - started

        await app(scope, receive, send)
        return time.monotonic() - started

    with patch(MAIL, side_effect=slow_mail):
        total = asyncio.run(run())
    assert json.loads(sent["body"])["code"] == "INSUFFICIENT_BALANCE"
    assert sent["done_at"] < 1.0, f"response took {sent['done_at']:.2f}s"
    assert total >= 2.0


# ── 7. history, earnings and admin ignore failed rows as money ───────────────────────────

def history(scene, user_id, headers):
    r = scene["env"].client.get(f"/api/wallet/{user_id}/transactions", headers=headers)
    assert r.status_code == 200
    return r.json()["transactions"]


def test_passenger_and_driver_history_show_failed_rows_without_moving_the_balance(scene):
    pay(scene, amount=100, key="hist-key-000001")                  # completed
    pay(scene, amount=600, key="hist-key-000002")                  # INSUFFICIENT_BALANCE
    pay(scene, uid="AABBCCDD", key="hist-key-000003")              # CARD_UNKNOWN (driver only)

    p = history(scene, scene["pax_id"], scene["pax_headers"])
    assert [t["status"] for t in p] == ["Failed", "Completed"]            # newest first
    failed, done = p
    assert failed["failure_code"] == "INSUFFICIENT_BALANCE" and failed["amount"] == 600
    assert failed["is_credit"] is False and "failed" in failed["description"].lower()
    assert "insufficient balance" in failed["failure_reason"]
    assert failed["balance_after"] == done["balance_after"] == 400
    assert sum(-t["amount"] if not t["is_credit"] else t["amount"] for t in p if t["status"] != "Failed") == -100

    d = history(scene, scene["driver_id"], scene["driver_headers"])
    assert [t["status"] for t in d] == ["Failed", "Failed", "Completed"]
    money_in = sum(t["amount"] for t in d if t["is_credit"])
    assert money_in == 100                                         # only the completed ride is income
    assert all(t["is_credit"] is False and t["type"] == "Failed Ride Payment" for t in d[:2])
    assert d[0]["balance_after"] == d[1]["balance_after"] == d[2]["balance_after"]
    assert scene["env"].balance(scene["driver_id"]) == 100


def test_admin_counts_lists_and_export_treat_failed_rows_correctly(scene):
    env = scene["env"]
    pay(scene, amount=100, key="admin-key-000001")
    pay(scene, amount=600, key="admin-key-000002")
    pay(scene, uid="AABBCCDD", key="admin-key-000003")
    ah = env.admin_headers(env.add_admin())

    dash = env.client.get("/api/admin/dashboard", headers=ah).json()
    assert dash["total_transactions"] == 1 and dash["today_transactions"] == 1
    assert dash["failed_today"] == 2 and dash["revenue"] == 100

    items = env.client.get("/api/admin/transactions", params={"status": "failed"}, headers=ah).json()["items"]
    assert sorted(i["failure_code"] for i in items) == ["CARD_UNKNOWN", "INSUFFICIENT_BALANCE"]
    assert all(i["status"] == "failed" and i["failure_reason"] for i in items)
    assert env.client.get("/api/admin/transactions", headers=ah).json()["total"] == 3

    csv_text = env.client.get("/api/admin/transactions/export", headers=ah).text
    assert csv_text.splitlines()[0].endswith("Failure Reason")
    assert csv_text.count(",failed,") == 2 and "insufficient balance" in csv_text

    detail = env.client.get(f"/api/admin/users/{scene['pax_id']}", headers=ah).json()
    assert sorted(t["status"] for t in detail["transactions"]) == ["completed", "failed"]


# ── 8. migration ─────────────────────────────────────────────────────────────────────────

def test_migration_adds_failure_code_to_an_existing_transactions_table(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.main import run_database_migrations

    eng = create_engine(f"sqlite:///{tmp_path / 'old_txn.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        c.execute(text("CREATE TABLE transactions (id INTEGER PRIMARY KEY, reference VARCHAR(64) NOT NULL, "
                       "amount NUMERIC(12,2) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending')"))
        c.execute(text("INSERT INTO transactions (reference, amount, status) VALUES ('OLD1', 5, 'completed')"))
    run_database_migrations(eng)
    run_database_migrations(eng)           # idempotent
    assert "failure_code" in {c["name"] for c in inspect(eng).get_columns("transactions")}
    with eng.begin() as c:
        assert c.execute(text("SELECT failure_code FROM transactions WHERE reference='OLD1'")).scalar() is None
