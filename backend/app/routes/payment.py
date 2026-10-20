from decimal import Decimal
import uuid
import json
import math
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Transaction, User, Wallet, EmailOTP, PaymentOrder
from app.services.payment.razorpay_service import razorpay_service, PaymentsNotConfigured
from app.routes.admin import current_admin
from app.utils.email_service import send_wallet_topup_email, send_topup_otp, _normalize_razorpay_method
from app.utils.security import get_elapsed_seconds, is_otp_expired, generate_otp
from app.routes.auth import (
    get_current_user,
    _verify_otp_code,
    _consume_otp,
    _hourly_code_cap_reached,
    OTP_MAX_ATTEMPTS,
    OTP_HOURLY_CAP_MESSAGE,
)
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment", tags=["Payment"])
debug_router = APIRouter(tags=["Debug"])


class CreateOrderRequest(BaseModel):
    amount: float   # Amount in INR Rupees
    otp: str        # Mandatory wallet_topup OTP (no bypass)


class TopupOTPRequest(BaseModel):
    amount: float   # Amount in INR Rupees to tie to the OTP


class VerifyPaymentRequest(BaseModel):
    # `user_id` and `amount` are accepted only so older clients keep working.
    # Neither is trusted: the owner and the amount come from the server-side
    # order (PaymentOrder) and the authenticated session.
    user_id: Optional[int] = None
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    amount: Optional[float] = None
    payment_method: Optional[str] = None


def get_or_create_wallet(user_id: int, db: Session, for_update: bool = False) -> Wallet:
    query = db.query(Wallet).filter(Wallet.user_id == user_id)
    if for_update:
        query = query.with_for_update()
    wallet = query.first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal("0.00"), is_frozen=False)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
        if for_update:
            wallet = db.query(Wallet).filter(Wallet.user_id == user_id).with_for_update().first()
    return wallet


@router.post("/topup/request-otp")
def request_topup_otp(
    data: TopupOTPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generates and emails a single-use, amount-tied OTP for wallet top-up authorisation.
    User identity derived from JWT. Amount is stored in OTP metadata for later verification.
    - 5-minute expiration
    - 60-second cooldown
    - Purpose = 'wallet_topup'
    """
    if not math.isfinite(data.amount) or data.amount < 1.0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Minimum top-up amount is ₹1.00.")

    wallet = get_or_create_wallet(current_user.id, db)
    if wallet.is_frozen:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Your wallet is frozen. Adding funds is disabled.")

    clean_email = current_user.email.strip().lower()
    # 60-second cooldown check
    existing_otp = db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == "wallet_topup",
            EmailOTP.purpose == "wallet_topup",
        )
    ).order_by(EmailOTP.created_at.desc()).first()

    if existing_otp and existing_otp.created_at:
        elapsed = get_elapsed_seconds(existing_otp.created_at)
        if elapsed < 60:
            remaining_seconds = max(1, min(60, int(60 - elapsed)))
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining_seconds} seconds before requesting another top-up OTP."
            )

    if _hourly_code_cap_reached(
        db,
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == "wallet_topup",
            EmailOTP.purpose == "wallet_topup",
        ),
    ):
        raise HTTPException(status_code=429, detail=OTP_HOURLY_CAP_MESSAGE)

    # Invalidate any prior unconsumed wallet_topup OTPs for this email (used=True)
    db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == "wallet_topup",
            EmailOTP.purpose == "wallet_topup",
        ),
        EmailOTP.used == False,
    ).update({"used": True}, synchronize_session=False)

    # Generate 6-digit OTP with 5-minute expiry
    otp_code = generate_otp()
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=5)
    # Store amount in metadata so /create-order can verify it matches
    otp_metadata = json.dumps({"amount": round(data.amount, 2), "user_id": current_user.id})

    new_otp = EmailOTP(
        email=current_user.email,
        otp=otp_code,
        reason="wallet_topup",
        purpose="wallet_topup",
        attempts=0,
        is_verified=False,
        used=False,
        expires_at=expires_at,
        otp_metadata=otp_metadata,
        created_at=now,  # explicit UTC: cooldown and hourly cap must not depend on the database time zone
    )
    db.add(new_otp)
    db.commit()

    email_sent = send_topup_otp(to_email=current_user.email, otp=otp_code, amount=data.amount)
    if not email_sent:
        # The row stays persisted; the provider's error text stays in the server log.
        raise HTTPException(
            status_code=500,
            detail="We couldn't send the top-up verification email. Please try again.",
        )

    return {
        "success": True,
        "message": f"Top-up OTP has been sent to {current_user.email}. Enter it to proceed to checkout.",
        "email_sent": True,
    }


@router.post("/create-order")
def create_razorpay_order(
    data: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a Razorpay Order for adding money to a Tap & Go wallet.
    Requires mandatory wallet_topup OTP verified server-side before order creation.
    OTP must match: authenticated user, wallet_topup purpose, exact amount, expiry, attempt limit.
    User identity is derived from JWT — no user_id from request body.
    """
    if not math.isfinite(data.amount) or data.amount < 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum top-up amount is ₹1.00."
        )

    wallet = get_or_create_wallet(current_user.id, db)
    if wallet.is_frozen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your wallet is frozen. Adding funds is disabled."
        )

    # ── Mandatory server-side OTP gate ─────────────────────────────────────────
    # OTP must be present (no bypass)
    if not data.otp or not data.otp.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wallet top-up OTP is required. Please request an OTP first."
        )

    clean_email = current_user.email.strip().lower()
    db_otp = db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == "wallet_topup",
            EmailOTP.purpose == "wallet_topup",
        ),
        EmailOTP.used == False,
    ).order_by(EmailOTP.created_at.desc()).first()

    if not db_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No wallet top-up OTP found for this account. Please request an OTP first."
        )

    if db_otp.attempts >= OTP_MAX_ATTEMPTS:
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please request a new OTP.")

    if is_otp_expired(db_otp.expires_at):
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Top-up OTP has expired. Please request a new OTP.")

    # The guess is reserved atomically before the comparison (parallel guesses cannot exceed the
    # limit) and the comparison is constant-time.
    outcome, attempts = _verify_otp_code(db, db_otp, data.otp)
    if outcome == "locked" or (outcome == "wrong" and attempts >= OTP_MAX_ATTEMPTS):
        raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please request a new OTP.")
    if outcome == "gone":
        raise HTTPException(status_code=400, detail="This OTP is no longer valid. Please request a new OTP.")
    if outcome == "wrong":
        remaining = max(0, OTP_MAX_ATTEMPTS - attempts)
        raise HTTPException(status_code=400, detail=f"Invalid top-up OTP. ({remaining} attempts remaining)")

    # Verify amount and owner match (the OTP is amount-tied)
    try:
        meta = json.loads(db_otp.otp_metadata) if db_otp.otp_metadata else {}
        stored_amount = meta.get("amount")
        stored_user_id = meta.get("user_id")
        if stored_amount is not None and round(stored_amount, 2) != round(data.amount, 2):
            db.query(EmailOTP).filter(EmailOTP.id == db_otp.id).update(
                {EmailOTP.attempts: EmailOTP.attempts + 1}, synchronize_session=False
            )
            db.query(EmailOTP).filter(EmailOTP.id == db_otp.id, EmailOTP.attempts >= OTP_MAX_ATTEMPTS).update(
                {EmailOTP.used: True}, synchronize_session=False
            )
            db.commit()
            raise HTTPException(
                status_code=400,
                detail=f"OTP was issued for a different amount (₹{stored_amount:.2f}). Please request a new OTP for ₹{data.amount:.2f}."
            )
        if stored_user_id is not None and stored_user_id != current_user.id:
            db_otp.used = True
            db.commit()
            raise HTTPException(status_code=400, detail="OTP does not match authenticated user.")
    except HTTPException:
        raise
    except Exception:
        # If metadata is malformed, still allow but log
        logger.warning(f"[TopupOTP] Could not parse otp_metadata for user {current_user.id}")

    # Single use: only one request can flip used False -> True. The change is committed together
    # with the order below, so a failed order creation (provider down) leaves the OTP usable and
    # two parallel requests cannot both create an order from one code.
    if not _consume_otp(db, db_otp):
        db.rollback()
        raise HTTPException(status_code=400, detail="This OTP is no longer valid. Please request a new OTP.")
    # ── End OTP gate ────────────────────────────────────────────────────────────

    try:
        order = razorpay_service.create_order(
            amount_in_rupees=data.amount,
            notes={"user_id": str(current_user.id), "user_email": current_user.email}
        )
    except PaymentsNotConfigured as nc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(nc))
    except ValueError as ve:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        db.rollback()
        logger.error(f"[Payment] Error creating Razorpay order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate Razorpay order. Please try again."
        )

    # The server, not the client, remembers who the order belongs to and for
    # how much. verify-payment and the webhook credit exactly this amount.
    db.add(PaymentOrder(
        order_id=order["order_id"],
        user_id=current_user.id,
        amount_paise=int(order["amount"]),
        currency=order["currency"],
        status="created",
        is_mock=bool(order.get("is_mock", False)),
    ))
    db.commit()

    return {
        "success": True,
        "order_id": order["order_id"],
        "amount": order["amount"],
        "currency": order["currency"],
        "key_id": order["key_id"],
        "is_mock": order.get("is_mock", False)
    }


def _credit_order(db: Session, order: PaymentOrder, payment_id: str, raw_method: Optional[str], source: str):
    """Credit the wallet for `order` exactly once.

    Returns (transaction, newly_credited). The order row is claimed with a
    conditional UPDATE (status created -> paid) whose row count decides the
    single winner, so concurrent verify-payment calls, a verify racing the
    webhook, retries and replays can never credit twice - on any database,
    without relying on row locks. The wallet is changed with an atomic
    `balance = balance + amount` UPDATE inside the same transaction.
    """
    # The wallet row must exist BEFORE the order is claimed: creating it commits,
    # and a commit between "claim" and "credit" would lose the credit on a crash.
    user = db.get(User, order.user_id)
    wallet = get_or_create_wallet(order.user_id, db)

    claimed = db.query(PaymentOrder).filter(
        PaymentOrder.id == order.id, PaymentOrder.status == "created"
    ).update(
        {"status": "paid", "provider_payment_id": payment_id, "paid_at": datetime.utcnow()},
        synchronize_session=False,
    )
    if claimed != 1:
        db.rollback()
        existing = db.query(Transaction).filter(
            Transaction.provider_transaction_id == payment_id
        ).first()
        return existing, False

    credit_amount = (Decimal(order.amount_paise) / Decimal(100)).quantize(Decimal("0.01"))
    db.query(Wallet).filter(Wallet.id == wallet.id).update(
        {Wallet.balance: Wallet.balance + credit_amount}, synchronize_session=False
    )
    db.flush()
    db.refresh(wallet)

    normalized_method = _normalize_razorpay_method(raw_method)
    txn = Transaction(
        reference=f"RZP{uuid.uuid4().hex[:10].upper()}",
        passenger_id=user.id if user.account_type == "passenger" else None,
        driver_id=user.id if user.account_type == "driver" else None,
        wallet_id=wallet.id,
        amount=credit_amount,
        payment_method=normalized_method or "Razorpay",
        status="completed",
        otp_verified=True,
        fraud_status="clear",
        transaction_type="deposit",
        description=f"₹{float(credit_amount):.2f} added to wallet via Razorpay{' (webhook)' if source == 'webhook' else ''}",
        balance_after=wallet.balance,
        provider="RAZORPAY",
        provider_transaction_id=payment_id,
        utr=order.order_id,
    )
    db.add(txn)
    try:
        db.commit()
    except IntegrityError:
        # The unique index on provider_transaction_id caught a duplicate.
        db.rollback()
        return db.query(Transaction).filter(Transaction.provider_transaction_id == payment_id).first(), False
    db.refresh(txn)
    db.refresh(wallet)

    if user.email:
        try:
            send_wallet_topup_email(
                to_email=user.email,
                user_name=user.name,
                amount=float(credit_amount),
                reference=txn.reference,
                status="Successful",
                provider="Razorpay",
                payment_method=normalized_method,
                razorpay_payment_id=payment_id,
                razorpay_order_id=order.order_id,
                balance_after=float(wallet.balance),
                created_at=txn.created_at,
                account_type=user.account_type,
            )
        except Exception as e:
            logger.warning(f"[PaymentEmail] Topup email delivery failed: {e}")
    return txn, True


def _provider_payment_matches(order: PaymentOrder, payment_id: str):
    """Fetch the payment from Razorpay and require that it is a captured payment
    for exactly this order, amount and currency. Returns (ok, method)."""
    info = razorpay_service.get_payment_details(payment_id)
    if not isinstance(info, dict):
        return False, None
    ok = (
        info.get("status") == "captured"
        and info.get("order_id") == order.order_id
        and str(info.get("currency", "")).upper() == order.currency.upper()
        and int(info.get("amount", -1)) == int(order.amount_paise)
    )
    return ok, info.get("method")


@router.post("/verify-payment")
def verify_razorpay_payment(
    data: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Credits the wallet for a paid Razorpay order.

    The caller must be authenticated and must own the order. The credited
    amount is the amount stored on the server-side order and confirmed with
    Razorpay; the `amount` and `user_id` sent by a client are ignored.
    """
    if not data.razorpay_order_id or not data.razorpay_payment_id or not data.razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing required Razorpay verification parameters.")
    if data.user_id is not None and data.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to verify this payment.")

    order = db.query(PaymentOrder).filter(PaymentOrder.order_id == data.razorpay_order_id).first()
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Payment order not found.")

    # Replay / retry: the order was already credited.
    if order.status == "paid":
        existing = db.query(Transaction).filter(
            Transaction.provider_transaction_id == order.provider_payment_id
        ).first()
        if order.provider_payment_id != data.razorpay_payment_id:
            raise HTTPException(status_code=409, detail="This order was already paid with a different payment.")
        wallet = get_or_create_wallet(current_user.id, db)
        return {
            "success": True,
            "message": "Payment already verified and credited.",
            "balance": float(wallet.balance),
            "reference": existing.reference if existing else None,
            "idempotent": True,
        }

    if not razorpay_service.verify_payment_signature(
        razorpay_order_id=data.razorpay_order_id,
        razorpay_payment_id=data.razorpay_payment_id,
        razorpay_signature=data.razorpay_signature,
    ):
        logger.warning("[Payment] Invalid signature for order %s", data.razorpay_order_id)
        raise HTTPException(status_code=400, detail="Payment verification failed due to invalid signature.")

    raw_method = data.payment_method
    if order.is_mock:
        # A mock order can only be settled when mock payments are explicitly enabled.
        if not settings.ALLOW_MOCK_PAYMENTS:
            raise HTTPException(status_code=400, detail="Payment verification failed.")
    else:
        ok, provider_method = _provider_payment_matches(order, data.razorpay_payment_id)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail="The payment could not be confirmed with the payment provider.",
            )
        raw_method = provider_method or raw_method

    txn, credited = _credit_order(db, order, data.razorpay_payment_id, raw_method, "verify")
    wallet = get_or_create_wallet(current_user.id, db)
    if txn is None:
        raise HTTPException(status_code=409, detail="This order was already paid with a different payment.")
    return {
        "success": True,
        "message": (
            f"Successfully added ₹{float(txn.amount):.2f} to your wallet."
            if credited else "Payment already verified and credited."
        ),
        "balance": float(wallet.balance),
        "reference": txn.reference,
        **({} if credited else {"idempotent": True}),
    }


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db)
):
    """
    Razorpay webhook (asynchronous reconciliation).

    The signature is mandatory. Credits are made only for orders that this
    server created, for the stored amount, and at most once per order.
    """
    if not (settings.RAZORPAY_WEBHOOK_SECRET or settings.RAZORPAY_KEY_SECRET):
        raise HTTPException(status_code=503, detail="Webhook is not configured.")
    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing webhook signature.")

    body_bytes = await request.body()
    if not razorpay_service.verify_webhook_signature(body_bytes, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = json.loads(body_bytes)
        event = payload.get("event")
        if event not in ("payment.captured", "order.paid"):
            return {"status": "ignored"}

        entity = (payload.get("payload", {}).get("payment", {}) or {}).get("entity", {}) or {}
        payment_id = entity.get("id")
        order_id = entity.get("order_id")
        if not payment_id or not order_id:
            return {"status": "ignored"}

        order = db.query(PaymentOrder).filter(PaymentOrder.order_id == order_id).first()
        if not order:
            logger.warning("[Razorpay Webhook] Unknown order %s ignored.", order_id)
            return {"status": "ignored"}
        if order.status == "paid":
            return {"status": "ok", "duplicate": True}
        if (
            entity.get("status") not in (None, "captured")
            or str(entity.get("currency", order.currency)).upper() != order.currency.upper()
            or int(entity.get("amount", -1)) != int(order.amount_paise)
        ):
            logger.error("[Razorpay Webhook] Amount/currency/status mismatch for order %s.", order_id)
            return {"status": "ignored"}

        _credit_order(db, order, payment_id, entity.get("method"), "webhook")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[Razorpay Webhook] Error processing webhook: {e}")
        # Non-2xx so Razorpay retries instead of silently dropping the event.
        raise HTTPException(status_code=500, detail="Webhook processing failed.")


@debug_router.get("/debug/status")
def get_payment_debug_status(admin=Depends(current_admin), db: Session = Depends(get_db)):
    """Status check for payment gateway setup (administrators only)."""
    has_key_id = bool(settings.RAZORPAY_KEY_ID)
    has_key_secret = bool(settings.RAZORPAY_KEY_SECRET)

    return {
        "payment_gateway": "Razorpay",
        "key_id_configured": has_key_id,
        "key_secret_configured": has_key_secret,
        "environment_ready": has_key_id and has_key_secret,
    }
