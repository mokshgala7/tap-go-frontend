import secrets
import bcrypt
from datetime import datetime
from typing import Optional

def generate_otp() -> str:
    """Returns a 6-digit one-time code from a cryptographically secure generator."""
    return f"{secrets.randbelow(900000) + 100000}"

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
    """Checks whether an OTP has expired.

    Every OTP `expires_at` is written as naive UTC (`datetime.utcnow() + ...`), so it is
    compared with UTC only. (The previous version also compared against local time and took
    the smaller difference, which made a code that expired hours ago look valid on a server
    whose local clock is behind UTC.)
    """
    if not expires_at:
        return True
    return (expires_at - datetime.utcnow()).total_seconds() <= 0

