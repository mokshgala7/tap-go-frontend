import bcrypt

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
