import logging
import traceback
from typing import Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal

from app.config import settings
from app.models import PaymentRequest, Transaction, User, Wallet
from app.routes.wallet import get_or_create_wallet, wallet_to_dict

logger = logging.getLogger("payment_verification_service")

class PaymentVerificationService:
    """
    Abstract Payment Verification Service.
    The wallet module and API routes call ONLY this service.
    No wallet code directly depends on email/Outlook or specific gateway APIs.
    """

    def __init__(self):
        self.provider_name = settings.PAYMENT_PROVIDER or "FAMPAY_TEST"

    def verify_payment(self, request_id: int, db: Session, force_check: bool = False) -> Dict[str, Any]:
        """
        Main verification interface method.
        Delegates verification to provider logic, updates payment_requests status,
        and atomically credits the user's wallet upon verified completion.
        """
        logger.info(f"[PaymentVerificationService] Starting verification for request_id={request_id} (force_check={force_check})")
        
        try:
            # Log every pending request currently in the database
            pending_requests = db.query(PaymentRequest).filter(PaymentRequest.status == "Pending").all()
            logger.info(f"[PaymentVerificationService] Active pending requests in DB: count={len(pending_requests)}")
            for pr in pending_requests:
                logger.info(f" - PendingRequest: id={pr.id}, user_id={pr.user_id}, amount={pr.amount}, created_at={pr.created_at}")

            pay_req = db.get(PaymentRequest, request_id)
            if not pay_req:
                logger.error(f"[PaymentVerificationService] Request ID={request_id} not found in database.")
                return {"success": False, "status": "Failed", "message": "Payment request not found."}

            logger.info(f"[PaymentVerificationService] Target request status: '{pay_req.status}'")
            if pay_req.status == "Completed":
                logger.info(f"[PaymentVerificationService] Request ID={request_id} is already Completed.")
                return {
                    "success": True,
                    "status": "Completed",
                    "message": "Payment already completed.",
                    "amount": float(pay_req.amount),
                    "utr": pay_req.utr,
                    "payer_name": pay_req.payer_name,
                }

            now = datetime.now()
            pay_req.last_checked_at = now

            # Delegate verification check to provider implementation
            from app.services.payment.providers.fampay_provider import fampay_provider
            logger.info("[PaymentVerificationService] Invoking provider verification check...")
            provider_result = fampay_provider.check_verification(pay_req, db, force_check=force_check)
            logger.info(f"[PaymentVerificationService] Provider result: verified={provider_result.get('verified')}, message='{provider_result.get('message')}'")

            if not provider_result.get("verified"):
                logger.info("[PaymentVerificationService] Payment not verified yet. Committing last_checked_at timestamp.")
                db.commit()
                return {
                    "success": False,
                    "status": pay_req.status,
                    "message": provider_result.get("message", "Payment verification pending."),
                    "failure_reason": provider_result.get("failure_reason"),
                    "validation_results": provider_result.get("validation_results") or [],
                    "amount": float(pay_req.amount),
                }

            # Match is approved! Credit wallet
            logger.info(f"[PaymentVerificationService] MATCH APPROVED! Invoking wallet credit for user_id={pay_req.user_id}")
            wallet = db.get(Wallet, pay_req.wallet_id)
            if not wallet:
                logger.warning(f"[PaymentVerificationService] Wallet not found for user_id={pay_req.user_id}. Creating new wallet.")
                user = db.get(User, pay_req.user_id)
                wallet = get_or_create_wallet(user.id, db)

            req_amount = float(pay_req.amount)
            amount_dec = Decimal(str(round(req_amount, 2)))
            previous_balance = wallet.balance
            wallet.balance += amount_dec
            logger.info(f"[PaymentVerificationService] Balance updated: previous={previous_balance}, added={amount_dec}, new={wallet.balance}")

            # Update PaymentRequest row
            pay_req.status = "Completed"
            pay_req.provider_transaction_id = provider_result.get("provider_transaction_id") or f"FAM-{pay_req.id}"
            pay_req.utr = provider_result.get("utr") or f"UTR{pay_req.id:08d}"
            pay_req.payer_name = provider_result.get("payer_name") or "FamPay User"
            pay_req.raw_email_id = provider_result.get("raw_email_id")
            pay_req.verified_at = now
            logger.info(f"[PaymentVerificationService] Set PaymentRequest ID={pay_req.id} status to Completed. UTR={pay_req.utr}")

            # Create Transaction ledger entry in MySQL
            ref_code = f"FAM-{pay_req.utr or pay_req.provider_transaction_id or pay_req.id}"
            logger.info(f"[PaymentVerificationService] Inserting Transaction record. Ref={ref_code}")
            
            txn = Transaction(
                reference=ref_code,
                passenger_id=pay_req.user_id,
                wallet_id=wallet.id,
                amount=amount_dec,
                payment_method="FamPay Test",
                status="completed",
                otp_verified=True,
                fraud_status="clear",
                transaction_type="deposit",
                description=f"₹{req_amount:.2f} credited via FamPay Test",
                balance_after=wallet.balance,
                provider="FAMPAY_TEST",
                provider_transaction_id=pay_req.provider_transaction_id,
                utr=pay_req.utr,
                payer_name=pay_req.payer_name,
                payment_request_id=pay_req.id,
                payment_source="FAMPAY_TEST",
                email_received_at=now,
                raw_email_id=pay_req.raw_email_id,
            )
            db.add(txn)
            
            logger.info("[PaymentVerificationService] Committing database changes (Wallet, PaymentRequest, and Transaction)...")
            db.commit()
            
            db.refresh(pay_req)
            db.refresh(wallet)
            logger.info("[PaymentVerificationService] DB transaction committed successfully.")

            return {
                "success": True,
                "status": "Completed",
                "message": f"₹{req_amount:.2f} added successfully via FamPay Test.",
                "amount": req_amount,
                "wallet": wallet_to_dict(wallet),
                "utr": pay_req.utr,
                "payer_name": pay_req.payer_name,
                "validation_results": provider_result.get("validation_results") or [],
            }
        except Exception as e:
            logger.error(f"[PaymentVerificationService] Exception in verify_payment: {e}")
            logger.error(traceback.format_exc())
            return {
                "success": False,
                "status": "Failed",
                "message": f"System error during verification: {str(e)}",
            }

payment_verification_service = PaymentVerificationService()
