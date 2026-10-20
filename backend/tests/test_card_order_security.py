"""NFC card-order authorization (finding F-19)."""
from unittest.mock import patch

import pytest

from helpers import Env

BODY = dict(recipient_name="Asha K", phone="9876543210", address_line1="12 Main Rd", area="Andheri",
            city="Mumbai", state="Maharashtra", pincode="400053")


@pytest.fixture
def env():
    e = Env()
    e.a = e.add_user("a@test.local")
    e.b = e.add_user("b@test.local")
    e.ah, e.bh = e.user_headers(e.a), e.user_headers(e.b)
    with patch("app.routes.card_order.send_nfc_card_order_email", return_value=True):
        yield e


def test_create_requires_authentication(env):
    assert env.client.post("/api/card-order/create", json={**BODY, "user_id": env.a}).status_code == 401


def test_cannot_order_for_another_user(env):
    assert env.client.post("/api/card-order/create", json={**BODY, "user_id": env.b}, headers=env.ah).status_code == 403
    assert env.client.get(f"/api/card-order/user/{env.b}", headers=env.ah).status_code == 403


def test_order_belongs_to_the_authenticated_user_even_without_user_id(env):
    r = env.client.post("/api/card-order/create", json=BODY, headers=env.ah)
    assert r.status_code == 200, r.text
    mine = env.client.get(f"/api/card-order/user/{env.a}", headers=env.ah).json()["orders"]
    assert len(mine) == 1 and mine[0]["user_id"] == env.a
    assert env.client.get(f"/api/card-order/user/{env.a}").status_code == 401
    assert env.client.get(f"/api/card-order/user/{env.a}", headers=env.bh).status_code == 403


def test_delivery_quote_stays_public(env):
    r = env.client.post("/api/card-order/calculate-delivery", json={"city": "Mumbai", "state": "Maharashtra", "pincode": "400053"})
    assert r.status_code == 200
