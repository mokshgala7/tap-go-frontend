"""Edit-request review: status strings, filters, and what a decision does (and does not) allow.

Regression for the defect where a rejection was stored as the invalid status
"rejectd" ("reject" + "d"): the admin list could never filter rejected requests.
Passenger and driver accounts are both covered.
"""
from unittest.mock import patch

import pytest

from app.models import EditRequest
from helpers import Env


@pytest.fixture
def env():
    e = Env()
    e.passenger = e.add_user("pax@test.local", phone="9111111111")
    e.driver = e.add_user("drv@test.local", account_type="driver", phone="9222222222")
    e.ph = e.user_headers(e.passenger)
    e.dh = e.user_headers(e.driver)
    e.ah = e.admin_headers(e.add_admin())
    return e


def ask(env, headers, kind):
    return env.client.post("/api/auth/request-admin-access", json={"request_type": kind}, headers=headers)


def rid_for(env, user_id, kind):
    db = env.db()
    try:
        row = db.query(EditRequest).filter(EditRequest.user_id == user_id, EditRequest.field_name == kind).first()
        return row.id
    finally:
        db.close()


def review(env, rid, action, headers=None):
    with patch("app.utils.email_service.send_edit_request_decision_email", return_value=True):
        return env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": action},
                               headers=env.ah if headers is None else headers)


def listed(env, status=None):
    url = "/api/admin/edit-requests" + (f"?status={status}" if status else "")
    r = env.client.get(url, headers=env.ah)
    assert r.status_code == 200
    return r.json()["items"]


@pytest.mark.parametrize("who", ["passenger", "driver"])
@pytest.mark.parametrize("kind", ["phone", "bank", "documents"])
def test_requests_from_both_roles_reach_the_admin_list(env, who, kind):
    uid, headers = (env.passenger, env.ph) if who == "passenger" else (env.driver, env.dh)
    assert ask(env, headers, kind).status_code == 200
    items = listed(env, "pending")
    assert len(items) == 1
    assert items[0]["user_id"] == uid and items[0]["field_name"] == kind
    assert items[0]["account_type"] == who and items[0]["status"] == "pending"


def test_reject_is_stored_as_rejected_never_rejectd(env):
    ask(env, env.ph, "phone")
    rid = rid_for(env, env.passenger, "phone")
    r = review(env, rid, "reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    db = env.db()
    assert db.get(EditRequest, rid).status == "rejected"
    db.close()
    assert [i["id"] for i in listed(env, "rejected")] == [rid]
    assert listed(env, "pending") == [] and listed(env, "approved") == []
    assert listed(env, "rejectd") == []


def test_approve_is_stored_as_approved_and_filterable(env):
    ask(env, env.dh, "bank")
    rid = rid_for(env, env.driver, "bank")
    assert review(env, rid, "approve").json()["status"] == "approved"
    assert [i["id"] for i in listed(env, "approved")] == [rid]


def test_all_statuses_stay_in_the_known_set(env):
    for kind, action in [("phone", "approve"), ("bank", "reject"), ("documents", "reject")]:
        ask(env, env.ph, kind)
        review(env, rid_for(env, env.passenger, kind), action)
    assert {i["status"] for i in listed(env)} <= {"pending", "approved", "rejected"}


def test_rejected_phone_request_grants_nothing(env):
    ask(env, env.ph, "phone")
    review(env, rid_for(env, env.passenger, "phone"), "reject")
    r = env.client.put("/api/auth/profile", json={"phone": "9333333333"}, headers=env.ph)
    assert r.status_code == 400 and "approval" in r.json()["detail"].lower()
    profile = env.client.get(f"/api/auth/profile/{env.passenger}", headers=env.ph).json()["user"]
    assert profile["phone"] == "9111111111" and profile["phone_request_status"] == "rejected"


def test_a_rejected_request_may_be_asked_again(env):
    ask(env, env.ph, "phone")
    review(env, rid_for(env, env.passenger, "phone"), "reject")
    assert ask(env, env.ph, "phone").status_code == 200
    assert len(listed(env, "pending")) == 1 and len(listed(env, "rejected")) == 1


def test_approval_is_permission_only_and_is_consumed(env):
    ask(env, env.dh, "phone")
    review(env, rid_for(env, env.driver, "phone"), "approve")
    before = env.client.get(f"/api/auth/profile/{env.driver}", headers=env.dh).json()["user"]
    assert before["phone"] == "9222222222" and before["phone_request_status"] == "approved"  # nothing changed yet
    assert env.client.put("/api/auth/profile", json={"phone": "bad"}, headers=env.dh).status_code == 400
    ok = env.client.put("/api/auth/profile", json={"phone": "9444444444"}, headers=env.dh)
    assert ok.status_code == 200 and ok.json()["user"]["phone"] == "9444444444"
    assert ok.json()["user"]["phone_request_status"] == "none"  # permission consumed
    again = env.client.put("/api/auth/profile", json={"phone": "9555555555"}, headers=env.dh)
    assert again.status_code == 400  # a second change needs a new request


def test_approved_phone_cannot_take_another_users_number(env):
    ask(env, env.ph, "phone")
    review(env, rid_for(env, env.passenger, "phone"), "approve")
    r = env.client.put("/api/auth/profile", json={"phone": "9222222222"}, headers=env.ph)  # the driver's number
    assert r.status_code == 400 and "already registered" in r.json()["detail"]


def test_repeated_decisions_do_not_corrupt_state(env):
    ask(env, env.ph, "bank")
    rid = rid_for(env, env.passenger, "bank")
    assert review(env, rid, "approve").status_code == 200
    assert review(env, rid, "reject").status_code == 400
    assert review(env, rid, "approve").status_code == 400
    db = env.db()
    assert db.get(EditRequest, rid).status == "approved"
    db.close()
    profile = env.client.get(f"/api/auth/profile/{env.passenger}", headers=env.ph).json()["user"]
    assert profile["bank_request_status"] == "approved"


def test_only_an_administrator_can_list_or_decide(env):
    ask(env, env.ph, "documents")
    rid = rid_for(env, env.passenger, "documents")
    for headers in ({}, env.ph, env.dh):
        assert env.client.get("/api/admin/edit-requests", headers=headers).status_code in (401, 403)
        r = env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": "approve"}, headers=headers)
        assert r.status_code in (401, 403)
    db = env.db()
    assert db.get(EditRequest, rid).status == "pending"
    db.close()


def test_invalid_actions_and_request_types_are_rejected(env):
    assert ask(env, env.ph, "email").status_code == 400
    assert ask(env, env.ph, "").status_code == 400
    ask(env, env.ph, "bank")
    rid = rid_for(env, env.passenger, "bank")
    assert env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": "rejectd"}, headers=env.ah).status_code == 422
    assert env.client.post(f"/api/admin/edit-requests/{rid}/review", json={"action": "delete"}, headers=env.ah).status_code == 422
    assert env.client.post("/api/admin/edit-requests/99999/review", json={"action": "approve"}, headers=env.ah).status_code == 404


def test_document_upload_needs_an_approved_request(env):
    files = {"file": ("id.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")}
    r = env.client.post("/api/auth/profile/document", data={"document_type": "id_document"}, files=files, headers=env.ph)
    assert r.status_code == 400 and "not authorized" in r.json()["detail"].lower()
    ask(env, env.ph, "documents")
    r = env.client.post("/api/auth/profile/document", data={"document_type": "id_document"}, files=files, headers=env.ph)
    assert r.status_code == 400  # pending is not approval
    review(env, rid_for(env, env.passenger, "documents"), "reject")
    r = env.client.post("/api/auth/profile/document", data={"document_type": "id_document"}, files=files, headers=env.ph)
    assert r.status_code == 400  # rejected grants nothing
