-- NFC card chip UID (Tap&Go backend, Supabase Postgres).
-- Also applied automatically at startup by run_database_migrations() (step 8b in app/main.py);
-- run it once in the Supabase SQL editor BEFORE the backend redeploys if you want the column in place first.
--
-- Adds nullable nfc_cards.card_uid (uppercase hex, no separators, 8 or 14 chars) with a UNIQUE index.
-- Nothing is deleted or rewritten. Existing cards keep card_uid = NULL until an admin assigns one.
-- Safe to run more than once.

ALTER TABLE nfc_cards ADD COLUMN IF NOT EXISTS card_uid VARCHAR(32) NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_nfc_cards_card_uid ON nfc_cards(card_uid);
