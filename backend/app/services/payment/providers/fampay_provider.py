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
        STRICT VERIFICATION: Never credits wallet unless a real matching email is verified within the exact PaymentRequest lifetime.
        """
        from datetime import timedelta
        from app.models import Transaction
        from app.services.payment.fampay.verifier import parse_fampay_email

        req_amount = float(pay_req.amount)
        req_created = pay_req.created_at.replace(tzinfo=None) if hasattr(pay_req.created_at, 'tzinfo') and pay_req.created_at.tzinfo else pay_req.created_at
        req_expires = pay_req.expires_at.replace(tzinfo=None) if hasattr(pay_req, 'expires_at') and pay_req.expires_at and (pay_req.expires_at.replace(tzinfo=None) if hasattr(pay_req.expires_at, 'tzinfo') else pay_req.expires_at) else (req_created + timedelta(minutes=15))

        logger.info(
            f"[FamPay Provider] Payment Request Verification Initialized:\n"
            f"  Request ID: {pay_req.id}\n"
            f"  Requested Amount: ₹{req_amount:.2f}\n"
            f"  Created At: {req_created}\n"
            f"  Expires At: {req_expires}\n"
            f"  Status: {pay_req.status}"
        )

        try:
            emails = gmail_imap_client.fetch_fampay_emails()
            logger.info(f"[FamPay Provider] Retrieved {len(emails)} candidate email(s) from Gmail IMAP client.")

            failure_summary_list = []
            validation_results_summary = []

            for index, item in enumerate(emails):
                imap_uid = item.get("imap_uid") or item.get("id")

                parsed = parse_fampay_email(item)
                if not parsed:
                    reason_msg = f"Email #{index + 1} (UID: {imap_uid}): ✗ Sender/Format rejected by parser (Not from no-reply@famapp.in)."
                    failure_summary_list.append(reason_msg)
                    validation_results_summary.append({
                        "email_uid": imap_uid,
                        "approved": False,
                        "reason": "Sender/Format rejected by parser (Not from no-reply@famapp.in)",
                    })
                    logger.warning(
                        f"--------------------------------\n"
                        f"Payment Request\n"
                        f"--------------------------------\n"
                        f"Request ID: {pay_req.id}\n"
                        f"Amount: ₹{req_amount:.2f}\n"
                        f"created_at: {req_created}\n"
                        f"expires_at: {req_expires}\n\n"
                        f"--------------------------------\n"
                        f"Email Candidate\n"
                        f"--------------------------------\n"
                        f"IMAP UID: {imap_uid}\n"
                        f"Top-level From: '{item.get('from', '')}'\n"
                        f"Subject: '{item.get('subject', '')}'\n\n"
                        f"--------------------------------\n"
                        f"Validation\n"
                        f"--------------------------------\n"
                        f"✗ Sender: Rejected by parser (Not from no-reply@famapp.in)\n\n"
                        f"--------------------------------\n"
                        f"FINAL RESULT\n"
                        f"--------------------------------\n"
                        f"REJECTED: Sender is not no-reply@famapp.in"
                    )
                    continue

                sender_ok = True
                parsed_amount = float(parsed["amount"])
                amount_diff = abs(parsed_amount - req_amount)
                amount_ok = amount_diff < 0.01

                # Strict PaymentRequest lifetime check: created_at <= received_at <= expires_at
                email_received = parsed["received_at"].replace(tzinfo=None) if hasattr(parsed["received_at"], 'tzinfo') and parsed["received_at"].tzinfo else parsed["received_at"]
                
                time_ok = (req_created <= email_received <= req_expires)
                if email_received < req_created:
                    time_msg = f"✗ Time validation failed (Email received at {email_received} is BEFORE PaymentRequest created_at {req_created})"
                elif email_received > req_expires:
                    time_msg = f"✗ Time validation failed (Email received at {email_received} is AFTER PaymentRequest expires_at {req_expires})"
                else:
                    time_msg = f"✓ Time OK (Received at {email_received} is within [{req_created} ... {req_expires}])"

                # Duplicate protection check against BOTH PaymentRequest and Transaction tables
                dup_req_email = db.query(PaymentRequest).filter(
                    PaymentRequest.status == "Completed",
                    PaymentRequest.raw_email_id == parsed["raw_email_id"]
                ).first()

                dup_txn_email = db.query(Transaction).filter(
                    Transaction.raw_email_id == parsed["raw_email_id"]
                ).first()

                dup_email_ok = not (dup_req_email or dup_txn_email)

                dup_req_utr = None
                dup_txn_utr = None
                if parsed.get("utr"):
                    dup_req_utr = db.query(PaymentRequest).filter(
                        PaymentRequest.status == "Completed",
                        PaymentRequest.utr == parsed["utr"]
                    ).first()
                    dup_txn_utr = db.query(Transaction).filter(
                        Transaction.utr == parsed["utr"]
                    ).first()

                dup_utr_ok = not (dup_req_utr or dup_txn_utr)

                # Format structured logging
                log_lines = [
                    "--------------------------------",
                    "Payment Request",
                    "--------------------------------",
                    f"Request ID: {pay_req.id}",
                    f"Amount: ₹{req_amount:.2f}",
                    f"created_at: {req_created}",
                    f"expires_at: {req_expires}",
                    "",
                    "--------------------------------",
                    "Email Candidate",
                    "--------------------------------",
                    f"IMAP UID: {imap_uid}",
                    f"Top-level From: '{parsed.get('top_level_from', '')}'",
                    f"Original Forwarded From: '{parsed.get('original_from', '')}'",
                    f"Subject: '{parsed.get('original_subject') or parsed.get('top_level_subject', '')}'",
                    f"Amount: ₹{parsed_amount:.2f}",
                    f"UTR: '{parsed.get('utr')}'",
                    f"received_at: {email_received}",
                    "",
                    "--------------------------------",
                    "Validation",
                    "--------------------------------",
                    f"✓ Sender (From: {parsed.get('original_from') or parsed.get('top_level_from')})",
                ]

                if amount_ok:
                    log_lines.append(f"✓ Amount OK (Req: ₹{req_amount:.2f}, Parsed: ₹{parsed_amount:.2f})")
                else:
                    log_lines.append(f"✗ Amount mismatch (Req: ₹{req_amount:.2f}, Parsed: ₹{parsed_amount:.2f}, Diff: ₹{amount_diff:.2f})")

                log_lines.append(time_msg)

                if dup_email_ok:
                    log_lines.append(f"✓ Duplicate Email check passed (raw_email_id: '{parsed['raw_email_id']}' never used before)")
                else:
                    used_in = "PaymentRequest" if dup_req_email else "Transaction"
                    log_lines.append(f"✗ Duplicate Email (raw_email_id '{parsed['raw_email_id']}' already redeemed in {used_in})")

                if dup_utr_ok:
                    log_lines.append(f"✓ Duplicate UTR check passed (UTR: '{parsed.get('utr')}' never used before)")
                else:
                    used_in = "PaymentRequest" if dup_req_utr else "Transaction"
                    log_lines.append(f"✗ Duplicate UTR (UTR '{parsed.get('utr')}' already redeemed in {used_in})")

                final_approved = sender_ok and amount_ok and time_ok and dup_email_ok and dup_utr_ok

                log_lines.extend([
                    "",
                    "--------------------------------",
                    "FINAL RESULT",
                    "--------------------------------",
                    f"{'APPROVED' if final_approved else 'REJECTED'}"
                ])

                rejection_reasons = [line for line in log_lines if line.startswith("✗")]
                exact_rejection_reason = " | ".join(rejection_reasons) if rejection_reasons else None
                if not final_approved:
                    log_lines.append(f"Reason: {exact_rejection_reason}")

                logger.info("\n".join(log_lines))

                validation_results_summary.append({
                    "email_uid": imap_uid,
                    "approved": final_approved,
                    "sender_ok": sender_ok,
                    "amount_ok": amount_ok,
                    "time_ok": time_ok,
                    "dup_email_ok": dup_email_ok,
                    "dup_utr_ok": dup_utr_ok,
                    "reason": exact_rejection_reason or "Approved",
                })

                if final_approved:
                    logger.info(f"[FamPay Provider] Match APPROVED! UTR={parsed['utr']} is fresh and valid for PaymentRequest ID={pay_req.id}.")
                    return {
                        "verified": True,
                        "provider_transaction_id": parsed["provider_transaction_id"],
                        "utr": parsed["utr"],
                        "payer_name": parsed["payer_name"],
                        "raw_email_id": parsed["raw_email_id"],
                        "validation_results": validation_results_summary,
                    }

                failure_summary_list.append(f"Email #{index + 1} (UID {imap_uid}): {exact_rejection_reason}")

            # If we reach here, verification failed for all checked emails
            if not emails:
                exact_failure_reason = "No candidate FamPay emails found in Gmail INBOX."
            else:
                exact_failure_reason = f"Examined {len(emails)} candidate email(s). None satisfied verification criteria:\n" + "\n".join(failure_summary_list)

            logger.warning(
                f"[FamPay Provider] Verification FAILED for PaymentRequest ID={pay_req.id}.\n"
                f"EXACT FAILURE REASON:\n{exact_failure_reason}"
            )

            return {
                "verified": False,
                "message": "Payment notification email not found yet.",
                "failure_reason": exact_failure_reason,
                "validation_results": validation_results_summary,
            }
        except Exception as ex:
            err_msg = f"Verification exception: {str(ex)}"
            logger.error(f"[FamPay Provider] Error in check_verification for request_id={pay_req.id}: {ex}")
            logger.error(traceback.format_exc())

            return {
                "verified": False,
                "message": f"Verification error: {str(ex)}",
                "failure_reason": err_msg,
                "validation_results": [],
            }


fampay_provider = FamPayVerificationProvider()
