import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Form, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EditRequest, User, EmailOTP
from app.schemas import UserRegisterForm, UserLoginRequest, SendOTPRequest, EMAIL_REGEX, PHONE_REGEX
from pydantic import BaseModel
from app.utils.security import hash_password, verify_password
from app.utils.email_service import send_otp_email, send_welcome_email
from app.config import settings
import random
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

BASE_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def save_uploaded_file(file: UploadFile, folder: str, allowed_extensions=None) -> str:
    """Helper to validate and save uploaded files to specified folder."""
    if not file or not file.filename:
        return None

    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS

    # Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}."
        )

    # Read content to validate size
    contents = file.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{file.filename}' exceeds maximum allowed size of 5 MB."
        )

    # Reset file cursor
    file.file.seek(0)

    # Ensure target directory exists
    target_dir = os.path.join(BASE_UPLOAD_DIR, folder)
    os.makedirs(target_dir, exist_ok=True)

    # Generate unique filename
    filename = f"{uuid.uuid4().hex}_{os.path.basename(file.filename)}"
    file_path = os.path.join(target_dir, filename)

    with open(file_path, "wb") as f:
        f.write(contents)

    # Return relative path for MySQL storage
    return f"uploads/{folder}/{filename}"


@router.post("/send-otp")
async def send_otp(request: SendOTPRequest, db: Session = Depends(get_db)):
    """
    Generate a 6-digit OTP and send it via email.
    The OTP is stored in DB and expires in 10 minutes.
    In REVIEW_DEMO_MODE, if the email delivery fails (e.g. Resend sandbox restriction),
    the OTP is returned directly in the response so the tester can still complete the flow.
    """
    existing_user = db.query(User).filter(User.email == request.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email is already registered.")

    otp = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Invalidate all old OTPs for this email
    db.query(EmailOTP).filter(EmailOTP.email == request.email).delete()

    new_otp = EmailOTP(email=request.email, otp=otp, expires_at=expires_at)
    db.add(new_otp)
    db.commit()

    success = send_otp_email(request.email, otp, request.account_type)
    if not success:
        if settings.REVIEW_DEMO_MODE:
            # In review/demo mode, Resend sandbox may restrict delivery to unverified emails.
            # Return the OTP directly in the response so the reviewer can still test the full flow.
            import logging
            logging.getLogger(__name__).warning(
                "[REVIEW_DEMO] Email delivery failed for %s. Returning OTP in response for demo purposes.",
                request.email,
            )
            return {
                "success": True,
                "demo_mode": True,
                "otp": otp,
                "message": (
                    "Demo mode: Email delivery is restricted to verified addresses on the free plan. "
                    f"Your OTP is: {otp} — please enter this code to continue."
                ),
            }
        # Rollback OTP so user can retry
        db.query(EmailOTP).filter(EmailOTP.email == request.email).delete()
        db.commit()
        raise HTTPException(status_code=500, detail="Failed to send OTP email. Please check your email address and try again.")

    return {"success": True, "message": "OTP sent to your email. Please check your inbox (and spam folder)."}



class VerifyOTPRequest(BaseModel):
    email: str
    otp: str


@router.post("/verify-otp")
async def verify_otp(request: VerifyOTPRequest, db: Session = Depends(get_db)):
    """
    Verify OTP on the spot — does NOT consume it.
    The OTP remains valid for the final registration step.
    """
    db_otp = db.query(EmailOTP).filter(EmailOTP.email == request.email).first()
    if not db_otp:
        raise HTTPException(status_code=400, detail="No OTP found for this email. Please request a new OTP.")
    if db_otp.otp != request.otp:
        raise HTTPException(status_code=400, detail="Incorrect OTP. Please try again.")
    if db_otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP has expired. Please request a new OTP.")

    return {"success": True, "message": "OTP verified successfully!"}


class ForgotPasswordRequest(BaseModel):
    account: str


@router.post("/forgot-password-otp")
async def forgot_password_otp(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """
    Generate and send OTP for forgot password flow.
    """
    user = db.query(User).filter(
        (User.email == request.account) | (User.phone == request.account)
    ).first()

    if not user:
        # Security: don't reveal if email/phone exists
        return {"success": True, "message": "If the account exists, an OTP will be sent."}

    otp = f"{random.randint(100000, 999999)}"
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    db.query(EmailOTP).filter(EmailOTP.email == user.email).delete()
    new_otp = EmailOTP(email=user.email, otp=otp, expires_at=expires_at)
    db.add(new_otp)
    db.commit()

    email_sent = send_otp_email(user.email, otp, user.account_type)
    if not email_sent and settings.REVIEW_DEMO_MODE:
        return {
            "success": True,
            "demo_mode": True,
            "otp": otp,
            "email": user.email,
            "message": (
                f"Demo mode: Email delivery restricted. Your OTP is: {otp} — use it to reset your password."
            ),
        }
    return {"success": True, "message": "If the account exists, an OTP will be sent.", "email": user.email}


class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    db_otp = db.query(EmailOTP).filter(EmailOTP.email == request.email).first()
    if not db_otp or db_otp.otp != request.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP.")
    if db_otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP has expired.")

    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.password_hash = hash_password(request.new_password)
    db.delete(db_otp)
    db.commit()

    return {"success": True, "message": "Password reset successfully."}


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
    email_otp: str = Form(...),            # REQUIRED — must provide OTP
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
    try:
        validated_data = UserRegisterForm(
            account_type=account_type,
            name=name,
            email=email,
            phone=phone,
            address=address,
            city=city,
            pincode=pincode,
            aadhaar=aadhaar,
            email_otp=email_otp,
            pan=pan,
            password=password,
            vehicle_type=vehicle_type,
            vehicle_registration=vehicle_registration,
            vehicle_make=vehicle_make,
            vehicle_model=vehicle_model,
            driving_licence_number=driving_licence_number
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    # 2. MANDATORY OTP verification — always required
    db_otp = db.query(EmailOTP).filter(EmailOTP.email == validated_data.email).first()
    if not db_otp:
        raise HTTPException(
            status_code=400,
            detail="Email OTP not found. Please click 'Send OTP' and verify your email first."
        )
    if db_otp.otp != validated_data.email_otp:
        raise HTTPException(status_code=400, detail="Invalid Email OTP. Please check and try again.")
    if db_otp.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Email OTP has expired. Please request a new OTP.")

    # Consume the OTP immediately
    db.delete(db_otp)
    db.commit()

    if settings.REVIEW_DEMO_MODE:
        return {
            "success": True,
            "review_demo": True,
            "message": (
                "Registration completed in the demonstration environment. "
                "This demo resets automatically, so please sign in with one of the supplied tester accounts."
            ),
        }

    # 3. Check for duplicate email or phone
    if db.query(User).filter(User.email == validated_data.email).first():
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
    photo_path = save_uploaded_file(photo, "profile", ALLOWED_IMAGE_EXTENSIONS) if photo and photo.filename else None
    id_doc_path = save_uploaded_file(id_doc, "id_documents") if id_doc and id_doc.filename else None
    signature_path = save_uploaded_file(signature, "signatures", ALLOWED_IMAGE_EXTENSIONS) if signature and signature.filename else None
    rc_path = save_uploaded_file(rc, "rc") if rc and rc.filename else None
    licence_path = save_uploaded_file(licence, "licence") if licence and licence.filename else None
    insurance_path = save_uploaded_file(insurance, "insurance") if insurance and insurance.filename else None

    # 5. Hash password
    hashed_pwd = hash_password(validated_data.password)

    # 6. Create and save user
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


def user_to_dict(user: User):
    return {
        "id": user.id,
        "name": user.name,
        "account_type": user.account_type,
        "email": user.email,
        "phone": user.phone,
        "address": user.address,
        "city": user.city,
        "state": user.state,
        "pincode": user.pincode,
        "aadhaar": user.aadhaar,
        "pan": user.pan,
        "profile_photo": user.profile_photo,
        "id_document": user.id_document,
        "signature_document": user.signature_document,
        "rc_document": user.rc_document,
        "licence_document": user.licence_document,
        "insurance_document": user.insurance_document,
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
        (User.email == account_input) | (User.phone == account_input)
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

    return {
        "success": True,
        "user": user_to_dict(user)
    }


@router.get("/profile/{user_id}")
async def get_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"success": True, "user": user_to_dict(user)}


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
async def update_profile(data: ProfileUpdateRequest, db: Session = Depends(get_db)):
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
        if user.bank_locked and user.bank_request_status != "approved":
            raise HTTPException(
                status_code=400,
                detail="Bank details are locked. You must request admin access to edit bank details again."
            )

        if data.bank_account_holder is not None:
            user.bank_account_holder = data.bank_account_holder
        if data.bank_account_number is not None:
            user.bank_account_number = data.bank_account_number
        if data.bank_ifsc is not None:
            user.bank_ifsc = data.bank_ifsc
        if data.bank_upi_id is not None:
            user.bank_upi_id = data.bank_upi_id

        # Lock after initial edit if bank account number exists
        if user.bank_account_number:
            user.bank_locked = 1
            if user.bank_request_status == "approved":
                user.bank_request_status = "none"

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


@router.post("/request-admin-access")
async def request_admin_access(data: AdminAccessRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if data.request_type == "bank":
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
        previous_value=None,
        new_value=None,
        reason=f"Requested administrator access to update {data.request_type} details.",
    ))

    db.commit()
    db.refresh(user)
    return {
        "success": True,
        "message": f"Admin access request submitted for {data.request_type}. Pending admin review.",
        "user": user_to_dict(user)
    }
