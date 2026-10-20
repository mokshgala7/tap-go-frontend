-- Stage 1 security migration (Tap&Go backend) -- REVIEW BEFORE RUNNING; NOT applied by Claude.
--
-- What changes
--   1. New table admin_sessions   (server-side administrator sessions)       -- created automatically by Base.metadata.create_all at startup
--   2. New table payment_orders   (server-side record of each Razorpay order) -- created automatically by Base.metadata.create_all at startup
--   3. UNIQUE index on transactions.provider_transaction_id                   -- created at startup by ensure_unique_provider_transaction_index()
--      ONLY if no duplicates exist; otherwise skipped with an error log.
--
-- Nothing in this file deletes or rewrites existing rows.
--
-- ============================================================================
-- STEP 0 -- DUPLICATE CHECK (read-only). Run on a COPY / read replica first.
-- Expected result: zero rows. Any row returned must be reviewed by a human.
-- ============================================================================
SELECT provider_transaction_id, COUNT(*) AS n,
       MIN(id) AS first_id, MAX(id) AS last_id
FROM transactions
WHERE provider_transaction_id IS NOT NULL
GROUP BY provider_transaction_id
HAVING COUNT(*) > 1;

-- Details of any duplicates (inspect amounts / wallets / times before deciding):
-- SELECT t.* FROM transactions t
-- WHERE t.provider_transaction_id IN (<values from above>) ORDER BY t.provider_transaction_id, t.id;

-- Data-cleanup implications if duplicates exist
--   A duplicated Razorpay payment id means the same payment may have credited a wallet twice
--   (the former verify-payment/webhook race). Do NOT delete rows. Decide, per case, whether the
--   second credit must be reversed with an explicit compensating ledger entry, then (and only then)
--   make provider_transaction_id values unique (e.g. set the later duplicate's value to NULL after
--   recording it in a note) and re-run the index step.

-- ============================================================================
-- STEP 1 -- CREATE THE INDEX (PostgreSQL / MySQL / SQLite all accept this form)
-- (The application runs this itself at startup when STEP 0 returns no rows.)
-- ============================================================================
CREATE UNIQUE INDEX ux_transactions_provider_transaction_id
    ON transactions (provider_transaction_id);

-- ============================================================================
-- ROLLBACK
-- ============================================================================
-- PostgreSQL / SQLite:  DROP INDEX ux_transactions_provider_transaction_id;
-- MySQL:                DROP INDEX ux_transactions_provider_transaction_id ON transactions;
-- Dropping the new tables is safe only while they are unused:
--   DROP TABLE payment_orders;   -- (loses the order->user/amount mapping; unpaid orders could no longer be verified)
--   DROP TABLE admin_sessions;   -- (all administrators must log in again)
-- Reverting the code without these drops is also safe: the old code ignores the extra tables/index.
