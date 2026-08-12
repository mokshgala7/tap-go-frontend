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
from app.models import Transaction, User, Wallet, EmailOTP
from app.utils.email_service import send_otp_email

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


def get_or_create_wallet(user_id: int, db: Session) -> Wallet:
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
    if not wallet:
        wallet = Wallet(user_id=user_id, balance=Decimal("0.00"), is_frozen=False)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
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
    Generates and emails a single-use OTP for withdrawal confirmation.
    Validates user, bank details, and wallet balance before sending.
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

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Clear previous pending OTPs for this email
    db.query(EmailOTP).filter(EmailOTP.email == user.email).delete()

    new_otp = EmailOTP(email=user.email, otp=otp_code, expires_at=expires_at)
    db.add(new_otp)
    db.commit()

    # Send Email
    email_sent = send_otp_email(to_email=user.email, otp=otp_code, account_type=user.account_type)

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
    Deducts balance atomically and records a pending/processing transaction.
    """
    if data.idempotency_key:
        existing = db.query(Transaction).filter(Transaction.idempotency_key == data.idempotency_key).first()
        if existing:
            wallet = get_or_create_wallet(data.user_id, db)
            return {
                "success": True,
                "message": f"Successfully submitted withdrawal of ₹{data.amount:.2f}.",
                "wallet": wallet_to_dict(wallet),
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

    db_otp = db.query(EmailOTP).filter(EmailOTP.email == user.email).first()
    if not db_otp or db_otp.otp != data.otp.strip():
        raise HTTPException(status_code=400, detail="Invalid OTP code. Please enter the correct 6-digit OTP sent to your email.")

    if datetime.utcnow() > db_otp.expires_at:
        db.query(EmailOTP).filter(EmailOTP.email == user.email).delete()
        db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new OTP.")

    # Single-use OTP: delete after successful verification
    db.query(EmailOTP).filter(EmailOTP.email == user.email).delete()

    wallet = get_or_create_wallet(data.user_id, db)
    if wallet.is_frozen:
        raise HTTPException(status_code=400, detail="Your wallet is frozen. Withdrawals are disabled.")

    withdraw_dec = Decimal(str(round(data.amount, 2)))
    if wallet.balance < withdraw_dec:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance. Available balance is ₹{float(wallet.balance):.2f}."
        )

    # Atomic reduction
    wallet.balance -= withdraw_dec

    dest_desc = f"Bank Account (XXXX XXXX {user.bank_account_number.strip()[-4:]})" if has_bank else f"UPI ID ({user.bank_upi_id})"
    ref_code = f"WD-{uuid.uuid4().hex[:10].upper()}"
    desc = f"₹{data.amount:.2f} withdrawal requested to {dest_desc}"

    txn = Transaction(
        reference=ref_code,
        passenger_id=user.id if user.account_type == "passenger" else None,
        driver_id=user.id if user.account_type == "driver" else None,
        wallet_id=wallet.id,
        amount=withdraw_dec,
        payment_method="bank_transfer",
        status="pending",
        otp_verified=True,
        fraud_status="clear",
        transaction_type="withdrawal",
        description=desc,
        balance_after=wallet.balance,
        idempotency_key=data.idempotency_key,
    )
    db.add(txn)
    db.commit()
    db.refresh(wallet)
    db.refresh(txn)

    return {
        "success": True,
        "message": f"Withdrawal request of ₹{data.amount:.2f} submitted to {dest_desc}. Status: Pending processing.",
        "wallet": wallet_to_dict(wallet),
    }


@router.post("/pay")
def pay_fare(data: PayRequest, db: Session = Depends(get_db)):
    """
    Normal Tap & Go Ride Payment Flow.
    Passenger Wallet -> Internal Tap & Go Ledger -> Driver Wallet.
    RAZORPAY IS NOT USED FOR NORMAL RIDES.
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

    p_wallet = get_or_create_wallet(passenger.id, db)
    if p_wallet.is_frozen:
        raise HTTPException(status_code=400, detail="Your passenger wallet is frozen. Payment failed.")

    fare_dec = Decimal(str(round(data.fare, 2)))
    if p_wallet.balance < fare_dec:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient wallet balance (₹{float(p_wallet.balance):.2f}). Please add funds first."
        )

    driver_id = data.driver_id
    driver_name = data.driver_name
    if not driver_id:
        active_driver = db.query(User).filter(User.account_type == "driver", User.status == "active").first()
        if active_driver:
            driver_id = active_driver.id
            if not driver_name:
                driver_name = active_driver.name
    elif not driver_name:
        driver_obj = db.get(User, driver_id)
        if driver_obj:
            driver_name = driver_obj.name

    if not driver_name:
        driver_name = f"Driver #{driver_id}" if driver_id else "Driver"

    p_wallet.balance -= fare_dec

    d_wallet = None
    if driver_id:
        d_wallet = get_or_create_wallet(driver_id, db)
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

    return {
        "success": True,
        "message": f"Payment of ₹{data.fare:.2f} completed.",
        "wallet": wallet_to_dict(p_wallet),
    }
