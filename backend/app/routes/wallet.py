from decimal import Decimal
import uuid
import random
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transaction, User, Wallet, EmailOTP, WithdrawalRequest
from app.utils.email_service import (
    send_withdrawal_otp,
    send_withdrawal_email,
    send_ride_passenger_email,
    send_ride_driver_email,
    send_withdrawal_approved_email,
    send_withdrawal_paid_email,
    send_withdrawal_rejected_email,
)
from app.utils.security import get_elapsed_seconds, is_otp_expired
from app.routes.auth import get_current_user
from sqlalchemy import func
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wallet", tags=["Wallet"])


class TopupRequest(BaseModel):
    user_id: int
    amount: float
    payment_method: Optional[str] = "razorpay"
    idempotency_key: Optional[str] = None


class WithdrawOTPRequest(BaseModel):
    user_id: int
    amount: float


class WithdrawRequest(BaseModel):
    user_id: int
    amount: float
    otp: Optional[str] = None
    idempotency_key: Optional[str] = None


class PayRequest(BaseModel):
    passenger_id: int
    driver_id: Optional[int] = None
    fare: float
    vehicle_type: Optional[str] = None
    vehicle_number: Optional[str] = None
    driver_name: Optional[str] = None
    payment_method: Optional[str] = "QR"
    idempotency_key: Optional[str] = None


def wallet_to_dict(wallet: Wallet):
    return {
        "id": wallet.id,
        "user_id": wallet.user_id,
        "balance": float(wallet.balance),
        "is_frozen": wallet.is_frozen,
        "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None,
    }


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


@router.get("/{user_id}")
def get_user_wallet(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    wallet = get_or_create_wallet(user_id, db)
    return {"success": True, "wallet": wallet_to_dict(wallet)}


@router.get("/{user_id}/transactions")
def get_user_transactions(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    wallet = get_or_create_wallet(user_id, db)

    txns = db.query(Transaction).filter(
        or_(
            Transaction.passenger_id == user_id,
            Transaction.driver_id == user_id,
            Transaction.wallet_id == wallet.id,
        )
    ).order_by(Transaction.created_at.asc(), Transaction.id.asc()).all()

    user_ids = set()
    for t in txns:
        if t.passenger_id:
            user_ids.add(t.passenger_id)
        if t.driver_id:
            user_ids.add(t.driver_id)

    user_map = {}
    if user_ids:
        users = db.query(User).filter(User.id.in_(user_ids)).all()
        user_map = {u.id: u.name for u in users}

    formatted_txns = []
    running_balance = Decimal("0.00")

    for t in txns:
        amount_dec = Decimal(str(t.amount))
        is_credit = False
        change = amount_dec

        if t.passenger_id == user_id:
            if t.payment_method in ("razorpay", "topup", "payment_gateway", "deposit", "upi") or t.transaction_type == "deposit" or t.amount < 0:
                is_credit = True
                change = abs(amount_dec)
                type_label = "Add Money (Razorpay)" if t.payment_method == "razorpay" or t.provider == "RAZORPAY" else "Deposit"
                description = t.description or f"₹{float(change):.2f} credited to wallet"
            elif t.payment_method == "bank_transfer" or t.transaction_type == "withdrawal":
                is_credit = False
                change = abs(amount_dec)
                type_label = "Withdrawal"
                description = t.description or f"₹{float(change):.2f} transferred to bank account"
            else:
                is_credit = False
                change = abs(amount_dec)
                d_name = user_map.get(t.driver_id, f"Driver #{t.driver_id}" if t.driver_id else "Driver")
                type_label = "Ride Payment"
                description = f"₹{float(change):.2f} paid to {d_name}"
        elif t.driver_id == user_id:
            if t.payment_method == "bank_transfer" or t.transaction_type == "withdrawal":
                is_credit = False
                change = abs(amount_dec)
                type_label = "Withdrawal"
                description = t.description or f"₹{float(change):.2f} transferred to bank account"
            else:
                is_credit = True
                change = abs(amount_dec)
                p_name = user_map.get(t.passenger_id, f"Passenger #{t.passenger_id}" if t.passenger_id else "Passenger")
                type_label = "Ride Payment Received"
                description = f"₹{float(change):.2f} received from {p_name}"
        else:
            is_credit = t.amount > 0
            change = abs(amount_dec)
            type_label = "Deposit" if is_credit else "Payment"
            description = t.description or f"₹{float(change):.2f} {'credited to' if is_credit else 'debited from'} wallet"

        if is_credit:
            running_balance += change
        else:
            running_balance -= change

        final_balance_after = float(t.balance_after) if t.balance_after is not None else float(running_balance)

        formatted_txns.append({
            "id": t.reference or f"TXN-{t.id}",
            "reference": t.reference,
            "type": type_label,
            "description": description,
            "amount": float(change),
            "fare": -float(change) if is_credit else float(change),
            "is_credit": is_credit,
            "payment_method": t.payment_method.upper() if t.payment_method else "WALLET",
            "status": t.status.title() if t.status else "Completed",
            "balance_after": final_balance_after,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "timestamp": int(t.created_at.timestamp() * 1000) if t.created_at else 0,
            "passenger_id": t.passenger_id,
            "driver_id": t.driver_id,
            "driver": user_map.get(t.driver_id, "Driver"),
            "passenger": user_map.get(t.passenger_id, "Passenger"),
        })

    formatted_txns.reverse()

    return {
        "success": True,
        "transactions": formatted_txns
    }


@router.post("/withdraw/request-otp")
def request_withdrawal_otp(data: WithdrawOTPRequest, db: Session = Depends(get_db)):
    """
    Generates and emails a single-use OTP for withdrawal confirmation via Amazon SES.
    - 5-minute expiration
    - 60-second cooldown
    - Canonical reason 'withdraw_balance', synchronized purpose 'withdraw_balance'
    - Prior unconsumed OTPs invalidated with used=True
    - OTP record remains persisted even if SES delivery fails
    - Never physically deleted
    """
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be greater than zero.")

    user = db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not (user.bank_account_number and user.bank_account_number.strip()) and not (user.bank_upi_id and user.bank_upi_id.strip()):
        raise HTTPException(
            status_code=400,
            detail="No saved payout destination found (Bank account or UPI ID). Please update your bank details in profile first."
        )

    wallet = get_or_create_wallet(user.id, db)
    if wallet.is_frozen:
        raise HTTPException(status_code=400, detail="Your wallet is frozen. Withdrawals are disabled.")

    withdraw_dec = Decimal(str(round(data.amount, 2)))
    if wallet.balance < withdraw_dec:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance (Available: ₹{float(wallet.balance):.2f})."
        )

    clean_email = user.email.strip().lower()

    # 60-second cooldown check
    existing_otp = db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == "withdraw_balance",
            EmailOTP.purpose.in_(["withdraw_balance", "withdrawal"]),
        )
    ).order_by(EmailOTP.created_at.desc()).first()

    if existing_otp and existing_otp.created_at:
        elapsed = get_elapsed_seconds(existing_otp.created_at)
        if elapsed < 60:
            remaining_seconds = max(1, min(60, int(60 - elapsed)))
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining_seconds} seconds before requesting another withdrawal OTP."
            )

    # Invalidate previous unconsumed withdrawal OTPs for this email (used=True)
    db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == "withdraw_balance",
            EmailOTP.purpose.in_(["withdraw_balance", "withdrawal"]),
        ),
        EmailOTP.used == False,
    ).update({"used": True}, synchronize_session=False)

    # Generate 6-digit OTP with 5-minute expiration
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    new_otp = EmailOTP(
        email=user.email,
        otp=otp_code,
        reason="withdraw_balance",
        purpose="withdraw_balance",
        attempts=0,
        is_verified=False,
        used=False,
        expires_at=expires_at,
    )
    db.add(new_otp)
    db.commit()

    # Deliver via real Amazon SES
    email_sent = send_withdrawal_otp(to_email=user.email, otp=otp_code, amount=data.amount)

    dest_str = f"Bank Account (ending in {user.bank_account_number.strip()[-4:]})" if user.bank_account_number else f"UPI ID ({user.bank_upi_id})"

    return {
        "success": True,
        "message": f"Withdrawal OTP has been sent to {user.email}. Target destination: {dest_str}",
        "otp_required": True,
        "email_sent": email_sent
    }


@router.post("/withdraw")
def withdraw_to_bank(data: WithdrawRequest, db: Session = Depends(get_db)):
    """
    Submits a withdrawal request using server-side Email OTP verification.
    Atomically reserves (deducts) the balance and creates a WithdrawalRequest
    (status=pending). The balance stays deducted until admin approves/rejects.
    Prevents concurrent double-spending via with_for_update() row locking.
    Idempotency: duplicate idempotency_key returns the existing request.
    Notification email sent post-commit; email failure never rolls back the transaction.
    """
    if data.idempotency_key:
        existing_wr = db.query(WithdrawalRequest).filter(
            WithdrawalRequest.idempotency_key == data.idempotency_key
        ).first()
        if existing_wr:
            wallet = get_or_create_wallet(data.user_id, db)
            return {
                "success": True,
                "message": "Withdrawal request already submitted. Awaiting admin review.",
                "wallet": wallet_to_dict(wallet),
                "request_id": existing_wr.id,
                "request_status": existing_wr.status,
            }

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Withdrawal amount must be greater than zero.")

    user = db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    has_bank = user.bank_account_number and user.bank_account_number.strip()
    has_upi = user.bank_upi_id and user.bank_upi_id.strip()

    if not has_bank and not has_upi:
        raise HTTPException(
            status_code=400,
            detail="No saved payout destination found. Please add bank or UPI details in your Profile first."
        )

    # Validate OTP
    if not data.otp or not data.otp.strip():
        raise HTTPException(status_code=400, detail="Email OTP is required for withdrawal confirmation.")

    clean_email = user.email.strip().lower()
    db_otp = db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == "withdraw_balance",
            EmailOTP.purpose.in_(["withdraw_balance", "withdrawal"]),
        ),
        EmailOTP.used == False,
    ).order_by(EmailOTP.created_at.desc()).first()

    if not db_otp:
        raise HTTPException(status_code=400, detail="No withdrawal OTP found. Please request a new OTP.")

    if db_otp.attempts >= 5:
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please request a new OTP.")

    if is_otp_expired(db_otp.expires_at):
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new OTP.")

    if db_otp.otp != data.otp.strip():
        db_otp.attempts += 1
        if db_otp.attempts >= 5:
            db_otp.used = True
        db.commit()
        if db_otp.attempts >= 5:
            raise HTTPException(status_code=400, detail="Too many incorrect OTP attempts. Please request a new OTP.")
        remaining = max(0, 5 - db_otp.attempts)
        raise HTTPException(status_code=400, detail=f"Invalid OTP code. ({remaining} attempts remaining)")

    # Single-use OTP: mark used=True (persisted, never deleted)
    db_otp.is_verified = True
    db_otp.used = True


    # ── Atomic Balance Reservation (with row-level lock) ──────────────────────
    # Lock wallet row exclusively to prevent concurrent double-spending
    wallet = get_or_create_wallet(data.user_id, db, for_update=True)
    if wallet.is_frozen:
        raise HTTPException(status_code=400, detail="Your wallet is frozen. Withdrawals are disabled.")

    withdraw_dec = Decimal(str(round(data.amount, 2)))
    if wallet.balance < withdraw_dec:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance. Available balance is ₹{float(wallet.balance):.2f}."
        )

    # Deduct balance atomically (reservation/hold)
    wallet.balance -= withdraw_dec

    dest_desc = f"Bank Account (XXXX XXXX {user.bank_account_number.strip()[-4:]})" if has_bank else f"UPI ID ({user.bank_upi_id})"
    ref_code = f"WD-{uuid.uuid4().hex[:10].upper()}"
    desc = f"₹{data.amount:.2f} withdrawal hold — pending admin approval to {dest_desc}"

    # Record withdrawal_hold transaction (status=pending, not completed)
    hold_txn = Transaction(
        reference=ref_code,
        passenger_id=user.id if user.account_type == "passenger" else None,
        driver_id=user.id if user.account_type == "driver" else None,
        wallet_id=wallet.id,
        amount=withdraw_dec,
        payment_method="bank_transfer",
        status="pending",
        otp_verified=True,
        fraud_status="clear",
        transaction_type="withdrawal_hold",
        description=desc,
        balance_after=wallet.balance,
        idempotency_key=data.idempotency_key,
    )
    db.add(hold_txn)
    db.flush()  # get hold_txn.id without committing

    # Create WithdrawalRequest record
    wr = WithdrawalRequest(
        user_id=user.id,
        wallet_id=wallet.id,
        hold_transaction_id=hold_txn.id,
        amount=withdraw_dec,
        destination_desc=dest_desc,
        reference=ref_code,
        otp_verified=True,
        status="pending",
        idempotency_key=data.idempotency_key,
    )
    db.add(wr)
    db.commit()
    db.refresh(wallet)
    db.refresh(hold_txn)
    db.refresh(wr)

    # Post-commit notification (never rolls back the transaction)
    try:
        send_withdrawal_email(
            to_email=user.email,
            user_name=user.name,
            amount=data.amount,
            reference=ref_code,
            destination=dest_desc,
            status="Pending Admin Review",
        )
    except Exception as e:
        logger.warning(f"[WithdrawalEmail] Notification delivery failed: {e}")

    return {
        "success": True,
        "message": f"Withdrawal request of ₹{data.amount:.2f} submitted and is pending admin review. Your balance has been reserved.",
        "wallet": wallet_to_dict(wallet),
        "request_id": wr.id,
        "request_status": wr.status,
    }
@router.get("/withdraw/history")
def get_withdrawal_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns the authenticated user's withdrawal request history.
    User identity is derived from JWT — no user_id parameter accepted.
    """
    requests = db.query(WithdrawalRequest).filter(
        WithdrawalRequest.user_id == current_user.id
    ).order_by(WithdrawalRequest.created_at.desc()).all()

    return {
        "success": True,
        "withdrawal_requests": [
            {
                "id": wr.id,
                "reference": wr.reference,
                "amount": float(wr.amount),
                "destination_desc": wr.destination_desc,
                "status": wr.status,
                "admin_note": wr.admin_note,
                "created_at": wr.created_at.isoformat() if wr.created_at else None,
                "reviewed_at": wr.reviewed_at.isoformat() if wr.reviewed_at else None,
                "paid_at": wr.paid_at.isoformat() if wr.paid_at else None,
            }
            for wr in requests
        ]
    }



@router.post("/pay")
def pay_fare(data: PayRequest, db: Session = Depends(get_db)):
    """
    Normal Tap & Go Ride Payment Flow.
    Passenger Wallet -> Internal Tap & Go Ledger -> Driver Wallet.
    RAZORPAY IS NOT USED FOR NORMAL RIDES.
    Transaction committed first, then email notifications dispatched safely.
    """
    if data.idempotency_key:
        existing = db.query(Transaction).filter(Transaction.idempotency_key == data.idempotency_key).first()
        if existing:
            wallet = get_or_create_wallet(data.passenger_id, db)
            return {
                "success": True,
                "message": f"Payment of ₹{data.fare:.2f} completed.",
                "wallet": wallet_to_dict(wallet),
            }

    if data.fare <= 0:
        raise HTTPException(status_code=400, detail="Fare amount must be greater than zero.")

    passenger = db.get(User, data.passenger_id)
    if not passenger:
        raise HTTPException(status_code=404, detail="Passenger user not found.")

    # Exclusively lock passenger wallet row to prevent concurrent double-spending
    p_wallet = get_or_create_wallet(passenger.id, db, for_update=True)
    if p_wallet.is_frozen:
        # Failure notification
        try:
            if passenger.email:
                send_ride_passenger_email(
                    to_email=passenger.email,
                    passenger_name=passenger.name,
                    fare=data.fare,
                    driver_name=data.driver_name or "Driver",
                    reference=f"FAIL-{uuid.uuid4().hex[:8].upper()}",
                    status="Failed (Account Frozen)",
                )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail="Your passenger wallet is frozen. Payment failed.")

    fare_dec = Decimal(str(round(data.fare, 2)))
    if p_wallet.balance < fare_dec:
        # Failure notification
        try:
            if passenger.email:
                send_ride_passenger_email(
                    to_email=passenger.email,
                    passenger_name=passenger.name,
                    fare=data.fare,
                    driver_name=data.driver_name or "Driver",
                    reference=f"FAIL-{uuid.uuid4().hex[:8].upper()}",
                    status="Failed (Insufficient Balance)",
                )
        except Exception:
            pass
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance (₹{float(p_wallet.balance):.2f}). Please add funds first."
        )

    driver_id = data.driver_id
    driver_name = data.driver_name
    driver_user = None
    if not driver_id:
        active_driver = db.query(User).filter(User.account_type == "driver", User.status == "active").first()
        if active_driver:
            driver_id = active_driver.id
            driver_user = active_driver
            if not driver_name:
                driver_name = active_driver.name
    elif not driver_name:
        driver_user = db.get(User, driver_id)
        if driver_user:
            driver_name = driver_user.name
    else:
        driver_user = db.get(User, driver_id)

    if not driver_name:
        driver_name = f"Driver #{driver_id}" if driver_id else "Driver"

    p_wallet.balance -= fare_dec

    d_wallet = None
    if driver_id:
        # Exclusively lock driver wallet row during credit
        d_wallet = get_or_create_wallet(driver_id, db, for_update=True)
        if not d_wallet.is_frozen:
            d_wallet.balance += fare_dec

    ref_code = f"TXN{uuid.uuid4().hex[:10].upper()}"
    desc = f"₹{data.fare:.2f} paid to {driver_name}"

    txn = Transaction(
        reference=ref_code,
        passenger_id=passenger.id,
        driver_id=driver_id,
        wallet_id=p_wallet.id,
        amount=fare_dec,
        payment_method=data.payment_method or "QR",
        status="completed",
        otp_verified=True,
        fraud_status="clear",
        transaction_type="ride_payment",
        description=desc,
        balance_after=p_wallet.balance,
        idempotency_key=data.idempotency_key,
    )
    db.add(txn)
    db.commit()
    db.refresh(p_wallet)
    if d_wallet:
        db.refresh(d_wallet)
    db.refresh(txn)

    # Post-commit notifications (financial transaction already completed safely)
    try:
        if passenger.email:
            send_ride_passenger_email(
                to_email=passenger.email,
                passenger_name=passenger.name,
                fare=data.fare,
                driver_name=driver_name,
                reference=ref_code,
                status="Successful",
            )
    except Exception as e:
        logger.warning(f"[RideEmail] Passenger receipt failed: {e}")

    try:
        if driver_user and driver_user.email:
            send_ride_driver_email(
                to_email=driver_user.email,
                driver_name=driver_name,
                fare=data.fare,
                passenger_name=passenger.name,
                reference=ref_code,
            )
    except Exception as e:
        logger.warning(f"[RideEmail] Driver credit receipt failed: {e}")

    return {
        "success": True,
        "message": f"Payment of ₹{data.fare:.2f} completed.",
        "wallet": wallet_to_dict(p_wallet),
    }
