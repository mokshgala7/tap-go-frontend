"""Edit-request lifecycle: user submits -> admin decides (once) -> user is told."""
from unittest.mock import patch

import pytest

from app.models import EditRequest, User
from helpers import Env

BANK = dict(bank_account_holder="A B", bank_account_number="123456789012", bank_ifsc="HDFC0001234",
            bank_upi_id="a@hdfc", bank_locked=1)


@pytest.fixture
def env():
    e = Env()
    e.u = e.add_user("user@test.local", **BANK)
    e.uh = e.user_headers(e.u)
    e.ah = e.admin_headers(e.add_admin())
    return e


def submit(env, kind="bank", headers=None):
    return env.client.post("/api/auth/request-admin-access", json={"request_type": kind},
                           headers=env.uh if headers is None else headers)


def test_request_requires_login_and_ownership(env):
    assert submit(env, headers={}).status_code == 401
    other = env.add_user("o@test.local")
    r = env.client.post("/api/auth/request-admin-access", json={"request_type": "bank", "user_id": other}, headers=env.uh)
    assert r.status_code == 403


def test_duplicate_pending_requests_are_refused(env):
    assert submit(env).status_code == 200
    assert submit(env).status_code == 400


@pytest.mark.parametrize("action,approved", [("approve", True), ("reject", False)])
def test_decision_is_stored_and_the_user_is_emailed(env, action, approved):
    assert submit(env).status_code == 200
    rid = env.client.get("/api/admin/edit-requests", headers=env.ah).json()["items"][0]["id"]
    with patch("app.utils.email_service.send_edit_request_decision_email", return_value=True) as mail:
        r = env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": action}, headers=env.ah)
    assert r.status_code == 200
    kwargs = mail.call_args.kwargs
    assert kwargs["to_email"] == "user@test.local" and kwargs["request_type"] == "bank" and kwargs["approved"] is approved
    profile = env.client.get(f"/api/auth/profile/{env.u}", headers=env.uh).json()["user"]
    assert profile["bank_request_status"] == ("approved" if approved else "rejected")
    assert profile["bank_locked"] is (not approved)


def test_a_request_can_only_be_decided_once_and_only_by_an_admin(env):
    submit(env)
    rid = env.client.get("/api/admin/edit-requests", headers=env.ah).json()["items"][0]["id"]
    assert env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": "approve"}, headers=env.uh).status_code == 401
    with patch("app.utils.email_service.send_edit_request_decision_email", return_value=True):
        assert env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": "approve"}, headers=env.ah).status_code == 200
        assert env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": "reject"}, headers=env.ah).status_code == 400


def test_email_failure_never_undoes_the_decision(env):
    submit(env)
    rid = env.client.get("/api/admin/edit-requests", headers=env.ah).json()["items"][0]["id"]
    with patch("app.utils.email_service.send_edit_request_decision_email", side_effect=RuntimeError("SES down")):
        assert env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": "approve"}, headers=env.ah).status_code == 200
    db = env.db()
    assert db.get(EditRequest, rid).status == "approved"


def test_email_template_renders_for_both_outcomes():
    from app.utils import email_service
    with patch.object(email_service, "send_email", return_value=True) as send:
        email_service.send_edit_request_decision_email("a@b.c", "Asha K", "bank", True)
        email_service.send_edit_request_decision_email("a@b.c", "Asha K", "phone", False)
    assert "approved" in send.call_args_list[0].kwargs["subject"]
    assert "not approved" in send.call_args_list[1].kwargs["subject"]
