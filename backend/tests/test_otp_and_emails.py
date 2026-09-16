import os
import sys
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError, BotoCoreError

from sqlalchemy import or_
from app.database import SessionLocal, engine
from app.models import Base, User, Wallet, EmailOTP, EmailLog, Transaction, NFCCardOrder
from app.schemas import SendOTPRequest, UserLoginRequest
from app.utils.security import hash_password, verify_password
from app.routes.auth import (
    send_otp,
    verify_otp,
    VerifyOTPRequest,
    forgot_password_otp,
    ForgotPasswordRequest,
    reset_password,
    ResetPasswordRequest,
    register,
    login,
)
from app.routes.wallet import (
    request_withdrawal_otp,
    WithdrawOTPRequest,
    withdraw_to_bank,
    WithdrawRequest,
    pay_fare,
    PayRequest,
    get_or_create_wallet,
)
from app.routes.payment import (
    request_topup_otp,
    create_razorpay_order,
    CreateOrderRequest,
    TopupOTPRequest,
)
from app.utils.email_service import (
    send_registration_otp,
    send_password_reset_otp,
    send_withdrawal_otp,
    send_wallet_topup_email,
    send_withdrawal_email,
    send_ride_passenger_email,
    send_ride_driver_email,
    send_nfc_card_order_email,
    send_nfc_status_update_email,
    send_welcome_email,
    send_security_alert_email,
    send_topup_otp,
    send_support_ticket_created,
    send_support_ticket_reply,
    send_withdrawal_approved_email,
    send_withdrawal_paid_email,
    send_withdrawal_rejected_email,
    get_last_email_error,
    _get_ses_client,
    _send_ses_email,
    send_email,
    _sanitize_error_message,
)
from app.config import settings
from fastapi import HTTPException


# ============================================================================
# TEST 1: Amazon SES Mocked Delivery & Client Verification
# ============================================================================

def test_ses_client_initialization():
    """Verify Amazon SES client initializes with configured region."""
    client = _get_ses_client()
    assert client is not None, "Failed to initialize Amazon SES client"
    assert client.meta.region_name == (settings.AWS_REGION or "ap-south-1")


def test_ses_mocked_successful_send():
    """Mock boto3 SES client and verify send_email dispatches via HTTPS and logs to DB."""
    mock_ses = MagicMock()
    mock_ses.send_email.return_value = {"MessageId": "ses-msg-mock-12345"}

    with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
        success, err = _send_ses_email(
            to_email="verified.test@thetapandgo.in",
            subject="Test Subject",
            html_content="<p>Test Body</p>",
        )
        assert success is True
        assert err is None

        # Verify arguments passed to boto3 client
        mock_ses.send_email.assert_called_once()
        call_kwargs = mock_ses.send_email.call_args[1]
        assert "verified.test@thetapandgo.in" in call_kwargs["Destination"]["ToAddresses"]
        assert "Test Subject" == call_kwargs["Message"]["Subject"]["Data"]
        assert "<p>Test Body</p>" == call_kwargs["Message"]["Body"]["Html"]["Data"]
        assert call_kwargs.get("Source") == "Tap & Go <tapandgosupport@gmail.com>"
        assert call_kwargs.get("ReplyToAddresses") is None

    # Verify central send_email dispatcher logs to EmailLog
    with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
        res = send_email(
            to_email="verified.test@thetapandgo.in",
            subject="Central Dispatcher Test",
            html_content="<p>Central body</p>",
            email_type="registration_otp",
            reference="REF-001",
        )
        assert res is True

    with SessionLocal() as db:
        log_entry = db.query(EmailLog).filter(
            EmailLog.recipient == "verified.test@thetapandgo.in",
            EmailLog.email_type == "registration_otp",
        ).order_by(EmailLog.created_at.desc()).first()
        assert log_entry is not None
        assert log_entry.status == "SENT"


def test_ses_failure_handling_and_credential_sanitization():
    """Verify SES client errors, network failures, and redaction of AWS secrets."""
    # 1. Simulate SES ClientError (e.g. unverified address in sandbox)
    client_err = ClientError(
        {"Error": {"Code": "MessageRejected", "Message": "Email address is not verified."}},
        "SendEmail",
    )
    mock_ses = MagicMock()
    mock_ses.send_email.side_effect = client_err

    with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
        success, err = _send_ses_email(
            to_email="unverified@example.com",
            subject="Test Subject",
            html_content="<p>Test Body</p>",
        )
        assert success is False
        assert "MessageRejected" in err
        assert "Email address is not verified" in err

    # 2. Verify sanitization function strips AWS secrets
    raw_leak = f"Failed with {settings.AWS_ACCESS_KEY_ID} and secret {settings.AWS_SECRET_ACCESS_KEY}"
    clean = _sanitize_error_message(raw_leak)
    if settings.AWS_ACCESS_KEY_ID:
        assert settings.AWS_ACCESS_KEY_ID not in clean
    if settings.AWS_SECRET_ACCESS_KEY:
        assert settings.AWS_SECRET_ACCESS_KEY not in clean

    # 3. Simulate BotoCoreError
    mock_ses.send_email.side_effect = BotoCoreError()
    with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
        success, err = _send_ses_email(
            to_email="fail@example.com",
            subject="Test Subject",
            html_content="<p>Test Body</p>",
        )
        assert success is False
        assert "SES BotoCoreError" in err


# ============================================================================
# TEST 2: Registration OTP Flow (6-digit, 5-min expiry, cooldown, security)
# ============================================================================

def test_registration_otp_flow():
    """Verify registration OTP generation, expiry, 60s cooldown, 5 attempts limit, and no bypass."""
    test_reg_email = f"test_reg_{int(datetime.now().timestamp())}@thetapandgo.in"

    with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
        with SessionLocal() as db:
            # 2a. Request OTP
            req = SendOTPRequest(email=test_reg_email, account_type="passenger")
            res = asyncio.run(send_otp(req, db=db))
            assert res.get("success") is True
            assert "otp" not in res, "CRITICAL: OTP exposed in API response!"
            assert "demo_mode" not in res, "CRITICAL: demo_mode flag found in response!"

            # Verify DB entry
            otp_row = db.query(EmailOTP).filter(
                EmailOTP.email == test_reg_email,
                EmailOTP.reason == "create_account",
            ).first()
            assert otp_row is not None
            assert len(otp_row.otp) == 6 and otp_row.otp.isdigit(), f"Invalid OTP format: {otp_row.otp}"
            assert otp_row.reason == "create_account"
            assert otp_row.purpose == "create_account"
            assert otp_row.used is False
            assert otp_row.attempts == 0

            # Verify 5-minute expiry
            now = datetime.now(otp_row.expires_at.tzinfo) if otp_row.expires_at.tzinfo else datetime.utcnow()
            time_diff = (otp_row.expires_at - now).total_seconds()
            assert 240 <= time_diff <= 310, f"Expiry diff unexpected: {time_diff}s"

            # 2b. Cooldown: second request within 60 seconds must be rejected
            req2 = SendOTPRequest(email=test_reg_email, account_type="passenger")
            try:
                asyncio.run(send_otp(req2, db=db))
                pytest.fail("Cooldown did not trigger 429!")
            except HTTPException as e:
                assert e.status_code == 429
                assert "Please wait" in e.detail

            # 2c. Incorrect OTP attempt increments attempts
            v_req = VerifyOTPRequest(email=test_reg_email, otp="000000", reason="create_account")
            try:
                asyncio.run(verify_otp(v_req, db=db))
                pytest.fail("Incorrect OTP did not raise 400!")
            except HTTPException as e:
                assert e.status_code == 400
                assert "4 attempts remaining" in e.detail

            db.refresh(otp_row)
            assert otp_row.attempts == 1

            # 2d. 5 incorrect attempts triggers lockout and marks used=True
            otp_row.attempts = 4
            db.commit()
            try:
                asyncio.run(verify_otp(v_req, db=db))
                pytest.fail("Lockout did not trigger!")
            except HTTPException as e:
                assert e.status_code == 400
                assert "Too many incorrect attempts" in e.detail

            db.refresh(otp_row)
            assert otp_row.used is True, "Lockout must mark used=True"

            # 2e. Re-issue fresh OTP and test valid verification
            fresh_otp = EmailOTP(
                email=test_reg_email,
                otp="849201",
                reason="create_account",
                purpose="create_account",
                attempts=0,
                is_verified=False,
                used=False,
                expires_at=datetime.utcnow() + timedelta(minutes=5),
            )
            db.add(fresh_otp)
            db.commit()

            v_req_valid = VerifyOTPRequest(email=test_reg_email, otp="849201", reason="create_account")
            v_res = asyncio.run(verify_otp(v_req_valid, db=db))
            assert v_res.get("success") is True

            db.refresh(fresh_otp)
            assert fresh_otp.is_verified is True
            assert fresh_otp.used is False


# ============================================================================
# TEST 3: Forgot Password OTP Flow & Purpose Separation
# ============================================================================

def test_forgot_password_otp_flow():
    """Verify forgot-password OTP flow, purpose separation, and password reset."""
    ts = int(datetime.now().timestamp())
    test_email = f"forgot_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        # Create user
        user = User(
            account_type="passenger",
            name="Password Reset User",
            email=test_email,
            phone=f"98{ts % 100000000:08d}",
            password_hash=hash_password("OldPassword@123"),
            status="active",
        )
        db.add(user)
        db.commit()

        # Request forgot-password OTP
        with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
            fp_req = ForgotPasswordRequest(account=test_email)
            fp_res = asyncio.run(forgot_password_otp(fp_req, db=db))
            assert fp_res.get("success") is True
            assert "otp" not in fp_res

            # DB check
            fp_otp = db.query(EmailOTP).filter(
                EmailOTP.email == test_email,
                EmailOTP.reason == "forgot_password",
            ).first()
            assert fp_otp is not None
            assert fp_otp.reason == "forgot_password"
            assert fp_otp.purpose == "forgot_password"
            assert fp_otp.used is False
            assert len(fp_otp.otp) == 6

            # Cross-purpose rejection check: cannot use forgot_password OTP for registration
            try:
                asyncio.run(verify_otp(VerifyOTPRequest(email=test_email, otp=fp_otp.otp, reason="create_account"), db=db))
                pytest.fail("Cross-purpose OTP was accepted!")
            except HTTPException as e:
                assert e.status_code == 400

            # Verify with correct reason/purpose
            v_res = asyncio.run(verify_otp(VerifyOTPRequest(email=test_email, otp=fp_otp.otp, reason="forgot_password"), db=db))
            assert v_res.get("success") is True

            # Reset password
            r_res = asyncio.run(reset_password(ResetPasswordRequest(
                email=test_email,
                otp=fp_otp.otp,
                new_password="NewPassword@2026",
            ), db=db))
            assert r_res.get("success") is True

            # OTP must remain persisted in DB and marked used=True
            db.refresh(fp_otp)
            assert fp_otp.used is True, "Password reset OTP must be marked used=True"
            assert fp_otp.is_verified is True

            # Verify login with old password fails, new password succeeds
            db.refresh(user)
            assert verify_password("NewPassword@2026", user.password_hash) is True
            assert verify_password("OldPassword@123", user.password_hash) is False


# ============================================================================
# TEST 4: Financial Resiliency: SES Failure MUST NOT Rollback Transactions
# ============================================================================

def test_financial_resiliency_on_ses_failure():
    """Verify that email dispatch failures (SES down) NEVER roll back financial transactions."""
    ts = int(datetime.now().timestamp())
    p_email = f"passenger_{ts}@thetapandgo.in"
    d_email = f"driver_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        passenger = User(
            account_type="passenger",
            name="Resilience Passenger",
            email=p_email,
            phone=f"97{ts % 100000000:08d}",
            password_hash=hash_password("Pass@123"),
            status="active",
        )
        driver = User(
            account_type="driver",
            name="Resilience Driver",
            email=d_email,
            phone=f"96{ts % 100000000:08d}",
            password_hash=hash_password("Driver@123"),
            status="active",
        )
        db.add_all([passenger, driver])
        db.commit()

        p_wallet = get_or_create_wallet(passenger.id, db)
        p_wallet.balance = Decimal("1000.00")
        d_wallet = get_or_create_wallet(driver.id, db)
        d_wallet.balance = Decimal("0.00")
        db.commit()

        # Test A: Successful payment with mocked SES success
        with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
            pay_res = pay_fare(PayRequest(
                passenger_id=passenger.id,
                driver_id=driver.id,
                fare=200.00,
                driver_name=driver.name,
                payment_method="QR",
            ), db=db)
            assert pay_res.get("success") is True
            db.refresh(p_wallet)
            db.refresh(d_wallet)
            assert p_wallet.balance == Decimal("800.00")
            assert d_wallet.balance == Decimal("200.00")

        # Test B: CRITICAL: SES completely fails / throws exception during ride payment
        with patch("app.utils.email_service._send_ses_email", side_effect=Exception("SES Service Unavailable Outage")):
            pay_res2 = pay_fare(PayRequest(
                passenger_id=passenger.id,
                driver_id=driver.id,
                fare=300.00,
                driver_name=driver.name,
                payment_method="QR",
            ), db=db)
            assert pay_res2.get("success") is True
            db.refresh(p_wallet)
            db.refresh(d_wallet)
            # The financial transaction MUST have completed and committed!
            assert p_wallet.balance == Decimal("500.00"), f"Expected 500.00, got {p_wallet.balance}"
            assert d_wallet.balance == Decimal("500.00"), f"Expected 500.00, got {d_wallet.balance}"

        # Test C: Bank withdrawal email failure resiliency
        passenger.bank_account_number = "987654321012"
        passenger.bank_ifsc = "SBIN0001234"
        db.commit()

        w_otp = EmailOTP(
            email=passenger.email,
            otp="776655",
            purpose="withdrawal",
            attempts=0,
            is_verified=False,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(w_otp)
        db.commit()

        with patch("app.utils.email_service._send_ses_email", side_effect=Exception("SES Down")):
            w_res = withdraw_to_bank(WithdrawRequest(
                user_id=passenger.id,
                amount=150.00,
                otp="776655",
            ), db=db)
            assert w_res.get("success") is True
            db.refresh(p_wallet)
            assert p_wallet.balance == Decimal("350.00"), f"Expected 350.00, got {p_wallet.balance}"


def test_all_branded_email_helpers():
    """Verify that all branded Tap & Go email helpers execute cleanly with mocked SES."""
    with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
        assert send_registration_otp("user@thetapandgo.in", "123456", "passenger") is True
        assert send_password_reset_otp("user@thetapandgo.in", "654321") is True
        assert send_withdrawal_otp("user@thetapandgo.in", "112233", 500.0) is True
        assert send_wallet_topup_email("user@thetapandgo.in", "User", 1000.0, 1500.0, "TXN-001") is True
        assert send_withdrawal_email("user@thetapandgo.in", "User", 500.0, "TXN-002", "HDFC - 1234") is True
        assert send_ride_passenger_email("user@thetapandgo.in", "User", 120.0, "Driver", "TXN-003") is True
        assert send_ride_driver_email("driver@thetapandgo.in", "Driver", 120.0, "User", "TXN-003") is True
        assert send_welcome_email("user@thetapandgo.in", "User", "passenger") is True
        assert send_security_alert_email("user@thetapandgo.in", "User", "Password Changed", "Your password was updated.") is True
        assert send_topup_otp("user@thetapandgo.in", "998877", 500.0) is True
        assert send_support_ticket_created("user@thetapandgo.in", "User", 101, "Help Needed") is True
        assert send_support_ticket_reply("user@thetapandgo.in", "User", 101, "Help Needed", "Resolved") is True
        assert send_withdrawal_approved_email("user@thetapandgo.in", "User", 500.0, "REF-01") is True
        assert send_withdrawal_paid_email("user@thetapandgo.in", "User", 500.0, "REF-01") is True
        assert send_withdrawal_rejected_email("user@thetapandgo.in", "User", 500.0, "REF-01", "Invalid IFSC") is True
        assert send_nfc_card_order_email("user@thetapandgo.in", "User", "ORD-01", 150.0, "Mumbai") is True
        assert send_nfc_status_update_email("user@thetapandgo.in", "User", "ORD-01", "shipped") is True


def test_local_development_smtp_fallback():
    """Verify that if AWS credentials are absent in local dev, send_email falls back to local dev SMTP when configured."""
    with patch.object(settings.__class__, "IS_PRODUCTION", False):
        with patch.object(settings.__class__, "AWS_ACCESS_KEY_ID", ""):
            with patch.object(settings.__class__, "AWS_SECRET_ACCESS_KEY", ""):
                with patch.object(settings.__class__, "SMTP_HOST", "smtp.local.test"):
                    with patch.object(settings.__class__, "SMTP_USER", "local-user@example.com"):
                        with patch.object(settings.__class__, "SMTP_PASSWORD", "local-test-password"):
                            with patch("app.utils.email_service._send_smtp_email", return_value=(True, None)) as mock_smtp:
                                res = send_email(
                                    to_email="dev@example.com",
                                    subject="Dev Subject",
                                    html_content="<p>Dev</p>",
                                )
                                assert res is True
                                mock_smtp.assert_called_once()


def test_no_hardcoded_smtp_credentials_or_obsolete_defaults():
    """Verify that SMTP settings have no hardcoded Gmail defaults or credentials."""
    with patch.dict(os.environ, {}, clear=True):
        # Fresh instance or property checks with clean environment
        assert settings.SMTP_HOST == "" or "gmail" not in settings.SMTP_HOST.lower()
        assert settings.SMTP_PASSWORD == ""
        assert "mokshgala070" not in settings.SMTP_USER.lower()



# ============================================================================
# COMPREHENSIVE TESTS FOR OTP PERSISTENCE, REASONS, CROSS-PURPOSE & RESILIENCE
# ============================================================================

def test_canonical_reasons_and_purpose_sync():
    """Verify all canonical reasons (create_account, forgot_password, withdraw_balance, wallet_topup) synchronize purpose and initialize used=False."""
    ts = int(datetime.now().timestamp())
    email = f"canon_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        user = User(
            account_type="passenger",
            name="Canonical Test User",
            email=email,
            phone=f"95{ts % 100000000:08d}",
            password_hash=hash_password("Pass@123"),
            bank_account_number="1234567890",
            status="active",
        )
        db.add(user)
        db.commit()

        # 1. create_account via send_otp
        with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
            res1 = asyncio.run(send_otp(SendOTPRequest(email=f"new_{ts}@thetapandgo.in", account_type="passenger"), db=db))
            assert res1.get("success") is True
            row1 = db.query(EmailOTP).filter(EmailOTP.email == f"new_{ts}@thetapandgo.in").first()
            assert row1.reason == "create_account"
            assert row1.purpose == "create_account"
            assert row1.used is False

            # 2. forgot_password via forgot_password_otp
            res2 = asyncio.run(forgot_password_otp(ForgotPasswordRequest(account=email), db=db))
            assert res2.get("success") is True
            row2 = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.reason == "forgot_password").first()
            assert row2.reason == "forgot_password"
            assert row2.purpose == "forgot_password"
            assert row2.used is False

            # 3. withdraw_balance via request_withdrawal_otp
            wallet = get_or_create_wallet(user.id, db)
            wallet.balance = Decimal("500.00")
            db.commit()
            res3 = request_withdrawal_otp(WithdrawOTPRequest(user_id=user.id, amount=100.0), db=db)
            assert res3.get("success") is True
            row3 = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.reason == "withdraw_balance").first()
            assert row3.reason == "withdraw_balance"
            assert row3.purpose == "withdraw_balance"
            assert row3.used is False

            # 4. wallet_topup via request_topup_otp
            res4 = request_topup_otp(TopupOTPRequest(amount=250.0), current_user=user, db=db)
            assert res4.get("success") is True
            row4 = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.reason == "wallet_topup").first()
            assert row4.reason == "wallet_topup"
            assert row4.purpose == "wallet_topup"
            assert row4.used is False
            assert "250.0" in (row4.otp_metadata or "")


def test_otp_persistence_no_deletion_on_consumption():
    """Verify that consuming an OTP marks used=True and never deletes the row from the database."""
    ts = int(datetime.now().timestamp())
    email = f"persist_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        user = User(
            account_type="passenger",
            name="Persist User",
            email=email,
            phone=f"94{ts % 100000000:08d}",
            password_hash=hash_password("Pass@123"),
            bank_account_number="987654321098",
            status="active",
        )
        db.add(user)
        db.commit()

        wallet = get_or_create_wallet(user.id, db)
        wallet.balance = Decimal("1000.00")
        db.commit()

        # Seed an OTP for withdrawal
        w_otp = EmailOTP(
            email=email,
            otp="654321",
            reason="withdraw_balance",
            purpose="withdraw_balance",
            attempts=0,
            is_verified=False,
            used=False,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(w_otp)
        db.commit()
        otp_id = w_otp.id

        initial_count = db.query(EmailOTP).count()

        # Execute withdrawal
        with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
            res = withdraw_to_bank(WithdrawRequest(user_id=user.id, amount=100.0, otp="654321"), db=db)
            assert res.get("success") is True

        # Row MUST still exist in database with used=True and is_verified=True
        consumed_otp = db.get(EmailOTP, otp_id)
        assert consumed_otp is not None, "CRITICAL: OTP row was physically deleted on consumption!"
        assert consumed_otp.used is True, "OTP row must be marked used=True"
        assert consumed_otp.is_verified is True
        assert db.query(EmailOTP).count() >= initial_count


def test_strict_cross_purpose_rejection():
    """Verify that an OTP created for one reason CANNOT be verified or consumed for another reason."""
    ts = int(datetime.now().timestamp())
    email = f"crossp_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        # Create an account creation OTP
        acc_otp = EmailOTP(
            email=email,
            otp="112233",
            reason="create_account",
            purpose="create_account",
            attempts=0,
            is_verified=False,
            used=False,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(acc_otp)
        db.commit()

        # 1. Attempt to verify create_account OTP as forgot_password -> MUST FAIL
        try:
            asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp="112233", reason="forgot_password"), db=db))
            pytest.fail("Cross-purpose OTP was accepted for forgot_password!")
        except HTTPException as e:
            assert e.status_code == 400

        # 2. Attempt to verify create_account OTP as withdraw_balance -> MUST FAIL
        try:
            asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp="112233", reason="withdraw_balance"), db=db))
            pytest.fail("Cross-purpose OTP was accepted for withdraw_balance!")
        except HTTPException as e:
            assert e.status_code == 400

        # 3. Attempt to verify create_account OTP as wallet_topup -> MUST FAIL
        try:
            asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp="112233", reason="wallet_topup"), db=db))
            pytest.fail("Cross-purpose OTP was accepted for wallet_topup!")
        except HTTPException as e:
            assert e.status_code == 400

        # 4. Verify with correct reason succeeds
        v_res = asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp="112233", reason="create_account"), db=db))
        assert v_res.get("success") is True


def test_single_use_behavior():
    """Verify that once an OTP is used (used=True), it cannot be re-verified or consumed a second time."""
    ts = int(datetime.now().timestamp())
    email = f"single_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        user = User(
            account_type="passenger",
            name="Single Use User",
            email=email,
            phone=f"93{ts % 100000000:08d}",
            password_hash=hash_password("Pass@123"),
            status="active",
        )
        db.add(user)
        db.commit()

        otp_row = EmailOTP(
            email=email,
            otp="991122",
            reason="forgot_password",
            purpose="forgot_password",
            attempts=0,
            is_verified=False,
            used=False,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(otp_row)
        db.commit()

        # First consumption succeeds
        res1 = asyncio.run(reset_password(ResetPasswordRequest(email=email, otp="991122", new_password="NewPass@123"), db=db))
        assert res1.get("success") is True

        db.refresh(otp_row)
        assert otp_row.used is True

        # Second attempt with same OTP must fail with 400
        try:
            asyncio.run(reset_password(ResetPasswordRequest(email=email, otp="991122", new_password="AnotherPass@123"), db=db))
            pytest.fail("Single-use OTP was re-consumed!")
        except HTTPException as e:
            assert e.status_code == 400
            assert "No password reset request found" in e.detail or "expired" in e.detail


def test_resend_cooldown_and_invalidation():
    """Verify 60s cooldown, and that a resend after cooldown marks prior active OTP as used=True while persisting both."""
    ts = int(datetime.now().timestamp())
    email = f"resend_{ts}@thetapandgo.in"

    with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
        with SessionLocal() as db:
            # First send
            res1 = asyncio.run(send_otp(SendOTPRequest(email=email, account_type="passenger"), db=db))
            assert res1.get("success") is True

            otp1 = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.used == False).first()
            assert otp1 is not None
            otp1_id = otp1.id
            otp1_code = otp1.otp

            # Immediate second send must raise 429
            try:
                asyncio.run(send_otp(SendOTPRequest(email=email, account_type="passenger"), db=db))
                pytest.fail("Cooldown did not trigger!")
            except HTTPException as e:
                assert e.status_code == 429

            # Simulate 61 seconds elapsed on otp1
            otp1.created_at = datetime.utcnow() - timedelta(seconds=65)
            db.commit()

            # Second send after cooldown succeeds
            res2 = asyncio.run(send_otp(SendOTPRequest(email=email, account_type="passenger"), db=db))
            assert res2.get("success") is True

            # Both rows MUST still exist in database
            db.refresh(otp1)
            assert otp1.used is True, "Prior OTP must be marked used=True upon resend"

            otp2 = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.used == False).first()
            assert otp2 is not None
            assert otp2.id != otp1_id
            assert otp2.used is False

            # First OTP code cannot be verified anymore
            try:
                asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp=otp1_code, reason="create_account"), db=db))
                pytest.fail("Invalidated prior OTP was accepted!")
            except HTTPException as e:
                assert e.status_code == 400

            # Second OTP code verifies successfully
            v_res = asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp=otp2.otp, reason="create_account"), db=db))
            assert v_res.get("success") is True


def test_failed_attempt_lockout_marks_used():
    """Verify 5 failed attempts mark OTP as used=True and locks out further attempts."""
    ts = int(datetime.now().timestamp())
    email = f"lockout_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        otp_row = EmailOTP(
            email=email,
            otp="778899",
            reason="create_account",
            purpose="create_account",
            attempts=0,
            is_verified=False,
            used=False,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(otp_row)
        db.commit()
        otp_id = otp_row.id

        # 4 wrong attempts
        for i in range(1, 5):
            try:
                asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp="000000", reason="create_account"), db=db))
            except HTTPException as e:
                assert e.status_code == 400
                assert f"{5 - i} attempts remaining" in e.detail

        db.refresh(otp_row)
        assert otp_row.attempts == 4
        assert otp_row.used is False

        # 5th wrong attempt triggers lockout
        try:
            asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp="000000", reason="create_account"), db=db))
            pytest.fail("5th failed attempt did not lockout!")
        except HTTPException as e:
            assert e.status_code == 400
            assert "Too many incorrect attempts" in e.detail

        # Row MUST still exist and be marked used=True
        persisted = db.get(EmailOTP, otp_id)
        assert persisted is not None, "Row must not be deleted on lockout"
        assert persisted.used is True
        assert persisted.attempts >= 5


def test_otp_expiry_marks_used():
    """Verify that verifying an expired OTP marks it used=True and rejects with 400."""
    ts = int(datetime.now().timestamp())
    email = f"expiry_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        expired_otp = EmailOTP(
            email=email,
            otp="123987",
            reason="create_account",
            purpose="create_account",
            attempts=0,
            is_verified=False,
            used=False,
            expires_at=datetime.utcnow() - timedelta(minutes=2),
        )
        db.add(expired_otp)
        db.commit()
        otp_id = expired_otp.id

        try:
            asyncio.run(verify_otp(VerifyOTPRequest(email=email, otp="123987", reason="create_account"), db=db))
            pytest.fail("Expired OTP was verified!")
        except HTTPException as e:
            assert e.status_code == 400
            assert "expired" in e.detail.lower()

        # Row MUST still exist and be marked used=True
        persisted = db.get(EmailOTP, otp_id)
        assert persisted is not None, "Expired OTP row must not be deleted"
        assert persisted.used is True


def test_ses_failure_keeps_otp_persisted():
    """Verify that when SES delivery fails, the OTP record remains persisted in the database."""
    ts = int(datetime.now().timestamp())
    email = f"sesfail_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        user = User(
            account_type="passenger",
            name="SES Fail User",
            email=email,
            phone=f"92{ts % 100000000:08d}",
            password_hash=hash_password("Pass@123"),
            bank_account_number="111222333444",
            status="active",
        )
        db.add(user)
        db.commit()

        # Simulate SES failure
        with patch("app.utils.email_service._send_ses_email", return_value=(False, "SES Mock Service Down")):
            # 1. send_otp failure
            try:
                asyncio.run(send_otp(SendOTPRequest(email=f"failreg_{ts}@thetapandgo.in", account_type="passenger"), db=db))
                pytest.fail("send_otp should fail on SES failure")
            except HTTPException as e:
                assert e.status_code == 500

            reg_row = db.query(EmailOTP).filter(EmailOTP.email == f"failreg_{ts}@thetapandgo.in").first()
            assert reg_row is not None, "CRITICAL: Registration OTP was deleted on SES failure!"
            assert reg_row.reason == "create_account"

            # 2. forgot_password_otp failure
            try:
                asyncio.run(forgot_password_otp(ForgotPasswordRequest(account=email), db=db))
                pytest.fail("forgot_password_otp should fail on SES failure")
            except HTTPException as e:
                assert e.status_code == 500

            fp_row = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.reason == "forgot_password").first()
            assert fp_row is not None, "CRITICAL: Forgot password OTP was deleted on SES failure!"

            # 3. request_withdrawal_otp failure
            wallet = get_or_create_wallet(user.id, db)
            wallet.balance = Decimal("500.00")
            db.commit()

            # Advance cooldown
            if fp_row:
                fp_row.created_at = datetime.utcnow() - timedelta(seconds=65)
                db.commit()

            res_w = request_withdrawal_otp(WithdrawOTPRequest(user_id=user.id, amount=50.0), db=db)
            assert res_w.get("email_sent") is False
            w_row = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.reason == "withdraw_balance").first()
            assert w_row is not None, "CRITICAL: Withdrawal OTP was deleted on SES failure!"


def test_topup_otp_metadata_and_persistence():
    """Verify wallet_topup OTP stores amount in metadata, enforces amount matching, marks used=True, and persists."""
    ts = int(datetime.now().timestamp())
    email = f"topup_{ts}@thetapandgo.in"

    with SessionLocal() as db:
        user = User(
            account_type="passenger",
            name="Topup User",
            email=email,
            phone=f"91{ts % 100000000:08d}",
            password_hash=hash_password("Pass@123"),
            status="active",
        )
        db.add(user)
        db.commit()

        wallet = get_or_create_wallet(user.id, db)

        with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
            res = request_topup_otp(TopupOTPRequest(amount=500.0), current_user=user, db=db)
            assert res.get("success") is True

        topup_otp = db.query(EmailOTP).filter(EmailOTP.email == email, EmailOTP.reason == "wallet_topup", EmailOTP.used == False).first()
        assert topup_otp is not None
        assert topup_otp.reason == "wallet_topup"
        assert topup_otp.purpose == "wallet_topup"
        assert "500.0" in (topup_otp.otp_metadata or "")
        topup_id = topup_otp.id
        otp_code = topup_otp.otp

        # Amount mismatch should fail
        try:
            create_razorpay_order(CreateOrderRequest(amount=750.0, otp=otp_code), current_user=user, db=db)
            pytest.fail("Order created with mismatched amount!")
        except HTTPException as e:
            assert e.status_code == 400
            assert "different amount" in e.detail

        # Correct amount with mocked Razorpay creation
        mock_order = {
            "order_id": "order_mock_123",
            "amount": 50000,
            "currency": "INR",
            "key_id": "rzp_test_123",
            "is_mock": True,
        }
        with patch("app.services.payment.razorpay_service.razorpay_service.create_order", return_value=mock_order):
            order_res = create_razorpay_order(CreateOrderRequest(amount=500.0, otp=otp_code), current_user=user, db=db)
            assert order_res.get("success") is True
            assert order_res.get("order_id") == "order_mock_123"

        # Row MUST still exist and be marked used=True
        consumed_row = db.get(EmailOTP, topup_id)
        assert consumed_row is not None, "Top-up OTP row was physically deleted!"
        assert consumed_row.used is True
        assert consumed_row.is_verified is True


def test_ses_sender_remains_production_gmail():
    """Requirement 16: Verify production SES sender remains tapandgosupport@gmail.com and does not invent unverified Reply-To."""
    from app.config import settings

    # Config verification
    assert "tapandgosupport@gmail.com" in settings.SES_FROM_EMAIL
    assert settings.SES_SENDER_EMAIL == "tapandgosupport@gmail.com"

    mock_ses = MagicMock()
    mock_ses.send_email.return_value = {"MessageId": "mock-ses-headers-123"}

    # Case 1: Default call without configured reply-to -> Source is tapandgosupport@gmail.com, ReplyToAddresses is None
    with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
        success, err = _send_ses_email(
            to_email="headers.test@thetapandgo.in",
            subject="Header Verification",
            html_content="<h1>Hello</h1><p>Test Content</p>",
            text_content="Hello\n\nTest Content",
        )
        assert success is True
        mock_ses.send_email.assert_called_once()
        kwargs = mock_ses.send_email.call_args[1]
        assert kwargs.get("Source") == "Tap & Go <tapandgosupport@gmail.com>"
        assert kwargs.get("ReplyToAddresses") is None
        assert kwargs["Message"]["Body"]["Text"]["Data"] == "Hello\n\nTest Content"

    # Case 2: When SES_REPLY_TO_EMAIL is intentionally configured in settings
    mock_ses.reset_mock()
    with patch.object(settings.__class__, "SES_REPLY_TO_EMAIL", "custom-reply@thetapandgo.in"):
        with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
            success, err = _send_ses_email(
                to_email="headers.test@thetapandgo.in",
                subject="Header Verification With Reply-To",
                html_content="<h1>Hello</h1><p>Test Content</p>",
                text_content="Hello\n\nTest Content",
            )
            assert success is True
            kwargs = mock_ses.send_email.call_args[1]
            assert kwargs.get("ReplyToAddresses") == ["custom-reply@thetapandgo.in"]


def test_plain_text_otp_formatting():
    """Requirement 17: Verify plain-text OTP formatting has clean 6-digit code, no fragmentation, and support email."""
    # Test registration OTP
    with patch("app.utils.email_service.send_email") as mock_send:
        mock_send.return_value = True
        send_registration_otp("passenger@thetapandgo.in", "482019", "passenger")
        mock_send.assert_called_once()
        text = mock_send.call_args[1]["text_content"]
        assert "482019" in text
        assert "4\n8\n2\n0\n1\n9" not in text
        assert "Support: tapandgosupport@gmail.com" in text
        assert "support@thetapandgo.in" not in text

    # Test password reset OTP
    with patch("app.utils.email_service.send_email") as mock_send:
        mock_send.return_value = True
        send_password_reset_otp("passenger@thetapandgo.in", "739104")
        mock_send.assert_called_once()
        text = mock_send.call_args[1]["text_content"]
        assert "739104" in text
        assert "Support: tapandgosupport@gmail.com" in text
        assert "support@thetapandgo.in" not in text

    # Test withdrawal OTP
    with patch("app.utils.email_service.send_email") as mock_send:
        mock_send.return_value = True
        send_withdrawal_otp("passenger@thetapandgo.in", "102938", 500.0)
        mock_send.assert_called_once()
        text = mock_send.call_args[1]["text_content"]
        assert "102938" in text
        assert "₹500.00" in text
        assert "Support: tapandgosupport@gmail.com" in text
        assert "support@thetapandgo.in" not in text

    # Test topup OTP
    with patch("app.utils.email_service.send_email") as mock_send:
        mock_send.return_value = True
        send_topup_otp("passenger@thetapandgo.in", "847291", 250.0)
        mock_send.assert_called_once()
        text = mock_send.call_args[1]["text_content"]
        assert "847291" in text
        assert "₹250.00" in text
        assert "Support: tapandgosupport@gmail.com" in text
        assert "support@thetapandgo.in" not in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

