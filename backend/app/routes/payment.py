from decimal import Decimal
import uuid
import json
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.database import get_db
from app.models import Transaction, User, Wallet, EmailOTP
from app.services.payment.razorpay_service import razorpay_service
from app.utils.email_service import send_wallet_topup_email, send_topup_otp
from app.utils.security import get_elapsed_seconds, is_otp_expired
from app.routes.auth import get_current_user
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
    user_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    amount: float  # Amount in INR Rupees


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
    if data.amount < 1.0:
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
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=5)
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
    )
    db.add(new_otp)
    db.commit()

    email_sent = send_topup_otp(to_email=current_user.email, otp=otp_code, amount=data.amount)

    return {
        "success": True,
        "message": f"Top-up OTP has been sent to {current_user.email}. Enter it to proceed to checkout.",
        "email_sent": email_sent,
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
    if data.amount < 1.0:
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

    if db_otp.attempts >= 5:
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please request a new OTP.")

    if is_otp_expired(db_otp.expires_at):
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Top-up OTP has expired. Please request a new OTP.")

    if db_otp.otp != data.otp.strip():
        db_otp.attempts += 1
        if db_otp.attempts >= 5:
            db_otp.used = True
        db.commit()
        if db_otp.attempts >= 5:
            raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please request a new OTP.")
        remaining = max(0, 5 - db_otp.attempts)
        raise HTTPException(status_code=400, detail=f"Invalid top-up OTP. ({remaining} attempts remaining)")

    # Verify amount match (OTP is amount-tied)
    try:
        meta = json.loads(db_otp.otp_metadata) if db_otp.otp_metadata else {}
        stored_amount = meta.get("amount")
        stored_user_id = meta.get("user_id")
        if stored_amount is not None and round(stored_amount, 2) != round(data.amount, 2):
            db_otp.attempts += 1
            if db_otp.attempts >= 5:
                db_otp.used = True
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

    # OTP valid and amount-verified — consume it (used=True, single-use, persisted)
    db_otp.is_verified = True
    db_otp.used = True
    db.commit()
    # ── End OTP gate ────────────────────────────────────────────────────────────

    try:
        order = razorpay_service.create_order(
            amount_in_rupees=data.amount,
            notes={"user_id": str(current_user.id), "user_email": current_user.email}
        )
        return {
            "success": True,
            "order_id": order["order_id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": order["key_id"],
            "is_mock": order.get("is_mock", False)
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"[Payment] Error creating Razorpay order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate Razorpay order. Please try again."
        )


@router.post("/verify-payment")
def verify_razorpay_payment(data: VerifyPaymentRequest, db: Session = Depends(get_db)):
    """
    Verifies Razorpay HMAC signature and credits the user's wallet atomically.
    Includes strict idempotency checks to prevent double-crediting.
    """
    if not data.razorpay_order_id or not data.razorpay_payment_id or not data.razorpay_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required Razorpay verification parameters."
        )

    user = db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    wallet = get_or_create_wallet(user.id, db)

    # 1. Idempotency Check: Verify if this payment ID was already processed
    existing_txn = db.query(Transaction).filter(
        Transaction.provider_transaction_id == data.razorpay_payment_id
    ).first()

    if existing_txn:
        logger.info(f"[Payment] Payment {data.razorpay_payment_id} already processed. Returning idempotent result.")
        return {
            "success": True,
            "message": "Payment already verified and credited.",
            "balance": float(wallet.balance),
            "reference": existing_txn.reference,
            "idempotent": True
        }

    # 2. Verify HMAC Signature
    is_valid = razorpay_service.verify_payment_signature(
        razorpay_order_id=data.razorpay_order_id,
        razorpay_payment_id=data.razorpay_payment_id,
        razorpay_signature=data.razorpay_signature
    )

    if not is_valid:
        logger.warning(f"[Payment] Invalid signature for payment {data.razorpay_payment_id}")
        if user and user.email:
            try:
                send_wallet_topup_email(
                    to_email=user.email,
                    user_name=user.name,
                    amount=data.amount,
                    reference=data.razorpay_order_id,
                    status="Failed",
                    provider="Razorpay",
                )
            except Exception:
                pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed due to invalid signature."
        )

    # 3. Lock wallet row exclusively and credit balance atomically
    wallet = get_or_create_wallet(user.id, db, for_update=True)
    credit_amount = Decimal(str(round(data.amount, 2)))
    wallet.balance += credit_amount

    # 4. Record transaction in database ledger
    ref_code = f"RZP{uuid.uuid4().hex[:10].upper()}"
    desc = f"₹{data.amount:.2f} added to wallet via Razorpay"

    txn = Transaction(
        reference=ref_code,
        passenger_id=user.id if user.account_type == "passenger" else None,
        driver_id=user.id if user.account_type == "driver" else None,
        wallet_id=wallet.id,
        amount=credit_amount,
        payment_method="razorpay",
        status="completed",
        otp_verified=True,
        fraud_status="clear",
        transaction_type="deposit",
        description=desc,
        balance_after=wallet.balance,
        provider="RAZORPAY",
        provider_transaction_id=data.razorpay_payment_id,
        utr=data.razorpay_order_id,
    )

    db.add(txn)
    db.commit()
    db.refresh(wallet)

    logger.info(f"[Payment] Successfully credited ₹{data.amount} to user {user.id} (Wallet {wallet.id}) via Razorpay.")

    # Safely dispatch topup confirmation email (financial transaction is already committed)
    if user and user.email:
        try:
            send_wallet_topup_email(
                to_email=user.email,
                user_name=user.name,
                amount=data.amount,
                reference=ref_code,
                status="Successful",
                provider="Razorpay",
            )
        except Exception as e:
            logger.warning(f"[PaymentEmail] Topup email delivery failed: {e}")

    return {
        "success": True,
        "message": f"Successfully added ₹{data.amount:.2f} to your wallet.",
        "balance": float(wallet.balance),
        "reference": ref_code,
    }


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    db: Session = Depends(get_db)
):
    """
    Webhook endpoint for asynchronous Razorpay payment reconciliation.
    """
    body_bytes = await request.body()

    if x_razorpay_signature:
        verified = razorpay_service.verify_webhook_signature(body_bytes, x_razorpay_signature)
        if not verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    try:
        payload = await request.json()
        event = payload.get("event")

        if event in ("payment.captured", "order.paid"):
            payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
            payment_id = payment_entity.get("id")
            order_id = payment_entity.get("order_id")
            amount_paise = payment_entity.get("amount", 0)
            amount_rupees = amount_paise / 100.0
            notes = payment_entity.get("notes", {})
            user_id_str = notes.get("user_id")

            if user_id_str and payment_id:
                user_id = int(user_id_str)
                existing = db.query(Transaction).filter(
                    Transaction.provider_transaction_id == payment_id
                ).first()

                if not existing:
                    user = db.get(User, user_id)
                    if user:
                        # Lock wallet row exclusively for asynchronous webhook credit
                        wallet = get_or_create_wallet(user.id, db, for_update=True)
                        credit_amt = Decimal(str(round(amount_rupees, 2)))
                        wallet.balance += credit_amt

                        txn = Transaction(
                            reference=f"RZP{uuid.uuid4().hex[:10].upper()}",
                            passenger_id=user.id if user.account_type == "passenger" else None,
                            driver_id=user.id if user.account_type == "driver" else None,
                            wallet_id=wallet.id,
                            amount=credit_amt,
                            payment_method="razorpay",
                            status="completed",
                            otp_verified=True,
                            fraud_status="clear",
                            transaction_type="deposit",
                            description=f"₹{amount_rupees:.2f} added to wallet via Razorpay Webhook",
                            balance_after=wallet.balance,
                            provider="RAZORPAY",
                            provider_transaction_id=payment_id,
                            utr=order_id,
                        )
                        db.add(txn)
                        db.commit()

                        if user.email:
                            try:
                                send_wallet_topup_email(
                                    to_email=user.email,
                                    user_name=user.name,
                                    amount=amount_rupees,
                                    reference=txn.reference,
                                    status="Successful",
                                    provider="Razorpay",
                                )
                            except Exception as e:
                                logger.warning(f"[PaymentEmail] Webhook topup email delivery failed: {e}")

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[Razorpay Webhook] Error processing webhook: {e}")
        return {"status": "error", "detail": str(e)}


@debug_router.get("/debug/status")
def get_payment_debug_status(db: Session = Depends(get_db)):
    """Status check for payment gateway setup."""
    has_key_id = bool(settings.RAZORPAY_KEY_ID)
    has_key_secret = bool(settings.RAZORPAY_KEY_SECRET)

    return {
        "payment_gateway": "Razorpay",
        "key_id_configured": has_key_id,
        "key_secret_configured": has_key_secret,
        "environment_ready": has_key_id and has_key_secret,
    }
