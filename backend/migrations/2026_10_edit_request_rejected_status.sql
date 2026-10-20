-- Repair of rows written by the old admin review bug ("reject" + "d" = "rejectd").
-- NOT executed automatically. Review, take a backup, then run once on the target database.
-- Idempotent: after it runs, the WHERE clause matches nothing.
UPDATE edit_requests SET status = 'rejected' WHERE status = 'rejectd';
-- Verify afterwards (expect only pending / approved / rejected):
-- SELECT status, COUNT(*) FROM edit_requests GROUP BY status;
