from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

def get_engine():
    """Create the SQLAlchemy engine targeting MySQL, with graceful SQLite fallback.

    If MySQL is reachable, it uses MySQL. If MySQL is unreachable or not configured,
    it falls back to SQLite so the server runs smoothly on any deployment.
    """
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite"):
        print("[Database] Using SQLite database file.")
        return create_engine(db_url, connect_args={"check_same_thread": False}, echo=False)

    try:
        eng = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600, echo=False)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[Database] Connected to MySQL database successfully.")
        return eng
    except Exception as e:
        print(f"[Database Warning] MySQL connection failed ({e}). Falling back to SQLite for seamless deployment.")
        return create_engine("sqlite:///./tapgo.db", connect_args={"check_same_thread": False}, echo=False)

engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency to yield a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

