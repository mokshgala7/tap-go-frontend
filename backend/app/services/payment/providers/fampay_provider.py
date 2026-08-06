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
        logger.info(
            f"[FamPay Provider] Payment Request Verification Initialized:\n"
            f"  Request ID: {pay_req.id}\n"
            f"  Requested Amount: {pay_req.amount}\n"
            f"  Created At: {pay_req.created_at}\n"
            f"  Status: {pay_req.status}"
        )

        try:
            emails = gmail_imap_client.fetch_fampay_emails()
            logger.info(f"[FamPay Provider] Retrieved {len(emails)} emails from Gmail IMAP client.")

            req_amount = float(pay_req.amount)
            failure_summary_list = []

            for index, item in enumerate(emails):
                imap_uid = item.get("imap_uid") or item.get("id")
                from app.services.payment.fampay.verifier import parse_fampay_email

                logger.info(f"--- Inspecting Email #{index + 1} (IMAP UID: {imap_uid}) ---")
                parsed = parse_fampay_email(item)
                if not parsed:
                    reason_msg = f"Email #{index + 1} (UID: {imap_uid}): ✗ Sender/Format rejected by parser."
                    failure_summary_list.append(reason_msg)
                    logger.warning(
                        f"Email #{index + 1} (UID: {imap_uid})\n"
                        f"✗ Sender / Format validation failed\n"
                        f"Final decision: REJECTED"
                    )
                    continue

                # 1. Amount match check
                parsed_amount = float(parsed["amount"])
                amount_diff = abs(parsed_amount - req_amount)
                amount_ok = amount_diff < 0.01

                # 2. Time validation (Email date must be within 24h prior to payment request creation)
                time_ok = True
                time_fail_reason = ""
                if pay_req.created_at and parsed.get("received_at"):
                    from datetime import timedelta
                    req_created = pay_req.created_at.replace(tzinfo=None) if hasattr(pay_req.created_at, 'tzinfo') and pay_req.created_at.tzinfo else pay_req.created_at
                    email_received = parsed["received_at"].replace(tzinfo=None) if hasattr(parsed["received_at"], 'tzinfo') and parsed["received_at"].tzinfo else parsed["received_at"]
                    window_start = req_created - timedelta(hours=24)
                    if email_received < window_start:
                        time_ok = False
                        time_fail_reason = f"Email received_at ({email_received}) is older than 24h window start ({window_start})"

                # 3. Duplicate protection check
                from app.models import Transaction

                filter_conditions = [PaymentRequest.raw_email_id == parsed["raw_email_id"]]
                if parsed.get("utr"):
                    filter_conditions.append(PaymentRequest.utr == parsed["utr"])

                already_used_req = db.query(PaymentRequest).filter(
                    PaymentRequest.status == "Completed",
                    or_(*filter_conditions)
                ).first()

                already_used_txn = None
                if parsed.get("utr"):
                    already_used_txn = db.query(Transaction).filter(
                        or_(
                            Transaction.utr == parsed["utr"],
                            Transaction.raw_email_id == parsed["raw_email_id"]
                        )
                    ).first()

                dup_email_ok = not (already_used_req or already_used_txn)
                dup_utr_ok = not (already_used_req or already_used_txn)

                # Log verification result for this email in prompt's required format:
                log_lines = [f"Email #{index + 1} (UID: {imap_uid})"]
                log_lines.append("✓ Sender OK")
                
                if amount_ok:
                    log_lines.append(f"✓ Amount OK (Req: ₹{req_amount:.2f}, Parsed: ₹{parsed_amount:.2f}, Diff: 0)")
                else:
                    log_lines.append(f"✗ Amount mismatch (Req: ₹{req_amount:.2f}, Parsed: ₹{parsed_amount:.2f}, Diff: ₹{amount_diff:.2f})")

                if time_ok:
                    log_lines.append("✓ Time OK")
                else:
                    log_lines.append(f"✗ Time validation failed ({time_fail_reason})")

                if dup_email_ok and dup_utr_ok:
                    log_lines.append("✓ Duplicate email/UTR check passed")
                else:
                    log_lines.append(f"✗ Duplicate UTR/Email (UTR '{parsed.get('utr')}' or email ID '{parsed.get('raw_email_id')}' already redeemed)")

                final_approved = amount_ok and time_ok and dup_email_ok and dup_utr_ok
                log_lines.append(f"Final decision: {'APPROVED' if final_approved else 'REJECTED'}")

                logger.info("\n".join(log_lines))

                if final_approved:
                    logger.info(f"[FamPay Provider] Match APPROVED! UTR={parsed['utr']} is fresh and valid for PaymentRequest ID={pay_req.id}.")
                    return {
                        "verified": True,
                        "provider_transaction_id": parsed["provider_transaction_id"],
                        "utr": parsed["utr"],
                        "payer_name": parsed["payer_name"],
                        "raw_email_id": parsed["raw_email_id"],
                    }

                # Record failure reason for summary
                fail_summary_item = f"Email #{index + 1} (UID {imap_uid}): " + " | ".join([line for line in log_lines[1:-1] if line.startswith("✗")])
                failure_summary_list.append(fail_summary_item)

            # If we reach here, verification failed for all checked emails
            if not emails:
                exact_failure_reason = "No emails found in Gmail IMAP INBOX."
            else:
                exact_failure_reason = f"Examined {len(emails)} email(s). None satisfied verification criteria:\n" + "\n".join(failure_summary_list)

            logger.warning(
                f"[FamPay Provider] Verification FAILED for PaymentRequest ID={pay_req.id}.\n"
                f"EXACT FAILURE REASON:\n{exact_failure_reason}"
            )

            return {
                "verified": False,
                "message": "Payment notification email not found yet.",
                "failure_reason": exact_failure_reason,
            }
        except Exception as ex:
            err_msg = f"Verification exception: {str(ex)}"
            logger.error(f"[FamPay Provider] Error in check_verification for request_id={pay_req.id}: {ex}")
            logger.error(traceback.format_exc())

            return {
                "verified": False,
                "message": f"Verification error: {str(ex)}",
                "failure_reason": err_msg,
            }


fampay_provider = FamPayVerificationProvider()
