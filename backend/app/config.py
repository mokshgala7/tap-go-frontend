import os
from dotenv import load_dotenv

# Search and load environment variables from all candidate .env paths
possible_env_paths = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'),
    os.path.join(os.getcwd(), '.env'),
    os.path.join(os.getcwd(), 'backend', '.env'),
]

for p in possible_env_paths:
    if os.path.exists(p):
        load_dotenv(dotenv_path=p, override=True)

class Settings:
    @property
    def DB_HOST(self) -> str:
        return os.getenv("DB_HOST", "localhost")

    @property
    def DB_PORT(self) -> int:
        return int(os.getenv("DB_PORT", 3306))

    @property
    def DB_USER(self) -> str:
        return os.getenv("DB_USER", "root")

    @property
    def DB_PASSWORD(self) -> str:
        return os.getenv("DB_PASSWORD", "")

    @property
    def DB_NAME(self) -> str:
        return os.getenv("DB_NAME", "tapgo")

    @property
    def SECRET_KEY(self) -> str:
        return os.getenv("SECRET_KEY", "tapgo_super_secret_jwt_key_2026")

    @property
    def ADMIN_EMAIL(self) -> str:
        return os.getenv("ADMIN_EMAIL", "admin@example.com")

    @property
    def ADMIN_PASSWORD(self) -> str:
        return os.getenv("ADMIN_PASSWORD", "admin123")

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        return os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")

    @property
    def SMTP_HOST(self) -> str:
        return os.getenv("SMTP_HOST", "smtp.gmail.com")

    @property
    def SMTP_PORT(self) -> int:
        return int(os.getenv("SMTP_PORT", "587"))

    @property
    def SMTP_USER(self) -> str:
        return os.getenv("SMTP_USER", "")

    @property
    def SMTP_PASSWORD(self) -> str:
        return os.getenv("SMTP_PASSWORD", "")

    @property
    def SMTP_FROM_EMAIL(self) -> str:
        return os.getenv("SMTP_FROM_EMAIL", "TapAndGo <test@gmail.com>")

    @property
    def DATABASE_URL(self) -> str:
        # Allow Railway or any platform to inject a full DATABASE_URL directly.
        # Supports both mysql:// and mysql+pymysql:// formats.
        raw = os.getenv("DATABASE_URL", "")
        if raw:
            # Normalise mysql:// -> mysql+pymysql://
            if raw.startswith("mysql://"):
                raw = "mysql+pymysql://" + raw[len("mysql://"):]
            return raw
        # Fallback: build from individual DB_* components
        if self.DB_PASSWORD:
            return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        return f"mysql+pymysql://{self.DB_USER}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def OUTLOOK_CLIENT_ID(self) -> str:
        return os.getenv("OUTLOOK_CLIENT_ID", "")

    @property
    def OUTLOOK_CLIENT_SECRET(self) -> str:
        return os.getenv("OUTLOOK_CLIENT_SECRET", "")

    @property
    def OUTLOOK_TENANT_ID(self) -> str:
        return os.getenv("OUTLOOK_TENANT_ID", "common")

    @property
    def OUTLOOK_REFRESH_TOKEN(self) -> str:
        return os.getenv("OUTLOOK_REFRESH_TOKEN", "")

    @property
    def OUTLOOK_IMAP_SERVER(self) -> str:
        return os.getenv("OUTLOOK_IMAP_SERVER") or os.getenv("IMAP_HOST") or "outlook.office365.com"

    @property
    def OUTLOOK_IMAP_PORT(self) -> int:
        val = os.getenv("OUTLOOK_IMAP_PORT") or os.getenv("IMAP_PORT") or "993"
        return int(val)

    @property
    def OUTLOOK_EMAIL(self) -> str:
        return os.getenv("OUTLOOK_EMAIL") or os.getenv("IMAP_USER") or ""

    @property
    def OUTLOOK_APP_PASSWORD(self) -> str:
        return os.getenv("OUTLOOK_APP_PASSWORD") or os.getenv("IMAP_PASSWORD") or os.getenv("OUTLOOK_PASSWORD") or ""

    @property
    def IMAP_HOST(self) -> str:
        return self.OUTLOOK_IMAP_SERVER

    @property
    def IMAP_PORT(self) -> int:
        return self.OUTLOOK_IMAP_PORT

    @property
    def IMAP_USER(self) -> str:
        return self.OUTLOOK_EMAIL

    @property
    def IMAP_PASSWORD(self) -> str:
        return self.OUTLOOK_APP_PASSWORD

    @property
    def FAMPAY_UPI_ID(self) -> str:
        return os.getenv("FAMPAY_UPI_ID", "mokshsaysthanks@fam")

    @property
    def FAMPAY_MERCHANT_NAME(self) -> str:
        return os.getenv("FAMPAY_MERCHANT_NAME", "Moksh Gala")

    @property
    def PAYMENT_PROVIDER(self) -> str:
        return os.getenv("PAYMENT_PROVIDER", "FAMPAY_TEST")

    @property
    def PAYMENT_CHECK_INTERVAL(self) -> int:
        return int(os.getenv("PAYMENT_CHECK_INTERVAL", "5"))

    @property
    def PAYMENT_TIMEOUT(self) -> int:
        return int(os.getenv("PAYMENT_TIMEOUT", "30"))

    @property
    def PAYU_REVIEW_MODE(self) -> bool:
        """When True, demo accounts are auto-created and the PayU info card is
        shown in the frontend (controlled via VITE_PAYU_REVIEW_MODE on the FE)."""
        return os.getenv("PAYU_REVIEW_MODE", "true").lower() in ("1", "true", "yes")

settings = Settings()
