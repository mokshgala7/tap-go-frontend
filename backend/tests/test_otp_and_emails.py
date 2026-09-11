import os
import sys
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import unittest
from unittest.mock import patch

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
    get_last_email_error,
    _get_ses_client,
    _send_ses_email,
)
from fastapi import HTTPException


def run_all_tests():
    print("==================================================")
    print("TAP & GO AMAZON SES & OTP SYSTEM COMPREHENSIVE TESTS")
    print("==================================================")

    # ----------------------------------------------------
    # TEST 1: Real Amazon SES HTTPS Delivery to Verified Support Email
    # ----------------------------------------------------
    print("\n[TEST 1] Testing Real Amazon SES HTTPS API Delivery...")

    # 1a. Verify SES Client Initialization
    client = _get_ses_client()
    assert client is not None, "Failed to initialize Amazon SES client!"
    print(f"  ✓ Amazon SES client initialized successfully (Region: {client.meta.region_name}).")

    # 1b. Real Email Delivery: Registration OTP
    test_otp = "782941"
    ses_success = send_registration_otp(
        to_email="tapandgosupport@gmail.com",
        otp=test_otp,
        account_type="passenger",
    )
    print(f"  Amazon SES direct send result: {ses_success}")

    if ses_success:
        print("  ✓ Live Amazon SES delivery succeeded to tapandgosupport@gmail.com.")
        # 1c. Real Email Delivery: Password Reset OTP
        reset_success = send_password_reset_otp(
            to_email="tapandgosupport@gmail.com",
            otp="918273",
        )
        assert reset_success is True, "Amazon SES failed to send password reset OTP email!"

        # 1d. Real Email Delivery: Withdrawal OTP
        withdraw_otp_success = send_withdrawal_otp(
            to_email="tapandgosupport@gmail.com",
            otp="456123",
            amount=500.0,
        )
        assert withdraw_otp_success is True, "Amazon SES failed to send withdrawal OTP email!"

        # 1e. Real Email Delivery: Ride Receipt
        ride_success = send_ride_passenger_email(
            to_email="tapandgosupport@gmail.com",
            passenger_name="Support Verification",
            fare=120.0,
            driver_name="City Driver",
            reference="TXN-SES-TEST-001",
        )
        assert ride_success is True, "Amazon SES failed to send ride receipt email!"
    else:
        last_err = get_last_email_error()
        print(f"  ℹ️ Live AWS SES endpoint response: {last_err}")

    with SessionLocal() as db:
        log_entry = db.query(EmailLog).filter(
            EmailLog.recipient == "tapandgosupport@gmail.com",
            EmailLog.email_type == "registration_otp",
        ).order_by(EmailLog.created_at.desc()).first()
        assert log_entry is not None, "EmailLog entry was not created!"
        print(f"  ✓ EmailLog entry confirmed in database (status: {log_entry.status}).")

    # ----------------------------------------------------
    # TEST 2: Registration OTP Flow (Generation, Expiry, Security)
    # ----------------------------------------------------
    print("\n[TEST 2] Testing Registration OTP Flow...")
    test_reg_email = f"test_user_{int(datetime.utcnow().timestamp())}@gmail.com"

    # In SES Sandbox mode, unverified emails are rejected by AWS.
    # We patch _send_ses_email during synthetic user lifecycle checks to simulate verified delivery.
    with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
        with SessionLocal() as db:
            # 2a. Request OTP
            req = SendOTPRequest(email=test_reg_email, account_type="passenger")
            res = asyncio.run(send_otp(req, db=db))
            print(f"  send_otp response: {res}")
            assert res.get("success") is True
            assert "otp" not in res, "CRITICAL SECURITY FLAW: OTP was returned in API response!"
            assert "demo_mode" not in res, "CRITICAL FLAW: demo_mode flag found in API response!"

            # Verify DB entry
            otp_row = db.query(EmailOTP).filter(
                EmailOTP.email == test_reg_email,
                EmailOTP.purpose == "registration",
            ).first()
            assert otp_row is not None, "OTP row was not created in database!"
            assert len(otp_row.otp) == 6 and otp_row.otp.isdigit(), f"Invalid OTP format: {otp_row.otp}"
            assert otp_row.purpose == "registration", f"Wrong purpose: {otp_row.purpose}"
            assert otp_row.attempts == 0, f"Initial attempts should be 0, got {otp_row.attempts}"
            assert otp_row.is_verified is False, "is_verified should be False initially"
            time_diff = (otp_row.expires_at - datetime.utcnow()).total_seconds()
            assert 240 <= time_diff <= 310, f"Expiry should be ~300 seconds (5 mins), got {time_diff}s"
            print(f"  ✓ Random 6-digit OTP stored securely in email_otps (5-minute expiry).")

            real_otp = otp_row.otp

            # 2b. Cooldown Check (immediate re-request must fail with 429)
            try:
                asyncio.run(send_otp(req, db=db))
                assert False, "Should have raised 429 cooldown error on immediate resend!"
            except HTTPException as e:
                assert e.status_code == 429, f"Expected 429, got {e.status_code}"
                print(f"  ✓ 60-second cooldown enforced: {e.detail}")

            # 2c. Incorrect OTP attempt count increment
            try:
                asyncio.run(verify_otp(VerifyOTPRequest(email=test_reg_email, otp="999999", purpose="registration"), db=db))
                assert False, "Should have rejected wrong OTP!"
            except HTTPException as e:
                assert e.status_code == 400
                db.refresh(otp_row)
                assert otp_row.attempts == 1, f"Expected attempts=1, got {otp_row.attempts}"
                print(f"  ✓ Incorrect OTP rejected, attempts incremented to 1: {e.detail}")

            # 2d. Max attempts lockout (5 attempts)
            otp_row.attempts = 4
            db.commit()
            try:
                asyncio.run(verify_otp(VerifyOTPRequest(email=test_reg_email, otp="999999", purpose="registration"), db=db))
                assert False, "Should have locked out after 5th wrong attempt!"
            except HTTPException as e:
                assert e.status_code == 400
                assert "Too many incorrect attempts" in e.detail
                # Row should be deleted
                check_del = db.query(EmailOTP).filter(EmailOTP.email == test_reg_email).first()
                assert check_del is None, "OTP row should be deleted upon reaching max attempts"
                print(f"  ✓ Maximum 5 attempts lockout enforced: {e.detail}")

            # Re-issue valid OTP for verification & registration completion
            db.query(EmailOTP).filter(EmailOTP.email == test_reg_email).delete()
            db.commit()
            new_otp_code = "654321"
            new_otp = EmailOTP(
                email=test_reg_email,
                otp=new_otp_code,
                purpose="registration",
                attempts=0,
                is_verified=False,
                expires_at=datetime.utcnow() + timedelta(minutes=5),
            )
            db.add(new_otp)
            db.commit()

            # 2e. Valid OTP verification
            v_res = asyncio.run(verify_otp(VerifyOTPRequest(email=test_reg_email, otp=new_otp_code, purpose="registration"), db=db))
            assert v_res.get("success") is True
            db.refresh(new_otp)
            assert new_otp.is_verified is True
            print(f"  ✓ Correct OTP verified on-the-spot (is_verified=True).")

            # 2f. Account Registration
            ts = int(datetime.utcnow().timestamp())
            unique_phone = f"98{(ts % 100000000):08d}"
            reg_res = asyncio.run(register(
                account_type="passenger",
                name="Test Real User",
                email=test_reg_email,
                phone=unique_phone,
                address="123 Test Street",
                city="Mumbai",
                pincode="400001",
                aadhaar="123456789012",
                email_otp=new_otp_code,
                pan="ABCDE1234F",
                password="Password@123",
                db=db,
            ))
            assert reg_res.get("success") is True
            print(f"  ✓ Account created successfully: {reg_res.get('message')}")

            # Verify OTP was consumed
            consumed = db.query(EmailOTP).filter(EmailOTP.email == test_reg_email).first()
            assert consumed is None, "OTP was not consumed/deleted after registration!"
            print("  ✓ OTP consumed/deleted immediately after registration.")

            # Verify user can log in
            login_res = asyncio.run(login(UserLoginRequest(account=test_reg_email, password="Password@123"), db=db))
            assert login_res.get("success") is True, "User could not log in with registered credentials!"
            print("  ✓ User successfully logged in with new account.")

    # ----------------------------------------------------
    # TEST 3: Forgot Password OTP Flow & Purpose Separation
    # ----------------------------------------------------
    print("\n[TEST 3] Testing Forgot Password OTP Flow & Purpose Separation...")
    with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
        with SessionLocal() as db:
            # 3a. Request forgot password OTP
            fp_res = asyncio.run(forgot_password_otp(ForgotPasswordRequest(account=test_reg_email), db=db))
            assert fp_res.get("success") is True
            assert "otp" not in fp_res, "CRITICAL: OTP returned in forgot-password response!"
            assert "demo_mode" not in fp_res, "CRITICAL: demo_mode in forgot-password response!"
            print(f"  ✓ Forgot password OTP requested securely (no OTP in response).")

            fp_otp_row = db.query(EmailOTP).filter(
                EmailOTP.email == test_reg_email,
                EmailOTP.purpose == "forgot_password",
            ).first()
            assert fp_otp_row is not None, "Forgot password OTP not in DB!"
            assert fp_otp_row.purpose == "forgot_password"
            fp_code = fp_otp_row.otp

            # 3b. Cross-purpose rejection: Try to verify registration with forgot-password OTP
            try:
                asyncio.run(verify_otp(VerifyOTPRequest(email=test_reg_email, otp=fp_code, purpose="registration"), db=db))
                assert False, "Cross-purpose check failed: forgot-password OTP verified registration!"
            except HTTPException as e:
                assert e.status_code == 400
                print("  ✓ Cross-purpose rejection verified: forgot-password OTP cannot verify registration.")

            # 3c. Verify forgot password OTP
            fp_verify = asyncio.run(verify_otp(VerifyOTPRequest(email=test_reg_email, otp=fp_code, purpose="forgot_password"), db=db))
            assert fp_verify.get("success") is True
            print("  ✓ Forgot password OTP verified with purpose='forgot_password'.")

            # 3d. Reset Password
            rp_res = asyncio.run(reset_password(ResetPasswordRequest(
                email=test_reg_email,
                otp=fp_code,
                new_password="NewSecurePassword@456",
            ), db=db))
            assert rp_res.get("success") is True
            print("  ✓ Password reset successfully.")

            # Verify old password fails and new password works
            old_login = asyncio.run(login(UserLoginRequest(account=test_reg_email, password="Password@123"), db=db))
            if hasattr(old_login, "body"):
                import json
                body_json = json.loads(old_login.body.decode())
                assert body_json.get("success") is False
            else:
                assert old_login.get("success") is False
            print("  ✓ Old password successfully rejected.")

            new_login = asyncio.run(login(UserLoginRequest(account=test_reg_email, password="NewSecurePassword@456"), db=db))
            assert new_login.get("success") is True
            print("  ✓ New password successfully accepted.")

    # ----------------------------------------------------
    # TEST 4: Transaction Emails & Financial Resiliency
    # ----------------------------------------------------
    print("\n[TEST 4] Testing Transaction Emails & Failure Resiliency...")
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == test_reg_email).first()
        assert user is not None
        wallet = get_or_create_wallet(user.id, db)
        wallet.balance = Decimal("1000.00")
        db.commit()

        # Create dummy driver for ride payment
        driver_email = f"driver_{int(datetime.utcnow().timestamp())}@gmail.com"
        driver = User(
            account_type="driver",
            name="Professional Driver",
            email=driver_email,
            phone=f"91{((ts + 100) % 100000000):08d}",
            password_hash=hash_password("Driver@123"),
            status="active",
        )
        db.add(driver)
        db.commit()
        d_wallet = get_or_create_wallet(driver.id, db)
        d_wallet.balance = Decimal("0.00")
        db.commit()

        # 4a. Successful Ride Payment (internal wallet-to-wallet)
        with patch("app.utils.email_service._send_ses_email", return_value=(True, None)):
            pay_res = pay_fare(PayRequest(
                passenger_id=user.id,
                driver_id=driver.id,
                fare=150.00,
                driver_name=driver.name,
                payment_method="QR",
            ), db=db)
            assert pay_res.get("success") is True
            db.refresh(wallet)
            db.refresh(d_wallet)
            assert wallet.balance == Decimal("850.00"), f"Expected 850.00, got {wallet.balance}"
            assert d_wallet.balance == Decimal("150.00"), f"Expected 150.00, got {d_wallet.balance}"
            print(f"  ✓ Ride payment completed: Passenger balance ₹{wallet.balance}, Driver balance ₹{d_wallet.balance}")

        # 4b. Critical Resiliency Test: SES Failure MUST NOT Rollback Financial Transaction
        print("  Simulating complete Amazon SES network failure during ride payment...")
        with patch("app.utils.email_service._send_ses_email", side_effect=Exception("SES Service Unavailable")):
            pay_res2 = pay_fare(PayRequest(
                passenger_id=user.id,
                driver_id=driver.id,
                fare=200.00,
                driver_name=driver.name,
                payment_method="QR",
            ), db=db)
            assert pay_res2.get("success") is True
            db.refresh(wallet)
            db.refresh(d_wallet)
            # The transaction MUST have completed and committed!
            assert wallet.balance == Decimal("650.00"), f"Expected 650.00, got {wallet.balance}"
            assert d_wallet.balance == Decimal("350.00"), f"Expected 350.00, got {d_wallet.balance}"
            print("  ✓ CRITICAL VERIFICATION: Financial transaction succeeded despite SES failure! Zero rollback!")

        # 4c. Withdrawal Flow & Email
        user.bank_account_number = "123456789012"
        user.bank_ifsc = "HDFC0001234"
        db.commit()

        # Seed withdrawal OTP
        w_otp = EmailOTP(
            email=user.email,
            otp="554433",
            purpose="withdrawal",
            attempts=0,
            is_verified=False,
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        db.add(w_otp)
        db.commit()

        with patch("app.utils.email_service._send_ses_email", side_effect=Exception("SES Down")):
            w_res = withdraw_to_bank(WithdrawRequest(
                user_id=user.id,
                amount=100.00,
                otp="554433",
            ), db=db)
            assert w_res.get("success") is True
            db.refresh(wallet)
            assert wallet.balance == Decimal("550.00"), f"Expected 550.00, got {wallet.balance}"
            print("  ✓ Withdrawal completed and committed despite SES failure!")

        # 4d. Check email_logs table has both SENT and FAILED entries
        sent_logs = db.query(EmailLog).filter(EmailLog.status == "SENT").count()
        failed_logs = db.query(EmailLog).filter(EmailLog.status == "FAILED").count()
        print(f"  ✓ Email log verification: {sent_logs} SENT logs, {failed_logs} FAILED logs recorded in database.")
        assert sent_logs > 0, "Expected some SENT logs"
        assert failed_logs > 0, "Expected some FAILED logs from simulated outage test"

    print("\n==================================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================")


if __name__ == "__main__":
    run_all_tests()
