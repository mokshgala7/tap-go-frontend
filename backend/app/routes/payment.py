from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PaymentRequest, User
from app.services.payment.fampay.verifier import create_payment_request, parse_fampay_email
from app.services.payment.verification.verification_service import payment_verification_service
from app.services.payment.outlook.imap_client import outlook_imap_client

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


@debug_router.get("/debug/payment-status")
def get_debug_payment_status(db: Session = Depends(get_db)):
    """
    Temporary debug endpoint to diagnose Outlook IMAP connection, parsed email payload,
    and pending requests mapping.
    """
    # 1. Fetch emails to trigger IMAP connection
    emails = []
    try:
        emails = outlook_imap_client.fetch_fampay_emails()
    except Exception as e:
        pass

    # 2. Get latest parsed email details
    latest_parsed = None
    if emails:
        for item in emails:
            parsed = parse_fampay_email(item)
            if parsed:
                latest_parsed = {
                    "raw_email_id": parsed.get("raw_email_id"),
                    "amount": parsed.get("amount"),
                    "utr": parsed.get("utr"),
                    "provider_transaction_id": parsed.get("provider_transaction_id"),
                    "payer_name": parsed.get("payer_name"),
                    "received_at": parsed.get("received_at").isoformat() if parsed.get("received_at") else None,
                    "subject": parsed.get("subject"),
                }
                break

    # 3. Get pending requests
    pending_reqs = db.query(PaymentRequest).filter(PaymentRequest.status == "Pending").all()
    pending_list = []
    for pr in pending_reqs:
        pending_list.append({
            "id": pr.id,
            "user_id": pr.user_id,
            "wallet_id": pr.wallet_id,
            "amount": float(pr.amount),
            "status": pr.status,
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
        })

    # 4. Generate matching diagnostics
    matching_result = "No pending requests or no emails found."
    if pending_list and latest_parsed:
        match_found = False
        for pr in pending_list:
            if abs(pr["amount"] - latest_parsed["amount"]) < 0.01:
                matching_result = f"Potential match found on Amount={pr['amount']} for Request ID={pr['id']}"
                match_found = True
                break
        if not match_found:
            matching_result = f"No amount match found. Pending amounts: {[p['amount'] for p in pending_list]}. Latest email amount: {latest_parsed['amount']}"

    return {
        "imap_host": outlook_imap_client.host,
        "imap_user": outlook_imap_client.user,
        "imap_login_success": outlook_imap_client.last_login_success,
        "inbox_connection_status": outlook_imap_client.last_inbox_success,
        "imap_last_error": outlook_imap_client.last_error,
        "fampay_emails_found_count": len(emails),
        "latest_parsed_payment": latest_parsed,
        "pending_payment_requests": pending_list,
        "matching_result": matching_result,
        "final_verification_status": "Success" if (latest_parsed and pending_list and "Potential match found" in matching_result) else "Pending"
    }
