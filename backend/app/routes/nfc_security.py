"""
NFC Card lifecycle management routes for Tap&Go.

User endpoints: JWT-authenticated. User identity from JWT only.
Admin endpoints: current_admin dependency.

Lifecycle (server-side enforced):
  active  -> blocked | mark_lost
  blocked -> unblock | mark_lost
  lost    -> replace  (via replacement NFCCardOrder only, idempotent)
  replaced -> (terminal, no transitions)

nfc_card_orders table is NEVER modified/deleted. Replacement creates a NEW
NFCCardOrder using the existing model columns and references it via FK.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NFCCard, NFCCardOrder, User, Admin
from app.routes.auth import get_current_user
from app.routes.admin import current_admin
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nfc", tags=["NFC Card Security"])

# Server-side lifecycle transition table
ALLOWED_TRANSITIONS: dict = {
    "active":   {"block", "mark_lost"},
    "blocked":  {"unblock", "mark_lost"},
    "lost":     {"replace"},
    "replaced": set(),            # terminal
}


def nfc_card_to_dict(card: NFCCard) -> dict:
    return {
        "id": card.id,
        "user_id": card.user_id,
        "card_reference": card.card_reference,
        "card_type": card.card_type,
        "status": card.status,
        "blocked_reason": card.blocked_reason,
        "block_requested_at": card.block_requested_at.isoformat() if card.block_requested_at else None,
        "nfc_order_id": card.nfc_order_id,
        "replacement_order_id": card.replacement_order_id,
        "issued_at": card.issued_at.isoformat() if card.issued_at else None,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "updated_at": card.updated_at.isoformat() if card.updated_at else None,
    }


def _get_user_active_card(current_user: User, db: Session) -> NFCCard:
    """Returns the user's most recent non-replaced card."""
    card = db.query(NFCCard).filter(
        NFCCard.user_id == current_user.id
    ).order_by(NFCCard.created_at.desc()).first()
    if not card:
        raise HTTPException(status_code=404, detail="No issued NFC card found for your account.")
    return card


def _assert_transition(card: NFCCard, action: str):
    allowed = ALLOWED_TRANSITIONS.get(card.status, set())
    if action not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Action '{action}' is not allowed for a card in status '{card.status}'. "
                f"Allowed actions from this state: {sorted(allowed) if allowed else 'none (terminal state)'}."
            )
        )


# ── User endpoints (JWT-authenticated) ──────────────────────────────────────

@router.get("/my")
def get_my_cards(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all NFC cards issued to the authenticated user."""
    cards = db.query(NFCCard).filter(
        NFCCard.user_id == current_user.id
    ).order_by(NFCCard.created_at.desc()).all()
    return {"success": True, "cards": [nfc_card_to_dict(c) for c in cards]}


class BlockCardRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/my/block")
def user_block_card(
    data: BlockCardRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Block user's own NFC card. Allowed only from status: active."""
    card = _get_user_active_card(current_user, db)
    _assert_transition(card, "block")
    card.status = "blocked"
    card.blocked_reason = data.reason.strip() if data.reason else "Blocked by user request"
    card.block_requested_at = datetime.utcnow()
    db.commit()
    db.refresh(card)
    return {"success": True, "message": "Your NFC card has been blocked.", "card": nfc_card_to_dict(card)}


@router.post("/my/unblock")
def user_unblock_card(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unblock user's own NFC card. Allowed only from status: blocked."""
    card = _get_user_active_card(current_user, db)
    _assert_transition(card, "unblock")
    card.status = "active"
    card.blocked_reason = None
    card.block_requested_at = None
    db.commit()
    db.refresh(card)
    return {"success": True, "message": "Your NFC card has been unblocked.", "card": nfc_card_to_dict(card)}


@router.post("/my/report-lost")
def user_report_lost(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Report NFC card as lost. Allowed from: active or blocked. Lost is irreversible."""
    card = _get_user_active_card(current_user, db)
    _assert_transition(card, "mark_lost")
    card.status = "lost"
    card.block_requested_at = datetime.utcnow()
    db.commit()
    db.refresh(card)
    return {
        "success": True,
        "message": "Your NFC card has been reported as lost. Please request a replacement.",
        "card": nfc_card_to_dict(card),
    }


class ReplacementRequest(BaseModel):
    """Delivery address for the replacement NFC card order."""
    recipient_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = None
    area: str
    city: str
    state: str
    pincode: str
    card_type: Optional[str] = "standard_nfc"


@router.post("/my/request-replacement")
def user_request_replacement(
    data: ReplacementRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Request a replacement NFC card. Allowed only from status: lost.
    Idempotent: if a replacement order already exists for this card, returns it.
    Creates a new NFCCardOrder (identical to existing order flow), then marks card as replaced.
    """
    card = _get_user_active_card(current_user, db)
    _assert_transition(card, "replace")

    # Idempotency: if replacement_order_id already set, return existing
    if card.replacement_order_id:
        existing_order = db.get(NFCCardOrder, card.replacement_order_id)
        return {
            "success": True,
            "message": "A replacement order for this card already exists.",
            "card": nfc_card_to_dict(card),
            "replacement_order_id": card.replacement_order_id,
            "order_status": existing_order.order_status if existing_order else "unknown",
            "order_reference": existing_order.order_reference if existing_order else None,
        }

    # Create replacement order using existing NFCCardOrder model columns
    new_order = NFCCardOrder(
        order_reference=f"RPL-{uuid.uuid4().hex[:10].upper()}",
        user_id=current_user.id,
        card_type=data.card_type or "standard_nfc",
        card_price=Decimal("50.00"),
        delivery_charge=Decimal("0.00"),
        total_amount=Decimal("50.00"),
        delivery_tier="local",
        recipient_name=data.recipient_name.strip(),
        phone=data.phone.strip(),
        address_line1=data.address_line1.strip(),
        address_line2=data.address_line2.strip() if data.address_line2 else None,
        area=data.area.strip(),
        city=data.city.strip(),
        state=data.state.strip(),
        pincode=data.pincode.strip(),
        order_status="processing",
        payment_status="paid",
        is_demo=False,
        notes=f"Replacement for lost card {card.card_reference}",
    )
    db.add(new_order)
    db.flush()  # get new_order.id before commit

    # Mark old card as replaced (only after order creation succeeds)
    card.status = "replaced"
    card.replacement_order_id = new_order.id

    db.commit()
    db.refresh(card)
    db.refresh(new_order)

    return {
        "success": True,
        "message": "Replacement NFC card order placed. You will receive it at the registered address.",
        "card": nfc_card_to_dict(card),
        "replacement_order_id": new_order.id,
        "order_reference": new_order.order_reference,
    }


# ── Admin endpoints ──────────────────────────────────────────────────────────

class IssueCardRequest(BaseModel):
    user_id: int
    card_reference: Optional[str] = None
    card_type: Optional[str] = "standard_nfc"
    nfc_order_id: Optional[int] = None


@router.post("/admin/issue")
def admin_issue_card(
    data: IssueCardRequest,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """Admin issues an NFC card to a user. Optionally links to existing nfc_card_orders record."""
    user = db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if data.nfc_order_id:
        order = db.get(NFCCardOrder, data.nfc_order_id)
        if not order:
            raise HTTPException(status_code=404, detail="NFC card order not found.")
        if order.user_id != data.user_id:
            raise HTTPException(status_code=400, detail="NFC card order does not belong to this user.")

    card_ref = data.card_reference.strip() if data.card_reference else f"NFC-{uuid.uuid4().hex[:12].upper()}"
    existing = db.query(NFCCard).filter(NFCCard.card_reference == card_ref).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Card reference '{card_ref}' already exists.")

    card = NFCCard(
        user_id=data.user_id,
        card_reference=card_ref,
        card_type=data.card_type or "standard_nfc",
        status="active",
        nfc_order_id=data.nfc_order_id,
        issued_at=datetime.utcnow(),
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return {"success": True, "card": nfc_card_to_dict(card)}


@router.get("/admin/all")
def admin_list_cards(
    card_status: Optional[str] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    page: int = 1,
    page_size: int = 20,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """List all NFC cards. Filterable by status and user_id."""
    query = db.query(NFCCard)
    if card_status:
        query = query.filter(NFCCard.status == card_status)
    if user_id:
        query = query.filter(NFCCard.user_id == user_id)
    total = query.count()
    cards = query.order_by(NFCCard.created_at.desc()).offset(
        (max(page, 1) - 1) * min(page_size, 100)
    ).limit(min(page_size, 100)).all()
    return {
        "items": [nfc_card_to_dict(c) for c in cards],
        "total": total,
        "page": page,
        "page_size": min(page_size, 100),
    }


class AdminCardActionRequest(BaseModel):
    action: str   # block | unblock | mark_lost | replace
    reason: Optional[str] = None
    # Required when action == "replace"
    recipient_name: Optional[str] = None
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    area: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None


@router.post("/admin/{card_id}/action")
def admin_card_action(
    card_id: int,
    data: AdminCardActionRequest,
    admin: Admin = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """
    Admin performs a lifecycle action on an NFC card.
    Server-side lifecycle enforcement via ALLOWED_TRANSITIONS.
    Replacement is idempotent.
    """
    card = db.get(NFCCard, card_id)
    if not card:
        raise HTTPException(status_code=404, detail="NFC card not found.")

    action = data.action.strip().lower()
    _assert_transition(card, action)

    if action == "block":
        card.status = "blocked"
        card.blocked_reason = data.reason.strip() if data.reason else "Blocked by admin"
        card.block_requested_at = datetime.utcnow()

    elif action == "unblock":
        card.status = "active"
        card.blocked_reason = None
        card.block_requested_at = None

    elif action == "mark_lost":
        card.status = "lost"
        card.block_requested_at = datetime.utcnow()

    elif action == "replace":
        # Idempotency: if already replaced with an order, return
        if card.replacement_order_id:
            db.commit()
            return {
                "success": True,
                "message": "Replacement order already exists.",
                "card": nfc_card_to_dict(card),
                "replacement_order_id": card.replacement_order_id,
            }

        required = [data.recipient_name, data.phone, data.address_line1, data.area, data.city, data.state, data.pincode]
        if not all(required):
            raise HTTPException(
                status_code=400,
                detail="Replacement requires: recipient_name, phone, address_line1, area, city, state, pincode."
            )

        new_order = NFCCardOrder(
            order_reference=f"RPL-{uuid.uuid4().hex[:10].upper()}",
            user_id=card.user_id,
            card_type=card.card_type,
            card_price=Decimal("50.00"),
            delivery_charge=Decimal("0.00"),
            total_amount=Decimal("50.00"),
            delivery_tier="local",
            recipient_name=data.recipient_name.strip(),
            phone=data.phone.strip(),
            address_line1=data.address_line1.strip(),
            address_line2=data.address_line2.strip() if data.address_line2 else None,
            area=data.area.strip(),
            city=data.city.strip(),
            state=data.state.strip(),
            pincode=data.pincode.strip(),
            order_status="processing",
            payment_status="paid",
            is_demo=False,
            notes=f"Admin replacement for lost card {card.card_reference}",
        )
        db.add(new_order)
        db.flush()

        card.status = "replaced"
        card.replacement_order_id = new_order.id

    db.commit()
    db.refresh(card)
    return {"success": True, "card": nfc_card_to_dict(card)}
