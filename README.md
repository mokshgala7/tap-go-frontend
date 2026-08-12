# Tap&Go — Smart Transit Payouts & Cashless Payment Platform

Tap&Go is a modern, secure, and instant cashless payment and payout ecosystem built for transit (passengers, drivers, and fleet operators). It features Razorpay Standard Checkout for wallet funding, internal wallet-to-wallet ride payments, Email OTP protected withdrawals, NFC Tap-to-Pay, QR Payments, digital signature integration, document verification, database-backed wallet management, admin request approval workflows, and role-based dashboards.

---

## 🚧 Development Notice

Tap&Go is currently under active development. Some features may be unavailable while we complete development and testing.

---

## 📋 Technical & Operational Overview

This deployment demonstrates the complete application workflow of **Tap&Go**.

### 1. Payment Gateway (Razorpay)
- **Wallet Top-Up (Add Money):** Integrated with Razorpay Standard Checkout. Users enter the desired top-up amount, an order is generated via `POST /api/payment/create-order`, and Razorpay modal handles checkout (UPI, cards, netbanking). Payments are verified atomically on the backend via HMAC SHA256 signature check before crediting wallet balances.
- **Internal Ride Payments:** Normal passenger-to-driver fare settlements bypass external gateways completely and execute internally as atomic wallet transactions (`POST /api/wallet/pay`), avoiding payment gateway transaction fees during transit.
- **Withdrawals:** Wallet withdrawals require a 6-digit Email OTP request (`POST /api/wallet/withdraw/request-otp`) and verification before processing atomic balance deductions and logging withdrawal records.

### 2. Database Persistence
- The backend database uses MySQL / SQLite (ORM via SQLAlchemy). Account registrations, wallet top-ups, ride payments, profile updates, and admin actions are persisted in active database storage.

### 3. Uploaded Document Storage
- Uploaded driver licences, vehicle RC books, Aadhaar/PAN cards, and digital signatures are stored in `backend/uploads/` and served via static endpoints.

---

## 🚀 Architecture & Tech Stack

```text
React 18 / Vite Frontend  <--->  FastAPI (Python 3.14+) Backend  <--->  MySQL / SQLite Database
       │                                     │
   Single Page App                      Uploads Server
 (Session/Tab Persistence)          (backend/uploads/)
                                             │
                                   Razorpay Gateway SDK
                                (Add Money & Signature Checks)
```

- **Frontend:** React 18, Vite, Vanilla CSS Design Tokens, Razorpay Standard Web Checkout, HTML5 Canvas (Digital Signature & QR Code Renderer), jsQR (QR Code Scanning).
- **Backend:** FastAPI, Uvicorn, SQLAlchemy ORM, Razorpay Python SDK, PyMySQL.
- **Database:** MySQL / SQLite (`tapgo`).
- **Authentication & Security:** Password Hashing (bcrypt), HMAC-SHA256 Payment Verification, Email OTP Verification.
- **File Storage:** Local Static File Server (`backend/uploads/`) for Profile Photos, Digital Signatures, Aadhaar/PAN, RC, Licence, and Insurance documents.

---

## 💻 Environment Variables

### Backend Configuration (`backend/.env`):

```ini
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_razorpay_secret
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret

DATABASE_URL=sqlite:///./tapgo.db
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_app_password
SECRET_KEY=your_jwt_secret_key
```

### Frontend Configuration (`frontend/.env`):

```ini
VITE_RAZORPAY_KEY_ID=rzp_test_your_key_id
VITE_API_BASE_URL=https://tap-go-backend.onrender.com
```
