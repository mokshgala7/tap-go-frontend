from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PaymentRequest, User
from app.services.payment.fampay.verifier import create_payment_request, parse_fampay_email
from app.services.payment.verification.verification_service import payment_verification_service
from app.services.payment.gmail.imap_client import gmail_imap_client

router = APIRouter(prefix="/api/payment", tags=["Payment"])
debug_router = APIRouter(tags=["Debug"])


class CreatePaymentRequest(BaseModel):
    user_id: int
    amount: float
    payment_method: Optional[str] = "fampay"


@router.post("/create-request")
def handle_create_payment_request(data: CreatePaymentRequest, db: Session = Depends(get_db)):
    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")

    user = db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    try:
        req = create_payment_request(data.user_id, data.amount, db)
        return {
            "success": True,
            "payment_request_id": req.id,
            "upi_uri": req.upi_uri,
            "amount": float(req.amount),
            "status": req.status,
            "provider": req.provider,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "expires_at": req.expires_at.isoformat() if req.expires_at else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{request_id}")
def check_payment_status(request_id: int, db: Session = Depends(get_db)):
    req = db.get(PaymentRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Payment request not found.")

    res = payment_verification_service.verify_payment(request_id, db, force_check=False)
    return res


@router.post("/check-now/{request_id}")
def force_check_payment(request_id: int, db: Session = Depends(get_db)):
    req = db.get(PaymentRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Payment request not found.")

    res = payment_verification_service.verify_payment(request_id, db, force_check=True)
    return res


@router.get("/debug/status")
def get_payment_debug_status(db: Session = Depends(get_db)):
    """
    Temporary debug endpoint: GET /api/payment/debug/status
    Traces Gmail IMAP login, mailbox selection, parsed email payload,
    pending requests, and payment verification diagnostic result.
    """
    emails = []
    try:
        emails = gmail_imap_client.fetch_fampay_emails()
    except Exception:
        pass

    latest_email = None
    if emails:
        for item in emails:
            parsed = parse_fampay_email(item)
            if parsed:
                latest_email = {
                    "from": parsed.get("original_from") or parsed.get("top_level_from"),
                    "subject": parsed.get("original_subject") or parsed.get("top_level_subject"),
                    "amount": parsed.get("amount"),
                    "utr": parsed.get("utr"),
                    "received_at": parsed.get("received_at").isoformat() if parsed.get("received_at") else None,
                }
                break

        if not latest_email and len(emails) > 0:
            first = emails[0]
            latest_email = {
                "from": first.get("from", ""),
                "subject": first.get("subject", ""),
                "amount": None,
                "utr": None,
                "received_at": first.get("receivedDateTime", ""),
            }

    pending_reqs = db.query(PaymentRequest).filter(PaymentRequest.status == "Pending").all()
    pending_list = []
    for pr in pending_reqs:
        pending_list.append({
            "id": pr.id,
            "amount": float(pr.amount),
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
            "status": pr.status,
        })

    verification_result = "Pending"
    failure_reason = None

    if pending_reqs:
        latest_req = pending_reqs[-1]
        res = payment_verification_service.verify_payment(latest_req.id, db, force_check=True)
        if res.get("success") and res.get("status") == "Completed":
            verification_result = "Verified"
            failure_reason = None
        else:
            verification_result = "Failed"
            failure_reason = res.get("failure_reason") or res.get("message")
    else:
        verification_result = "No pending payment requests"
        failure_reason = "No pending payment requests found in DB."

    return {
        "gmail_login_success": gmail_imap_client.last_login_success,
        "gmail_account": gmail_imap_client.user or "Not configured",
        "mailbox_selected": gmail_imap_client.last_inbox_success,
        "emails_found": len(emails),
        "latest_email": latest_email,
        "pending_payment_requests": pending_list,
        "verification_result": verification_result,
        "failure_reason": failure_reason,
    }


@debug_router.get("/debug/payment-status")
def get_debug_payment_status(db: Session = Depends(get_db)):
    """Legacy alias endpoint for backward compatibility."""
    return get_payment_debug_status(db)

