import re
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PaymentRequest, Transaction, User, Wallet
from app.routes.wallet import get_or_create_wallet, wallet_to_dict

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
    Parses FamPay payment notification email text/HTML.
    Supports both direct emails from no-reply@famapp.in and Outlook/Hotmail auto-forwarded emails.
    Extracts Amount, Payer Name, Transaction ID, UTR, and Received Timestamp.
    """
    try:
        raw_id = email_item.get("id")
        imap_uid = email_item.get("imap_uid") or raw_id
        top_level_from = email_item.get("from", "")
        top_level_subject = email_item.get("subject", "")
        body_content = email_item.get("body", {}).get("content", "")
        received_str = email_item.get("receivedDateTime", "")

        # Clean HTML tags for text matching
        clean_text = re.sub(r"<[^>]+>", " ", body_content)

        # ── 1. Extract Original Forwarded Sender & Subject (if Outlook auto-forwarded) ────
        fwd_from_match = re.search(r"From:\s*([^\r\n]+(?:famapp\.in|famapp|fampay)[^\r\n]*)", clean_text, re.IGNORECASE)
        if not fwd_from_match:
            fwd_from_match = re.search(r"From:\s*([^\r\n]+)", clean_text, re.IGNORECASE)

        fwd_subj_match = re.search(r"Subject:\s*([^\r\n]+)", clean_text, re.IGNORECASE)

        original_from = fwd_from_match.group(1).strip() if fwd_from_match else "None"
        original_subject = fwd_subj_match.group(1).strip() if fwd_subj_match else "None"

        # ── 2. Explicit Debug Logging ──────────────────────────────────────────
        logger.info(f"[FamPay Parser] Parsing email (UID: {imap_uid}):")
        logger.info(f"[FamPay Parser]  Top-level sender: '{top_level_from}'")
        logger.info(f"[FamPay Parser]  Top-level Subject: '{top_level_subject}'")
        logger.info(f"[FamPay Parser]  Original forwarded sender: '{original_from}'")
        logger.info(f"[FamPay Parser]  Original forwarded Subject: '{original_subject}'")

        # ── 3. Security Verification: Validate FamApp Sender ──────────────────
        # Email MUST be sent directly by no-reply@famapp.in OR contain original sender no-reply@famapp.in inside forwarded header block
        is_direct_famapp = "no-reply@famapp.in" in top_level_from.lower() or "famapp.in" in top_level_from.lower()
        is_forwarded_famapp = "no-reply@famapp.in" in original_from.lower() or "famapp.in" in original_from.lower() or "famapp" in original_from.lower()

        if not (is_direct_famapp or is_forwarded_famapp):
            fail_reason = (
                f"Sender verification FAILED: Top-level sender '{top_level_from}' and original sender '{original_from}' "
                f"do not match FamApp sender domain ('no-reply@famapp.in' / 'famapp.in')."
            )
            logger.warning(f"[FamPay Parser] [UID: {imap_uid}] {fail_reason}")
            return None

        # ── 4. Extract Amount ────────────────────────────────────────────────
        full_text = f"{top_level_subject} {clean_text}"

        amt_match = re.search(r"(?:₹|Rs\.?|INR|\u20b9)\s*([\d,]+(?:\.\d{1,2})?)", full_text, re.IGNORECASE)
        if not amt_match:
            amt_match = re.search(r"(?:received|credited|paid|payment of)\s+(?:₹|Rs\.?|INR|\u20b9)?\s*([\d,]+(?:\.\d{1,2})?)", full_text, re.IGNORECASE)

        if not amt_match:
            fail_reason = f"Amount extraction FAILED: Could not locate numeric payment amount (₹/Rs/INR) in email text."
            logger.warning(f"[FamPay Parser] [UID: {imap_uid}] {fail_reason}")
            return None

        val_str = amt_match.group(1).replace(",", "").strip()
        if not val_str:
            fail_reason = f"Amount extraction FAILED: Amount text string was empty after cleanup."
            logger.warning(f"[FamPay Parser] [UID: {imap_uid}] {fail_reason}")
            return None

        try:
            amount_val = float(val_str)
        except ValueError as ve:
            fail_reason = f"Amount parsing FAILED: Could not convert '{val_str}' to float ({ve})."
            logger.warning(f"[FamPay Parser] [UID: {imap_uid}] {fail_reason}")
            return None

        # ── 5. Extract UTR / RRN (12 digits) ──────────────────────────────────
        utr_match = re.search(r"(?:utr|rrn|ref(?:erence)?(?:\s*no)?)\s*[:\-]?\s*([A-Za-z0-9]{10,18})", full_text, re.IGNORECASE)
        utr_val = utr_match.group(1) if utr_match else None

        # ── 6. Extract Transaction ID ─────────────────────────────────────────
        txn_match = re.search(r"(?:txn|transaction)\s*(?:id|no)?\s*[:\-]?\s*([A-Za-z0-9]{8,24})", full_text, re.IGNORECASE)
        txn_id_val = txn_match.group(1) if txn_match else (utr_val or f"FAM-{raw_id[:10] if raw_id else 'TXN'}")

        # ── 7. Extract Payer Name ──────────────────────────────────────────────
        payer_match = re.search(r"(?:from|by|sender)\s+([A-Za-z\s]{2,40})(?:\.|\s+via|\s+to|\s+on|\s*$)", clean_text, re.IGNORECASE)
        payer_name = payer_match.group(1).strip() if payer_match else "FamPay User"

        received_dt = datetime.now(timezone.utc).replace(tzinfo=None)
        if received_str:
            try:
                import email.utils
                dt_parsed = email.utils.parsedate_to_datetime(received_str)
                if dt_parsed:
                    received_dt = dt_parsed.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass

        logger.info(
            f"[FamPay Parser] Parse SUCCESS for Email UID: {imap_uid}\n"
            f"  Top-level sender: '{top_level_from}'\n"
            f"  Original forwarded sender: '{original_from}'\n"
            f"  Parsed amount: {amount_val}\n"
            f"  Parsed UTR: {utr_val}\n"
            f"  Parsed transaction ID: {txn_id_val}\n"
            f"  Parsed payer: '{payer_name}'\n"
            f"  Parsed received_at: {received_dt}"
        )

        return {
            "raw_email_id": raw_id,
            "imap_uid": imap_uid,
            "top_level_from": top_level_from,
            "top_level_subject": top_level_subject,
            "original_from": original_from,
            "original_subject": original_subject,
            "amount": amount_val,
            "utr": utr_val,
            "provider_transaction_id": txn_id_val,
            "payer_name": payer_name,
            "received_at": received_dt,
        }
    except Exception as e:
        fail_reason = f"Unhandled exception during parsing: {e}"
        logger.error(f"[FamPay Parser] [UID: {email_item.get('id')}] {fail_reason}")
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
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    expires_at = now_utc + timedelta(minutes=15)

    pay_req = PaymentRequest(
        user_id=user.id,
        wallet_id=wallet.id,
        amount=Decimal(str(round(amount, 2))),
        upi_uri=upi_uri,
        status="Pending",
        provider="FAMPAY_TEST",
        expires_at=expires_at,
        created_at=now_utc,
    )
    db.add(pay_req)
    db.commit()
    db.refresh(pay_req)
    return pay_req
