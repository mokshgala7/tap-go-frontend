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
    {"success": false, "status": "Failed", "code": "<CODE>", "message": "...", "reference": "TXN..."}
  Business failures are HTTP 200; a caller that is not an allowed driver gets HTTP 403 with the
  same body. A missing/expired session is the usual 401, a bad idempotency key a plain 400.
- Nothing about the passenger except their first name is returned (no balance, email or phone).
- Failed taps are recorded: once the driver and the idempotency key are valid, every business
  failure (CARD_UNKNOWN, CARD_BLOCKED, CARD_LOST, PASSENGER_INACTIVE, WALLET_FROZEN,
  INSUFFICIENT_BALANCE, AMOUNT_INVALID) inserts a Transaction with status="failed" and
  failure_code, and never touches a wallet balance. DRIVER_NOT_ALLOWED, IDEMPOTENCY_CONFLICT,
  401 and the bad-key 400 are not recorded.
- The failed row owns the idempotency key, so a retry with the same key replays the SAME failure
  ("idempotent": true) without a second row or email. The firmware uses a new key per fare.
- All emails (success receipts and failure notices) are sent AFTER the response with FastAPI
  BackgroundTasks, from plain values captured before the response. The POS never waits on
  SES/PDF generation, and an email problem is only ever logged, never a payment problem.
- Failure emails to a card owner are throttled per passenger: at most one per
  NFC_FAILURE_EMAIL_COOLDOWN_SECONDS (default 300; 0 = no throttle). Every failure is still a row.
  The throttle is process-local (like the admin login throttle): it resets on restart.

Known demo limitation: the card UID is a plain identifier, not a secret. A UID can be read and
cloned, so there is no cryptographic proof of card possession. OTP/fraud checks and per-card rate
limiting are intentionally out of scope for now (fraud_status stays "clear").
"""
import logging
import os
import re
import threading
import time
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NFCCard, Transaction, User, Wallet
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
from app.utils.nfc_failure_email import send_nfc_failure_email

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


# Message shown on the POS, per code (a replay returns exactly the same text).
FAILURE_MESSAGES = {
    "CARD_UNKNOWN": "Card not recognised.",
    "CARD_BLOCKED": "This card is blocked.",
    "CARD_LOST": "This card was reported lost.",
    "PASSENGER_INACTIVE": "This card's account is not active.",
    "WALLET_FROZEN": "This card's wallet is frozen.",
    "INSUFFICIENT_BALANCE": "Insufficient balance.",
    "AMOUNT_INVALID": "Amount is not valid.",
    "DRIVER_NOT_ALLOWED": "Only an active driver terminal can take NFC payments.",
    "IDEMPOTENCY_CONFLICT": "This payment key was already used for a different payment.",
}
# Short reason stored in the failed transaction's description.
FAILURE_REASONS = {
    "CARD_UNKNOWN": "card not recognised",
    "CARD_BLOCKED": "card blocked",
    "CARD_LOST": "card reported lost",
    "PASSENGER_INACTIVE": "passenger account not active",
    "WALLET_FROZEN": "wallet frozen",
    "INSUFFICIENT_BALANCE": "insufficient balance",
    "AMOUNT_INVALID": "invalid amount",
}
# Failure emails go to the owner for every recorded failure except an unknown card.
_NO_OWNER_EMAIL = {"CARD_UNKNOWN"}
DEFAULT_FAILURE_EMAIL_COOLDOWN = 300

_failure_email_lock = threading.Lock()
_failure_email_last_sent: dict = {}          # passenger_id -> time.monotonic() of the last failure email


def _failure_email_cooldown() -> int:
    try:
        return max(0, int(os.getenv("NFC_FAILURE_EMAIL_COOLDOWN_SECONDS", str(DEFAULT_FAILURE_EMAIL_COOLDOWN))))
    except ValueError:
        return DEFAULT_FAILURE_EMAIL_COOLDOWN


def _may_send_failure_email(passenger_id: int) -> bool:
    cooldown = _failure_email_cooldown()
    if cooldown <= 0:
        return True
    now = time.monotonic()
    with _failure_email_lock:
        last = _failure_email_last_sent.get(passenger_id)
        if last is not None and now - last < cooldown:
            return False
        _failure_email_last_sent[passenger_id] = now
        return True


def _fail(code: str, message: Optional[str] = None, http_status: int = 200,
          reference: Optional[str] = None, idempotent: bool = False) -> JSONResponse:
    content = {"success": False, "status": "Failed", "code": code, "message": message or FAILURE_MESSAGES[code]}
    if reference:
        content["reference"] = reference
    if idempotent:
        content["idempotent"] = True
    return JSONResponse(status_code=http_status, content=content)


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


def _parse_amount(raw):
    """(amount, None) when usable, else (None, message)."""
    try:
        dec = to_money(raw if raw is not None else float("nan"))
    except HTTPException:
        return None, FAILURE_MESSAGES["AMOUNT_INVALID"]
    if dec > MAX_PAYMENT_AMOUNT:
        return None, f"Payments are limited to \u20b9{MAX_PAYMENT_AMOUNT:.2f} each."
    return dec, None


# ── background email tasks (run after the response; they never raise) ────────

def _send_passenger_receipt(*, reference, fare, passenger_email, passenger_name, driver_name,
                            vehicle_type, vehicle_registration, payment_method, balance_after,
                            created_at, **_ignored):
    """Delivery is logged to email_logs by send_email itself."""
    try:
        if passenger_email and not send_ride_passenger_email(
            to_email=passenger_email,
            passenger_name=passenger_name,
            fare=fare,
            driver_name=driver_name,
            reference=reference,
            status="Successful",
            vehicle_type=vehicle_type,
            vehicle_registration=vehicle_registration,
            payment_method=payment_method,
            balance_after=balance_after,
            created_at=created_at,
        ):
            logger.warning(f"[NFCEmail] Passenger receipt for {reference} was not delivered")
    except Exception as e:
        logger.warning(f"[NFCEmail] Passenger receipt failed: {e}")


def _send_driver_receipt(*, reference, fare, passenger_name, driver_email, driver_name,
                         payment_method, **_ignored):
    try:
        if driver_email and not send_ride_driver_email(
            to_email=driver_email,
            driver_name=driver_name,
            fare=fare,
            passenger_name=passenger_name,
            reference=reference,
            payment_method=payment_method,
        ):
            logger.warning(f"[NFCEmail] Driver credit receipt for {reference} was not delivered")
    except Exception as e:
        logger.warning(f"[NFCEmail] Driver credit receipt failed: {e}")


def _send_failure_notice(**kwargs):
    reference = kwargs.get("reference")
    try:
        if not send_nfc_failure_email(**kwargs):
            logger.warning(f"[NFCEmail] Failure notice for {reference} was not delivered")
    except Exception as e:
        logger.warning(f"[NFCEmail] Failure notice for {reference} failed: {e}")


@router.post("/pay")
def nfc_pay(
    data: NFCPayRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    driver = current_user
    if driver.account_type != "driver" or driver.status != "active":
        return _fail("DRIVER_NOT_ALLOWED", http_status=403)

    key = (data.idempotency_key or "").strip()
    if len(key) < 8 or len(key) > 100:
        raise HTTPException(status_code=400, detail="A valid idempotency key (8-100 chars) is required.")
    scoped_key = f"nfc:{driver.id}:{key}"

    amount, amount_problem = _parse_amount(data.amount)
    uid = normalize_card_uid(data.card_uid)
    card = db.query(NFCCard).filter(NFCCard.card_uid == uid).first() if uid else None

    def replay():
        """The stored outcome for this key, or None. A key reused for a different tap is a conflict."""
        existing = db.query(Transaction).filter(Transaction.idempotency_key == scoped_key).first()
        if not existing:
            return None
        conflict = _fail("IDEMPOTENCY_CONFLICT", http_status=409)
        if existing.status == "completed":
            if (amount_problem or existing.amount != amount or card is None
                    or card.user_id != existing.passenger_id):
                return conflict
            return _ok(existing, db.get(User, existing.passenger_id), idempotent=True)
        if existing.status == "failed" and existing.failure_code in FAILURE_REASONS:
            code = existing.failure_code
            if code == "AMOUNT_INVALID":
                if not amount_problem:
                    return conflict
                return _fail(code, amount_problem, reference=existing.reference, idempotent=True)
            if amount_problem or existing.amount != amount:
                return conflict
            if existing.passenger_id is not None and (card is None or card.user_id != existing.passenger_id):
                return conflict
            return _fail(code, reference=existing.reference, idempotent=True)
        return conflict

    done = replay()
    if done:
        return done

    def record_failure(code: str, message: Optional[str] = None, owner: Optional[User] = None,
                       wallet: Optional[Wallet] = None, detail: str = ""):
        """Store the failed tap (no wallet is touched), answer the POS and queue the owner's email."""
        shown_amount = Decimal("0.00") if code == "AMOUNT_INVALID" else amount
        owner_id = owner.id if owner is not None else None
        wallet_id = wallet.id if wallet is not None else (
            db.query(Wallet.id).filter(Wallet.user_id == owner_id).scalar() if owner_id else None
        )
        txn = Transaction(
            reference=f"TXN{uuid.uuid4().hex[:10].upper()}",
            passenger_id=owner_id,
            driver_id=driver.id,
            wallet_id=wallet_id,
            amount=shown_amount,
            payment_method="NFC",
            status="failed",
            otp_verified=False,
            fraud_status="clear",
            transaction_type="ride_payment",
            description=f"NFC payment failed: {FAILURE_REASONS[code]}{detail}",
            balance_after=None,
            idempotency_key=scoped_key,
            failure_code=code,
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
            raise HTTPException(status_code=409, detail="Could not record the payment. Please tap again.")

        if owner is not None and code not in _NO_OWNER_EMAIL and owner.email and _may_send_failure_email(owner.id):
            background_tasks.add_task(
                _send_failure_notice,
                to_email=owner.email,
                passenger_name=owner.name,
                fare=float(shown_amount) if shown_amount else None,
                driver_name=driver.name,
                reference=txn.reference,
                code=code,
                vehicle_type=driver.vehicle_type,
                vehicle_registration=driver.vehicle_registration,
                wallet_balance=float(wallet.balance) if wallet is not None and code == "INSUFFICIENT_BALANCE" else None,
                created_at=txn.created_at,
            )
        return _fail(code, message, reference=txn.reference)

    if amount_problem:
        return record_failure("AMOUNT_INVALID", amount_problem,
                              owner=db.get(User, card.user_id) if card else None,
                              detail=f" (received: {str(data.amount)[:40]})")

    if card is None:
        return record_failure("CARD_UNKNOWN", detail=f" ({mask_card_uid(uid) if uid else 'invalid UID'})")
    owner = db.get(User, card.user_id)
    if card.status == "blocked":
        return record_failure("CARD_BLOCKED", owner=owner)
    if card.status in ("lost", "replaced"):
        return record_failure("CARD_LOST", owner=owner)
    if card.status != "active":
        return record_failure("CARD_UNKNOWN", detail=f" ({mask_card_uid(uid)})")

    passenger = owner
    if not passenger or passenger.account_type != "passenger" or passenger.status != "active":
        return record_failure("PASSENGER_INACTIVE", owner=passenger)

    # Wallet rows must exist before the money transaction starts (creating one commits).
    p_wallet = get_or_create_wallet(passenger.id, db)
    d_wallet = get_or_create_wallet(driver.id, db)
    if p_wallet.is_frozen:
        return record_failure("WALLET_FROZEN", owner=passenger, wallet=p_wallet)
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
                    return record_failure("WALLET_FROZEN", owner=passenger, wallet=p_wallet)
                return record_failure("INSUFFICIENT_BALANCE", owner=passenger, wallet=p_wallet)
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
        description=f"\u20b9{amount:.2f} paid to {driver.name} via NFC",
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

    # Receipts run after the response. The request's DB session is closed by then, so everything
    # the emails need is copied into plain values here.
    receipt = dict(
        reference=txn.reference,
        fare=float(amount),
        passenger_email=passenger.email,
        passenger_name=passenger.name,
        driver_email=driver.email,
        driver_name=driver.name,
        vehicle_type=driver.vehicle_type,
        vehicle_registration=driver.vehicle_registration,
        payment_method=txn.payment_method,
        balance_after=float(p_wallet.balance),
        created_at=txn.created_at,
    )
    response = _ok(txn, passenger)
    background_tasks.add_task(_send_passenger_receipt, **receipt)
    background_tasks.add_task(_send_driver_receipt, **receipt)
    return response
