"""
NFC card payment for the Tap&Go POS terminal (ESP32-S3 + PN532).

POST /api/nfc/pay   An authenticated, active DRIVER (the POS) submits the UID read from a
                    passenger's card plus the fare. Money moves passenger wallet -> that
                    driver's wallet with the same atomic helpers as /api/wallet/pay.

Design decisions
────────────────
- The payee is always the authenticated driver; the body never names a passenger or a driver.
- The passenger is resolved server-side from nfc_cards.card_uid (uppercase hex, no separators).
- Every outcome has one small JSON shape so a microcontroller can parse it:
    {"success": true,  "status": "Completed", "reference": "TXN...", "amount": 12.5, "passenger_name": "Asha"}
    {"success": false, "status": "Failed", "code": "<CODE>", "message": "..."}
  Business failures are HTTP 200; a caller that is not an allowed driver gets HTTP 403 with the
  same body. A missing/expired session is the usual 401, a bad idempotency key a plain 400.
- Nothing about the passenger except their first name is returned (no balance, email or phone).
- Failed taps change nothing and are not stored, so retrying the same key after e.g. a top-up
  simply tries again. A completed payment replays its original result for the same key.

Known demo limitation: the card UID is a plain identifier, not a secret. A UID can be read and
cloned, so there is no cryptographic proof of card possession. OTP/fraud checks and per-card rate
limiting are intentionally out of scope for now (fraud_status stays "clear").
"""
import logging
import re
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NFCCard, Transaction, User
from app.routes.auth import get_current_user
from app.routes.wallet import (
    MAX_PAYMENT_AMOUNT,
    _credit,
    _debit,
    _lock_order,
    get_or_create_wallet,
    to_money,
)
from app.utils.email_service import send_ride_driver_email, send_ride_passenger_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nfc", tags=["NFC Card Payment"])

_UID_SEPARATORS = re.compile(r"[\s:\-]")
_UID_HEX = re.compile(r"^[0-9A-F]+$")
_UID_LENGTHS = (8, 14)          # 4-byte and 7-byte UIDs, as hex characters


def normalize_card_uid(raw: Optional[str]) -> Optional[str]:
    """Canonical form of a chip UID: uppercase hex without separators, 4 or 7 bytes.
    Returns None when the value is not a valid UID."""
    if not isinstance(raw, str):
        return None
    uid = _UID_SEPARATORS.sub("", raw).upper()
    if len(uid) not in _UID_LENGTHS or not _UID_HEX.match(uid):
        return None
    return uid


def mask_card_uid(uid: Optional[str]) -> Optional[str]:
    """UID with all but the last 4 characters hidden, for passenger-facing / log output."""
    if not uid:
        return None
    return "•" * max(0, len(uid) - 4) + uid[-4:]


class NFCPayRequest(BaseModel):
    # Loosely typed on purpose: bad values must come back as a coded failure, not a 422.
    card_uid: Optional[str] = None
    amount: Optional[float] = None
    idempotency_key: Optional[str] = None


def _fail(code: str, message: str, http_status: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"success": False, "status": "Failed", "code": code, "message": message},
    )


def _first_name(name: Optional[str]) -> str:
    parts = (name or "").split()
    return parts[0] if parts else "Passenger"


def _ok(txn: Transaction, passenger: User, idempotent: bool = False) -> dict:
    body = {
        "success": True,
        "status": "Completed",
        "reference": txn.reference,
        "amount": float(txn.amount),
        "passenger_name": _first_name(passenger.name),
    }
    if idempotent:
        body["idempotent"] = True
    return body


@router.post("/pay")
def nfc_pay(
    data: NFCPayRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    driver = current_user
    if driver.account_type != "driver" or driver.status != "active":
        return _fail("DRIVER_NOT_ALLOWED", "Only an active driver terminal can take NFC payments.", 403)

    try:
        amount = to_money(data.amount if data.amount is not None else float("nan"))
    except HTTPException:
        return _fail("AMOUNT_INVALID", "Amount is not valid.")
    if amount > MAX_PAYMENT_AMOUNT:
        return _fail("AMOUNT_INVALID", f"Payments are limited to ₹{MAX_PAYMENT_AMOUNT:.2f} each.")

    key = (data.idempotency_key or "").strip()
    if len(key) < 8 or len(key) > 100:
        raise HTTPException(status_code=400, detail="A valid idempotency key (8-100 chars) is required.")
    scoped_key = f"nfc:{driver.id}:{key}"

    uid = normalize_card_uid(data.card_uid)
    card = db.query(NFCCard).filter(NFCCard.card_uid == uid).first() if uid else None

    def replay():
        existing = db.query(Transaction).filter(Transaction.idempotency_key == scoped_key).first()
        if not existing:
            return None
        if existing.amount != amount or card is None or card.user_id != existing.passenger_id:
            return _fail("IDEMPOTENCY_CONFLICT", "This payment key was already used for a different payment.", 409)
        return _ok(existing, db.get(User, existing.passenger_id), idempotent=True)

    done = replay()
    if done:
        return done

    if card is None:
        return _fail("CARD_UNKNOWN", "Card not recognised.")
    if card.status == "blocked":
        return _fail("CARD_BLOCKED", "This card is blocked.")
    if card.status in ("lost", "replaced"):
        return _fail("CARD_LOST", "This card was reported lost.")
    if card.status != "active":
        return _fail("CARD_UNKNOWN", "Card not recognised.")

    passenger = db.get(User, card.user_id)
    if not passenger or passenger.account_type != "passenger" or passenger.status != "active":
        return _fail("PASSENGER_INACTIVE", "This card's account is not active.")

    # Wallet rows must exist before the money transaction starts (creating one commits).
    p_wallet = get_or_create_wallet(passenger.id, db)
    d_wallet = get_or_create_wallet(driver.id, db)
    if p_wallet.is_frozen:
        return _fail("WALLET_FROZEN", "This card's wallet is frozen.")
    if d_wallet.is_frozen:
        return _fail("DRIVER_NOT_ALLOWED", "This terminal cannot receive payments right now.", 403)

    steps = {
        passenger.id: lambda: _debit(db, passenger.id, amount),
        driver.id: lambda: _credit(db, driver.id, amount),
    }
    for uid_ in _lock_order(passenger.id, driver.id):
        if not steps[uid_]():
            db.rollback()
            if uid_ == passenger.id:
                db.refresh(p_wallet)
                if p_wallet.is_frozen:
                    return _fail("WALLET_FROZEN", "This card's wallet is frozen.")
                return _fail("INSUFFICIENT_BALANCE", "Insufficient balance.")
            return _fail("DRIVER_NOT_ALLOWED", "This terminal cannot receive payments right now.", 403)

    db.refresh(p_wallet)
    ref_code = f"TXN{uuid.uuid4().hex[:10].upper()}"
    txn = Transaction(
        reference=ref_code,
        passenger_id=passenger.id,
        driver_id=driver.id,
        wallet_id=p_wallet.id,
        amount=amount,
        payment_method="NFC",
        status="completed",
        otp_verified=False,
        fraud_status="clear",
        transaction_type="ride_payment",
        description=f"₹{amount:.2f} paid to {driver.name} via NFC",
        balance_after=p_wallet.balance,
        idempotency_key=scoped_key,
    )
    db.add(txn)
    try:
        db.commit()
    except IntegrityError:
        # Another request with the same key committed first: nothing of ours persists.
        db.rollback()
        done = replay()
        if done:
            return done
        logger.warning("[NFCPay] commit conflict for driver %s card ...%s", driver.id, uid[-4:])
        raise HTTPException(status_code=409, detail="Could not record the payment. Please tap again.")
    db.refresh(p_wallet)
    db.refresh(txn)

    # Post-commit notifications (never affect the financial record).
    try:
        if passenger.email:
            send_ride_passenger_email(
                to_email=passenger.email,
                passenger_name=passenger.name,
                fare=float(amount),
                driver_name=driver.name,
                reference=txn.reference,
                status="Successful",
                vehicle_type=driver.vehicle_type,
                vehicle_registration=driver.vehicle_registration,
                payment_method=txn.payment_method,
                balance_after=float(p_wallet.balance),
                created_at=txn.created_at,
            )
    except Exception as e:
        logger.warning(f"[NFCEmail] Passenger receipt failed: {e}")
    try:
        if driver.email:
            send_ride_driver_email(
                to_email=driver.email,
                driver_name=driver.name,
                fare=float(amount),
                passenger_name=passenger.name,
                reference=txn.reference,
                payment_method=txn.payment_method,
            )
    except Exception as e:
        logger.warning(f"[NFCEmail] Driver credit receipt failed: {e}")

    return _ok(txn, passenger)
