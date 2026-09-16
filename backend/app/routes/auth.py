import os
import uuid
import json
from typing import Optional
from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException, status, Header
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EditRequest, User, EmailOTP, UserSession

# Canonical reason constants
REASON_CREATE_ACCOUNT = "create_account"
REASON_FORGOT_PASSWORD = "forgot_password"
REASON_WITHDRAW_BALANCE = "withdraw_balance"
REASON_WALLET_TOPUP = "wallet_topup"

REASON_ALIASES = {
    "registration": REASON_CREATE_ACCOUNT,
    "create_account": REASON_CREATE_ACCOUNT,
    "forgot_password": REASON_FORGOT_PASSWORD,
    "reset_password": REASON_FORGOT_PASSWORD,
    "withdrawal": REASON_WITHDRAW_BALANCE,
    "withdraw_balance": REASON_WITHDRAW_BALANCE,
    "wallet_topup": REASON_WALLET_TOPUP,
    "topup": REASON_WALLET_TOPUP,
}

def canonicalize_reason(val: Optional[str]) -> str:
    """Normalizes any reason or legacy purpose string to its canonical reason."""
    if not val:
        return REASON_CREATE_ACCOUNT
    norm = val.strip().lower()
    return REASON_ALIASES.get(norm, norm)

def legacy_alias_for(canonical: str) -> Optional[str]:
    """Returns the legacy purpose string corresponding to a canonical reason, if any."""
    if canonical == REASON_CREATE_ACCOUNT:
        return "registration"
    if canonical == REASON_WITHDRAW_BALANCE:
        return "withdrawal"
    return None

from app.schemas import UserRegisterForm, UserLoginRequest, SendOTPRequest, EMAIL_REGEX, PHONE_REGEX
from pydantic import BaseModel
from app.utils.security import hash_password, verify_password, get_elapsed_seconds, is_otp_expired
import hashlib
import secrets
from app.utils.email_service import (
    send_registration_otp,
    send_password_reset_otp,
    send_welcome_email,
    send_security_alert_email,
    get_last_email_error,
)
from app.config import settings
import random
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

BASE_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
from app.utils.storage_service import upload_document, delete_document

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    
    token = authorization.split(" ")[1]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    session = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
    if not session or session.revoked_at or session.expires_at < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    
    return user


@router.post("/send-otp")
async def send_otp(request: SendOTPRequest, db: Session = Depends(get_db)):
    """
    Generate a 6-digit OTP and send it via Amazon SES for account registration.
    - 5-minute expiration
    - 60-second resend cooldown
    - Server-side persistence in email_otps (never physically deleted)
    - Prior unconsumed OTPs invalidated with used=True
    - Canonical reason 'create_account', synchronized purpose 'create_account'
    - OTP record remains persisted even if SES delivery fails
    - No OTP returned in API response
    """
    clean_email = request.email.strip().lower()
    existing_user = db.query(User).filter(func.lower(User.email) == clean_email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="This email address is already registered.")

    # 60-second cooldown check for account creation OTP
    existing_otp = db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == REASON_CREATE_ACCOUNT,
            EmailOTP.purpose.in_([REASON_CREATE_ACCOUNT, "registration"]),
        )
    ).order_by(EmailOTP.created_at.desc()).first()

    if existing_otp and existing_otp.created_at:
        elapsed = get_elapsed_seconds(existing_otp.created_at)
        if elapsed < 60:
            remaining_seconds = max(1, min(60, int(60 - elapsed)))
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining_seconds} seconds before requesting another code."
            )

    # Invalidate (used=True) all prior active registration OTPs for this email
    db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_email,
        or_(
            EmailOTP.reason == REASON_CREATE_ACCOUNT,
            EmailOTP.purpose.in_([REASON_CREATE_ACCOUNT, "registration"]),
        ),
        EmailOTP.used == False,
    ).update({"used": True}, synchronize_session=False)

    # Generate random 6-digit OTP with 5-minute validity
    otp = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    new_otp = EmailOTP(
        email=clean_email,
        otp=otp,
        reason=REASON_CREATE_ACCOUNT,
        purpose=REASON_CREATE_ACCOUNT,
        attempts=0,
        is_verified=False,
        used=False,
        expires_at=expires_at,
    )
    db.add(new_otp)
    db.commit()

    # Deliver via real Amazon SES
    success = send_registration_otp(clean_email, otp, request.account_type)
    if not success:
        # OTP record remains persisted in database per system resilience rules
        last_err = get_last_email_error()
        diag = f": {last_err}" if last_err else ""
        raise HTTPException(
            status_code=500,
            detail=f"We couldn't send the verification email{diag}. Please check your email address and try again."
        )

    return {
        "success": True,
        "message": "Verification code sent to your email. Please check your inbox (and spam folder)."
    }


class VerifyOTPRequest(BaseModel):
    email: str
    otp: str
    purpose: Optional[str] = None
    reason: Optional[str] = None


@router.post("/verify-otp")
async def verify_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    """
    Verify OTP on the spot.
    Validates email, reason/purpose, attempt count (max 5), and 5-minute expiry.
    Prevents cross-purpose OTP usage.
    Marks is_verified = True.
    """
    clean_email = request.email.strip().lower()
    clean_digits = "".join(ch for ch in clean_email if ch.isdigit())
    phone_10 = clean_digits[-10:] if len(clean_digits) >= 10 else clean_digits

    # If input is a phone number, resolve to user's registered email
    if "@" not in clean_email:
        user_match = db.query(User).filter(
            (func.trim(User.phone) == clean_email) |
            (func.trim(User.phone) == phone_10)
        ).first()
        if user_match and user_match.email:
            clean_email = user_match.email.strip().lower()

    target_reason = canonicalize_reason(request.reason or request.purpose or REASON_CREATE_ACCOUNT)
    legacy_purpose = legacy_alias_for(target_reason)

    purpose_conditions = [EmailOTP.reason == target_reason, EmailOTP.purpose == target_reason]
    if legacy_purpose:
        purpose_conditions.append(EmailOTP.purpose == legacy_purpose)

    db_otp = db.query(EmailOTP).filter(
        func.trim(func.lower(EmailOTP.email)) == clean_email,
        or_(*purpose_conditions),
        EmailOTP.used == False,
    ).order_by(EmailOTP.created_at.desc()).first()

    if not db_otp:
        raise HTTPException(
            status_code=400,
            detail="No verification code found for this email. Please request a new code."
        )

    # Max 5 attempts check
    if db_otp.attempts >= 5:
        db_otp.used = True
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Too many incorrect attempts. Please request a new code."
        )

    # Expiry check
    if is_otp_expired(db_otp.expires_at):
        db_otp.used = True
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="This code has expired. Please request a new code."
        )

    # Code mismatch check
    if db_otp.otp != request.otp.strip():
        db_otp.attempts += 1
        if db_otp.attempts >= 5:
            db_otp.used = True
        db.commit()
        if db_otp.attempts >= 5:
            raise HTTPException(
                status_code=400,
                detail="Too many incorrect attempts. Please request a new code."
            )
        remaining = max(0, 5 - db_otp.attempts)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verification code. Please try again. ({remaining} attempts remaining)"
        )

    # Success
    db_otp.is_verified = True
    db.commit()

    return {"success": True, "message": "Email verified successfully!"}


class ForgotPasswordRequest(BaseModel):
    account: str


@router.post("/forgot-password-otp")
async def forgot_password_otp(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Generate and send OTP for forgot password flow via Amazon SES.
    - 5-minute expiration
    - 60-second cooldown
    - Canonical reason 'forgot_password' distinct from registration
    - Unconsumed prior OTPs invalidated with used=True
    - OTP record remains persisted if SES fails
    - No OTP returned in API response
    """
    clean_account = request.account.strip()
    clean_account_lower = clean_account.lower()

    # Support normalized phone lookup (stripping +91, 91, leading 0, spaces, dashes)
    clean_digits = "".join(ch for ch in clean_account if ch.isdigit())
    phone_10 = clean_digits[-10:] if len(clean_digits) >= 10 else clean_digits

    user = db.query(User).filter(
        (func.trim(func.lower(User.email)) == clean_account_lower) |
        (func.trim(User.phone) == clean_account) |
        (func.trim(User.phone) == phone_10)
    ).first()

    if not user or not user.email or not user.email.strip():
        # Security: don't reveal if email/phone exists
        return {"success": True, "message": "If the account exists, a verification code will be sent."}

    clean_email = user.email.strip().lower()

    # 60-second cooldown check
    existing_otp = db.query(EmailOTP).filter(
        func.trim(func.lower(EmailOTP.email)) == clean_email,
        or_(
            EmailOTP.reason == REASON_FORGOT_PASSWORD,
            EmailOTP.purpose == REASON_FORGOT_PASSWORD,
        )
    ).order_by(EmailOTP.created_at.desc()).first()

    if existing_otp and existing_otp.created_at:
        elapsed = get_elapsed_seconds(existing_otp.created_at)
        if elapsed < 60:
            remaining_seconds = max(1, min(60, int(60 - elapsed)))
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {remaining_seconds} seconds before requesting another code."
            )

    # Invalidate previous password-reset OTPs (used=True)
    db.query(EmailOTP).filter(
        func.trim(func.lower(EmailOTP.email)) == clean_email,
        or_(
            EmailOTP.reason == REASON_FORGOT_PASSWORD,
            EmailOTP.purpose == REASON_FORGOT_PASSWORD,
        ),
        EmailOTP.used == False,
    ).update({"used": True}, synchronize_session=False)

    # Generate 6-digit random OTP
    otp = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=5)

    new_otp = EmailOTP(
        email=clean_email,
        otp=otp,
        reason=REASON_FORGOT_PASSWORD,
        purpose=REASON_FORGOT_PASSWORD,
        attempts=0,
        is_verified=False,
        used=False,
        expires_at=expires_at,
    )
    db.add(new_otp)
    db.commit()

    email_sent = send_password_reset_otp(clean_email, otp)
    if not email_sent:
        # Record remains persisted in database
        last_err = get_last_email_error()
        diag = f": {last_err}" if last_err else ""
        raise HTTPException(
            status_code=500,
            detail=f"We couldn't send the password reset email{diag}. Please try again."
        )

    # Mask email for UI display: m****@gmail.com
    parts = clean_email.split("@")
    masked_email = f"{parts[0][:1]}****@{parts[1]}" if len(parts) == 2 else clean_email

    return {
        "success": True,
        "message": "Verification code sent to your email. Please check your inbox.",
        "email": clean_email,
        "masked_email": masked_email,
    }


class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset user password after OTP verification.
    - Requires active forgot_password OTP
    - Hashes password using bcrypt
    - Consumes OTP immediately (used=True, never physically deleted)
    - Sends security alert notification
    """
    clean_email = request.email.strip().lower()
    clean_digits = "".join(ch for ch in clean_email if ch.isdigit())
    phone_10 = clean_digits[-10:] if len(clean_digits) >= 10 else clean_digits

    # If input is a phone number, resolve to user's registered email
    if "@" not in clean_email:
        user_match = db.query(User).filter(
            (func.trim(User.phone) == clean_email) |
            (func.trim(User.phone) == phone_10)
        ).first()
        if user_match and user_match.email:
            clean_email = user_match.email.strip().lower()

    db_otp = db.query(EmailOTP).filter(
        func.trim(func.lower(EmailOTP.email)) == clean_email,
        or_(
            EmailOTP.reason == REASON_FORGOT_PASSWORD,
            EmailOTP.purpose == REASON_FORGOT_PASSWORD,
        ),
        EmailOTP.used == False,
    ).order_by(EmailOTP.created_at.desc()).first()

    if not db_otp:
        raise HTTPException(
            status_code=400,
            detail="No password reset request found. Please request a new code."
        )

    if db_otp.attempts >= 5:
        db_otp.used = True
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="Too many incorrect attempts. Please request a new code."
        )

    if is_otp_expired(db_otp.expires_at):
        db_otp.used = True
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="This code has expired. Please request a new code."
        )

    if db_otp.otp != request.otp.strip():
        db_otp.attempts += 1
        if db_otp.attempts >= 5:
            db_otp.used = True
        db.commit()
        if db_otp.attempts >= 5:
            raise HTTPException(
                status_code=400,
                detail="Too many incorrect attempts. Please request a new code."
            )
        remaining = max(0, 5 - db_otp.attempts)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid verification code. ({remaining} attempts remaining)"
        )

    user = db.query(User).filter(
        (func.trim(func.lower(User.email)) == clean_email) |
        (func.trim(User.phone) == clean_email) |
        (func.trim(User.phone) == phone_10)
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    # Update password using bcrypt
    user.password_hash = hash_password(request.new_password)

    # Consume OTP (used=True, single-use, persisted)
    db_otp.is_verified = True
    db_otp.used = True
    db.commit()

    # Dispatch security notification email safely
    try:
        user_email = (user.email or clean_email).strip()
        if "@" in user_email:
            send_security_alert_email(
                to_email=user_email,
                user_name=user.name,
                title="Password Changed Successfully",
                details="Your Tap & Go password has been reset successfully. You can now sign in using your new credentials.",
            )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[SecurityAlert] Password reset email notice failed: {e}")

    return {
        "success": True,
        "message": "Password reset successfully. You can now sign in with your new password."
    }


@router.post("/register")
async def register(
    account_type: str = Form("passenger"),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    aadhaar: Optional[str] = Form(None),
    email_otp: str = Form(...),            # REQUIRED — must provide verified OTP
    pan: Optional[str] = Form(None),
    password: str = Form(...),
    vehicle_type: Optional[str] = Form(None),
    vehicle_registration: Optional[str] = Form(None),
    vehicle_make: Optional[str] = Form(None),
    vehicle_model: Optional[str] = Form(None),
    driving_licence_number: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),          # Face / profile photo
    id_doc: Optional[UploadFile] = File(None),         # Aadhaar / PAN card image
    signature: Optional[UploadFile] = File(None),      # Digital signature PNG
    rc: Optional[UploadFile] = File(None),
    licence: Optional[UploadFile] = File(None),
    insurance: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    """
    User Registration API endpoint.
    Accepts multipart/form-data with user info and uploaded documents.
    OTP is mandatory — the email must be verified before account creation.
    """
    # 1. Validate form data via Pydantic schema
    def _clean_str(v):
        return v if isinstance(v, str) else None

    try:
        validated_data = UserRegisterForm(
            account_type=str(account_type) if account_type else "passenger",
            name=str(name),
            email=str(email),
            phone=str(phone),
            address=_clean_str(address),
            city=_clean_str(city),
            pincode=_clean_str(pincode),
            aadhaar=_clean_str(aadhaar),
            email_otp=str(email_otp),
            pan=_clean_str(pan),
            password=str(password),
            vehicle_type=_clean_str(vehicle_type),
            vehicle_registration=_clean_str(vehicle_registration),
            vehicle_make=_clean_str(vehicle_make),
            vehicle_model=_clean_str(vehicle_model),
            driving_licence_number=_clean_str(driving_licence_number),
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    # 2. MANDATORY OTP verification — verified OTP matching reason/purpose='create_account'
    clean_reg_email = validated_data.email.strip().lower()
    db_otp = db.query(EmailOTP).filter(
        func.lower(EmailOTP.email) == clean_reg_email,
        or_(
            EmailOTP.reason == REASON_CREATE_ACCOUNT,
            EmailOTP.purpose.in_([REASON_CREATE_ACCOUNT, "registration"]),
        ),
        EmailOTP.used == False,
    ).order_by(EmailOTP.created_at.desc()).first()

    if not db_otp:
        raise HTTPException(
            status_code=400,
            detail="Email OTP not found. Please click 'Send OTP' and verify your email first."
        )
    if db_otp.attempts >= 5:
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Too many incorrect attempts. Please request a new code.")
    if is_otp_expired(db_otp.expires_at):
        db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Email OTP has expired. Please request a new OTP.")
    if db_otp.otp != validated_data.email_otp.strip():
        db_otp.attempts += 1
        if db_otp.attempts >= 5:
            db_otp.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid Email OTP. Please check and try again.")

    # Consume the OTP immediately: mark used=True (persisted, never deleted)
    db_otp.is_verified = True
    db_otp.used = True
    db.commit()


    # 3. Check for duplicate email or phone
    if db.query(User).filter(func.lower(User.email) == clean_reg_email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email address is already registered."
        )
    if db.query(User).filter(User.phone == validated_data.phone).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This phone number is already registered."
        )

    # 4. Handle file uploads
    # We keep track of uploaded paths for cleanup if DB commit fails
    uploaded_paths = []
    
    def _upload(file, folder, extensions=None):
        if file and hasattr(file, "filename") and file.filename:
            path = upload_document(file, folder, extensions)
            if path:
                uploaded_paths.append(path)
            return path
        return None

    photo_path = _upload(photo, "profile", ALLOWED_IMAGE_EXTENSIONS)
    id_doc_path = _upload(id_doc, "id_documents")
    signature_path = _upload(signature, "signatures", ALLOWED_IMAGE_EXTENSIONS)
    rc_path = _upload(rc, "rc")
    licence_path = _upload(licence, "licence")
    insurance_path = _upload(insurance, "insurance")

    # 5. Hash password
    hashed_pwd = hash_password(validated_data.password)

    # 6. Create and save user
    try:
        new_user = User(
            account_type=validated_data.account_type,
            name=validated_data.name,
            email=validated_data.email,
            phone=validated_data.phone,
            address=validated_data.address,
            city=validated_data.city,
            pincode=validated_data.pincode,
            aadhaar=validated_data.aadhaar,
            pan=validated_data.pan,
            password_hash=hashed_pwd,
            profile_photo=photo_path,
            id_document=id_doc_path,
            signature_document=signature_path,
            vehicle_type=validated_data.vehicle_type,
            vehicle_registration=validated_data.vehicle_registration,
            vehicle_make=validated_data.vehicle_make,
            vehicle_model=validated_data.vehicle_model,
            driving_licence_number=validated_data.driving_licence_number,
            rc_document=rc_path,
            licence_document=licence_path,
            insurance_document=insurance_path
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except Exception as e:
        db.rollback()
        # Cleanup uploaded files on failure
        for path in uploaded_paths:
            delete_document(path)
        raise HTTPException(
            status_code=500,
            detail="Registration failed. Please try again."
        )

    # 7. Send welcome email (non-blocking — failure won't break registration)
    try:
        send_welcome_email(new_user.email, new_user.name, new_user.account_type)
    except Exception as e:
        pass  # Welcome email failure should not fail registration

    return {
        "success": True,
        "message": "Account created successfully! Welcome to Tap&Go.",
        "user": {
            "id": new_user.id,
            "name": new_user.name,
            "account_type": new_user.account_type,
            "email": new_user.email,
            "phone": new_user.phone,
            "profile_photo": new_user.profile_photo,
        }
    }


def user_to_dict(user: User, include_docs: bool = False) -> dict:
    from app.utils.storage_service import get_signed_url
    
    def _doc(path):
        if not path:
            return None
        if include_docs:
            return get_signed_url(path)
        return "[REDACTED] - Requires Auth"

    return {
        "id": user.id,
        "account_type": user.account_type,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "address": user.address,
        "city": user.city,
        "state": user.state,
        "pincode": user.pincode,
        "aadhaar": user.aadhaar,
        "pan": user.pan,
        "profile_photo": get_signed_url(user.profile_photo) if include_docs and user.profile_photo else user.profile_photo,
        "id_document": _doc(user.id_document),
        "signature_document": _doc(user.signature_document),
        "rc_document": _doc(user.rc_document),
        "licence_document": _doc(user.licence_document),
        "insurance_document": _doc(user.insurance_document),
        "vehicle_type": user.vehicle_type,
        "vehicle_registration": user.vehicle_registration,
        "vehicle_make": user.vehicle_make,
        "vehicle_model": user.vehicle_model,
        "driving_licence_number": user.driving_licence_number,
        "emergency_contact_name": user.emergency_contact_name,
        "emergency_contact_phone": user.emergency_contact_phone,
        "bank_account_holder": user.bank_account_holder,
        "bank_account_number": user.bank_account_number,
        "bank_ifsc": user.bank_ifsc,
        "bank_upi_id": user.bank_upi_id,
        "bank_locked": bool(user.bank_locked),
        "bank_request_status": user.bank_request_status or "none",
        "doc_request_status": user.doc_request_status or "none",
        "phone_request_status": user.phone_request_status or "none",
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.post("/login")
async def login(credentials: UserLoginRequest, db: Session = Depends(get_db)):
    """
    User Login — accepts email or phone + password.
    Admin accounts must use the Admin Console (/api/admin/login), not this route.
    """
    account_input = credentials.account.strip()

    user = db.query(User).filter(
        (func.lower(User.email) == account_input.lower()) | (User.phone == account_input)
    ).first()

    if not user:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"success": False, "message": "Invalid Credentials"}
        )

    # Admin accounts must use the Admin Console, not the user login
    if getattr(user, 'account_type', None) == 'admin':
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": False,
                "message": "This account is an administrator account. Please use the Admin Console to sign in.",
                "redirect_admin": True
            }
        )

    if not verify_password(credentials.password, user.password_hash):
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"success": False, "message": "Invalid Credentials"}
        )

    # Create session
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.utcnow() + timedelta(days=30)  # 30 days expiration
    
    new_session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )
    db.add(new_session)
    db.commit()

    return {
        "success": True,
        "token": raw_token,
        "user": user_to_dict(user, include_docs=True)
    }

@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), authorization: str = Header(None), db: Session = Depends(get_db)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        session = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
        if session:
            session.revoked_at = datetime.utcnow()
            db.commit()
    return {"success": True}


@router.get("/profile/{user_id}")
async def get_profile(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to access this profile.")
    
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    return {"success": True, "user": user_to_dict(user, include_docs=True)}


class ProfileUpdateRequest(BaseModel):
    user_id: int
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    bank_account_holder: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_upi_id: Optional[str] = None


@router.put("/profile")
async def update_profile(data: ProfileUpdateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.id != data.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this profile.")

    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if data.phone is not None and data.phone.strip() != user.phone.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registered phone number cannot be modified directly."
        )

    if data.name is not None:
        user.name = data.name
    if data.email is not None:
        user.email = data.email
    if data.address is not None:
        user.address = data.address
    if data.city is not None:
        user.city = data.city
    if data.state is not None:
        user.state = data.state
    if data.emergency_contact_name is not None:
        user.emergency_contact_name = data.emergency_contact_name
    if data.emergency_contact_phone is not None:
        user.emergency_contact_phone = data.emergency_contact_phone

    # Check bank details modification
    bank_changed = any([
        data.bank_account_holder is not None and data.bank_account_holder != user.bank_account_holder,
        data.bank_account_number is not None and data.bank_account_number != user.bank_account_number,
        data.bank_ifsc is not None and data.bank_ifsc != user.bank_ifsc,
        data.bank_upi_id is not None and data.bank_upi_id != user.bank_upi_id,
    ])

    if bank_changed:
        bank_values = (
            data.bank_account_holder if data.bank_account_holder is not None else user.bank_account_holder,
            data.bank_account_number if data.bank_account_number is not None else user.bank_account_number,
            data.bank_ifsc if data.bank_ifsc is not None else user.bank_ifsc,
            data.bank_upi_id if data.bank_upi_id is not None else user.bank_upi_id,
        )
        if not all(isinstance(value, str) and value.strip() for value in bank_values):
            raise HTTPException(status_code=400, detail="All bank details are required.")
        if user.bank_locked:
            raise HTTPException(
                status_code=400,
                detail="Bank details are locked. Submit a bank-details change request for administrator approval."
            )

        if data.bank_account_holder is not None:
            user.bank_account_holder = data.bank_account_holder
        if data.bank_account_number is not None:
            user.bank_account_number = data.bank_account_number
        if data.bank_ifsc is not None:
            user.bank_ifsc = data.bank_ifsc
        if data.bank_upi_id is not None:
            user.bank_upi_id = data.bank_upi_id

        # Lock after the initial database-backed bank-details save.
        if user.bank_account_number:
            user.bank_locked = 1

    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "message": "Profile updated successfully.",
        "user": user_to_dict(user)
    }


class AdminAccessRequest(BaseModel):
    user_id: int
    request_type: str  # "bank" or "documents"
    bank_details: Optional[dict[str, str]] = None


@router.post("/request-admin-access")
async def request_admin_access(data: AdminAccessRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.id != data.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to request changes for another user.")

    user = current_user

    if data.request_type == "bank":
        if not user.bank_account_number:
            raise HTTPException(status_code=400, detail="Save initial bank details before requesting a change.")
        required_fields = {"bank_account_holder", "bank_account_number", "bank_ifsc", "bank_upi_id"}
        if not data.bank_details or not required_fields.issubset(data.bank_details) or not all(data.bank_details[field].strip() for field in required_fields):
            raise HTTPException(status_code=400, detail="Provide all proposed bank details for administrator review.")
        pending_request = db.query(EditRequest).filter(
            EditRequest.user_id == user.id,
            EditRequest.field_name == "bank",
            EditRequest.status == "pending",
        ).first()
        if pending_request:
            raise HTTPException(status_code=400, detail="A bank-details change request is already pending review.")
        user.bank_request_status = "requested"
    elif data.request_type == "documents":
        user.doc_request_status = "requested"
    elif data.request_type == "phone":
        user.phone_request_status = "requested"
    else:
        raise HTTPException(status_code=400, detail="Invalid request type.")

    db.add(EditRequest(
        user_id=user.id,
        field_name=data.request_type,
        previous_value=json.dumps({
            "bank_account_holder": user.bank_account_holder,
            "bank_account_number": user.bank_account_number,
            "bank_ifsc": user.bank_ifsc,
            "bank_upi_id": user.bank_upi_id,
        }) if data.request_type == "bank" else None,
        new_value=json.dumps(data.bank_details) if data.request_type == "bank" else None,
        reason=f"Requested administrator review to update {data.request_type} details.",
    ))

    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "message": f"Admin access request submitted for {data.request_type}. Pending admin review.",
        "user": user_to_dict(user)
    }
