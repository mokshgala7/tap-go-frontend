import uuid
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import NFCCardOrder, User, Admin

router = APIRouter(prefix="/api/card-order", tags=["nfc_card_orders"])

# ── Pydantic Request & Response Schemas ─────────────────────────────────────

class CalculateDeliveryRequest(BaseModel):
    city: str
    state: str
    pincode: str

class CardOrderCreateRequest(BaseModel):
    user_id: int
    recipient_name: str
    phone: str
    address_line1: str
    address_line2: Optional[str] = None
    area: str
    city: str
    state: str
    pincode: str

class StatusUpdateRequest(BaseModel):
    order_status: str

# ── Helper Calculation Function ──────────────────────────────────────────────

def calculate_delivery_charge_info(city: str, state: str, pincode: str):
    clean_city = (city or "").strip().lower()
    clean_state = (state or "").strip().lower()
    clean_pin = (pincode or "").strip()

    # Tier 1: Local Mumbai Metro Region
    if (
        clean_city in ["mumbai", "navi mumbai", "thane", "kalyan", "dombivli"]
        or any(clean_pin.startswith(prefix) for prefix in ["400", "401", "410"])
    ):
        return {
            "tier": "local",
            "tier_name": "Local Mumbai Metro Region Delivery",
            "delivery_charge": settings.LOCAL_DELIVERY_CHARGE,
        }

    # Tier 2: Maharashtra Regional (Outside Mumbai)
    if clean_state == "maharashtra" or any(clean_pin.startswith(prefix) for prefix in ["41", "42", "43", "44"]):
        return {
            "tier": "regional",
            "tier_name": "Maharashtra Regional Delivery",
            "delivery_charge": settings.REGIONAL_DELIVERY_CHARGE,
        }

    # Tier 3: Rest of India (National)
    return {
        "tier": "national",
        "tier_name": "Rest of India National Delivery",
        "delivery_charge": settings.NATIONAL_DELIVERY_CHARGE,
    }

def order_to_dict(order: NFCCardOrder):
    return {
        "id": order.id,
        "order_reference": order.order_reference,
        "user_id": order.user_id,
        "card_type": order.card_type,
        "card_price": float(order.card_price),
        "delivery_charge": float(order.delivery_charge),
        "total_amount": float(order.total_amount),
        "delivery_tier": order.delivery_tier,
        "recipient_name": order.recipient_name,
        "phone": order.phone,
        "address_line1": order.address_line1,
        "address_line2": order.address_line2,
        "area": order.area,
        "city": order.city,
        "state": order.state,
        "pincode": order.pincode,
        "order_status": order.order_status,
        "payment_status": order.payment_status,
        "is_demo": order.is_demo,
        "notes": order.notes,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }

# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/calculate-delivery")
def calculate_delivery(data: CalculateDeliveryRequest):
    if not data.pincode or len(data.pincode.strip()) != 6 or not data.pincode.strip().isdigit():
        raise HTTPException(status_code=400, detail="Please enter a valid 6-digit Indian PIN code.")

    if not data.city or not data.city.strip():
        raise HTTPException(status_code=400, detail="City is required for delivery calculation.")

    if not data.state or not data.state.strip():
        raise HTTPException(status_code=400, detail="State is required for delivery calculation.")

    info = calculate_delivery_charge_info(data.city, data.state, data.pincode)
    card_price = settings.NFC_CARD_PRICE
    delivery_charge = info["delivery_charge"]
    total_amount = round(card_price + delivery_charge, 2)

    return {
        "success": True,
        "card_price": card_price,
        "delivery_charge": delivery_charge,
        "total_amount": total_amount,
        "delivery_tier": info["tier"],
        "tier_name": info["tier_name"],
    }


@router.post("/create")
def create_card_order(data: CardOrderCreateRequest, db: Session = Depends(get_db)):
    # 1. Input Validations
    if not data.recipient_name or not data.recipient_name.strip():
        raise HTTPException(status_code=400, detail="Recipient full name is required.")

    clean_phone = data.phone.strip().replace(" ", "").replace("-", "")
    if not clean_phone or len(clean_phone) < 10 or not clean_phone.isdigit():
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")

    if not data.address_line1 or not data.address_line1.strip():
        raise HTTPException(status_code=400, detail="Address Line 1 is required.")

    if not data.area or not data.area.strip():
        raise HTTPException(status_code=400, detail="Area / Locality is required.")

    if not data.city or not data.city.strip():
        raise HTTPException(status_code=400, detail="City is required.")

    if not data.state or not data.state.strip():
        raise HTTPException(status_code=400, detail="State is required.")

    clean_pin = data.pincode.strip()
    if not clean_pin or len(clean_pin) != 6 or not clean_pin.isdigit():
        raise HTTPException(status_code=400, detail="Please enter a valid 6-digit Indian PIN code.")

    user = db.get(User, data.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    # 2. Server-side Independent Price & Delivery Calculation
    delivery_info = calculate_delivery_charge_info(data.city, data.state, clean_pin)
    card_price_dec = Decimal(str(settings.NFC_CARD_PRICE))
    delivery_dec = Decimal(str(delivery_info["delivery_charge"]))
    total_dec = card_price_dec + delivery_dec

    order_ref = f"NFC-ORD-{uuid.uuid4().hex[:8].upper()}"

    # 3. Check Demo Mode vs Production Mode
    if settings.DEMO_MODE:
        order = NFCCardOrder(
            order_reference=order_ref,
            user_id=user.id,
            card_type="standard_nfc",
            card_price=card_price_dec,
            delivery_charge=delivery_dec,
            total_amount=total_dec,
            delivery_tier=delivery_info["tier"],
            recipient_name=data.recipient_name.strip(),
            phone=clean_phone,
            address_line1=data.address_line1.strip(),
            address_line2=data.address_line2.strip() if data.address_line2 else None,
            area=data.area.strip(),
            city=data.city.strip(),
            state=data.state.strip(),
            pincode=clean_pin,
            order_status="processing",
            payment_status="simulated",
            is_demo=True,
            notes="Academic Demonstration Order — Simulated Payment",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        return {
            "success": True,
            "is_demo": True,
            "message": "Demo Order Created. This is an academic demonstration order. No real payment has been processed and no physical shipment will be initiated from Demo Mode.",
            "order": order_to_dict(order),
        }
    else:
        # Production Mode: Requires external payment gateway verification
        order = NFCCardOrder(
            order_reference=order_ref,
            user_id=user.id,
            card_type="standard_nfc",
            card_price=card_price_dec,
            delivery_charge=delivery_dec,
            total_amount=total_dec,
            delivery_tier=delivery_info["tier"],
            recipient_name=data.recipient_name.strip(),
            phone=clean_phone,
            address_line1=data.address_line1.strip(),
            address_line2=data.address_line2.strip() if data.address_line2 else None,
            area=data.area.strip(),
            city=data.city.strip(),
            state=data.state.strip(),
            pincode=clean_pin,
            order_status="pending_payment",
            payment_status="pending",
            is_demo=False,
            notes="Awaiting Payment Gateway Callback",
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        return {
            "success": False,
            "is_demo": False,
            "message": "NFC card payment is currently unavailable because the payment gateway is not configured.",
            "order": order_to_dict(order),
            "support_email": "tapandgosupport@gmail.com",
            "support_phone": "8779914564",
        }


@router.get("/user/{user_id}")
def get_user_card_orders(user_id: int, db: Session = Depends(get_db)):
    orders = db.query(NFCCardOrder).filter(NFCCardOrder.user_id == user_id).order_by(NFCCardOrder.created_at.desc()).all()
    return {
        "success": True,
        "orders": [order_to_dict(o) for o in orders]
    }


@router.get("/admin/all")
def get_all_card_orders(
    x_admin_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    orders = db.query(NFCCardOrder).order_by(NFCCardOrder.created_at.desc()).all()
    return {
        "success": True,
        "orders": [order_to_dict(o) for o in orders]
    }


@router.patch("/admin/{order_id}/status")
def update_card_order_status(
    order_id: int,
    data: StatusUpdateRequest,
    x_admin_id: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    order = db.get(NFCCardOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="NFC Card Order not found.")

    valid_statuses = ["pending_payment", "processing", "dispatched", "delivered", "cancelled", "failed"]
    if data.order_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid order status. Allowed: {valid_statuses}")

    order.order_status = data.order_status
    if data.order_status == "delivered":
        order.payment_status = "paid"

    db.commit()
    db.refresh(order)

    return {
        "success": True,
        "message": f"Order status updated to {data.order_status}.",
        "order": order_to_dict(order)
    }
