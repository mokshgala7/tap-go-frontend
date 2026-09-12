import os
import sys
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError, BotoCoreError

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
                EmailOTP.purpose == "registration",
            ).first()
            assert otp_row is not None
            assert len(otp_row.otp) == 6 and otp_row.otp.isdigit(), f"Invalid OTP format: {otp_row.otp}"
            assert otp_row.purpose == "registration"
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
            v_req = VerifyOTPRequest(email=test_reg_email, otp="000000", purpose="registration")
            try:
                asyncio.run(verify_otp(v_req, db=db))
                pytest.fail("Incorrect OTP did not raise 400!")
            except HTTPException as e:
                assert e.status_code == 400
                assert "4 attempts remaining" in e.detail

            db.refresh(otp_row)
            assert otp_row.attempts == 1

            # 2d. 5 incorrect attempts triggers lockout
            otp_row.attempts = 4
            db.commit()
            try:
                asyncio.run(verify_otp(v_req, db=db))
                pytest.fail("Lockout did not trigger!")
            except HTTPException as e:
                assert e.status_code == 400
                assert "Too many incorrect attempts" in e.detail

            # 2e. Re-issue fresh OTP and test valid verification
            fresh_otp = EmailOTP(
                email=test_reg_email,
                otp="849201",
                purpose="registration",
                attempts=0,
                is_verified=False,
                expires_at=datetime.utcnow() + timedelta(minutes=5),
            )
            db.add(fresh_otp)
            db.commit()

            v_req_valid = VerifyOTPRequest(email=test_reg_email, otp="849201", purpose="registration")
            v_res = asyncio.run(verify_otp(v_req_valid, db=db))
            assert v_res.get("success") is True

            db.refresh(fresh_otp)
            assert fresh_otp.is_verified is True


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
                EmailOTP.purpose == "forgot_password",
            ).first()
            assert fp_otp is not None
            assert len(fp_otp.otp) == 6

            # Cross-purpose rejection check: cannot use forgot_password OTP for registration
            try:
                asyncio.run(verify_otp(VerifyOTPRequest(email=test_email, otp=fp_otp.otp, purpose="registration"), db=db))
                pytest.fail("Cross-purpose OTP was accepted!")
            except HTTPException as e:
                assert e.status_code == 400

            # Verify with correct purpose
            v_res = asyncio.run(verify_otp(VerifyOTPRequest(email=test_email, otp=fp_otp.otp, purpose="forgot_password"), db=db))
            assert v_res.get("success") is True

            # Reset password
            r_res = asyncio.run(reset_password(ResetPasswordRequest(
                email=test_email,
                otp=fp_otp.otp,
                new_password="NewPassword@2026",
            ), db=db))
            assert r_res.get("success") is True

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
    """Verify that if AWS credentials are absent in local dev, send_email falls back to local dev SMTP."""
    with patch.object(settings.__class__, "IS_PRODUCTION", False):
        with patch.object(settings.__class__, "AWS_ACCESS_KEY_ID", ""):
            with patch.object(settings.__class__, "AWS_SECRET_ACCESS_KEY", ""):
                with patch("app.utils.email_service._send_smtp_email", return_value=(True, None)) as mock_smtp:
                    res = send_email(
                        to_email="dev@example.com",
                        subject="Dev Subject",
                        html_content="<p>Dev</p>",
                    )
                    assert res is True
                    mock_smtp.assert_called_once()


def test_production_no_silent_smtp_fallback():
    """Verify that in production, if AWS credentials are missing, SMTP fallback is NEVER attempted."""
    with patch.object(settings.__class__, "IS_PRODUCTION", True):
        with patch.object(settings.__class__, "AWS_ACCESS_KEY_ID", ""):
            with patch.object(settings.__class__, "AWS_SECRET_ACCESS_KEY", ""):
                with patch("app.utils.email_service._send_smtp_email") as mock_smtp:
                    res = send_email(
                        to_email="prod.test@thetapandgo.in",
                        subject="Production Test",
                        html_content="<p>Test</p>",
                    )
                    assert res is False
                    mock_smtp.assert_not_called()
                    last_err = get_last_email_error()
                    assert "Silent SMTP fallback is disabled in production" in last_err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
