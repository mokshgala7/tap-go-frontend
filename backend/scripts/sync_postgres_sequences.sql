-- Synchronize PostgreSQL SERIAL sequences after data import.
-- Ensures that next inserted ID = MAX(existing ID) + 1, handling empty tables safely.
-- Run this in the Supabase SQL Editor immediately following data import.

-- 1. users
SELECT setval(
    pg_get_serial_sequence('users', 'id'),
    COALESCE((SELECT MAX(id) FROM users), 1),
    (SELECT MAX(id) FROM users) IS NOT NULL
);

-- 2. email_otps
SELECT setval(
    pg_get_serial_sequence('email_otps', 'id'),
    COALESCE((SELECT MAX(id) FROM email_otps), 1),
    (SELECT MAX(id) FROM email_otps) IS NOT NULL
);

-- 3. admins
SELECT setval(
    pg_get_serial_sequence('admins', 'id'),
    COALESCE((SELECT MAX(id) FROM admins), 1),
    (SELECT MAX(id) FROM admins) IS NOT NULL
);

-- 4. wallets
SELECT setval(
    pg_get_serial_sequence('wallets', 'id'),
    COALESCE((SELECT MAX(id) FROM wallets), 1),
    (SELECT MAX(id) FROM wallets) IS NOT NULL
);

-- 5. payment_requests
SELECT setval(
    pg_get_serial_sequence('payment_requests', 'id'),
    COALESCE((SELECT MAX(id) FROM payment_requests), 1),
    (SELECT MAX(id) FROM payment_requests) IS NOT NULL
);

-- 6. transactions
SELECT setval(
    pg_get_serial_sequence('transactions', 'id'),
    COALESCE((SELECT MAX(id) FROM transactions), 1),
    (SELECT MAX(id) FROM transactions) IS NOT NULL
);

-- 7. user_documents
SELECT setval(
    pg_get_serial_sequence('user_documents', 'id'),
    COALESCE((SELECT MAX(id) FROM user_documents), 1),
    (SELECT MAX(id) FROM user_documents) IS NOT NULL
);

-- 8. edit_requests
SELECT setval(
    pg_get_serial_sequence('edit_requests', 'id'),
    COALESCE((SELECT MAX(id) FROM edit_requests), 1),
    (SELECT MAX(id) FROM edit_requests) IS NOT NULL
);

-- 9. fraud_alerts
SELECT setval(
    pg_get_serial_sequence('fraud_alerts', 'id'),
    COALESCE((SELECT MAX(id) FROM fraud_alerts), 1),
    (SELECT MAX(id) FROM fraud_alerts) IS NOT NULL
);

-- 10. activity_logs
SELECT setval(
    pg_get_serial_sequence('activity_logs', 'id'),
    COALESCE((SELECT MAX(id) FROM activity_logs), 1),
    (SELECT MAX(id) FROM activity_logs) IS NOT NULL
);

-- 11. nfc_card_orders
SELECT setval(
    pg_get_serial_sequence('nfc_card_orders', 'id'),
    COALESCE((SELECT MAX(id) FROM nfc_card_orders), 1),
    (SELECT MAX(id) FROM nfc_card_orders) IS NOT NULL
);
