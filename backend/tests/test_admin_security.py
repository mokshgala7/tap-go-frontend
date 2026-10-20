"""Administrator authentication (findings F-11, F-12)."""
import hashlib
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

import app.routes.admin as admin_routes
from app.models import Admin, AdminSession
from app.utils.security import verify_password
from helpers import Env

ADMIN_ROUTES = [
    ("get", "/api/admin/dashboard"),
    ("get", "/api/admin/users"),
    ("get", "/api/admin/withdrawal-requests"),
    ("patch", "/api/admin/withdrawal-requests/1/approve"),
    ("patch", "/api/admin/withdrawal-requests/1/pay"),
    ("patch", "/api/admin/withdrawal-requests/1/reject"),
    ("post", "/api/admin/wallets/1"),
    ("get", "/api/admin/settings"),
    ("get", "/api/admin/transactions/export"),
    ("get", "/api/admin/support/admin/all"),
    ("get", "/api/admin/card-order/admin/all"),
    ("get", "/api/card-order/admin/all"),
    ("patch", "/api/card-order/admin/1/status"),
    ("get", "/api/nfc/admin/all"),
    ("post", "/api/nfc/admin/1/action"),
]


@pytest.fixture
def env():
    admin_routes._LOGIN_FAILURES.clear()
    e = Env()
    e.admin_id = e.add_admin()
    return e


def call(env, method, path, headers=None, **kw):
    return env.client.request(method.upper(), path, headers=headers or {}, **kw)


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_forged_x_admin_id_header_is_rejected(env, method, path):
    for headers in ({"X-Admin-Id": str(env.admin_id)}, {"x-admin-id": "1"}, {}):
        assert call(env, method, path, headers, json={}).status_code == 401, (path, headers)


@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_malformed_and_unknown_tokens_are_rejected(env, method, path):
    for auth in ("Bearer", "Bearer ", "Bearer not-a-real-token", "Token abc", str(env.admin_id)):
        assert call(env, method, path, {"Authorization": auth}, json={}).status_code == 401


def test_a_normal_user_session_is_not_an_admin_session(env):
    uid = env.add_user("rider@test.local")
    assert call(env, "get", "/api/admin/dashboard", env.user_headers(uid)).status_code == 401


def test_valid_admin_session_works(env):
    h = env.admin_headers(env.admin_id)
    assert call(env, "get", "/api/admin/dashboard", h).status_code == 200
    assert call(env, "get", "/api/admin/withdrawal-requests", h).status_code == 200


def test_expired_revoked_and_disabled_admin_sessions_fail(env):
    h = env.admin_headers(env.admin_id)
    token = h["Authorization"].split(" ")[1]
    th = hashlib.sha256(token.encode()).hexdigest()

    db = env.db()
    s = db.query(AdminSession).filter_by(token_hash=th).first()
    s.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    assert call(env, "get", "/api/admin/dashboard", h).status_code == 401

    s.expires_at = datetime.utcnow() + timedelta(hours=1)
    s.revoked_at = datetime.utcnow()
    db.commit()
    assert call(env, "get", "/api/admin/dashboard", h).status_code == 401

    s.revoked_at = None
    db.query(Admin).filter_by(id=env.admin_id).update({"is_active": False})
    db.commit()
    assert call(env, "get", "/api/admin/dashboard", h).status_code == 401
    db.close()


def test_login_returns_a_working_token_and_the_website_shape(env):
    r = call(env, "post", "/api/admin/login", json={"email": "admin@test.local", "password": "Adm1n-Strong-Pass"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["admin"]["id"] == env.admin_id            # existing website field
    assert body["admin"]["token"] == body["token"]        # stored by the website with result.admin
    assert "password" not in str(body).lower()
    assert call(env, "get", "/api/admin/dashboard", {"Authorization": f"Bearer {body['token']}"}).status_code == 200


def test_logout_revokes_the_session(env):
    token = call(env, "post", "/api/admin/login",
                 json={"email": "admin@test.local", "password": "Adm1n-Strong-Pass"}).json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    assert call(env, "post", "/api/admin/logout", h).status_code == 200
    assert call(env, "get", "/api/admin/dashboard", h).status_code == 401


@pytest.mark.parametrize("pw", ["admin@123", "admin123"])
def test_hardcoded_passwords_do_not_log_in_or_rewrite_the_hash(env, pw):
    db = env.db()
    before = db.query(Admin).filter_by(id=env.admin_id).first().password_hash
    db.close()
    r = call(env, "post", "/api/admin/login", json={"email": "admin@test.local", "password": pw})
    assert r.status_code == 401
    db = env.db()
    after = db.query(Admin).filter_by(id=env.admin_id).first().password_hash
    db.close()
    assert after == before
    assert verify_password("Adm1n-Strong-Pass", after)


def test_configured_admin_password_setting_is_not_a_backdoor(env):
    with patch.dict(os.environ, {"ADMIN_PASSWORD": "Configured-Secret-1"}):
        r = call(env, "post", "/api/admin/login", json={"email": "admin@test.local", "password": "Configured-Secret-1"})
    assert r.status_code == 401


def test_unknown_email_and_wrong_password_are_indistinguishable(env):
    a = call(env, "post", "/api/admin/login", json={"email": "nobody@test.local", "password": "x"})
    b = call(env, "post", "/api/admin/login", json={"email": "admin@test.local", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_disabled_admin_cannot_log_in(env):
    env.add_admin("off@test.local", "Off-Admin-Pass-1", active=False)
    r = call(env, "post", "/api/admin/login", json={"email": "off@test.local", "password": "Off-Admin-Pass-1"})
    assert r.status_code == 401


def test_repeated_failures_are_throttled(env):
    for _ in range(5):
        assert call(env, "post", "/api/admin/login", json={"email": "admin@test.local", "password": "bad"}).status_code == 401
    # even the right password is refused during the lock-out window
    r = call(env, "post", "/api/admin/login", json={"email": "admin@test.local", "password": "Adm1n-Strong-Pass"})
    assert r.status_code == 429


def test_admin_account_in_users_table_requires_its_own_password(env):
    env.add_user("boss@test.local", account_type="admin", password="Boss-Pass-12345")
    bad = call(env, "post", "/api/admin/login", json={"email": "boss@test.local", "password": "admin@123"})
    assert bad.status_code == 401
    ok = call(env, "post", "/api/admin/login", json={"email": "boss@test.local", "password": "Boss-Pass-12345"})
    assert ok.status_code == 200


class TestDefaultAdminProvisioning:
    def run(self, env, **vars):
        db = env.db()
        try:
            with patch.dict(os.environ, vars):
                return admin_routes.ensure_default_admin(db), db.query(Admin).count()
        finally:
            db.close()

    def test_nothing_is_created_without_explicit_values(self, env):
        assert self.run(env, ADMIN_EMAIL="", ADMIN_PASSWORD="")[0] is None

    @pytest.mark.parametrize("pw", ["admin@123", "admin123", "short"])
    def test_weak_passwords_are_refused(self, env, pw):
        got, count = self.run(env, ADMIN_EMAIL="new@test.local", ADMIN_PASSWORD=pw)
        assert got is None and count == 1

    def test_strong_explicit_values_provision_once_and_never_overwrite(self, env):
        got, count = self.run(env, ADMIN_EMAIL="new@test.local", ADMIN_PASSWORD="Very-Strong-Secret-9")
        assert got is not None and count == 2
        h1 = got.password_hash
        got2, count2 = self.run(env, ADMIN_EMAIL="new@test.local", ADMIN_PASSWORD="Another-Strong-Secret-9")
        assert count2 == 2 and got2.password_hash == h1
