-- Failed NFC taps are recorded as transactions with status = 'failed' (Tap&Go backend, Supabase Postgres).
-- Also applied automatically at startup by run_database_migrations() (step 4, txn_migrations in app/main.py);
-- run it once in the Supabase SQL editor BEFORE the backend redeploys if you want the column in place first.
--
-- Adds nullable transactions.failure_code (e.g. INSUFFICIENT_BALANCE, CARD_BLOCKED). NULL for every
-- existing row. Nothing is deleted or rewritten. Safe to run more than once.

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS failure_code VARCHAR(40) NULL;
