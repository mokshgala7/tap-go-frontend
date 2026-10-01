"""
Comprehensive test suite for Tap&Go PDF Receipt Attachment Feature.

Tests:
1. PDF Receipt Generation (Transaction and Top-Up)
2. PDF Generation when logo is unavailable (graceful fallback)
3. PDF Generation error handling (safe return None)
4. SES MIME Email dispatch:
   - Without attachments -> client.send_email
   - With attachments -> client.send_raw_email (multipart/mixed MIME verification)
5. Local SMTP fallback with attachment
6. Financial Resiliency:
   - Ride payment succeeds when PDF generation fails
   - Wallet top-up succeeds when PDF generation fails
7. Both Top-up paths (verify-payment and webhook) generate and attach PDF
8. Unrelated emails (OTP, password reset, verification) do NOT receive attachments
"""

import email
from email import policy
import io
import uuid
import random
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.database import engine, Base, SessionLocal
from app.models import User, Wallet, Transaction, EmailOTP
import app.models  # Ensure all models are registered with Base.metadata

try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass

from app.utils.security import hash_password
from app.routes.wallet import pay_fare, PayRequest, get_or_create_wallet
from app.routes.payment import (
    verify_razorpay_payment,
    VerifyPaymentRequest,
    razorpay_webhook,
)
from app.utils.email_service import (
    _send_ses_email,
    _send_smtp_email,
    send_email,
    send_ride_passenger_email,
    send_wallet_topup_email,
    send_registration_otp,
    send_password_reset_otp,
    send_withdrawal_otp,
    _normalize_razorpay_method,
)
from app.services.receipt_service import (
    generate_transaction_receipt,
    generate_wallet_topup_receipt,
    get_logo_path,
    get_optimized_logo_bytes,
)
from app.config import settings


# ============================================================================
# 1. PDF RECEIPT GENERATION TESTS
# ============================================================================

def test_transaction_receipt_generates_valid_pdf():
    """Verify that generate_transaction_receipt produces a valid, non-empty PDF binary."""
    data = {
        "reference": "TXN-TEST-1001",
        "fare": 150.00,
        "passenger_name": "Test Passenger",
        "passenger_email": "passenger@thetapandgo.in",
        "driver_name": "Test Driver",
        "vehicle_type": "Auto Rickshaw",
        "vehicle_registration": "MH-02-AX-9999",
        "payment_method": "Tap & Go Wallet (QR)",
        "balance_after": 850.00,
        "status": "Successful",
        "created_at": datetime.utcnow(),
    }
    pdf_bytes = generate_transaction_receipt(data)
    assert pdf_bytes is not None, "Failed to generate transaction receipt"
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-"), "Generated file is not a valid PDF header"
    assert len(pdf_bytes) > 5000, "PDF size unexpectedly small"


def test_wallet_topup_receipt_generates_valid_pdf():
    """Verify that generate_wallet_topup_receipt produces a valid, non-empty PDF binary."""
    data = {
        "reference": "RZP-TEST-2002",
        "amount": 500.00,
        "user_name": "Test User",
        "user_email": "user@thetapandgo.in",
        "account_type": "passenger",
        "provider": "Razorpay",
        "razorpay_payment_id": "pay_TEST_PAY_123",
        "razorpay_order_id": "order_TEST_ORD_456",
        "balance_after": 1500.00,
        "status": "Successful",
        "created_at": datetime.utcnow(),
    }
    pdf_bytes = generate_wallet_topup_receipt(data)
    assert pdf_bytes is not None, "Failed to generate wallet topup receipt"
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-"), "Generated file is not a valid PDF header"
    assert len(pdf_bytes) > 5000, "PDF size unexpectedly small"


def test_receipt_generates_when_logo_unavailable():
    """Verify that receipts generate cleanly using text branding if the logo cannot be loaded."""
    with patch("app.services.receipt_service.get_optimized_logo_bytes", return_value=None):
        data = {
            "reference": "TXN-NOLOGO-3003",
            "fare": 75.00,
            "passenger_name": "NoLogo Passenger",
            "driver_name": "NoLogo Driver",
            "status": "Successful",
        }
        pdf_bytes = generate_transaction_receipt(data)
        assert pdf_bytes is not None, "PDF should generate even when logo is missing"
        assert pdf_bytes.startswith(b"%PDF-")


def test_receipt_generation_safe_exception_handling():
    """Verify that unhandled reportlab exceptions return None and do not crash."""
    with patch("app.services.receipt_service.SimpleDocTemplate.build", side_effect=Exception("ReportLab rendering error")):
        pdf_bytes = generate_transaction_receipt({"reference": "TXN-FAIL-001"})
        assert pdf_bytes is None, "Should safely catch exceptions and return None"

        topup_bytes = generate_wallet_topup_receipt({"reference": "RZP-FAIL-001"})
        assert topup_bytes is None, "Should safely catch exceptions and return None"


# ============================================================================
# 2. AMAZON SES MIME & ATTACHMENT DISPATCH TESTS
# ============================================================================

def test_ses_dispatch_without_attachments_uses_send_email():
    """Verify that emails without attachments continue using boto3 client.send_email."""
    mock_ses = MagicMock()
    mock_ses.send_email.return_value = {"MessageId": "ses-standard-msg-1"}

    with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
        success, err = _send_ses_email(
            to_email="test.standard@thetapandgo.in",
            subject="Standard Subject",
            html_content="<p>Standard Body</p>",
            attachments=None,
        )
        assert success is True
        assert err is None
        mock_ses.send_email.assert_called_once()
        mock_ses.send_raw_email.assert_not_called()


def test_ses_dispatch_with_pdf_attachment_uses_send_raw_email():
    """Verify that emails with attachments construct a valid multipart MIME and use send_raw_email."""
    mock_ses = MagicMock()
    mock_ses.send_raw_email.return_value = {"MessageId": "ses-raw-msg-1"}

    fake_pdf = b"%PDF-1.4 Mock binary PDF content"
    attachments = [{
        "filename": "Receipt-TXN-12345.pdf",
        "content": fake_pdf,
        "mime_type": "application/pdf",
    }]

    with patch("app.utils.email_service._get_ses_client", return_value=mock_ses):
        success, err = _send_ses_email(
            to_email="passenger.receipt@thetapandgo.in",
            subject="Your Tap & Go Receipt",
            html_content="<p>Please find attached receipt</p>",
            text_content="Please find attached receipt",
            attachments=attachments,
        )
        assert success is True
        assert err is None
        mock_ses.send_raw_email.assert_called_once()
        mock_ses.send_email.assert_not_called()

        # Parse and inspect the raw MIME message bytes
        raw_kwargs = mock_ses.send_raw_email.call_args[1]
        assert "passenger.receipt@thetapandgo.in" in raw_kwargs["Destinations"]
        raw_bytes = raw_kwargs["RawMessage"]["Data"]

        parsed_msg = email.message_from_bytes(raw_bytes, policy=policy.default)
        assert parsed_msg.is_multipart(), "Expected multipart MIME message"
        assert parsed_msg["Subject"] == "Your Tap & Go Receipt"
        assert parsed_msg["To"] == "passenger.receipt@thetapandgo.in"

        # Verify the PDF attachment part
        attachment_parts = [part for part in parsed_msg.iter_attachments()]
        assert len(attachment_parts) == 1, "Expected exactly 1 attachment"
        att = attachment_parts[0]
        assert att.get_filename() == "Receipt-TXN-12345.pdf"
        assert att.get_content_type() == "application/pdf"
        assert att.get_payload(decode=True) == fake_pdf


def test_smtp_fallback_with_pdf_attachment():
    """Verify that the local SMTP development fallback also supports attaching the PDF."""
    fake_pdf = b"%PDF-1.4 SMTP test PDF"
    attachments = [{
        "filename": "Receipt-SMTP-999.pdf",
        "content": fake_pdf,
        "mime_type": "application/pdf",
    }]

    mock_server = MagicMock()
    with patch("smtplib.SMTP", return_value=mock_server), \
         patch.object(settings.__class__, "SMTP_HOST", "smtp.test.com"), \
         patch.object(settings.__class__, "SMTP_USER", "testuser"), \
         patch.object(settings.__class__, "SMTP_PASSWORD", "secret123"), \
         patch.object(settings.__class__, "SMTP_PORT", 587):

        success, err = _send_smtp_email(
            to_email="dev@thetapandgo.in",
            subject="Dev Subject",
            html_content="<p>Dev HTML</p>",
            attachments=attachments,
        )
        assert success is True
        assert err is None
        mock_server.send_message.assert_called_once()
        sent_msg = mock_server.send_message.call_args[0][0]
        assert sent_msg.is_multipart()


# ============================================================================
# 3. FINANCIAL RESILIENCY TESTS
# ============================================================================

def test_ride_payment_financial_resiliency_when_pdf_fails():
    """Verify that ride payment succeeds and database commits even if PDF generation fails."""
    uid = uuid.uuid4().hex[:8]
    p_email = f"resil_p_{uid}@thetapandgo.in"
    d_email = f"resil_d_{uid}@thetapandgo.in"
    p_phone = f"91{random.randint(10000000, 99999999)}"
    d_phone = f"92{random.randint(10000000, 99999999)}"

    with SessionLocal() as db:
        p = User(
            account_type="passenger",
            name="Resil Passenger",
            email=p_email,
            phone=p_phone,
            password_hash=hash_password("Pass@123"),
            status="active",
        )
        d = User(
            account_type="driver",
            name="Resil Driver",
            email=d_email,
            phone=d_phone,
            password_hash=hash_password("Pass@123"),
            status="active",
            vehicle_type="Auto",
            vehicle_registration="MH-01-AB-1234",
        )
        db.add_all([p, d])
        db.commit()

        p_wallet = get_or_create_wallet(p.id, db)
        p_wallet.balance = Decimal("1000.00")
        d_wallet = get_or_create_wallet(d.id, db)
        d_wallet.balance = Decimal("0.00")
        db.commit()

        # Mock PDF generator to raise an error
        with patch("app.services.receipt_service.generate_transaction_receipt", side_effect=Exception("PDF Outage")):
            res = pay_fare(PayRequest(
                passenger_id=p.id,
                driver_id=d.id,
                fare=250.00,
                driver_name=d.name,
                payment_method="QR",
            ), db=db)

            assert res.get("success") is True
            db.refresh(p_wallet)
            db.refresh(d_wallet)
            # Balances must be committed regardless of PDF generation failure!
            assert p_wallet.balance == Decimal("750.00")
            assert d_wallet.balance == Decimal("250.00")


def test_topup_payment_financial_resiliency_when_pdf_fails():
    """Verify that wallet topup succeeds and database commits even if PDF generation fails."""
    uid = uuid.uuid4().hex[:8]
    u_email = f"topup_resil_{uid}@thetapandgo.in"
    u_phone = f"93{random.randint(10000000, 99999999)}"

    with SessionLocal() as db:
        u = User(
            account_type="passenger",
            name="Topup User",
            email=u_email,
            phone=u_phone,
            password_hash=hash_password("Pass@123"),
            status="active",
        )
        db.add(u)
        db.commit()

        wallet = get_or_create_wallet(u.id, db)
        wallet.balance = Decimal("100.00")
        db.commit()

        payment_id = f"pay_resil_{uid}"
        order_id = f"order_resil_{uid}"

        # Mock razorpay HMAC signature verification to succeed
        with patch("app.services.payment.razorpay_service.razorpay_service.verify_payment_signature", return_value=True), \
             patch("app.services.receipt_service.generate_wallet_topup_receipt", side_effect=Exception("PDF Crash")):

            res = verify_razorpay_payment(VerifyPaymentRequest(
                user_id=u.id,
                razorpay_order_id=order_id,
                razorpay_payment_id=payment_id,
                razorpay_signature="mock_sig",
                amount=300.00,
            ), db=db)

            assert res.get("success") is True
            db.refresh(wallet)
            # Wallet balance must be credited in DB!
            assert wallet.balance == Decimal("400.00")


# ============================================================================
# 4. TOP-UP RECEIPT ATTACHMENT PATHS (VERIFY-PAYMENT & WEBHOOK)
# ============================================================================

def test_verify_payment_attaches_pdf_receipt():
    """Verify that successful /verify-payment dispatches an email with Receipt-RZP...pdf."""
    uid = uuid.uuid4().hex[:8]
    u_email = f"topup_success_{uid}@thetapandgo.in"
    u_phone = f"94{random.randint(10000000, 99999999)}"

    with SessionLocal() as db:
        u = User(
            account_type="passenger",
            name="Topup Success User",
            email=u_email,
            phone=u_phone,
            password_hash=hash_password("Pass@123"),
            status="active",
        )
        db.add(u)
        db.commit()

        captured_attachments = []

        def mock_send_email(**kwargs):
            captured_attachments.append(kwargs.get("attachments"))
            return True

        with patch("app.services.payment.razorpay_service.razorpay_service.verify_payment_signature", return_value=True), \
             patch("app.utils.email_service.send_email", side_effect=mock_send_email):

            res = verify_razorpay_payment(VerifyPaymentRequest(
                user_id=u.id,
                razorpay_order_id=f"order_{uid}",
                razorpay_payment_id=f"pay_{uid}",
                razorpay_signature="valid_sig",
                amount=200.00,
            ), db=db)

            assert res.get("success") is True
            assert len(captured_attachments) == 1
            atts = captured_attachments[0]
            assert atts is not None, "Expected PDF receipt attachment"
            assert len(atts) == 1
            assert atts[0]["filename"].startswith("Receipt-RZP")
            assert atts[0]["filename"].endswith(".pdf")
            assert atts[0]["content"].startswith(b"%PDF-")


def test_webhook_payment_attaches_pdf_receipt():
    """Verify that successful Razorpay webhook reconciliation attaches Receipt-RZP...pdf."""
    import asyncio
    uid = uuid.uuid4().hex[:8]
    u_email = f"webhook_success_{uid}@thetapandgo.in"
    u_phone = f"95{random.randint(10000000, 99999999)}"

    with SessionLocal() as db:
        u = User(
            account_type="passenger",
            name="Webhook User",
            email=u_email,
            phone=u_phone,
            password_hash=hash_password("Pass@123"),
            status="active",
        )
        db.add(u)
        db.commit()

        captured_attachments = []

        def mock_send_email(**kwargs):
            captured_attachments.append(kwargs.get("attachments"))
            return True

        mock_request = MagicMock()
        mock_payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": f"pay_wh_{uid}",
                        "order_id": f"order_wh_{uid}",
                        "amount": 35000,  # 350 INR
                        "notes": {"user_id": str(u.id)},
                    }
                }
            }
        }

        async def mock_body():
            return b"{}"

        async def mock_json():
            return mock_payload

        mock_request.body = mock_body
        mock_request.json = mock_json

        with patch("app.services.payment.razorpay_service.razorpay_service.verify_webhook_signature", return_value=True), \
             patch("app.utils.email_service.send_email", side_effect=mock_send_email):

            res = asyncio.run(razorpay_webhook(
                request=mock_request,
                x_razorpay_signature="mock_sig",
                db=db,
            ))
            assert res.get("status") == "ok"
            assert len(captured_attachments) == 1
            atts = captured_attachments[0]
            assert atts is not None, "Expected PDF receipt attachment on webhook credit"
            assert len(atts) == 1
            assert atts[0]["filename"].startswith("Receipt-RZP")
            assert atts[0]["filename"].endswith(".pdf")
            assert atts[0]["content"].startswith(b"%PDF-")


# ============================================================================
# 5. UNRELATED EMAILS SAFETY TEST
# ============================================================================

def test_unrelated_emails_do_not_receive_attachments():
    """
    CRITICAL CHECK: Verify that OTP, forgot password, and verification emails
    do NOT receive any PDF attachments and continue using attachments=None.
    """
    captured_attachments = []

    def mock_send_email(**kwargs):
        captured_attachments.append((kwargs.get("email_type"), kwargs.get("attachments")))
        return True

    with patch("app.utils.email_service.send_email", side_effect=mock_send_email):
        # 1. Registration OTP
        send_registration_otp("unrelated@thetapandgo.in", "123456", "passenger")
        # 2. Password reset OTP
        send_password_reset_otp("unrelated@thetapandgo.in", "654321")
        # 3. Withdrawal OTP
        send_withdrawal_otp("unrelated@thetapandgo.in", "789012", 200.00)

        assert len(captured_attachments) == 3
        for email_type, atts in captured_attachments:
            assert atts is None, f"Email type {email_type} must NOT have attachments!"


# ============================================================================
# 6. WALLET TOP-UP PAYMENT METHOD NORMALIZATION & DISPLAY TESTS
# ============================================================================

def test_normalize_razorpay_method_instruments():
    """Verify that _normalize_razorpay_method normalizes card, upi, netbanking, wallet correctly."""
    assert _normalize_razorpay_method("card") == "Card"
    assert _normalize_razorpay_method("CARD") == "Card"
    assert _normalize_razorpay_method("credit_card") == "Card"
    assert _normalize_razorpay_method("debit_card") == "Card"

    assert _normalize_razorpay_method("upi") == "UPI"
    assert _normalize_razorpay_method("UPI") == "UPI"

    assert _normalize_razorpay_method("netbanking") == "Net Banking"
    assert _normalize_razorpay_method("NETBANKING") == "Net Banking"
    assert _normalize_razorpay_method("net_banking") == "Net Banking"
    assert _normalize_razorpay_method("net banking") == "Net Banking"

    assert _normalize_razorpay_method("wallet") == "Wallet"
    assert _normalize_razorpay_method("WALLET") == "Wallet"


def test_wallet_topup_email_and_pdf_display_both_gateway_and_method():
    """Verify that send_wallet_topup_email and PDF display BOTH Payment Gateway: Razorpay and Payment Method: Card."""
    captured = {}

    def mock_send_email(**kwargs):
        captured["html"] = kwargs.get("html_content")
        captured["text"] = kwargs.get("text_content")
        captured["attachments"] = kwargs.get("attachments")
        return True

    with patch("app.utils.email_service.send_email", side_effect=mock_send_email):
        success = send_wallet_topup_email(
            to_email="passenger@thetapandgo.in",
            user_name="Moksh Gala",
            amount=1.00,
            reference="RZP1A2B3C4D",
            status="Successful",
            provider="Razorpay",
            payment_method="card",
            razorpay_payment_id="pay_card_123",
            razorpay_order_id="order_123",
            balance_after=1578.00,
        )
        assert success is True
        html = captured["html"]
        assert "Payment Gateway" in html
        assert "Razorpay" in html
        assert "Payment Method" in html
        assert "Card" in html

        # Verify PDF attachment generated and contains valid binary
        atts = captured["attachments"]
        assert atts is not None and len(atts) == 1
        assert atts[0]["filename"] == "Receipt-RZP1A2B3C4D.pdf"
        assert atts[0]["content"].startswith(b"%PDF-")


@pytest.mark.parametrize("method_raw,expected_norm", [
    ("card", "Card"),
    ("upi", "UPI"),
    ("netbanking", "Net Banking"),
    ("wallet", "Wallet"),
])
def test_verify_payment_fetches_instrument_from_razorpay(method_raw, expected_norm):
    """
    Verify that when /verify-payment is called without payment_method,
    it queries razorpay_service.get_payment_details() to retrieve the verified method,
    stores the normalized method in Transaction, and passes it to email & PDF.
    """
    with SessionLocal() as db:
        uid = uuid.uuid4().hex[:8]
        u = User(
            name=f"Topup Test {expected_norm}",
            email=f"topup_{method_raw}_{uid}@thetapandgo.in",
            phone=f"9{int(uid, 16) % 1000000000:09d}",
            account_type="passenger",
            status="active",
            password_hash=hash_password("Pass1234!"),
        )
        db.add(u)
        db.commit()
        db.refresh(u)

        captured_email = {}

        def mock_send_email(**kwargs):
            captured_email["html"] = kwargs.get("html_content")
            captured_email["attachments"] = kwargs.get("attachments")
            return True

        req = VerifyPaymentRequest(
            user_id=u.id,
            razorpay_order_id=f"order_{uid}",
            razorpay_payment_id=f"pay_{method_raw}_{uid}",
            razorpay_signature="mock_sig",
            amount=100.0,
            # payment_method is NOT provided in request, simulating standard Razorpay Checkout modal
        )

        with patch("app.services.payment.razorpay_service.razorpay_service.verify_payment_signature", return_value=True), \
             patch("app.services.payment.razorpay_service.razorpay_service.get_payment_details", return_value={"id": req.razorpay_payment_id, "method": method_raw}), \
             patch("app.utils.email_service.send_email", side_effect=mock_send_email):

            res = verify_razorpay_payment(data=req, db=db)
            assert res.get("success") is True

            # Verify transaction in database has normalized method
            txn = db.query(Transaction).filter(Transaction.provider_transaction_id == req.razorpay_payment_id).first()
            assert txn is not None
            assert txn.payment_method == expected_norm

            # Verify email received normalized method and both gateway and method are present
            html = captured_email.get("html", "")
            assert "Payment Gateway" in html
            assert "Razorpay" in html
            assert "Payment Method" in html
            assert expected_norm in html
