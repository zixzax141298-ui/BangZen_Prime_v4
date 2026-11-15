# Runbook

## Startup
1. `bangzen-prime status`: confirm live_trading=false, paper_trading=true, dry_run=true.
2. `bangzen-prime migrate`: applies pending migrations. Build also applies them, and it is idempotent.
3. `bangzen-prime health`: must print `"status": "OK"`.

## Routine
- `bangzen-prime scan <mint>...`: one scan per token (network).
- `bangzen-prime outbox`: one delivery pass. Schedule it. Repeat runs are safe.
- `bangzen-prime health`: exit 1 when status is DEGRADED or DOWN.
- `bangzen-prime audit-verify`: must print `intact: true`. Anything else is an incident.
- `bangzen-prime prune --days 30`: removes delivered outbox rows and old processed markers.
  Audit history is kept.
- `bangzen-prime backup <path>`: take a consistent copy. Store it outside the repository.

## Restore
1. Stop every process that writes to the database.
2. `bangzen-prime restore <path>`. It verifies integrity, required tables, and the audit chain
   before replacing the live file. A failed check changes nothing.
3. `bangzen-prime health` and `bangzen-prime audit-verify`.

## Stop new paper orders
Set `BANGZEN_EMERGENCY_STOP=true` and restart. The risk engine rejects new positions with
EMERGENCY_STOP. Existing audit history is kept.

## Troubleshooting
- `DEGRADED` with `outbox.FAILED > 0`: dead-lettered events exceeded max attempts. Read
  `last_error` in the outbox table, fix the cause (usually notifier outage), then correct the row
  by hand. There is no re-enqueue command. Record the change.
- `DEGRADED` with `audit_intact: false`: stop, do not write. Restore from the last verified backup.
- `DOWN`: database unreachable or locked. Check file permissions, disk space, and any other process
  holding the write lock. Busy errors surface as PersistenceError, not as silent failures.
- Worker disabled (`bangzen_worker_disabled` gauge = 1): repeated failures crossed the threshold.
  Fix the cause and restart the supervisor. Restarting resets the in-memory counter.
- Chain attempt in UNKNOWN: do not resubmit. Run `reconcile` on the attempt. It becomes DROPPED
  only after the plan's expiry with no signature found.

## Restart
Open paper positions are in `orders` with status FILLED or PARTIALLY_FILLED. They resume on the
next `on_price` call. `reconcile()` should return an empty list.
