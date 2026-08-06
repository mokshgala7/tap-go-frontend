# Tap&Go — Smart Transit Payouts & Cashless Payment Platform

Tap&Go is a modern, secure, and instant cashless payment and payout ecosystem built for transit (passengers, drivers, and fleet operators). It features NFC Tap-to-Pay, QR Payments, real-time OTP verification, digital signature integration, document verification, database-backed wallet management, FamPay backup payment verification via Outlook Microsoft Graph API, admin request approval workflows, and role-based dashboards.

---

## 📋 PayU Merchant Verification Notes

This deployment is created specifically for **PayU Merchant Verification**.

The PayU review team can test and evaluate all end-to-end business workflows in this demonstration deployment. Certain production infrastructure services are simulated due to hosting environment constraints (Render Free Tier & Vercel Free Tier). Below is a complete breakdown of hosted demonstration behavior vs live production implementation.

### 1. Database Persistence
- **Demo Deployment (Render Free Tier):** The backend database is **REAL and fully functional** while the server container is live. Account registrations, wallet top-ups, ride payments, profile updates, and admin actions are saved normally in active database storage. Whenever the Render server container restarts or redeploys, a clean seeded database snapshot is automatically restored. This behavior guarantees every PayU reviewer starts with a clean, fully-populated demonstration environment.
- **Production Environment:** Will use a persistent managed database service (e.g., AWS RDS MySQL / GCP Cloud SQL). User registrations, wallet balances, and transactions will remain permanently and never reset after redeployments.

### 2. OTP Verification
- **Demo Deployment:** Email OTP delivery is sent to the registered email address. In hosted demo mode, a 6-digit OTP is automatically generated and auto-filled in the frontend so reviewers can test seamlessly.
- **Production Environment:** The backend generates the OTP and dispatches it to the user's registered email address via the backend email service (Gmail SMTP / Mailer). The user enters the received email code for validation.

### 3. Uploaded Document Storage
- **Demo Deployment:** Uploaded driver licences, vehicle RC books, Aadhaar/PAN cards, and digital signatures are processed and stored temporarily within the active server container. File previews after container restarts are represented by professional documentation cards.
- **Production Environment:** Uploaded documents will be stored securely using persistent Object Storage (e.g., AWS S3 / Google Cloud Storage) with encrypted pre-signed URLs for reviewer access and document previews.

### 4. Payment Gateway Integration
- **Demo Deployment:** Demonstrates the cashless transit payment workflow using a dynamic UPI QR integration with real-time wallet ledger updates.
- **Production Environment:** Upon PayU Merchant Account approval, the temporary payment implementation will be replaced with official PayU Payment Gateway APIs (PayU Web Checkout SDK & Webhook Callbacks) without altering the user wallet experience or transaction history.

### 📊 Deployment vs Production Summary

| Feature | Demo Deployment (Hosted) | Production Environment |
| :--- | :--- | :--- |
| **Frontend** | Vercel Global CDN | Vercel / Custom CDN |
| **Backend API** | Render Web Service (FastAPI) | AWS ECS / Render Dedicated Instance |
| **Database** | Temporary Render Container Database | Persistent Managed Database (AWS RDS) |
| **OTP Delivery** | Auto-Filled Email OTP | Real Email OTP (Registered Email Address) |
| **Document Storage** | Temporary Instance Storage | Persistent Object Storage (AWS S3) |
| **Payment Gateway** | Demo UPI Payment Integration | Official PayU Payment Gateway APIs |

---

## 🚀 Architecture & Tech Stack

```text
React 18 / Vite Frontend  <--->  FastAPI (Python 3.14+) Backend  <--->  MySQL Database (tapgo)
       │                                     │
   Single Page App                      Uploads Server
 (Session/Tab Persistence)          (backend/uploads/)
                                             │
                                     Microsoft Graph API
                                  (FamPay Email Verification)
```

- **Frontend:** React 18, Vite, Vanilla CSS Design Tokens, HTML5 Canvas (Digital Signature & QR Code Renderer), jsQR (QR Code Scanning), Session/Hash Navigation Provider.
- **Backend:** FastAPI, Uvicorn, SQLAlchemy ORM, PyMySQL.
- **Database:** MySQL Server (`localhost:3306`, schema: `tapgo`).
- **Authentication:** Password Hashing (bcrypt), OTP Email Verification (Gmail SMTP with HTML templates).
- **Payment Verification:** FamPay Backup Payment Method verified via Microsoft Graph API (reads payment confirmation emails strictly from `no-reply@famapp.in`).
- **File Storage:** Local Static File Server (`backend/uploads/`) for Profile Photos, Digital Signatures, Aadhaar/PAN, RC, Licence, and Insurance documents.

---

## 📁 Project Structure

```text
Tap&Go(Test) 5/
├── backend/
│   ├── app/
│   │   ├── config.py             # Environment & Database settings
│   │   ├── database.py           # SQLAlchemy engine & session factory
│   │   ├── main.py               # FastAPI app, static file mounts & safe startup migrations
│   │   ├── models.py             # SQLAlchemy models (User, Wallet, Transaction, PaymentRequest, etc.)
│   │   ├── schemas.py            # Pydantic data validation schemas
│   │   ├── routes/
│   │   │   ├── admin.py          # Admin management APIs & audit logging
│   │   │   ├── auth.py           # Registration, Login, OTP, Profile & Admin Access Request APIs
│   │   │   ├── wallet.py         # DB-backed Wallet, Transaction, Top-up, Withdraw & Pay APIs
│   │   │   └── payment.py        # FamPay Payment Request & Outlook Verification APIs
│   │   └── services/
│   │       └── payment/
│   │           ├── fampay/
│   │           │   └── verifier.py # FamPay email parser, URI generator & wallet crediting engine
│   │           └── outlook/
│   │               └── graph_client.py # Microsoft Graph API client (reads ONLY no-reply@famapp.in)
│   ├── uploads/                  # Saved user files
│   ├── schema.sql                # Complete MySQL DDL schema script
│   ├── seed_admin.py             # Default admin account seeder
│   ├── .env                      # DB, Gmail SMTP & Outlook FamPay credentials (DO NOT OVERWRITE EXISTING)
│   └── requirements.txt          # Python backend dependencies
│
├── frontend/
│   ├── src/
│   │   ├── assets/               # Images & static assets
│   │   ├── components/
│   │   │   └── Payment/
│   │   │       └── FamPayPaymentModal.jsx # Professional Payment QR, Timer & Verification Modal
│   │   ├── context/
│   │   │   ├── AuthContext.jsx   # Auth state, profile sync & admin access helpers
│   │   │   ├── DriverContext.jsx # Driver wallet, earnings & trip data (100% DB-backed)
│   │   │   └── WalletContext.jsx # Passenger wallet balance & transactions (100% DB-backed)
│   │   ├── routes/
│   │   │   ├── navigation.jsx    # Persistent navigation provider (hash & session persistence)
│   │   │   └── AppRoutes.jsx     # View router
│   │   ├── pages/
│   │   │   ├── Home/             # Landing page
│   │   │   ├── Login.jsx         # Login page (with auto admin redirect)
│   │   │   ├── Register/         # Registration page with live preview & signature
│   │   │   ├── ForgotPassword/   # OTP password recovery page
│   │   │   ├── Driver/           # Driver Dashboard, Earnings, Account & Bank details
│   │   │   ├── Passenger/        # Passenger Dashboard, Activity, Wallet & Bank details
│   │   │   └── Admin/            # Admin Console, Database Viewer & Management tabs
│   └── package.json              # Node.js frontend dependencies
└── README.md
```

---

## 🛢️ Database Schema & Table Documentation

The source of truth for Tap&Go is the MySQL `tapgo` database. The backend uses safe, non-destructive startup migrations (`CREATE TABLE IF NOT EXISTS` & `ALTER TABLE ADD COLUMN`) so pre-existing populated installations retain all their data without modification or loss.

---

### 1. `users` Table
**Purpose:** Stores passenger and driver profiles, document file paths, identity verification info, and bank locking status.

| Column Name | Data Type | Key / Constraint / Index | Default | Nullable | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INT` | Primary Key, Auto Increment | — | No | Unique user ID. |
| `account_type` | `VARCHAR(20)` | — | `'passenger'` | No | Account role (`'passenger'` or `'driver'`). |
| `name` | `VARCHAR(100)` | — | — | No | User's full name. |
| `email` | `VARCHAR(120)` | Unique, Indexed | — | No | Primary login email address. |
| `phone` | `VARCHAR(20)` | Unique, Indexed | — | No | Registered phone number. Read-only in profile UI. |
| `status` | `VARCHAR(20)` | — | `'active'` | No | Account status (`'active'`, `'suspended'`, etc.). |

---

### 2. `wallets` Table
**Purpose:** Stores individual user wallet balances and administrative frozen states linked 1-to-1 with `users.id`.

| Column Name | Data Type | Key / Constraint / Index | Default | Nullable | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INT` | Primary Key, Auto Increment | — | No | Unique wallet record ID. |
| `user_id` | `INT` | Foreign Key (`users.id`), Unique, Indexed | — | No | Owner User ID. Exactly 1 wallet per user. |
| `balance` | `DECIMAL(12,2)` | — | `0.00` | No | Real-time wallet balance in ₹ (INR). Enforced non-negative. |
| `is_frozen` | `BOOLEAN` | — | `FALSE` | No | Admin freeze flag. |

---

### 3. `payment_requests` Table (NEW)
**Purpose:** Manages pending, completed, expired, or failed payment requests created during FamPay QR recharge flows.

| Column Name | Data Type | Key / Constraint / Index | Default | Nullable | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INT` | Primary Key, Auto Increment | — | No | Unique payment request ID. |
| `user_id` | `INT` | Foreign Key (`users.id`), Indexed | — | No | Requester User ID. |
| `wallet_id` | `INT` | Foreign Key (`wallets.id`) | — | No | Destination Wallet ID. |
| `amount` | `DECIMAL(12,2)` | — | — | No | Top-up amount in ₹ (INR). |
| `upi_uri` | `TEXT` | — | — | No | Standard UPI URI string (`upi://pay?pa=...`). |
| `status` | `VARCHAR(20)` | Indexed | `'Pending'` | No | Request status (`'Pending'`, `'Completed'`, `'Expired'`, `'Failed'`). |
| `provider` | `VARCHAR(30)` | — | `'FAMPAY_TEST'` | No | Payment provider identifier. |
| `provider_transaction_id` | `VARCHAR(128)` | — | `NULL` | Yes | FamPay transaction ID parsed from email. |
| `utr` | `VARCHAR(128)` | Indexed | `NULL` | Yes | 12-digit UTR/RRN parsed from email. |
| `payer_name` | `VARCHAR(120)` | — | `NULL` | Yes | Payer name extracted from notification email. |
| `raw_email_id` | `VARCHAR(255)` | — | `NULL` | Yes | Raw Graph API message ID. |
| `created_at` | `DATETIME` | — | `CURRENT_TIMESTAMP` | Yes | Request creation timestamp. |
| `expires_at` | `DATETIME` | — | `NULL` | Yes | Expiration timestamp (15 min window). |
| `verified_at` | `DATETIME` | — | `NULL` | Yes | Timestamp when Outlook email verified payment. |
| `last_checked_at` | `DATETIME` | — | `NULL` | Yes | Timestamp of last Graph API verification check. |

---

### 4. `transactions` Table
**Purpose:** Comprehensive financial ledger for top-ups, ride payments, fare transfers, withdrawals, and FamPay deposits.

| Column Name | Data Type | Key / Constraint / Index | Default | Nullable | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `id` | `INT` | Primary Key, Auto Increment | — | No | Unique transaction ID. |
| `reference` | `VARCHAR(64)` | Unique, Indexed | — | No | Unique reference code (e.g. `FAM-412345678901`, `TXN7F271DE256`). |
| `passenger_id` | `INT` | Foreign Key (`users.id`), Indexed | `NULL` | Yes | Passenger User ID. |
| `driver_id` | `INT` | Foreign Key (`users.id`), Indexed | `NULL` | Yes | Driver User ID. |
| `wallet_id` | `INT` | Foreign Key (`wallets.id`) | `NULL` | Yes | Associated Wallet ID. |
| `amount` | `DECIMAL(12,2)` | — | — | No | Transaction amount in ₹ (INR). |
| `payment_method` | `VARCHAR(20)` | — | `'wallet'` | No | Method (`'FamPay Test'`, `'QR'`, `'NFC'`, `'deposit'`, `'bank_transfer'`). |
| `status` | `VARCHAR(20)` | — | `'pending'` | No | Status (`'completed'`, `'pending'`, `'failed'`, `'reversed'`). |
| `transaction_type` | `VARCHAR(30)` | — | `NULL` | Yes | Type (`'deposit'`, `'ride_payment'`, `'withdrawal'`, `'transfer'`). |
| `description` | `TEXT` | — | `NULL` | Yes | Statement description (e.g. `"₹250.00 credited via FamPay Test"`). |
| `balance_after` | `DECIMAL(12,2)` | — | `NULL` | Yes | Wallet balance immediately after execution. |
| `idempotency_key` | `VARCHAR(128)` | Unique, Indexed | `NULL` | Yes | Duplicate submission protection key. |
| `provider` | `VARCHAR(30)` | — | `NULL` | Yes | Provider (`'FAMPAY_TEST'`). |
| `provider_transaction_id` | `VARCHAR(128)` | — | `NULL` | Yes | FamPay Transaction ID. |
| `utr` | `VARCHAR(128)` | — | `NULL` | Yes | 12-digit UTR/RRN. |
| `payer_name` | `VARCHAR(120)` | — | `NULL` | Yes | Payer Name. |
| `payment_request_id` | `INT` | Foreign Key (`payment_requests.id`) | `NULL` | Yes | Associated `payment_requests.id`. |
| `payment_source` | `VARCHAR(50)` | — | `NULL` | Yes | Source identifier (`'FAMPAY_TEST'`). |
| `email_received_at` | `DATETIME` | — | `NULL` | Yes | Timestamp of FamPay email receipt. |
| `raw_email_id` | `VARCHAR(255)` | — | `NULL` | Yes | Graph API message ID. |

---

## 💼 FamPay Backup Payment via Outlook Verification Workflow

1. **Passenger Initiates Top-Up:**
   - Passenger opens Wallet tab, enters amount (e.g., ₹250.00), and clicks **Proceed to Pay**.
   - Frontend calls `POST /api/payment/create-request`. Backend inserts a `Pending` row in `payment_requests` and generates standard UPI URI (`upi://pay?pa=fampay@upi&pn=TapAndGo&am=250.00&cu=INR`).
2. **Professional QR Screen Displayed:**
   - Frontend opens `FamPayPaymentModal` rendering a live canvas QR code from `upi_uri`, amount, FamPay UPI ID (`fampay@upi`), status indicator ("Waiting for payment..."), and a 30-second timer.
3. **Automatic Outlook Verification:**
   - Frontend automatically polls `GET /api/payment/status/{requestId}` every 5 seconds.
   - Backend connects to **Microsoft Graph API** (`https://graph.microsoft.com/v1.0/me/messages`), querying emails **strictly from `no-reply@famapp.in`**. All other emails, personal messages, and Gmail OTPs are ignored.
   - Backend parses email body for Amount, Payer Name, Transaction ID, UTR, and Received Timestamp.
4. **Instant Verification ("I Have Paid"):**
   - If payment isn't confirmed after 30 seconds (or user clicks "I Have Paid"), frontend calls `POST /api/payment/check-now/{requestId}` triggering an immediate Graph API query.
5. **Atomic DB Credit & History Entry:**
   - Upon matching email verification, backend updates `payment_requests` status to `Completed`, credits `wallets.balance` atomically, and logs a `transactions` record with `payment_method = "FamPay Test"` and `payment_source = "FAMPAY_TEST"`.
   - Frontend displays success checkmark (`✓ ₹250 added successfully!`), closes modal, and refreshes wallet balance.

---

## ⚡ Setup & Environment Configuration

### Append Outlook & FamPay Settings in `backend/.env`:

```env
# Existing DB & Gmail SMTP settings remain untouched!
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_db_password
DB_NAME=tapgo
SECRET_KEY=your_super_secret_jwt_key
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=TapAndGo <your_email@gmail.com>

# Outlook & FamPay Payment Verification Settings (Appended)
OUTLOOK_CLIENT_ID=
OUTLOOK_CLIENT_SECRET=
OUTLOOK_TENANT_ID=common
OUTLOOK_REFRESH_TOKEN=
OUTLOOK_EMAIL=
FAMPAY_UPI_ID=fampay@upi
FAMPAY_MERCHANT_NAME=TapAndGo
PAYMENT_PROVIDER=FAMPAY_TEST
PAYMENT_CHECK_INTERVAL=5
PAYMENT_TIMEOUT=30
```

### Start Backend & Frontend:

```bash
# Backend
cd backend
./venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm run dev
```

---

## 🔑 Admin Console Credentials

- **Admin Email:** `admin@example.com`
- **Admin Password:** `admin123`
- Logging in as `admin@example.com` on the main login form automatically redirects to `/admin`.
