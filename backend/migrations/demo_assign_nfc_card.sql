-- Demo helper: give ONE existing passenger an NFC card with a chip UID (Supabase SQL editor).
-- Run 2026_10_nfc_card_uid.sql first. Edit the two values below, then run the whole script.
--
-- Inserts exactly one row into nfc_cards and changes nothing else. It refuses (with a clear error,
-- and inserts nothing) when the email is not an active passenger, the UID is not 4/7 bytes of hex,
-- the UID already belongs to a card, or the passenger already has an active or blocked card.

DO $$
DECLARE
    v_email    text := lower(trim('PASSENGER_EMAIL_HERE'));      -- <- passenger's login email
    v_uid_raw  text := 'CARD_UID_HERE';                          -- <- e.g. 04:A2:B3:C4:D5:E6:80 or 04A2B3C4D5E680
    v_uid      text;
    v_user     record;
    v_existing record;
    v_ref      text;
    v_id       integer;
BEGIN
    v_uid := upper(regexp_replace(v_uid_raw, '[[:space:]:-]', '', 'g'));
    IF v_uid !~ '^([0-9A-F]{8}|[0-9A-F]{14})$' THEN
        RAISE EXCEPTION 'Card UID must be 8 or 14 hex characters (4 or 7 bytes); got "%".', v_uid_raw;
    END IF;

    SELECT id, name, account_type, status INTO v_user FROM users WHERE lower(email) = v_email;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'No user with email "%".', v_email;
    END IF;
    IF v_user.account_type <> 'passenger' OR v_user.status <> 'active' THEN
        RAISE EXCEPTION 'User % is % / %: cards can only go to active passengers.', v_user.id, v_user.account_type, v_user.status;
    END IF;

    SELECT id, card_reference, status INTO v_existing
      FROM nfc_cards WHERE user_id = v_user.id AND status IN ('active', 'blocked') LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'Passenger % already has a % card (%). Nothing inserted.', v_user.id, v_existing.status, v_existing.card_reference;
    END IF;

    PERFORM 1 FROM nfc_cards WHERE card_uid = v_uid;
    IF FOUND THEN
        RAISE EXCEPTION 'Card UID % is already assigned to another card. Nothing inserted.', v_uid;
    END IF;

    v_ref := 'NFC-' || upper(substr(md5(random()::text || clock_timestamp()::text), 1, 12));

    INSERT INTO nfc_cards (user_id, card_reference, card_uid, card_type, status, issued_at)
    VALUES (v_user.id, v_ref, v_uid, 'standard_nfc', 'active', (now() AT TIME ZONE 'utc'))
    RETURNING id INTO v_id;

    RAISE NOTICE 'Issued card id % (%) with UID % to passenger % (user_id %).', v_id, v_ref, v_uid, v_user.name, v_user.id;
END $$;

-- Check the result (replace the email):
-- SELECT c.id, c.card_reference, c.card_uid, c.status, u.name, u.email
--   FROM nfc_cards c JOIN users u ON u.id = c.user_id WHERE lower(u.email) = lower('PASSENGER_EMAIL_HERE');
