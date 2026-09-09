import bcrypt
from datetime import datetime
from typing import Optional

def hash_password(password: str) -> str:
    """Returns a bcrypt hash of the provided plaintext password."""
    # Truncate to 72 bytes if needed (bcrypt 72 byte limit)
    pwd_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a stored bcrypt hash."""
    plain_bytes = plain_password.encode('utf-8')[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False

def get_elapsed_seconds(dt: Optional[datetime]) -> float:
    """Calculates elapsed seconds since dt, handling naive UTC/local differences."""
    if not dt:
        return 999999.0
    now_utc = datetime.utcnow()
    now_local = datetime.now()
    e_utc = (now_utc - dt).total_seconds()
    e_local = (now_local - dt).total_seconds()
    candidates = [e for e in (e_utc, e_local) if e >= 0]
    return min(candidates) if candidates else max(0.0, e_utc)

def is_otp_expired(expires_at: Optional[datetime]) -> bool:
    """Checks whether OTP has expired, handling naive UTC/local differences."""
    if not expires_at:
        return True
    now_utc = datetime.utcnow()
    now_local = datetime.now()
    diff_utc = (expires_at - now_utc).total_seconds()
    diff_local = (expires_at - now_local).total_seconds()
    candidates = [d for d in (diff_utc, diff_local) if d >= -60]
    remaining = min(candidates) if candidates else -1
    return remaining <= 0

