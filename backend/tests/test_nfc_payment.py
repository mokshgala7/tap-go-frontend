"""
test_nfc_payment.py
───────────────────
POST /api/nfc/pay (POS taps a passenger card) and the admin endpoints that bind a chip UID
to a passenger's card. Mirrors test_qr_payment.py: in-memory SQLite, real session tokens.
"""
import threading
import uuid
from unittest.mock import patch

import pytest

from tests.helpers import Env
from app.models import NFCCard, Transaction
from app.routes.nfc_pay import normalize_card_uid

UID = "04A2B3C4D5E680"


@pytest.fixture
def env():
    return Env()


@pytest.fixture
def scene(env):
    driver_id = env.add_user("drv@nfctest.local", account_type="driver", balance=0, name="Rakesh Sharma")
    pax_id = env.add_user("pax@nfctest.local", account_type="passenger", balance=500, name="Asha Verma")
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax_id, card_reference="NFC-TEST0001", card_uid=UID, status="active"))
        db.commit()
    finally:
        db.close()
    return {
        "env": env,
        "driver_id": driver_id,
        "pax_id": pax_id,
        "driver_headers": env.user_headers(driver_id),
        "pax_headers": env.user_headers(pax_id),
    }


def pay(scene, uid=UID, amount=12.5, key=None, headers=None):
    return scene["env"].client.post(
        "/api/nfc/pay",
        json={"card_uid": uid, "amount": amount, "idempotency_key": key or f"tap-{uuid.uuid4().hex}"},
        headers=headers or scene["driver_headers"],
    )


def set_card_status(scene, status):
    db = scene["env"].db()
    try:
        db.query(NFCCard).filter(NFCCard.card_uid == UID).update({"status": status})
        db.commit()
    finally:
        db.close()


def assert_failed(r, code, http=200):
    assert r.status_code == http, r.text
    body = r.json()
    assert body["success"] is False and body["status"] == "Failed" and body["code"] == code
    assert body["message"]


# ── success ──────────────────────────────────────────────────────────────────

def test_successful_tap_moves_money_and_returns_small_body(scene):
    r = pay(scene, amount=12.5)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True and body["status"] == "Completed"
    assert body["amount"] == 12.5 and body["reference"].startswith("TXN")
    assert body["passenger_name"] == "Asha"
    assert set(body) <= {"success", "status", "reference", "amount", "passenger_name", "idempotent"}
    env = scene["env"]
    assert env.balance(scene["pax_id"]) == 487.5
    assert env.balance(scene["driver_id"]) == 12.5


def test_transaction_row_is_an_nfc_ride_payment_for_this_driver(scene):
    key = "tap-record-0001"
    pay(scene, amount=40, key=key)
    db = scene["env"].db()
    try:
        t = db.query(Transaction).one()
        assert (t.payment_method, t.transaction_type, t.status, t.fraud_status) == ("NFC", "ride_payment", "completed", "clear")
        assert t.passenger_id == scene["pax_id"] and t.driver_id == scene["driver_id"]
        assert t.idempotency_key == f"nfc:{scene['driver_id']}:{key}"
    finally:
        db.close()


@pytest.mark.parametrize("variant", ["04:a2:b3:c4:d5:e6:80", "04-A2-B3-C4-D5-E6-80", " 04a2b3c4d5e680 "])
def test_uid_formats_are_normalised(scene, variant):
    assert pay(scene, uid=variant).json()["success"] is True


def test_four_byte_uid_works(scene):
    db = scene["env"].db()
    try:
        db.query(NFCCard).update({"card_uid": "DEADBEEF"})
        db.commit()
    finally:
        db.close()
    assert pay(scene, uid="de:ad:be:ef").json()["success"] is True


def test_normalize_card_uid_rules():
    assert normalize_card_uid("04:a2:b3:c4") == "04A2B3C4"
    assert normalize_card_uid("04A2B3C4D5E680") == "04A2B3C4D5E680"
    for bad in (None, "", "04A2B3", "04A2B3C4D5", "ZZZZZZZZ", "04A2B3C4D5E680FF", 12345678):
        assert normalize_card_uid(bad) is None


# ── card state ───────────────────────────────────────────────────────────────

def test_unknown_card(scene):
    assert_failed(pay(scene, uid="AABBCCDD"), "CARD_UNKNOWN")
    assert_failed(pay(scene, uid="not-a-uid"), "CARD_UNKNOWN")
    assert scene["env"].balance(scene["pax_id"]) == 500


def test_blocked_card(scene):
    set_card_status(scene, "blocked")
    assert_failed(pay(scene), "CARD_BLOCKED")
    assert scene["env"].balance(scene["pax_id"]) == 500


@pytest.mark.parametrize("status", ["lost", "replaced"])
def test_lost_card(scene, status):
    set_card_status(scene, status)
    assert_failed(pay(scene), "CARD_LOST")


def test_unblocked_card_pays_again_with_a_new_key(scene):
    set_card_status(scene, "blocked")
    assert_failed(pay(scene, key="same-key-1234"), "CARD_BLOCKED")
    set_card_status(scene, "active")
    # The failed tap owns its key, so the same key replays the failure; a new tap uses a new key.
    again = pay(scene, key="same-key-1234").json()
    assert again["success"] is False and again["code"] == "CARD_BLOCKED" and again["idempotent"] is True
    assert pay(scene, key="another-key-5678").json()["success"] is True


# ── passenger / wallet ───────────────────────────────────────────────────────

def test_suspended_passenger(scene):
    from app.models import User
    db = scene["env"].db()
    try:
        db.query(User).filter(User.id == scene["pax_id"]).update({"status": "suspended"})
        db.commit()
    finally:
        db.close()
    assert_failed(pay(scene), "PASSENGER_INACTIVE")


def test_insufficient_balance_moves_no_money_and_is_recorded_as_failed(scene):
    assert_failed(pay(scene, amount=500.01), "INSUFFICIENT_BALANCE")
    assert scene["env"].balance(scene["pax_id"]) == 500
    assert scene["env"].balance(scene["driver_id"]) == 0
    db = scene["env"].db()
    try:
        t = db.query(Transaction).one()
        assert (t.status, t.failure_code) == ("failed", "INSUFFICIENT_BALANCE")
    finally:
        db.close()


def test_frozen_passenger_wallet(env):
    drv = env.add_user("d2@nfctest.local", account_type="driver", balance=0)
    pax = env.add_user("p2@nfctest.local", account_type="passenger", balance=100, frozen=True)
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax, card_reference="NFC-FROZEN01", card_uid=UID))
        db.commit()
    finally:
        db.close()
    r = env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 10, "idempotency_key": "frozen-key-01"},
                        headers=env.user_headers(drv))
    assert_failed(r, "WALLET_FROZEN")
    assert env.balance(pax) == 100


def test_frozen_driver_wallet_is_refused_without_debit(env):
    drv = env.add_user("d3@nfctest.local", account_type="driver", balance=0, frozen=True)
    pax = env.add_user("p3@nfctest.local", account_type="passenger", balance=100)
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax, card_reference="NFC-DFROZEN1", card_uid=UID))
        db.commit()
    finally:
        db.close()
    r = env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 10, "idempotency_key": "dfrozen-key-1"},
                        headers=env.user_headers(drv))
    assert_failed(r, "DRIVER_NOT_ALLOWED", 403)
    assert env.balance(pax) == 100


# ── amount ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [0, -5, 0.001, 12.345, None, 99999999])
def test_invalid_amounts(scene, bad):
    assert_failed(pay(scene, amount=bad), "AMOUNT_INVALID")
    assert scene["env"].balance(scene["pax_id"]) == 500


# ── caller ───────────────────────────────────────────────────────────────────

def test_passenger_cannot_call(scene):
    assert_failed(pay(scene, headers=scene["pax_headers"]), "DRIVER_NOT_ALLOWED", 403)
    assert scene["env"].balance(scene["pax_id"]) == 500


def test_suspended_driver_cannot_call(env):
    drv = env.add_user("d4@nfctest.local", account_type="driver", status="suspended", balance=0)
    r = env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 10, "idempotency_key": "susp-drv-key1"},
                        headers=env.user_headers(drv))
    assert_failed(r, "DRIVER_NOT_ALLOWED", 403)


def test_unauthenticated_is_401(scene):
    r = scene["env"].client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 10, "idempotency_key": "no-auth-key-1"})
    assert r.status_code == 401


def test_body_cannot_name_a_different_payee(scene):
    other = scene["env"].add_user("d5@nfctest.local", account_type="driver", balance=0)
    r = scene["env"].client.post(
        "/api/nfc/pay",
        json={"card_uid": UID, "amount": 20, "idempotency_key": "payee-key-001", "driver_id": other, "passenger_id": 999},
        headers=scene["driver_headers"],
    )
    assert r.json()["success"] is True
    assert scene["env"].balance(other) == 0
    assert scene["env"].balance(scene["driver_id"]) == 20


@pytest.mark.parametrize("key", [None, "", "short", "x" * 101])
def test_bad_idempotency_key_is_400(scene, key):
    r = scene["env"].client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 10, "idempotency_key": key},
                                 headers=scene["driver_headers"])
    assert r.status_code == 400


# ── idempotency ──────────────────────────────────────────────────────────────

def test_replay_returns_original_result_without_second_charge(scene):
    first = pay(scene, amount=30, key="replay-key-0001").json()
    second = pay(scene, amount=30, key="replay-key-0001").json()
    assert second["success"] is True and second["idempotent"] is True
    assert second["reference"] == first["reference"]
    assert scene["env"].balance(scene["pax_id"]) == 470
    assert scene["env"].balance(scene["driver_id"]) == 30


def test_replay_still_returns_success_after_card_is_blocked(scene):
    first = pay(scene, amount=30, key="replay-key-0002").json()
    set_card_status(scene, "blocked")
    again = pay(scene, amount=30, key="replay-key-0002").json()
    assert again["success"] is True and again["reference"] == first["reference"]


def test_key_reused_for_different_amount_or_card_is_a_conflict(scene):
    pay(scene, amount=30, key="conflict-key-01")
    assert_failed(pay(scene, amount=31, key="conflict-key-01"), "IDEMPOTENCY_CONFLICT", 409)
    assert_failed(pay(scene, uid="AABBCCDD", amount=30, key="conflict-key-01"), "IDEMPOTENCY_CONFLICT", 409)
    assert scene["env"].balance(scene["pax_id"]) == 470


def test_same_key_from_another_driver_is_a_separate_payment(scene):
    other = scene["env"].add_user("d6@nfctest.local", account_type="driver", balance=0)
    pay(scene, amount=10, key="shared-key-001")
    r = pay(scene, amount=10, key="shared-key-001", headers=scene["env"].user_headers(other))
    assert r.json()["success"] is True and "idempotent" not in r.json()
    assert scene["env"].balance(scene["pax_id"]) == 480


def test_concurrent_double_tap_charges_exactly_once(tmp_path):
    env = Env(path=str(tmp_path / "nfc_concurrent.db"))
    drv = env.add_user("dc@nfctest.local", account_type="driver", balance=0)
    pax = env.add_user("pc@nfctest.local", account_type="passenger", balance=500)
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax, card_reference="NFC-CONC0001", card_uid=UID))
        db.commit()
    finally:
        db.close()
    headers = env.user_headers(drv)
    results = []

    def tap():
        r = env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 50, "idempotency_key": "double-tap-key-1"},
                            headers=headers)
        results.append(r)

    threads = [threading.Thread(target=tap) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert env.balance(pax) == 450, [r.text for r in results]
    assert env.balance(drv) == 50
    db = env.db()
    try:
        assert db.query(Transaction).count() == 1
    finally:
        db.close()
    assert any(r.status_code == 200 and r.json()["success"] for r in results)


# ── notifications ────────────────────────────────────────────────────────────

def test_receipt_emails_sent_once_after_commit(scene):
    with patch("app.routes.nfc_pay.send_ride_passenger_email") as p_mail, \
         patch("app.routes.nfc_pay.send_ride_driver_email") as d_mail:
        pay(scene, amount=15, key="mail-key-00001")
        pay(scene, amount=15, key="mail-key-00001")     # replay: no further mail
    assert p_mail.call_count == 1 and d_mail.call_count == 1
    assert p_mail.call_args.kwargs["payment_method"] == "NFC"


def test_email_failure_does_not_undo_payment(scene):
    with patch("app.routes.nfc_pay.send_ride_passenger_email", side_effect=RuntimeError("smtp down")):
        assert pay(scene, amount=15).json()["success"] is True
    assert scene["env"].balance(scene["pax_id"]) == 485


# ── admin: assigning and replacing a UID ─────────────────────────────────────

@pytest.fixture
def admin_scene(env):
    pax = env.add_user("apax@nfctest.local", account_type="passenger", balance=0, name="Admin Pax")
    return env, pax, env.admin_headers(env.add_admin())


def test_admin_issue_with_uid_normalises_and_enables_payment(admin_scene):
    env, pax, ah = admin_scene
    r = env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": "04:a2:b3:c4:d5:e6:80"}, headers=ah)
    assert r.status_code == 200, r.text
    assert r.json()["card"]["card_uid"] == UID
    assert r.json()["card"]["card_uid_masked"].endswith("E680")


def test_admin_issue_rejects_bad_and_duplicate_uid(admin_scene):
    env, pax, ah = admin_scene
    other = env.add_user("apax2@nfctest.local", account_type="passenger")
    assert env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": "XYZ"}, headers=ah).status_code == 400
    assert env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": UID}, headers=ah).status_code == 200
    r = env.client.post("/api/nfc/admin/issue", json={"user_id": other, "card_uid": UID}, headers=ah)
    assert r.status_code == 409


def test_one_live_card_per_passenger(admin_scene):
    env, pax, ah = admin_scene
    assert env.client.post("/api/nfc/admin/issue", json={"user_id": pax}, headers=ah).status_code == 200
    r = env.client.post("/api/nfc/admin/issue", json={"user_id": pax}, headers=ah)
    assert r.status_code == 409


def test_card_can_be_issued_again_after_loss(admin_scene):
    env, pax, ah = admin_scene
    card_id = env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": UID}, headers=ah).json()["card"]["id"]
    env.client.post(f"/api/nfc/admin/{card_id}/action", json={"action": "mark_lost"}, headers=ah)
    r = env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": "AABBCCDD"}, headers=ah)
    assert r.status_code == 200


def test_admin_cannot_issue_card_to_a_driver(env):
    drv = env.add_user("adrv@nfctest.local", account_type="driver")
    ah = env.admin_headers(env.add_admin())
    assert env.client.post("/api/nfc/admin/issue", json={"user_id": drv}, headers=ah).status_code == 400


def test_admin_sets_and_replaces_uid_on_existing_card(admin_scene):
    env, pax, ah = admin_scene
    card = env.client.post("/api/nfc/admin/issue", json={"user_id": pax}, headers=ah).json()["card"]
    assert card["card_uid"] is None
    r = env.client.put(f"/api/nfc/admin/{card['id']}/uid", json={"card_uid": UID}, headers=ah)
    assert r.status_code == 200 and r.json()["card"]["card_uid"] == UID
    r = env.client.put(f"/api/nfc/admin/{card['id']}/uid", json={"card_uid": "DEADBEEF"}, headers=ah)
    assert r.json()["card"]["card_uid"] == "DEADBEEF"
    assert env.client.put(f"/api/nfc/admin/{card['id']}/uid", json={"card_uid": "nope"}, headers=ah).status_code == 400


def test_admin_cannot_set_uid_already_on_another_card_or_on_a_lost_card(admin_scene):
    env, pax, ah = admin_scene
    other = env.add_user("apax3@nfctest.local", account_type="passenger")
    env.client.post("/api/nfc/admin/issue", json={"user_id": other, "card_uid": UID}, headers=ah)
    mine = env.client.post("/api/nfc/admin/issue", json={"user_id": pax}, headers=ah).json()["card"]
    assert env.client.put(f"/api/nfc/admin/{mine['id']}/uid", json={"card_uid": UID}, headers=ah).status_code == 409
    env.client.post(f"/api/nfc/admin/{mine['id']}/action", json={"action": "mark_lost"}, headers=ah)
    assert env.client.put(f"/api/nfc/admin/{mine['id']}/uid", json={"card_uid": "DEADBEEF"}, headers=ah).status_code == 400


def test_set_uid_requires_admin(admin_scene):
    env, pax, ah = admin_scene
    card = env.client.post("/api/nfc/admin/issue", json={"user_id": pax}, headers=ah).json()["card"]
    assert env.client.put(f"/api/nfc/admin/{card['id']}/uid", json={"card_uid": UID}).status_code == 401
    assert env.client.put(f"/api/nfc/admin/{card['id']}/uid", json={"card_uid": UID},
                          headers=env.user_headers(pax)).status_code == 401


def test_passenger_sees_only_masked_uid(admin_scene):
    env, pax, ah = admin_scene
    env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": UID}, headers=ah)
    cards = env.client.get("/api/nfc/my", headers=env.user_headers(pax)).json()["cards"]
    assert "card_uid" not in cards[0] and cards[0]["card_uid_masked"].endswith("E680")
    assert UID not in str(cards)


def test_admin_list_filters_by_uid_and_shows_owner(admin_scene):
    env, pax, ah = admin_scene
    env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": UID}, headers=ah)
    r = env.client.get("/api/nfc/admin/all", params={"uid": "04:a2:b3:c4:d5:e6:80"}, headers=ah).json()
    assert r["total"] == 1 and r["items"][0]["user_name"] == "Admin Pax" and r["items"][0]["card_uid"] == UID
    assert env.client.get("/api/nfc/admin/all", params={"uid": "AABBCCDD"}, headers=ah).json()["total"] == 0


def test_end_to_end_issue_then_tap(env):
    pax = env.add_user("e2epax@nfctest.local", account_type="passenger", balance=100)
    drv = env.add_user("e2e@nfctest.local", account_type="driver", balance=0)
    ah = env.admin_headers(env.add_admin())
    env.client.post("/api/nfc/admin/issue", json={"user_id": pax, "card_uid": "04 a2 b3 c4 d5 e6 80"}, headers=ah)
    r = env.client.post("/api/nfc/pay", json={"card_uid": UID, "amount": 25, "idempotency_key": "e2e-key-0001"},
                        headers=env.user_headers(drv))
    assert r.json()["success"] is True
    assert env.balance(pax) == 75 and env.balance(drv) == 25


# ── startup migration on a database that already has nfc_cards ──────────────

def test_migration_adds_unique_card_uid_to_existing_table(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.exc import IntegrityError
    from app.main import run_database_migrations

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        c.execute(text("CREATE TABLE nfc_card_orders (id INTEGER PRIMARY KEY)"))
        c.execute(text(
            "CREATE TABLE nfc_cards (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "card_reference VARCHAR(64) NOT NULL UNIQUE, card_type VARCHAR(50) NOT NULL DEFAULT 'standard_nfc', "
            "status VARCHAR(20) NOT NULL DEFAULT 'active', blocked_reason TEXT, block_requested_at DATETIME, "
            "nfc_order_id INTEGER, replacement_order_id INTEGER, issued_at DATETIME, created_at DATETIME, updated_at DATETIME)"
        ))
        c.execute(text("INSERT INTO nfc_cards (user_id, card_reference) VALUES (1, 'NFC-OLD1'), (2, 'NFC-OLD2')"))
    run_database_migrations(eng)
    run_database_migrations(eng)        # idempotent
    insp = inspect(eng)
    assert "card_uid" in {c["name"] for c in insp.get_columns("nfc_cards")}
    assert any(i.get("unique") and i["column_names"] == ["card_uid"] for i in insp.get_indexes("nfc_cards"))
    with eng.begin() as c:              # many NULLs allowed, existing rows untouched
        assert c.execute(text("SELECT COUNT(*) FROM nfc_cards WHERE card_uid IS NULL")).scalar() == 2
        c.execute(text("UPDATE nfc_cards SET card_uid='04A2B3C4' WHERE card_reference='NFC-OLD1'"))
    with pytest.raises(IntegrityError):
        with eng.begin() as c:
            c.execute(text("UPDATE nfc_cards SET card_uid='04A2B3C4' WHERE card_reference='NFC-OLD2'"))


def test_migration_does_not_add_a_second_unique_index_when_one_exists(tmp_path):
    """Production state: card_uid and idx_nfc_cards_card_uid were applied by hand in Supabase."""
    from sqlalchemy import create_engine, inspect, text
    from app.main import run_database_migrations

    eng = create_engine(f"sqlite:///{tmp_path / 'prod_like.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        c.execute(text("CREATE TABLE nfc_card_orders (id INTEGER PRIMARY KEY)"))
        c.execute(text(
            "CREATE TABLE nfc_cards (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "
            "card_reference VARCHAR(64) NOT NULL UNIQUE, card_uid VARCHAR(32), "
            "card_type VARCHAR(50) NOT NULL DEFAULT 'standard_nfc', status VARCHAR(20) NOT NULL DEFAULT 'active', "
            "blocked_reason TEXT, block_requested_at DATETIME, nfc_order_id INTEGER, replacement_order_id INTEGER, "
            "issued_at DATETIME, created_at DATETIME, updated_at DATETIME)"
        ))
        c.execute(text("CREATE UNIQUE INDEX idx_nfc_cards_card_uid ON nfc_cards(card_uid)"))
    run_database_migrations(eng)
    run_database_migrations(eng)
    unique_on_uid = [i["name"] for i in inspect(eng).get_indexes("nfc_cards")
                     if i.get("unique") and i["column_names"] == ["card_uid"]]
    assert unique_on_uid == ["idx_nfc_cards_card_uid"]


# ── emails are sent after the response ───────────────────────────────────────

def test_response_does_not_wait_for_slow_emails(tmp_path):
    """Drive the ASGI app directly (the test suite blocks sockets): each email takes 1.5 s, but the last
    response byte must be sent at once, and the emails must still go out afterwards."""
    import asyncio
    import json
    import time
    from app.main import app

    env = Env(path=str(tmp_path / "nfc_timing.db"))
    drv = env.add_user("dt@nfctest.local", account_type="driver", balance=0)
    pax = env.add_user("pt@nfctest.local", account_type="passenger", balance=500)
    db = env.db()
    try:
        db.add(NFCCard(user_id=pax, card_reference="NFC-TIME0001", card_uid=UID))
        db.commit()
    finally:
        db.close()

    delivered = []

    def slow_mail(**kwargs):
        time.sleep(1.5)
        delivered.append(kwargs["to_email"])
        return True

    body = json.dumps({"card_uid": UID, "amount": 12.5, "idempotency_key": "timing-key-0001"}).encode()
    auth = env.user_headers(drv)["Authorization"].encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/api/nfc/pay", "raw_path": b"/api/nfc/pay", "query_string": b"", "root_path": "",
        "headers": [(b"host", b"testserver"), (b"authorization", auth), (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode())],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
    }
    sent = {"status": None, "body": b"", "done_at": None}

    async def run():
        started = time.monotonic()
        messages = iter([{"type": "http.request", "body": body, "more_body": False}])

        async def receive():
            try:
                return next(messages)
            except StopIteration:
                await asyncio.sleep(3600)

        async def send(message):
            if message["type"] == "http.response.start":
                sent["status"] = message["status"]
            elif message["type"] == "http.response.body":
                sent["body"] += message.get("body", b"")
                if not message.get("more_body"):
                    sent["done_at"] = time.monotonic() - started

        await app(scope, receive, send)
        return time.monotonic() - started

    with patch("app.routes.nfc_pay.send_ride_passenger_email", side_effect=slow_mail), \
         patch("app.routes.nfc_pay.send_ride_driver_email", side_effect=slow_mail):
        total = asyncio.run(run())

    assert sent["status"] == 200 and json.loads(sent["body"])["success"] is True
    assert sent["done_at"] < 1.0, f"response completed after {sent['done_at']:.2f}s: it waited for the emails"
    assert total >= 3.0, "the emails should still run (after the response)"
    assert sorted(delivered) == ["dt@nfctest.local", "pt@nfctest.local"]
    assert env.balance(pax) == 487.5


def test_undelivered_or_crashing_emails_are_logged_and_change_nothing(scene, caplog):
    import logging
    with patch("app.routes.nfc_pay.send_ride_passenger_email", return_value=False), \
         patch("app.routes.nfc_pay.send_ride_driver_email", side_effect=RuntimeError("ses down")), \
         caplog.at_level(logging.WARNING, logger="app.routes.nfc_pay"):
        r = pay(scene, amount=20, key="mail-fail-0001")
    assert r.status_code == 200 and r.json()["success"] is True
    text = caplog.text
    assert "was not delivered" in text and "Driver credit receipt failed" in text
    assert scene["env"].balance(scene["pax_id"]) == 480 and scene["env"].balance(scene["driver_id"]) == 20
