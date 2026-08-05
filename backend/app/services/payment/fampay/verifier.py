import re
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PaymentRequest, Transaction, User, Wallet
from app.routes.wallet import get_or_create_wallet, wallet_to_dict
from app.services.payment.gmail.imap_client import gmail_imap_client

logger = logging.getLogger("fampay_verifier")


def generate_upi_uri(amount: float) -> str:
    """
    Generates standard UPI URI for FamPay account.
    Example: upi://pay?pa=mokshsaysthanks@fam&pn=Moksh Gala&am=1&cu=INR
    """
    upi_id = (settings.FAMPAY_UPI_ID or "mokshsaysthanks@fam").strip()
    name = (settings.FAMPAY_MERCHANT_NAME or "Moksh Gala").strip()
    amt_str = f"{int(amount)}" if amount == int(amount) else f"{amount:.2f}".rstrip("0").rstrip(".")
    return f"upi://pay?pa={upi_id}&pn={name}&am={amt_str}&cu=INR"


def parse_fampay_email(email_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parses FamPay / FamApp / FamX payment notification email text/HTML.
    Extracts Amount, Payer Name, Transaction ID, UTR, and Received Timestamp.
    """
    try:
        raw_id = email_item.get("id")
        subject = email_item.get("subject", "")
        body_content = email_item.get("body", {}).get("content", "")
        received_str = email_item.get("receivedDateTime", "")

        # Clean HTML tags for text matching
        clean_text = re.sub(r"<[^>]+>", " ", body_content)
        full_text = f"{subject} {clean_text}"

        # 1. Extract Amount (supports ₹, Rs., INR, \u20b9, or text like "received 14.0")
        amt_match = re.search(r"(?:₹|Rs\.?|INR|\u20b9)\s*([\d,]+(?:\.\d{1,2})?)", full_text, re.IGNORECASE)
        if not amt_match:
            amt_match = re.search(r"(?:received|credited|paid|payment of)\s+(?:₹|Rs\.?|INR|\u20b9)?\s*([\d,]+(?:\.\d{1,2})?)", full_text, re.IGNORECASE)

        if not amt_match:
            return None

        val_str = amt_match.group(1).replace(",", "").strip()
        if not val_str:
            return None

        try:
            amount_val = float(val_str)
        except ValueError:
            return None

        # 2. Extract UTR / RRN (12 digits or alphanumeric reference)
        utr_match = re.search(r"(?:utr|rrn|ref(?:erence)?(?:\s*no)?)\s*[:\-]?\s*([A-Za-z0-9]{10,18})", full_text, re.IGNORECASE)
        utr_val = utr_match.group(1) if utr_match else None

        # 3. Extract Transaction ID
        txn_match = re.search(r"(?:txn|transaction)\s*(?:id|no)?\s*[:\-]?\s*([A-Za-z0-9]{8,24})", full_text, re.IGNORECASE)
        txn_id_val = txn_match.group(1) if txn_match else (utr_val or f"FAM-{raw_id[:10] if raw_id else 'TXN'}")

        # 4. Extract Payer Name (e.g., "from Moksh Gala")
        payer_match = re.search(r"(?:from|by|sender)\s+([A-Za-z\s]{2,40})(?:\.|\s+via|\s+to|\s+on|\s*$)", full_text, re.IGNORECASE)
        payer_name = payer_match.group(1).strip() if payer_match else "FamPay User"

        received_dt = datetime.now()
        if received_str:
            try:
                import email.utils
                from datetime import timezone
                dt_parsed = email.utils.parsedate_to_datetime(received_str)
                if dt_parsed:
                    received_dt = dt_parsed.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass

        return {
            "raw_email_id": raw_id,
            "amount": amount_val,
            "utr": utr_val,
            "provider_transaction_id": txn_id_val,
            "payer_name": payer_name,
            "received_at": received_dt,
            "subject": subject,
        }
    except Exception as e:
        logger.error(f"[FamPay] Email parse error: {e}")
        return None


def create_payment_request(user_id: int, amount: float, db: Session) -> PaymentRequest:
    """
    Creates a new Pending PaymentRequest record in MySQL and generates UPI URI.
    """
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found.")

    wallet = get_or_create_wallet(user_id, db)
    upi_uri = generate_upi_uri(amount)
    expires_at = datetime.now() + timedelta(minutes=15)

    pay_req = PaymentRequest(
        user_id=user.id,
        wallet_id=wallet.id,
        amount=Decimal(str(round(amount, 2))),
        upi_uri=upi_uri,
        status="Pending",
        provider="FAMPAY_TEST",
        expires_at=expires_at,
        created_at=datetime.now(),
    )
    db.add(pay_req)
    db.commit()
    db.refresh(pay_req)
    return pay_req
