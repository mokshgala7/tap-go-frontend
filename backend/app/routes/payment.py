from decimal import Decimal
import uuid
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transaction, User, Wallet
from app.services.payment.razorpay_service import razorpay_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payment", tags=["Payment"])
debug_router = APIRouter(tags=["Debug"])


class CreateOrderRequest(BaseModel):
    user_id: int
    amount: float  # Amount in INR Rupees


class VerifyPaymentRequest(BaseModel):
    user_id: int
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    amount: float  # Amount in INR Rupees


def get_or_create_wallet(user_id: int, db: Session) -> Wallet:
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal("0.00"), is_frozen=False)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
    return wallet


@router.post("/create-order")
def create_razorpay_order(data: CreateOrderRequest, db: Session = Depends(get_db)):
    """
    Creates a Razorpay Order for adding money to a Tap & Go wallet.
    Validates amount >= ₹1.00 (100 paise).
    """
    if data.amount < 1.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum top-up amount is ₹1.00."
        )

    user = db.get(User, data.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    wallet = get_or_create_wallet(user.id, db)
    if wallet.is_frozen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your wallet is frozen. Adding funds is disabled."
        )

    try:
        order = razorpay_service.create_order(
            amount_in_rupees=data.amount,
            notes={"user_id": str(user.id), "user_email": user.email}
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment verification failed due to invalid signature."
        )

    # 3. Credit wallet balance atomically
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
                        wallet = get_or_create_wallet(user.id, db)
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
