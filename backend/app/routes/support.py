"""
Support ticket routes for Tap&Go.

User endpoints: JWT-authenticated (get_current_user). User identity derived from token,
never from request body/path.

Admin endpoints: current_admin dependency (X-Admin-Id header).
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import SupportTicket, User, Admin
from app.routes.auth import get_current_user
from app.routes.admin import current_admin
from app.utils.email_service import send_support_ticket_created, send_support_ticket_reply
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/support", tags=["Support"])

VALID_CATEGORIES = {"billing", "technical", "nfc_card", "account", "other"}
VALID_PRIORITIES = {"low", "medium", "high", "urgent"}
VALID_STATUSES = {"open", "in_progress", "resolved", "closed"}


class CreateTicketRequest(BaseModel):
    name: str
    email: str
    phone: str
    category: str
    priority: str
    subject: str
    message: str


class AdminReplyRequest(BaseModel):
    admin_reply: str
    status: Optional[str] = None


class AdminStatusRequest(BaseModel):
    status: str


def ticket_to_dict(ticket: SupportTicket) -> dict:
    return {
        "id": ticket.id,
        "user_id": ticket.user_id,
        "name": ticket.name,
        "email": ticket.email,
        "phone": ticket.phone,
        "category": ticket.category,
        "priority": ticket.priority,
        "subject": ticket.subject,
        "message": ticket.message,
        "status": ticket.status,
        "admin_reply": ticket.admin_reply,
        "replied_by": ticket.replied_by,
        "replied_at": ticket.replied_at.isoformat() if ticket.replied_at else None,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
    }


# ── User endpoints (JWT-authenticated) ──────────────────────────────────────

@router.post("/")
def create_ticket(
    data: CreateTicketRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a support ticket. User identity derived from JWT (not from body)."""
    if not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="Name is required.")
    if not data.email or not data.email.strip():
        raise HTTPException(status_code=400, detail="Email is required.")
    if not data.phone or not data.phone.strip():
        raise HTTPException(status_code=400, detail="Phone is required.")
    if not data.subject or not data.subject.strip():
        raise HTTPException(status_code=400, detail="Subject is required.")
    if not data.message or not data.message.strip():
        raise HTTPException(status_code=400, detail="Message is required.")
    if data.category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Allowed: {sorted(VALID_CATEGORIES)}")
    if data.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority. Allowed: {sorted(VALID_PRIORITIES)}")

    ticket = SupportTicket(
        user_id=current_user.id,
        name=data.name.strip(),
        email=data.email.strip(),
        phone=data.phone.strip(),
        category=data.category,
        priority=data.priority,
        subject=data.subject.strip(),
        message=data.message.strip(),
        status="open",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    try:
        send_support_ticket_created(
            to_email=current_user.email,
            user_name=current_user.name,
            ticket_id=ticket.id,
            subject=ticket.subject,
        )
    except Exception as e:
        logger.warning(f"[SupportEmail] Ticket creation email failed: {e}")

    return {"success": True, "ticket": ticket_to_dict(ticket)}


@router.get("/my")
def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the authenticated user's support tickets. User identity from JWT."""
    tickets = db.query(SupportTicket).filter(
        SupportTicket.user_id == current_user.id
    ).order_by(SupportTicket.created_at.desc()).all()
    return {"success": True, "tickets": [ticket_to_dict(t) for t in tickets]}


# ── Admin endpoints ──────────────────────────────────────────────────────────

@router.get("/admin/all")
def admin_list_tickets(
    ticket_status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    page: int = 1,
    page_size: int = 20,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """List all support tickets with optional filtering."""
    query = db.query(SupportTicket)
    if ticket_status:
        query = query.filter(SupportTicket.status == ticket_status)
    if priority:
        query = query.filter(SupportTicket.priority == priority)
    if category:
        query = query.filter(SupportTicket.category == category)
    total = query.count()
    tickets = query.order_by(SupportTicket.created_at.desc()).offset(
        (max(page, 1) - 1) * min(page_size, 100)
    ).limit(min(page_size, 100)).all()
    return {
        "items": [ticket_to_dict(t) for t in tickets],
        "total": total,
        "page": page,
        "page_size": min(page_size, 100),
    }


@router.patch("/admin/{ticket_id}/reply")
def admin_reply_ticket(
    ticket_id: int,
    data: AdminReplyRequest,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """Admin replies to a support ticket. Optionally updates status."""
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found.")
    if not data.admin_reply or not data.admin_reply.strip():
        raise HTTPException(status_code=400, detail="Reply text is required.")
    if data.status and data.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {sorted(VALID_STATUSES)}")

    ticket.admin_reply = data.admin_reply.strip()
    ticket.replied_by = admin.id
    ticket.replied_at = datetime.utcnow()
    if data.status:
        ticket.status = data.status
    elif ticket.status == "open":
        ticket.status = "in_progress"
    db.commit()
    db.refresh(ticket)

    user = db.get(User, ticket.user_id)
    if user and user.email:
        try:
            send_support_ticket_reply(
                to_email=user.email,
                user_name=user.name,
                ticket_id=ticket.id,
                subject=ticket.subject,
                reply=data.admin_reply.strip(),
            )
        except Exception as e:
            logger.warning(f"[SupportEmail] Reply email failed: {e}")

    return {"success": True, "ticket": ticket_to_dict(ticket)}


@router.patch("/admin/{ticket_id}/status")
def admin_update_ticket_status(
    ticket_id: int,
    data: AdminStatusRequest,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """Update the status of a support ticket."""
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found.")
    if data.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {sorted(VALID_STATUSES)}")
    ticket.status = data.status
    db.commit()
    db.refresh(ticket)
    return {"success": True, "ticket": ticket_to_dict(ticket)}
