"""Live administrative APIs for the Tap&Go control centre.

The routes deliberately sit beside the existing authentication API so the
Passenger and Driver flows remain unchanged.  All list endpoints use MySQL
records; no seed or client-side demo data is returned.
"""
from datetime import datetime
from decimal import Decimal
from io import StringIO
import csv
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    ActivityLog, Admin, EditRequest, FraudAlert, ProjectSetting, Transaction,
    User, UserDocument, Wallet,
)
from app.utils.security import hash_password, verify_password

router = APIRouter(prefix="/api/admin", tags=["Administration"])


class AdminLogin(BaseModel):
    email: str
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    status: Optional[str] = None


class ActionRequest(BaseModel):
    action: str = Field(pattern="^(activate|suspend|approve|reject|delete)$")


class WalletAction(BaseModel):
    frozen: bool


class EditReview(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")


class FraudReview(BaseModel):
    action: str = Field(pattern="^(safe|block|freeze)$")


class SettingUpdate(BaseModel):
    value: Optional[str] = None


def ensure_default_admin(db: Session) -> Admin:
    """Provision the documented temporary account once, as a database record."""
    admin = db.query(Admin).filter(Admin.email == settings.ADMIN_EMAIL).first()
    if not admin:
        admin = Admin(
            email=settings.ADMIN_EMAIL,
            password_hash=hash_password(settings.ADMIN_PASSWORD),
            name="Tap&Go Administrator",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return admin


def current_admin(
    x_admin_id: Optional[int] = Header(default=None), db: Session = Depends(get_db)
) -> Admin:
    if not x_admin_id:
        raise HTTPException(status_code=401, detail="Administrator login is required.")
    admin = db.query(Admin).filter(Admin.id == x_admin_id, Admin.is_active.is_(True)).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Administrator session is invalid.")
    return admin


def to_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def document_rows(user: User, db: Session):
    """Expose every stored document attribute and future document-table entry."""
    rows = []
    for column in User.__table__.columns:
        value = getattr(user, column.name)
        if value and (column.name.endswith("_document") or column.name == "profile_photo"):
            rows.append({
                "id": f"user-{column.name}",
                "type": column.name.replace("_", " ").title(),
                "file_path": value,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            })
    for document in db.query(UserDocument).filter(UserDocument.user_id == user.id).all():
        rows.append({
            "id": document.id,
            "type": document.document_type,
            "file_path": document.file_path,
            "created_at": document.created_at.isoformat() if document.created_at else None,
        })
    return rows


def user_row(user: User, db: Session, detailed: bool = False):
    wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
    data = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "account_type": user.account_type,
        "status": user.status or "active",
        "city": user.city,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "wallet_balance": float(wallet.balance) if wallet else 0,
        "wallet_frozen": bool(wallet.is_frozen) if wallet else False,
    }
    if detailed:
        for column in User.__table__.columns:
            if column.name not in {"password_hash"}:
                data[column.name] = to_value(getattr(user, column.name))
        data["documents"] = document_rows(user, db)
    return data


def log(db: Session, admin: Admin, action: str, entity_type: str, entity_id: Optional[int], details: str = ""):
    db.add(ActivityLog(
        admin_id=admin.id, action=action, entity_type=entity_type,
        entity_id=entity_id, details=details,
    ))


@router.post("/login")
def login(payload: AdminLogin, db: Session = Depends(get_db)):
    ensure_default_admin(db)
    admin = db.query(Admin).filter(Admin.email == payload.email.strip().lower()).first()
    if not admin or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid administrator credentials.")
    log(db, admin, "login", "admin", admin.id, "Administrator signed in")
    db.commit()
    return {"success": True, "admin": {"id": admin.id, "name": admin.name, "email": admin.email}}


@router.get("/dashboard")
def dashboard(admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    count = lambda *criteria: db.query(func.count(User.id)).filter(*criteria).scalar() or 0
    transaction_count = db.query(func.count(Transaction.id)).scalar() or 0
    today_transactions = db.query(func.count(Transaction.id)).filter(
        func.date(Transaction.created_at) == datetime.utcnow().date()
    ).scalar() or 0
    wallet_balance = db.query(func.coalesce(func.sum(Wallet.balance), 0)).scalar() or 0
    revenue = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.status == "completed"
    ).scalar() or 0
    return {
        "total_drivers": count(User.account_type == "driver"),
        "active_drivers": count(User.account_type == "driver", User.status == "active"),
        "pending_drivers": count(User.account_type == "driver", User.status == "pending"),
        "suspended_drivers": count(User.account_type == "driver", User.status == "suspended"),
        "total_passengers": count(User.account_type == "passenger"),
        "active_passengers": count(User.account_type == "passenger", User.status == "active"),
        "total_transactions": transaction_count,
        "today_transactions": today_transactions,
        "wallet_balance": float(wallet_balance),
        "revenue": float(revenue),
        "fraud_alerts": db.query(func.count(FraudAlert.id)).filter(FraudAlert.status == "open").scalar() or 0,
        "pending_edit_requests": db.query(func.count(EditRequest.id)).filter(EditRequest.status == "pending").scalar() or 0,
    }


@router.get("/users")
def users(
    account_type: Optional[str] = Query(default=None, pattern="^(driver|passenger)$"),
    search: str = "", status: Optional[str] = None, page: int = 1, page_size: int = 20,
    admin: Admin = Depends(current_admin), db: Session = Depends(get_db),
):
    query = db.query(User)
    if account_type:
        query = query.filter(User.account_type == account_type)
    if status:
        query = query.filter(User.status == status)
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(User.name.ilike(term), User.email.ilike(term), User.phone.ilike(term)))
    total = query.count()
    records = query.order_by(User.created_at.desc()).offset((max(page, 1) - 1) * min(page_size, 100)).limit(min(page_size, 100)).all()
    return {"items": [user_row(user, db) for user in records], "total": total, "page": page, "page_size": min(page_size, 100)}


@router.get("/users/{user_id}")
def user_detail(user_id: int, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    data = user_row(user, db, detailed=True)
    data["transactions"] = transaction_rows(db.query(Transaction).filter(
        or_(Transaction.passenger_id == user.id, Transaction.driver_id == user.id)
    ).order_by(Transaction.created_at.desc()).limit(50).all(), db)
    return data


@router.put("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(user, key, value)
    log(db, admin, "update", "user", user.id, "Updated user profile")
    db.commit()
    db.refresh(user)
    return user_row(user, db, detailed=True)


@router.post("/users/{user_id}/action")
def user_action(user_id: int, payload: ActionRequest, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if payload.action == "delete":
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if wallet:
            db.query(Transaction).filter(Transaction.wallet_id == wallet.id).update({Transaction.wallet_id: None}, synchronize_session=False)
            db.delete(wallet)
        db.query(UserDocument).filter(UserDocument.user_id == user.id).delete()
        db.query(EditRequest).filter(EditRequest.user_id == user.id).delete()
        db.query(Transaction).filter(Transaction.passenger_id == user.id).update({Transaction.passenger_id: None}, synchronize_session=False)
        db.query(Transaction).filter(Transaction.driver_id == user.id).update({Transaction.driver_id: None}, synchronize_session=False)
        db.query(FraudAlert).filter(FraudAlert.user_id == user.id).update({FraudAlert.user_id: None}, synchronize_session=False)
        db.query(ActivityLog).filter(ActivityLog.user_id == user.id).update({ActivityLog.user_id: None}, synchronize_session=False)
        db.delete(user)
    elif payload.action == "approve":
        user.status = "active"
    elif payload.action == "reject":
        user.status = "rejected"
    else:
        user.status = "active" if payload.action == "activate" else "suspended"
    log(db, admin, payload.action, "user", user_id, f"{payload.action.title()} user")
    db.commit()
    return {"success": True, "action": payload.action}


def transaction_rows(rows, db: Session):
    user_ids = {value for row in rows for value in (row.passenger_id, row.driver_id) if value}
    people = {person.id: person.name for person in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    return [{
        "id": row.id, "reference": row.reference, "passenger": people.get(row.passenger_id),
        "driver": people.get(row.driver_id), "amount": float(row.amount), "payment_method": row.payment_method,
        "status": row.status, "otp_verified": row.otp_verified, "fraud_status": row.fraud_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]


@router.get("/transactions")
def transactions(
    search: str = "", status: Optional[str] = None, payment_method: Optional[str] = None,
    page: int = 1, page_size: int = 20, admin: Admin = Depends(current_admin), db: Session = Depends(get_db),
):
    query = db.query(Transaction)
    if search.strip():
        query = query.filter(Transaction.reference.ilike(f"%{search.strip()}%"))
    if status:
        query = query.filter(Transaction.status == status)
    if payment_method:
        query = query.filter(Transaction.payment_method == payment_method)
    total = query.count()
    rows = query.order_by(Transaction.created_at.desc()).offset((max(page, 1) - 1) * min(page_size, 100)).limit(min(page_size, 100)).all()
    return {"items": transaction_rows(rows, db), "total": total, "page": page, "page_size": min(page_size, 100)}


@router.get("/transactions/export")
def export_transactions(admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Transaction ID", "Passenger", "Driver", "Amount", "Method", "Status", "Date"])
    for row in transaction_rows(db.query(Transaction).order_by(Transaction.created_at.desc()).all(), db):
        writer.writerow([row["reference"], row["passenger"] or "", row["driver"] or "", row["amount"], row["payment_method"], row["status"], row["created_at"]])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=tapgo-transactions.csv"})


@router.get("/wallets")
def wallets(search: str = "", page: int = 1, page_size: int = 20, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    query = db.query(Wallet, User).join(User, Wallet.user_id == User.id)
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(User.name.ilike(term), User.email.ilike(term)))
    total = query.count()
    rows = query.order_by(Wallet.updated_at.desc()).offset((max(page, 1) - 1) * min(page_size, 100)).limit(min(page_size, 100)).all()
    return {"items": [{"id": wallet.id, "user_id": user.id, "name": user.name, "email": user.email, "account_type": user.account_type, "balance": float(wallet.balance), "is_frozen": wallet.is_frozen, "updated_at": wallet.updated_at.isoformat() if wallet.updated_at else None} for wallet, user in rows], "total": total, "page": page, "page_size": min(page_size, 100)}


@router.post("/wallets/{wallet_id}")
def set_wallet_state(wallet_id: int, payload: WalletAction, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")
    wallet.is_frozen = payload.frozen
    log(db, admin, "freeze" if payload.frozen else "unfreeze", "wallet", wallet.id, "Changed wallet state")
    db.commit()
    return {"success": True, "is_frozen": wallet.is_frozen}


@router.get("/documents")
def documents(search: str = "", page: int = 1, page_size: int = 30, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    query = db.query(User)
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(User.name.ilike(term), User.email.ilike(term)))
    records = query.order_by(User.created_at.desc()).all()
    rows = [{"user_id": user.id, "user_name": user.name, "account_type": user.account_type, **document} for user in records for document in document_rows(user, db)]
    start, size = (max(page, 1) - 1) * min(page_size, 100), min(page_size, 100)
    return {"items": rows[start:start + size], "total": len(rows), "page": page, "page_size": size}


@router.get("/edit-requests")
def edit_requests(status: Optional[str] = None, page: int = 1, page_size: int = 20, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    query = db.query(EditRequest, User).join(User, EditRequest.user_id == User.id)
    if status:
        query = query.filter(EditRequest.status == status)
    total = query.count()
    rows = query.order_by(EditRequest.created_at.desc()).offset((max(page, 1) - 1) * min(page_size, 100)).limit(min(page_size, 100)).all()
    return {"items": [{"id": request.id, "user_id": user.id, "user_name": user.name, "field_name": request.field_name, "previous_value": request.previous_value, "new_value": request.new_value, "proof_path": request.proof_path, "reason": request.reason, "status": request.status, "created_at": request.created_at.isoformat() if request.created_at else None, "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None} for request, user in rows], "total": total, "page": page, "page_size": min(page_size, 100)}


@router.post("/edit-requests/{request_id}/review")
def review_edit_request(request_id: int, payload: EditReview, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    request = db.get(EditRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Edit request not found.")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="This request has already been reviewed.")
    user = db.get(User, request.user_id)
    new_status = payload.action + "d"  # "approved" or "rejected"
    request.status = new_status
    request.reviewed_by = admin.id
    request.reviewed_at = datetime.utcnow()

    if user:
        request_state = "approved" if payload.action == "approve" else "rejected"
        if request.field_name == "bank":
            user.bank_request_status = request_state
        elif request.field_name == "documents":
            user.doc_request_status = request_state
        elif request.field_name == "phone":
            user.phone_request_status = request_state
        elif payload.action == "approve" and request.field_name in User.__table__.columns and request.new_value is not None:
            setattr(user, request.field_name, request.new_value)

    log(db, admin, payload.action, "edit_request", request.id, f"Reviewed edit request #{request.id} for user #{request.user_id} ({request.field_name}): {payload.action}")
    db.commit()
    return {"success": True, "status": request.status}


@router.get("/fraud-alerts")
def fraud_alerts(page: int = 1, page_size: int = 20, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    query = db.query(FraudAlert)
    total = query.count()
    rows = query.order_by(FraudAlert.created_at.desc()).offset((max(page, 1) - 1) * min(page_size, 100)).limit(min(page_size, 100)).all()
    return {"items": [{"id": alert.id, "user_id": alert.user_id, "transaction_id": alert.transaction_id, "risk_score": alert.risk_score, "reason": alert.reason, "status": alert.status, "created_at": alert.created_at.isoformat() if alert.created_at else None} for alert in rows], "total": total, "page": page, "page_size": min(page_size, 100)}


@router.post("/fraud-alerts/{alert_id}/review")
def review_fraud_alert(alert_id: int, payload: FraudReview, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    alert = db.get(FraudAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Fraud alert not found.")
    alert.status, alert.reviewed_at = payload.action, datetime.utcnow()
    user = db.get(User, alert.user_id) if alert.user_id else None
    if user and payload.action == "block":
        user.status = "suspended"
    if user and payload.action == "freeze":
        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if wallet:
            wallet.is_frozen = True
    log(db, admin, payload.action, "fraud_alert", alert.id, "Reviewed fraud alert")
    db.commit()
    return {"success": True, "status": alert.status}


@router.get("/activity-logs")
def activity_logs(page: int = 1, page_size: int = 30, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    query = db.query(ActivityLog)
    total = query.count()
    rows = query.order_by(ActivityLog.created_at.desc()).offset((max(page, 1) - 1) * min(page_size, 100)).limit(min(page_size, 100)).all()
    return {"items": [{"id": row.id, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "details": row.details, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows], "total": total, "page": page, "page_size": min(page_size, 100)}


@router.get("/settings")
def get_settings(admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    return {"items": [{"key": item.key, "value": item.value, "updated_at": item.updated_at.isoformat() if item.updated_at else None} for item in db.query(ProjectSetting).order_by(ProjectSetting.key).all()]}


@router.put("/settings/{key}")
def update_setting(key: str, payload: SettingUpdate, admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    setting = db.get(ProjectSetting, key)
    if not setting:
        setting = ProjectSetting(key=key, value=payload.value)
        db.add(setting)
    else:
        setting.value = payload.value
    log(db, admin, "update", "setting", None, key)
    db.commit()
    return {"key": setting.key, "value": setting.value}
