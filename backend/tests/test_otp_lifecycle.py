"""Registration OTP and password-recovery OTP lifecycle.

Everything here is MOCKED delivery: the Amazon SES hop (`_send_ses_email`) is replaced by a
recorder, so no e-mail leaves the machine. These tests prove the server-side rules (expiry,
single use, purpose/account binding, attempt limits, cooldown, concurrency, no secrets in
logs, no success when delivery fails). They say nothing about whether a real inbox receives a
message; that needs a verified SES sender and an authorised mailbox.
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.models import EmailOTP, User
from app.utils.security import hash_password, is_otp_expired, verify_password
from helpers import Env

PASSWORD = "Passw0rd!x"
NEW_PASSWORD = "N3w-Strong-Pass!"


class Outbox:
    """Stands in for Amazon SES: records every message instead of sending it."""

    def __init__(self):
        self.sent = []
        self.fail = False

    def __call__(self, to_email, subject, html_content, text_content=None, attachments=None):
        if self.fail:
            return False, "SES rejected the message (simulated)"
        self.sent.append({"to": to_email, "subject": subject, "html": html_content, "text": text_content or ""})
        return True, None

    def to(self, email):
        return [m for m in self.sent if m["to"].lower() == email.lower()]


@pytest.fixture
def outbox():
    box = Outbox()
    with patch("app.utils.email_service._send_ses_email", side_effect=box):
        yield box


@pytest.fixture
def env():
    return Env()


def code_in(mail):
    """The 6-digit code as a reader of the e-mail sees it (HTML cells joined / plain-text part)."""
    visible = re.sub(r"<[^>]+>|\s", "", mail["html"])
    return mail["text"] if re.search(r"\d{6}", mail["text"]) else visible


def otp_row(env, email, reason="create_account", used=None):
    db = env.db()
    try:
        q = db.query(EmailOTP).filter(EmailOTP.email == email.lower(), EmailOTP.reason == reason)
        if used is not None:
            q = q.filter(EmailOTP.used == used)
        row = q.order_by(EmailOTP.id.desc()).first()
        if row is not None:
            db.expunge(row)
        return row
    finally:
        db.close()


def age_otp(env, email, reason, *, created_seconds_ago=None, expires_in=None):
    db = env.db()
    try:
        row = db.query(EmailOTP).filter(EmailOTP.email == email.lower(), EmailOTP.reason == reason) \
            .order_by(EmailOTP.id.desc()).first()
        if created_seconds_ago is not None:
            row.created_at = datetime.utcnow() - timedelta(seconds=created_seconds_ago)
        if expires_in is not None:
            row.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        db.commit()
    finally:
        db.close()


def reg_form(email, otp, phone="9876543210", **extra):
    form = {"account_type": "passenger", "name": "Asha Verma", "email": email, "phone": phone,
            "email_otp": otp, "password": PASSWORD}
    form.update(extra)
    return form


def send_reg_otp(env, email):
    return env.client.post("/api/auth/send-otp", json={"email": email, "account_type": "passenger"})


def verify(env, email, code, reason="create_account"):
    return env.client.post("/api/auth/verify-otp", json={"email": email, "otp": code, "reason": reason})


def wrong_code(real):
    return "000000" if real != "000000" else "111111"


# ───────────────────────────── registration OTP ─────────────────────────────

class TestRegistrationOtp:
    def test_code_is_emailed_never_returned(self, env, outbox, caplog):
        caplog.set_level(logging.DEBUG)
        res = send_reg_otp(env, "new.user@example.com")
        assert res.status_code == 200 and res.json()["success"] is True
        row = otp_row(env, "new.user@example.com")
        assert row and len(row.otp) == 6 and row.otp.isdigit()
        assert row.purpose == "create_account" and row.used is False and row.attempts == 0
        assert (row.expires_at - datetime.utcnow()).total_seconds() <= 300
        assert row.otp not in res.text                                   # not in the HTTP response
        mails = outbox.to("new.user@example.com")
        assert len(mails) == 1 and row.otp in code_in(mails[0])          # but it is in the e-mail
        assert row.otp not in caplog.text                                # and not in any log line

    def test_delivery_failure_is_reported_not_hidden(self, env, outbox):
        outbox.fail = True
        res = send_reg_otp(env, "nomail@example.com")
        assert res.status_code == 500 and res.json().get("success") is not True
        assert "verification email" in res.json()["detail"].lower()
        assert outbox.sent == []

    def test_already_registered_email_gets_no_code(self, env, outbox):
        env.add_user("taken@example.com")
        res = send_reg_otp(env, "taken@example.com")
        assert res.status_code == 400
        assert outbox.sent == [] and otp_row(env, "taken@example.com") is None

    def test_resend_cooldown_then_new_code_invalidates_old(self, env, outbox):
        assert send_reg_otp(env, "resend@example.com").status_code == 200
        first = otp_row(env, "resend@example.com").otp
        again = send_reg_otp(env, "resend@example.com")
        assert again.status_code == 429 and "wait" in again.json()["detail"].lower()
        assert len(outbox.to("resend@example.com")) == 1

        age_otp(env, "resend@example.com", "create_account", created_seconds_ago=61)
        assert send_reg_otp(env, "resend@example.com").status_code == 200
        second_row = otp_row(env, "resend@example.com", used=False)
        assert second_row.otp is not None and len(outbox.to("resend@example.com")) == 2
        if second_row.otp != first:                                      # (1 in 900000 collision)
            assert verify(env, "resend@example.com", first).status_code == 400
        assert verify(env, "resend@example.com", second_row.otp).status_code == 200

    def test_wrong_codes_lock_the_code_after_five(self, env, outbox):
        send_reg_otp(env, "lock@example.com")
        real = otp_row(env, "lock@example.com").otp
        bad = wrong_code(real)
        details = [verify(env, "lock@example.com", bad).json()["detail"] for _ in range(5)]
        assert "4 attempts remaining" in details[0]
        assert "Too many incorrect attempts" in details[4]
        # the right code no longer works once locked
        late = verify(env, "lock@example.com", real)
        assert late.status_code == 400
        assert otp_row(env, "lock@example.com").used is True

    def test_expired_code_is_rejected(self, env, outbox):
        send_reg_otp(env, "old@example.com")
        real = otp_row(env, "old@example.com").otp
        age_otp(env, "old@example.com", "create_account", expires_in=-5)
        res = verify(env, "old@example.com", real)
        assert res.status_code == 400 and "expired" in res.json()["detail"].lower()
        res = env.client.post("/api/auth/register", data=reg_form("old@example.com", real))
        assert res.status_code == 400
        assert env.db().query(User).filter(User.email == "old@example.com").first() is None

    def test_code_of_another_purpose_or_another_email_is_rejected(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        fp_code = otp_row(env, "member@example.com", "forgot_password").otp
        # a password-reset code cannot be used as a registration code
        assert verify(env, "member@example.com", fp_code, "create_account").status_code == 400
        # a registration code for one address cannot verify another address
        send_reg_otp(env, "alice@example.com")
        alice = otp_row(env, "alice@example.com").otp
        assert verify(env, "bob@example.com", alice).status_code == 400
        res = env.client.post("/api/auth/register", data=reg_form("bob@example.com", alice, phone="9222222222"))
        assert res.status_code == 400

    def test_register_requires_the_emailed_code(self, env, outbox):
        no_code = env.client.post("/api/auth/register", data=reg_form("x@example.com", "123456"))
        assert no_code.status_code == 400
        send_reg_otp(env, "y@example.com")
        real = otp_row(env, "y@example.com").otp
        bad = env.client.post("/api/auth/register", data=reg_form("y@example.com", wrong_code(real)))
        assert bad.status_code == 400
        assert otp_row(env, "y@example.com").attempts == 1
        assert env.db().query(User).filter(User.email == "y@example.com").first() is None

    def test_successful_registration_consumes_the_code_once(self, env, outbox):
        send_reg_otp(env, "ok@example.com")
        real = otp_row(env, "ok@example.com").otp
        assert verify(env, "ok@example.com", real).status_code == 200
        res = env.client.post("/api/auth/register", data=reg_form("ok@example.com", real))
        assert res.status_code == 200 and res.json()["success"] is True
        row = otp_row(env, "ok@example.com")
        assert row.used is True and row.is_verified is True              # consumed, never deleted
        assert real not in res.text
        user = env.db().query(User).filter(User.email == "ok@example.com").first()
        assert user and verify_password(PASSWORD, user.password_hash) and user.password_hash != PASSWORD
        # replay: the same code cannot create a second account
        again = env.client.post("/api/auth/register", data=reg_form("ok@example.com", real, phone="9333333333"))
        assert again.status_code == 400

    def test_rejected_form_does_not_burn_the_code(self, env, outbox):
        env.add_user("someone@example.com", phone="9876543210")
        send_reg_otp(env, "fresh@example.com")
        real = otp_row(env, "fresh@example.com").otp
        taken = env.client.post("/api/auth/register", data=reg_form("fresh@example.com", real, phone="9876543210"))
        assert taken.status_code == 400 and "phone" in taken.json()["detail"].lower()
        assert otp_row(env, "fresh@example.com").used is False
        fixed = env.client.post("/api/auth/register", data=reg_form("fresh@example.com", real, phone="9444444444"))
        assert fixed.status_code == 200

    def test_invalid_document_does_not_burn_the_code(self, env, outbox):
        send_reg_otp(env, "docs@example.com")
        real = otp_row(env, "docs@example.com").otp
        bad_file = {"photo": ("avatar.exe", b"MZ", "application/octet-stream")}
        res = env.client.post("/api/auth/register", data=reg_form("docs@example.com", real), files=bad_file)
        assert res.status_code == 400
        assert otp_row(env, "docs@example.com").used is False
        assert env.db().query(User).filter(User.email == "docs@example.com").first() is None
        good = env.client.post("/api/auth/register", data=reg_form("docs@example.com", real),
                               files={"photo": ("avatar.png", b"\x89PNG\r\n", "image/png")})
        assert good.status_code == 200

    def test_registration_survives_a_failing_welcome_email(self, env, outbox):
        send_reg_otp(env, "welcome@example.com")
        real = otp_row(env, "welcome@example.com").otp
        outbox.fail = True                                               # the welcome e-mail will fail
        res = env.client.post("/api/auth/register", data=reg_form("welcome@example.com", real))
        assert res.status_code == 200


# ───────────────────────────── password recovery OTP ─────────────────────────────

class TestPasswordRecoveryOtp:
    def test_unknown_account_gets_a_generic_answer_and_no_mail(self, env, outbox):
        res = env.client.post("/api/auth/forgot-password-otp", json={"account": "ghost@example.com"})
        assert res.status_code == 200 and res.json()["success"] is True
        assert res.json().get("email") in (None, "ghost@example.com")     # at most what the caller typed
        assert outbox.sent == []

    def test_known_account_gets_a_code_by_email_only(self, env, outbox, caplog):
        caplog.set_level(logging.DEBUG)
        env.add_user("member@example.com", phone="9111111111")
        res = env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        assert res.status_code == 200 and res.json()["success"] is True
        row = otp_row(env, "member@example.com", "forgot_password")
        assert row and row.purpose == "forgot_password" and len(row.otp) == 6
        assert row.otp not in res.text and row.otp not in caplog.text
        assert len(outbox.to("member@example.com")) == 1 and row.otp in code_in(outbox.to("member@example.com")[0])

    def test_lookup_by_phone_mails_the_registered_address(self, env, outbox):
        env.add_user("phoneuser@example.com", phone="9555555555")
        res = env.client.post("/api/auth/forgot-password-otp", json={"account": "9555555555"})
        assert res.status_code == 200
        assert len(outbox.to("phoneuser@example.com")) == 1

    def test_delivery_failure_is_reported_not_hidden(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        outbox.fail = True
        res = env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        assert res.status_code == 500 and res.json().get("success") is not True

    def test_resend_cooldown(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        assert env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"}).status_code == 200
        res = env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        assert res.status_code == 429
        assert len(outbox.to("member@example.com")) == 1

    def _request_code(self, env, email="member@example.com"):
        env.client.post("/api/auth/forgot-password-otp", json={"account": email})
        return otp_row(env, email, "forgot_password").otp

    def _reset(self, env, code, email="member@example.com", password=NEW_PASSWORD):
        return env.client.post("/api/auth/reset-password", json={"email": email, "otp": code, "new_password": password})

    def _login(self, env, password, account="member@example.com"):
        return env.client.post("/api/auth/login", json={"account": account, "password": password}).json()

    def test_reset_changes_the_password_and_the_code_is_single_use(self, env, outbox, caplog):
        caplog.set_level(logging.DEBUG)
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        code = self._request_code(env)
        res = self._reset(env, code)
        assert res.status_code == 200 and res.json()["success"] is True
        assert self._login(env, NEW_PASSWORD).get("success") is True
        assert self._login(env, PASSWORD).get("success") is not True
        row = otp_row(env, "member@example.com", "forgot_password")
        assert row.used is True and row.is_verified is True              # consumed, kept for audit
        # replay with the same code is refused and the password stays as set
        replay = self._reset(env, code, password="Another-Pass-9!")
        assert replay.status_code == 400
        assert self._login(env, NEW_PASSWORD).get("success") is True
        # neither the code nor any password reaches the logs
        assert code not in caplog.text and NEW_PASSWORD not in caplog.text and PASSWORD not in caplog.text
        db = env.db()
        stored = db.query(User).filter(User.email == "member@example.com").first().password_hash
        assert NEW_PASSWORD not in stored and stored.startswith("$2")    # bcrypt hash only

    def test_wrong_codes_lock_and_never_change_the_password(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        code = self._request_code(env)
        bad = wrong_code(code)
        details = [self._reset(env, bad).json()["detail"] for _ in range(5)]
        assert "4 attempts remaining" in details[0] and "Too many incorrect attempts" in details[4]
        assert self._reset(env, code).status_code == 400                 # even the right code is dead now
        assert self._login(env, PASSWORD).get("success") is True

    def test_expired_code_is_rejected(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        code = self._request_code(env)
        age_otp(env, "member@example.com", "forgot_password", expires_in=-5)
        res = self._reset(env, code)
        assert res.status_code == 400 and "expired" in res.json()["detail"].lower()
        assert self._login(env, PASSWORD).get("success") is True

    def test_registration_code_cannot_reset_a_password(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        db = env.db()
        db.add(EmailOTP(email="member@example.com", otp="424242", reason="create_account", purpose="create_account",
                        attempts=0, is_verified=True, used=False, expires_at=datetime.utcnow() + timedelta(minutes=5)))
        db.commit()
        res = self._reset(env, "424242")
        assert res.status_code == 400
        assert self._login(env, PASSWORD).get("success") is True

    def test_code_for_one_account_cannot_reset_another(self, env, outbox):
        env.add_user("victim@example.com", phone="9111111111", password=PASSWORD)
        env.add_user("attacker@example.com", phone="9222222222", password=PASSWORD)
        attacker_code = self._request_code(env, "attacker@example.com")
        res = self._reset(env, attacker_code, email="victim@example.com")
        assert res.status_code == 400
        assert self._login(env, PASSWORD, "victim@example.com").get("success") is True

    def test_new_request_invalidates_the_previous_code(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        first = self._request_code(env)
        age_otp(env, "member@example.com", "forgot_password", created_seconds_ago=61)
        second = self._request_code(env)
        if first != second:
            assert self._reset(env, first).status_code == 400
        assert self._reset(env, second).status_code == 200


# ───────────────────────────── time zones ─────────────────────────────

class TestExpiryClock:
    def test_expiry_does_not_depend_on_the_server_time_zone(self):
        """OTP expiry is stored as UTC. The old check also compared local time, so on a server
        behind UTC a code that expired hours ago still looked valid."""
        original = os.environ.get("TZ")
        try:
            for zone in ("America/New_York", "Asia/Kolkata", "UTC", "Pacific/Auckland"):
                os.environ["TZ"] = zone
                time.tzset()
                assert is_otp_expired(datetime.utcnow() - timedelta(hours=3)) is True, zone
                assert is_otp_expired(datetime.utcnow() - timedelta(minutes=2)) is True, zone
                assert is_otp_expired(datetime.utcnow() - timedelta(seconds=1)) is True, zone
                assert is_otp_expired(datetime.utcnow() + timedelta(minutes=4)) is False, zone
                assert is_otp_expired(None) is True
        finally:
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            time.tzset()


# ───────────────────────────── concurrency ─────────────────────────────

def run_parallel(n, fn):
    results, barrier = [], threading.Barrier(n)

    def go(i):
        barrier.wait()
        results.append(fn(i))

    threads = [threading.Thread(target=go, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


class TestConcurrency:
    def test_parallel_guesses_cannot_exceed_the_attempt_limit(self, tmp_path, outbox):
        env = Env(str(tmp_path / "otp.db"))
        send_reg_otp(env, "burst@example.com")
        real = otp_row(env, "burst@example.com").otp
        bad = wrong_code(real)
        codes = run_parallel(24, lambda i: verify(env, "burst@example.com", bad).status_code)
        assert all(c == 400 for c in codes), codes
        row = otp_row(env, "burst@example.com")
        assert row.used is True and row.attempts == 5                    # exactly the limit, no under-count
        assert verify(env, "burst@example.com", real).status_code == 400

    def test_parallel_guesses_with_the_right_code_still_verify_once_allowed(self, tmp_path, outbox):
        env = Env(str(tmp_path / "otp2.db"))
        send_reg_otp(env, "mix@example.com")
        real = otp_row(env, "mix@example.com").otp
        codes = run_parallel(6, lambda i: verify(env, "mix@example.com", real).status_code)
        assert codes.count(200) == 6, codes                              # a correct code is not locked out by its own repeats
        assert otp_row(env, "mix@example.com").attempts == 0

    def test_same_code_cannot_create_two_accounts(self, tmp_path, outbox):
        env = Env(str(tmp_path / "reg.db"))
        send_reg_otp(env, "twin@example.com")
        real = otp_row(env, "twin@example.com").otp
        codes = run_parallel(
            6, lambda i: env.client.post("/api/auth/register", data=reg_form("twin@example.com", real, phone="9000000001")).status_code
        )
        assert codes.count(200) == 1, codes
        assert env.db().query(User).filter(User.email == "twin@example.com").count() == 1

    def test_same_code_cannot_reset_a_password_twice(self, tmp_path, outbox):
        env = Env(str(tmp_path / "pw.db"))
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        code = otp_row(env, "member@example.com", "forgot_password").otp

        def reset(i):
            return env.client.post("/api/auth/reset-password",
                                   json={"email": "member@example.com", "otp": code, "new_password": f"Pw-{i}-Strong!x"}).status_code

        codes = run_parallel(6, reset)
        assert codes.count(200) == 1, codes


# ───────────────────────────── pre-deployment security review ─────────────────────────────

class TestAccountBinding:
    def test_reset_changes_only_the_account_the_code_was_sent_to(self, env, outbox):
        """The code is bound to an e-mail address; the password that changes must belong to that
        same address. Digits inside an e-mail address must never select another user by phone."""
        victim = env.add_user("victim@example.com", phone="9111111111", password=PASSWORD)       # registered first
        attacker = env.add_user("att9111111111@example.com", phone="9222222222", password=PASSWORD)
        # A recovery code for the attacker's own address exists (the request side resolved to the
        # attacker; with unordered lookups the reset side can resolve differently).
        db = env.db()
        db.add(EmailOTP(email="att9111111111@example.com", otp="135790", reason="forgot_password", purpose="forgot_password",
                        attempts=0, is_verified=False, used=False, expires_at=datetime.utcnow() + timedelta(minutes=5)))
        db.commit()
        code = "135790"
        res = env.client.post("/api/auth/reset-password", json={
            "email": "att9111111111@example.com", "otp": code, "new_password": NEW_PASSWORD})
        assert res.status_code == 200
        db = env.db()
        v = db.query(User).filter(User.id == victim).first()
        a = db.query(User).filter(User.id == attacker).first()
        assert verify_password(PASSWORD, v.password_hash), "the victim's password was changed by someone else's code"
        assert verify_password(NEW_PASSWORD, a.password_hash)

    def test_recovery_by_e_mail_never_matches_a_phone_hidden_in_the_address(self, env, outbox):
        env.add_user("victim@example.com", phone="9111111111", password=PASSWORD)
        res = env.client.post("/api/auth/forgot-password-otp", json={"account": "nobody9111111111@example.com"})
        assert res.status_code == 200
        assert outbox.sent == [], "a code was mailed to the victim because a phone number appeared inside the typed e-mail"


class TestRecoveryAnswersDoNotLeak:
    def _ask(self, env, account):
        res = env.client.post("/api/auth/forgot-password-otp", json={"account": account})
        return res.status_code, res.json()

    def test_known_and_unknown_e_mail_get_the_same_answer(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        known = self._ask(env, "member@example.com")
        unknown = self._ask(env, "nobody@example.com")
        assert known[0] == unknown[0] == 200
        assert set(known[1]) == set(unknown[1])
        assert known[1]["message"] == unknown[1]["message"]
        assert known[1]["email"] == "member@example.com" and unknown[1]["email"] == "nobody@example.com"

    def test_phone_lookup_never_reveals_the_registered_address(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        known = self._ask(env, "9111111111")
        unknown = self._ask(env, "9000000000")
        assert known[0] == unknown[0] == 200 and known[1] == unknown[1]
        assert "@" not in json.dumps(known[1]) and "member" not in json.dumps(known[1])
        assert len(outbox.to("member@example.com")) == 1                  # (the code still goes to the real owner)

    def test_the_whole_flow_still_works_from_a_phone_number(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        self._ask(env, "9111111111")
        code = otp_row(env, "member@example.com", "forgot_password").otp
        assert env.client.post("/api/auth/verify-otp", json={"email": "9111111111", "otp": code, "reason": "forgot_password"}).status_code == 200
        res = env.client.post("/api/auth/reset-password", json={"email": "9111111111", "otp": code, "new_password": NEW_PASSWORD})
        assert res.status_code == 200
        login = env.client.post("/api/auth/login", json={"account": "member@example.com", "password": NEW_PASSWORD}).json()
        assert login.get("success") is True

    def test_provider_error_text_is_not_sent_to_the_caller(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        outbox.fail = True
        reg = send_reg_otp(env, "fresh@example.com")
        rec = self._ask(env, "member@example.com")
        for res_text in (reg.text, json.dumps(rec[1])):
            assert "SES" not in res_text and "simulated" not in res_text and "rejected" not in res_text.lower()
        assert reg.status_code == 500 and rec[0] == 500


class TestRequestLimits:
    def _fill_hour(self, env, send, email, reason, n=5):
        for _ in range(n):
            assert send().status_code == 200
            age_otp(env, email, reason, created_seconds_ago=61)

    def test_registration_codes_are_capped_per_hour(self, env, outbox):
        self._fill_hour(env, lambda: send_reg_otp(env, "cap@example.com"), "cap@example.com", "create_account")
        res = send_reg_otp(env, "cap@example.com")
        assert res.status_code == 429 and "hour" in res.json()["detail"].lower()
        assert len(outbox.to("cap@example.com")) == 5
        # the hour passes: requests are accepted again
        db = env.db()
        for row in db.query(EmailOTP).filter(EmailOTP.email == "cap@example.com"):
            row.created_at = datetime.utcnow() - timedelta(hours=2)
        db.commit()
        assert send_reg_otp(env, "cap@example.com").status_code == 200

    def test_recovery_codes_are_capped_per_hour(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        ask = lambda: env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        self._fill_hour(env, ask, "member@example.com", "forgot_password")
        res = ask()
        assert res.status_code == 429 and "hour" in res.json()["detail"].lower()
        assert len(outbox.to("member@example.com")) == 5

    def test_the_cap_is_per_address_and_per_purpose(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111")
        self._fill_hour(env, lambda: send_reg_otp(env, "cap2@example.com"), "cap2@example.com", "create_account")
        assert send_reg_otp(env, "other@example.com").status_code == 200            # another address
        assert env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"}).status_code == 200  # another purpose

    def test_the_public_verify_endpoint_only_serves_registration_and_recovery(self, env, outbox):
        db = env.db()
        db.add(EmailOTP(email="payer@example.com", otp="246810", reason="withdraw_balance", purpose="withdrawal",
                        attempts=0, is_verified=False, used=False, expires_at=datetime.utcnow() + timedelta(minutes=5)))
        db.commit()
        for reason in ("withdraw_balance", "wallet_topup", "withdrawal", "anything-else"):
            res = verify(env, "payer@example.com", "000000", reason)
            assert res.status_code == 400 and "cannot be verified here" in res.json()["detail"], reason
        row = otp_row(env, "payer@example.com", "withdraw_balance")
        assert row.attempts == 0 and row.used is False                    # nobody can burn another user's money code here


class TestPasswordRules:
    def test_reset_refuses_weak_or_absurd_passwords_without_spending_the_code(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        code = otp_row(env, "member@example.com", "forgot_password").otp
        for bad in ("", "short", "1234567", "x" * 129):
            res = env.client.post("/api/auth/reset-password", json={"email": "member@example.com", "otp": code, "new_password": bad})
            assert res.status_code == 400 and "between 8 and 128" in res.json()["detail"], bad
        row = otp_row(env, "member@example.com", "forgot_password")
        assert row.used is False and row.attempts == 0
        ok = env.client.post("/api/auth/reset-password", json={"email": "member@example.com", "otp": code, "new_password": "eight-ok"})
        assert ok.status_code == 200

    def test_registration_refuses_a_short_password_without_spending_the_code(self, env, outbox):
        send_reg_otp(env, "pw@example.com")
        real = otp_row(env, "pw@example.com").otp
        res = env.client.post("/api/auth/register", data=reg_form("pw@example.com", real, password="short"))
        assert res.status_code == 400 and "8 and 128" in res.json()["detail"]
        assert otp_row(env, "pw@example.com").used is False
        assert env.client.post("/api/auth/register", data=reg_form("pw@example.com", real)).status_code == 200


class TestSessionsAfterReset:
    def _two_sessions(self, env):
        uid = env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        return uid, env.user_headers(uid), env.user_headers(uid)

    def _profile_status(self, env, uid, headers):
        return env.client.get(f"/api/auth/profile/{uid}", headers=headers).status_code

    def _reset(self, env, headers=None):
        env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"})
        code = otp_row(env, "member@example.com", "forgot_password").otp
        return env.client.post("/api/auth/reset-password", headers=headers or {},
                               json={"email": "member@example.com", "otp": code, "new_password": NEW_PASSWORD})

    def test_forgotten_password_ends_every_session(self, env, outbox):
        uid, a, b = self._two_sessions(env)
        assert self._profile_status(env, uid, a) == 200 and self._profile_status(env, uid, b) == 200
        assert self._reset(env).status_code == 200
        assert self._profile_status(env, uid, a) == 401 and self._profile_status(env, uid, b) == 401
        login = env.client.post("/api/auth/login", json={"account": "member@example.com", "password": NEW_PASSWORD}).json()
        assert login.get("success") is True                                # a fresh sign-in works

    def test_in_app_change_keeps_only_the_callers_own_session(self, env, outbox):
        uid, mine, other = self._two_sessions(env)
        assert self._reset(env, headers=mine).status_code == 200
        assert self._profile_status(env, uid, mine) == 200
        assert self._profile_status(env, uid, other) == 401

    def test_someone_elses_session_is_never_kept(self, env, outbox):
        uid, a, _ = self._two_sessions(env)
        stranger = env.add_user("stranger@example.com", phone="9222222222")
        assert self._reset(env, headers=env.user_headers(stranger)).status_code == 200
        assert self._profile_status(env, uid, a) == 401
        assert self._profile_status(env, stranger, env.user_headers(stranger)) == 200   # the stranger's own account is untouched


class TestDeliveryFailureRecovery:
    def test_registration_survives_a_failed_send_and_a_later_success(self, env, outbox):
        outbox.fail = True
        assert send_reg_otp(env, "late@example.com").status_code == 500
        failed = otp_row(env, "late@example.com")
        assert failed is not None and failed.used is False and failed.attempts == 0     # persisted, usable by nobody who never got it
        assert send_reg_otp(env, "late@example.com").status_code == 429                  # the cooldown still applies

        outbox.fail = False
        age_otp(env, "late@example.com", "create_account", created_seconds_ago=61)
        assert send_reg_otp(env, "late@example.com").status_code == 200
        fresh = otp_row(env, "late@example.com", used=False)
        assert fresh.id != failed.id and otp_row(env, "late@example.com").otp in code_in(outbox.to("late@example.com")[-1])
        db = env.db()
        assert db.query(EmailOTP).filter(EmailOTP.id == failed.id).first().used is True  # the unsent code is retired
        assert verify(env, "late@example.com", fresh.otp).status_code == 200
        assert env.client.post("/api/auth/register", data=reg_form("late@example.com", fresh.otp)).status_code == 200

    def test_recovery_survives_a_failed_send_and_a_later_success(self, env, outbox):
        env.add_user("member@example.com", phone="9111111111", password=PASSWORD)
        outbox.fail = True
        assert env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"}).status_code == 500
        assert otp_row(env, "member@example.com", "forgot_password") is not None
        outbox.fail = False
        age_otp(env, "member@example.com", "forgot_password", created_seconds_ago=61)
        assert env.client.post("/api/auth/forgot-password-otp", json={"account": "member@example.com"}).status_code == 200
        code = otp_row(env, "member@example.com", "forgot_password", used=False).otp
        res = env.client.post("/api/auth/reset-password", json={"email": "member@example.com", "otp": code, "new_password": NEW_PASSWORD})
        assert res.status_code == 200
