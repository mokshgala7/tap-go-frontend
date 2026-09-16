"""Script to generate exactly 500 realistic demo transactions for mokshgala070@gmail.com.

Ensures:
- Realistic distribution across 1D, 1W, 1M, 3M, 6M, 1Y, and ALL.
- Consistent wallet ledger arithmetic with balance_after tracked on every row.
- Appropriate vehicle fares (Auto Rickshaw & Taxi), payment methods (wallet, QR, nfc, razorpay), and types.
- No other users receive these transactions (passenger_id=2, driver_id=None, wallet_id=2).
"""

import sys
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# Add backend to path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal
from app.models import User, Wallet, Transaction

def generate_demo_transactions():
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == "mokshgala070@gmail.com").first()
        if not user:
            print("[ERROR] User mokshgala070@gmail.com not found!")
            return False

        wallet = db.query(Wallet).filter(Wallet.user_id == user.id).first()
        if not wallet:
            print("[ERROR] Wallet for user not found!")
            return False

        user_id = user.id
        wallet_id = wallet.id
        print(f"[INFO] Target User ID: {user_id} ({user.name}), Wallet ID: {wallet_id}")

        # Delete any previous transactions for this user so there are EXACTLY 500
        old_count = db.query(Transaction).filter(Transaction.passenger_id == user_id).count()
        if old_count > 0:
            print(f"[INFO] Removing {old_count} existing test transactions for user {user_id}...")
            db.query(Transaction).filter(Transaction.passenger_id == user_id).delete(synchronize_session=False)
            db.commit()

        # Seed random for repeatable realism
        random.seed(42)

        now = datetime.now()

        # Target distribution across non-overlapping age segments:
        # Segment 0 (1D: 0 to 24 hours ago): 5 txns
        # Segment 1 (1W: 1 to 7 days ago): 20 txns
        # Segment 2 (1M: 7 to 30 days ago): 70 txns
        # Segment 3 (3M: 30 to 90 days ago): 125 txns
        # Segment 4 (6M: 90 to 180 days ago): 130 txns
        # Segment 5 (1Y: 180 to 360 days ago): 150 txns
        # Total = 500 txns
        segments = [
            {"count": 5, "min_sec": 3600 * 2, "max_sec": 3600 * 22},          # 2h to 22h ago
            {"count": 20, "min_sec": 86400 * 1.3, "max_sec": 86400 * 6.7},     # 1.3d to 6.7d ago
            {"count": 70, "min_sec": 86400 * 7.5, "max_sec": 86400 * 29.5},    # 7.5d to 29.5d ago
            {"count": 125, "min_sec": 86400 * 31.0, "max_sec": 86400 * 89.0},  # 31d to 89d ago
            {"count": 130, "min_sec": 86400 * 91.0, "max_sec": 86400 * 178.0}, # 91d to 178d ago
            {"count": 150, "min_sec": 86400 * 182.0, "max_sec": 86400 * 358.0} # 182d to 358d ago
        ]

        timestamps = []
        for seg in segments:
            c = seg["count"]
            # Generate sorted seconds ago
            step = (seg["max_sec"] - seg["min_sec"]) / c
            for i in range(c):
                jitter = random.uniform(-step * 0.4, step * 0.4)
                sec_ago = seg["min_sec"] + i * step + jitter
                # Ensure within bounds
                sec_ago = max(seg["min_sec"], min(seg["max_sec"], sec_ago))
                timestamps.append(sec_ago)

        # Sort timestamps descending (oldest seconds ago first -> chronological order)
        timestamps.sort(reverse=True)
        assert len(timestamps) == 500, f"Expected 500 timestamps, got {len(timestamps)}"

        # Realistic fare profiles
        auto_short_fares = [28.0, 32.0, 36.0, 42.0, 48.0, 54.0, 60.0, 68.0, 75.0, 84.0]
        auto_medium_fares = [92.0, 105.0, 118.0, 130.0, 145.0, 160.0, 175.0, 190.0]
        taxi_fares = [210.0, 245.0, 280.0, 315.0, 360.0, 420.0, 480.0, 540.0]
        topup_amounts = [500.0, 1000.0, 1500.0, 2000.0]
        withdraw_amounts = [100.0, 200.0, 500.0]

        ride_methods = ["wallet", "QR", "nfc", "wallet", "wallet"]

        # Initial starting balance before transaction 1
        current_balance = Decimal("2500.00")
        transactions_to_insert = []
        used_references = set()

        for idx, sec_ago in enumerate(timestamps):
            dt = now - timedelta(seconds=sec_ago)
            # Guarantee unique reference
            while True:
                ref = f"TXN{random.randint(1000000000, 9999999999)}"
                if ref not in used_references:
                    used_references.add(ref)
                    break

            # If this is the very first transaction, make it the initial topup
            if idx == 0:
                is_deposit = True
                is_withdraw = False
                amount = Decimal("2500.00")
                current_balance = Decimal("2500.00")
            elif current_balance < Decimal("350.00") or (idx % 22 == 0):
                # Periodic wallet top-up to simulate active passenger keeping wallet funded
                is_deposit = True
                is_withdraw = False
                amount = Decimal(str(random.choice(topup_amounts)))
                current_balance += amount
            elif idx % 65 == 0 and current_balance > Decimal("1200.00"):
                # Rare withdrawal / bank refund
                is_deposit = False
                is_withdraw = True
                amount = Decimal(str(random.choice(withdraw_amounts)))
                current_balance -= amount
            else:
                # Regular ride payment
                is_deposit = False
                is_withdraw = False
                roll = random.random()
                if roll < 0.50:
                    fare_val = random.choice(auto_short_fares)
                    desc = f"Auto Rickshaw ride (₹{fare_val:.2f})"
                elif roll < 0.85:
                    fare_val = random.choice(auto_medium_fares)
                    desc = f"Auto Rickshaw trip (₹{fare_val:.2f})"
                else:
                    fare_val = random.choice(taxi_fares)
                    desc = f"City Taxi ride (₹{fare_val:.2f})"
                amount = Decimal(str(fare_val))
                current_balance -= amount

            if is_deposit:
                txn = Transaction(
                    reference=ref,
                    passenger_id=user_id,
                    driver_id=None,
                    wallet_id=wallet_id,
                    amount=amount,
                    payment_method="razorpay",
                    provider="RAZORPAY",
                    status="completed",
                    otp_verified=True,
                    fraud_status="clear",
                    transaction_type="deposit",
                    description=f"₹{float(amount):.2f} credited via Razorpay (UPI)",
                    balance_after=current_balance,
                    created_at=dt,
                    updated_at=dt,
                )
            elif is_withdraw:
                ref_wd = f"WD-{ref[3:13]}"
                txn = Transaction(
                    reference=ref_wd,
                    passenger_id=user_id,
                    driver_id=None,
                    wallet_id=wallet_id,
                    amount=amount,
                    payment_method="bank_transfer",
                    status="completed",
                    otp_verified=True,
                    fraud_status="clear",
                    transaction_type="withdrawal",
                    description=f"Withdrawal of ₹{float(amount):.2f} transferred to bank account",
                    balance_after=current_balance,
                    created_at=dt,
                    updated_at=dt,
                )
            else:
                method = random.choice(ride_methods)
                txn = Transaction(
                    reference=ref,
                    passenger_id=user_id,
                    driver_id=None,
                    wallet_id=wallet_id,
                    amount=amount,
                    payment_method=method,
                    status="completed",
                    otp_verified=True,
                    fraud_status="clear",
                    transaction_type="ride_payment",
                    description=desc,
                    balance_after=current_balance,
                    created_at=dt,
                    updated_at=dt,
                )

            transactions_to_insert.append(txn)

        # Bulk insert
        db.add_all(transactions_to_insert)
        
        # Update wallet balance to match final balance
        wallet.balance = current_balance
        db.commit()

        print(f"[SUCCESS] Inserted exactly {len(transactions_to_insert)} transactions.")
        print(f"[SUCCESS] Final wallet balance set to: ₹{current_balance:.2f}")

        # Verification query
        total_in_db = db.query(Transaction).filter(Transaction.passenger_id == user_id).count()
        print(f"[VERIFY] Total transactions in DB for user {user_id}: {total_in_db}")

        # Verification across time ranges
        all_txns = db.query(Transaction).filter(Transaction.passenger_id == user_id).all()
        now_ts = datetime.now().timestamp()

        counts = {"1D": 0, "1W": 0, "1M": 0, "3M": 0, "6M": 0, "1Y": 0, "ALL": len(all_txns)}
        for t in all_txns:
            diff_ms = (now_ts - t.created_at.timestamp()) * 1000
            if diff_ms <= 1000 * 60 * 60 * 24:
                counts["1D"] += 1
            if diff_ms <= 1000 * 60 * 60 * 24 * 7:
                counts["1W"] += 1
            if diff_ms <= 1000 * 60 * 60 * 24 * 30:
                counts["1M"] += 1
            if diff_ms <= 1000 * 60 * 60 * 24 * 90:
                counts["3M"] += 1
            if diff_ms <= 1000 * 60 * 60 * 24 * 180:
                counts["6M"] += 1
            if diff_ms <= 1000 * 60 * 60 * 24 * 365:
                counts["1Y"] += 1

        print("[FILTER COUNTS]:", counts)
        return True
    finally:
        db.close()

if __name__ == "__main__":
    success = generate_demo_transactions()
    sys.exit(0 if success else 1)
