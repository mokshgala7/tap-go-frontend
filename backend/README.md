# Tap&Go Backend (coming next)

Nothing lives here yet. The frontend currently runs with no database and
no real API - login/register accept any values and are stored only in the
browser (localStorage) via `frontend/src/context/AuthContext.jsx`, and
wallet/transaction data is mocked in `frontend/src/context/WalletContext.jsx`.

Planned stack per the project spec: Python + FastAPI, Relational Database,
External Payment Gateway + Supported Withdrawal Provider, and the Random Forest fraud-detection model. This
folder is reserved for backend architecture.
