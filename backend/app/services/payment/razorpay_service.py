import hmac
import hashlib
import uuid
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)

try:
    import razorpay
except ImportError:
    razorpay = None


class RazorpayService:
    def __init__(self):
        self._client = None

    def get_client(self):
        key_id = settings.RAZORPAY_KEY_ID
        key_secret = settings.RAZORPAY_KEY_SECRET
        if not key_id or not key_secret:
            raise ValueError(
                "Razorpay API credentials missing. Please configure RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in environment variables."
            )
        if razorpay is None:
            raise RuntimeError("razorpay package is not installed. Please run `pip install razorpay`.")
        
        return razorpay.Client(auth=(key_id, key_secret))

    def create_order(self, amount_in_rupees: float, notes: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Creates a Razorpay Order.
        Amount is converted to paise (1 Rupee = 100 Paise).
        Minimum amount is 100 paise (₹1.00).
        """
        if amount_in_rupees < 1.0:
            raise ValueError("Minimum order amount is ₹1.00 (100 paise).")

        amount_paise = int(round(amount_in_rupees * 100))
        receipt_ref = f"rcpt_{uuid.uuid4().hex[:12]}"

        key_id = settings.RAZORPAY_KEY_ID
        key_secret = settings.RAZORPAY_KEY_SECRET

        if not key_id or not key_secret:
            # Fallback for development testing when keys are not set yet
            logger.warning("[Razorpay] Credentials not set in environment. Returning fallback structure for testing.")
            order_id = f"order_demo_{uuid.uuid4().hex[:14]}"
            return {
                "id": order_id,
                "order_id": order_id,
                "amount": amount_paise,
                "currency": "INR",
                "receipt": receipt_ref,
                "key_id": key_id or "rzp_test_placeholder",
                "is_mock": True,
            }

        client = self.get_client()
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_ref,
            "notes": notes or {"purpose": "Tap&Go Wallet Add Money"},
        }
        order = client.order.create(data=order_data)
        return {
            "id": order["id"],
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "receipt": order["receipt"],
            "key_id": key_id,
            "is_mock": False,
        }

    def verify_payment_signature(
        self, razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str
    ) -> bool:
        """
        Verifies Razorpay HMAC SHA256 Signature.
        generated_signature = HMAC-SHA256(order_id + "|" + payment_id, secret)
        """
        key_secret = settings.RAZORPAY_KEY_SECRET
        if not key_secret:
            # If no secret is configured yet, check if payment is a test mock
            if razorpay_order_id.startswith("order_demo_"):
                logger.warning("[Razorpay] Verifying mock order signature in development mode.")
                return True
            return False

        if razorpay is not None:
            try:
                client = self.get_client()
                client.utility.verify_payment_signature(
                    {
                        "razorpay_order_id": razorpay_order_id,
                        "razorpay_payment_id": razorpay_payment_id,
                        "razorpay_signature": razorpay_signature,
                    }
                )
                return True
            except Exception as e:
                logger.error(f"[Razorpay] Signature verification via SDK failed: {e}")
                pass

        # Manual HMAC verification
        body = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        expected_sig = hmac.new(key_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, razorpay_signature)

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verifies Razorpay Webhook Signature using RAZORPAY_WEBHOOK_SECRET or RAZORPAY_KEY_SECRET."""
        secret = settings.RAZORPAY_WEBHOOK_SECRET or settings.RAZORPAY_KEY_SECRET
        if not secret:
            return False
        expected_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_sig, signature)


razorpay_service = RazorpayService()
