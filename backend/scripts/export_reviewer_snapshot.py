"""Create a resettable SQLite reviewer snapshot from the local Tap&Go MySQL data.

Run this locally from the backend directory. It reads the local .env file but never
copies it. The resulting database is intentionally used only by REVIEW_DEMO_MODE.
"""

from pathlib import Path
import sys

from sqlalchemy import create_engine, select


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402  Registers every mapped table with Base.


OUTPUT_PATH = BACKEND_ROOT / "reviewer_seed" / "tapgo-reviewer.db"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    source_engine = create_engine(settings.DATABASE_URL)
    destination_engine = create_engine(f"sqlite:///{OUTPUT_PATH}")
    Base.metadata.create_all(destination_engine)

    with source_engine.connect() as source, destination_engine.begin() as destination:
        for table in Base.metadata.sorted_tables:
            # One-time codes are short-lived credentials, not reviewer history.
            # The hosted demo creates fresh OTPs as part of its own flow.
            rows = [] if table.name == "email_otps" else [
                dict(row) for row in source.execute(select(table)).mappings()
            ]
            if rows:
                destination.execute(table.insert(), rows)
            print(f"Copied {len(rows)} rows from {table.name}")

    print(f"Reviewer database snapshot written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
