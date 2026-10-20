"""PUT /api/auth/profile: identity fields (e-mail, phone) are not freely editable."""
import pytest

from app.models import User
from helpers import Env


@pytest.fixture
def env():
    e = Env()
    e.a = e.add_user("a@test.local", phone="9000000001", address="old", city="Pune")
    e.b = e.add_user("b@test.local", phone="9000000002")
    e.h = e.user_headers(e.a)
    return e


def put(env, body, headers=None):
    return env.client.put("/api/auth/profile", json=body, headers=env.h if headers is None else headers)


def test_requires_login_and_ownership(env):
    assert put(env, {"name": "X"}, headers={}).status_code == 401
    assert put(env, {"name": "X", "user_id": env.b}).status_code == 403


def test_name_address_and_city_can_be_changed(env):
    r = put(env, {"user_id": env.a, "name": "New Name", "address": "12 Main Rd", "city": "Mumbai"})
    assert r.status_code == 200
    u = r.json()["user"]
    assert (u["name"], u["address"], u["city"]) == ("New Name", "12 Main Rd", "Mumbai")


def test_email_cannot_be_changed_but_the_same_address_is_accepted(env):
    assert put(env, {"email": "attacker@evil.test"}).status_code == 400
    assert put(env, {"email": "b@test.local"}).status_code == 400          # also not another account's address
    assert put(env, {"email": "A@Test.Local", "name": "Same"}).status_code == 200   # unchanged (case-insensitive)
    db = env.db()
    assert db.get(User, env.a).email == "a@test.local"


def test_phone_needs_administrator_approval(env):
    r = put(env, {"phone": "9111111111"})
    assert r.status_code == 400 and "administrator approval" in r.json()["detail"]
    assert put(env, {"phone": "9000000001"}).status_code == 200            # unchanged is fine
