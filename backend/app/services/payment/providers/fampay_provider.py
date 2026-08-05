import logging
import traceback
from typing import Dict, Any
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PaymentRequest
from app.services.payment.gmail.imap_client import gmail_imap_client

logger = logging.getLogger("fampay_provider")

import urllib.parse


class FamPayVerificationProvider:
    """
    FamPay Verification Provider Implementation.
    Encapsulates UPI URI generation and payment checking strictly via Gmail IMAP.
    """

    def generate_upi_uri(self, amount: float) -> str:
        upi_id = (settings.FAMPAY_UPI_ID or "mokshsaysthanks@fam").strip()
        name = (settings.FAMPAY_MERCHANT_NAME or "Moksh Gala").strip()
        amt_str = f"{int(amount)}" if amount == int(amount) else f"{amount:.2f}".rstrip("0").rstrip(".")
        return f"upi://pay?pa={upi_id}&pn={name}&am={amt_str}&cu=INR"

    def check_verification(self, pay_req: PaymentRequest, db: Session, force_check: bool = False) -> Dict[str, Any]:
        """
        Checks verification status against Gmail IMAP strictly for FamPay / FamApp payment emails.
        STRICT VERIFICATION: Never credits wallet unless a real matching email is verified.
        """
        logger.info(f"[FamPay Provider] Checking verification for request_id={pay_req.id}, amount={pay_req.amount}")

        try:
            emails = gmail_imap_client.fetch_fampay_emails()
            logger.info(f"[FamPay Provider] Retrieved {len(emails)} emails from IMAP client.")

            req_amount = float(pay_req.amount)

            for index, item in enumerate(emails):
                from app.services.payment.fampay.verifier import parse_fampay_email
                logger.info(f"[FamPay Provider] Parsing email index={index}, subject='{item.get('subject')}'")

                parsed = parse_fampay_email(item)
                if not parsed:
                    logger.warning(f"[FamPay Provider] Email index={index} could not be parsed.")
                    continue

                logger.info(
                    f"[FamPay Provider] Parsed details: "
                    f"amount={parsed.get('amount')}, "
                    f"payer_name='{parsed.get('payer_name')}', "
                    f"provider_transaction_id='{parsed.get('provider_transaction_id')}', "
                    f"utr='{parsed.get('utr')}', "
                    f"received_at={parsed.get('received_at')}"
                )

                # Check amount match
                amount_diff = abs(parsed["amount"] - req_amount)
                if amount_diff < 0.01:
                    logger.info(f"[FamPay Provider] Amount MATCHED (diff={amount_diff}). Checking if transaction UTR is already used...")

                    filter_conditions = [PaymentRequest.raw_email_id == parsed["raw_email_id"]]
                    if parsed.get("utr"):
                        filter_conditions.append(PaymentRequest.utr == parsed["utr"])

                    already_used = db.query(PaymentRequest).filter(
                        PaymentRequest.status == "Completed",
                        or_(*filter_conditions)
                    ).first()

                    if already_used:
                        logger.warning(
                            f"[FamPay Provider] Match rejected: email ID={parsed['raw_email_id']} "
                            f"already used by completed PaymentRequest ID={already_used.id}"
                        )
                    else:
                        logger.info(f"[FamPay Provider] Match APPROVED! UTR={parsed['utr']} is fresh.")
                        return {
                            "verified": True,
                            "provider_transaction_id": parsed["provider_transaction_id"],
                            "utr": parsed["utr"],
                            "payer_name": parsed["payer_name"],
                            "raw_email_id": parsed["raw_email_id"],
                        }
                else:
                    logger.info(f"[FamPay Provider] Amount MISMATCH (req={req_amount}, parsed={parsed['amount']}, diff={amount_diff})")

            logger.info("[FamPay Provider] No fresh matching payment email found in IMAP.")

            return {
                "verified": False,
                "message": "Payment notification email not found yet. Please make sure payment was sent via UPI to the QR code above.",
            }
        except Exception as ex:
            logger.error(f"[FamPay Provider] Error in check_verification: {ex}")
            logger.error(traceback.format_exc())

            return {
                "verified": False,
                "message": f"Verification error: {str(ex)}",
            }


fampay_provider = FamPayVerificationProvider()
