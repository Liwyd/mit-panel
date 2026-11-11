# Monthly bot maintenance billing

## Using it

The default fee is **EUR 1.00 per active, enrolled bot per calendar month**.
Existing and new bots start with automatic maintenance invoicing **off**. Nothing
is billed just because this release is installed.

- Dashboard: open **ربات**, then **فاکتور ماهانه نگهداری ربات**. Set the monthly
  euro price and enable individual bots. Refresh to see the next run and the
  latest invoice/delivery status.
- Telegram superadmin: **امور مالی** → **🛠 فاکتور نگهداری ربات**. Pick a bot to
  enable/disable billing, or choose **تغییر قیمت یورویی**.
- The main Telegram invoicing bot must be running. A bot needs an assigned,
  active admin with a positive Telegram ID; observer admins are excluded.
  The customer's chat must allow messages from the main invoicing bot.
- The first invoice is issued on the next scheduler run (normally within one
  minute, provided the exchange-rate service is available), then on monthly
  anniversaries in Tehran time. January 31 becomes February 28/29, then March 31.
- Disabling stops future issuance. Existing bills stay payable; re-enabling
  within an already-invoiced period does not charge it again. Inactive bots or
  admins are skipped. Ownership/contact changes require explicit re-enrollment.
- Recovery after several missed months bills only the current period and sends
  the superadmin a notice listing how many earlier periods were skipped.

## Rate, invoices and payment

The free, no-key source is [PriceDB](https://github.com/margani/pricedb), using its
[TGJU euro market quote](https://api.priceto.day/v1/latest/irr/euro) and
[health endpoint](https://api.priceto.day/v1/health). It publishes periodically
(about every 30 minutes during market hours), not tick-by-tick or as a separate
buy/sell spread. No API key, subscription, new environment variable, or server
configuration is needed. Free third-party availability is not guaranteed.

The provider must report healthy updates. Malformed, non-positive, future-dated
(over five minutes), and older-than-72-hour quotes/health timestamps are rejected.
The age window permits market closures over weekends. Failed requests defer
invoicing with persisted exponential retry (one minute to one hour); the
superadmin receives at most one rate-failure notice per Tehran day.

Each invoice freezes the fee, IRR/EUR quote, source time, service period, and
recipient. Tomans = EUR fee × IRR quote ÷ 10, rounded half-up to an integer.
Price edits affect future invoices only. Fees accept 0.01–10000 EUR with at most
two decimal places. Maintenance payments never buy or credit traffic.

The customer pays through the existing invoice receipt/approval flow. Bills
appear in the existing customer and superadmin invoice lists, reports and ledger.
The payment deadline begins **three days after successful Telegram notification**.
An undelivered bill has no deadline and cannot trigger an automatic lock. After
the deadline plus the existing 12-hour grace, normal dashboard locking applies;
the existing payment/unlock logic restores access once obligations are clear.
No command is sent to shut down the customer's sales bot or Marzban panel.

Persistent delivery claims retry the same invoice after restarts or blocked chats.
A crash after Telegram accepted a message but before SQLite acknowledged delivery
can repeat that notification; it cannot create a second charge for the period.
Paid or cancelled invoices are not retried. Delivery failures are shown in the
dashboard and notified to the superadmin.

## Implementation and compatibility

All new tables/indexes are initialized idempotently by `backend/bot/db.py`.
No existing invoice columns, deployment files, Alembic revisions, or traffic
accounting rules change. Owner invalidation participates in the existing ORM
transaction; issuance rechecks the current identity under SQLite's writer lock.
Invoice insertion, period reservation, and schedule advancement share one local
transaction. Network calls never hold a SQLite transaction open. Scheduler work
runs in bounded batches and database work is offloaded from the asyncio loop.

Superadmin API (under the configured panel prefix):

- `GET /sales-bots/maintenance`: global price, runtime state, eligibility,
  enrollment, next run, latest invoice/delivery status for each registered bot.
- `PUT /sales-bots/maintenance/price`: `{"eur_price":"1.50"}`.
- `PUT /sales-bots/maintenance/{bot_id}`: `{"enabled":true}` (strict boolean).

All three reject non-superadmin users. Enabling through the web API requires the
main invoicing bot to be running. Configuration is stored through the existing
settings store, not `.env`.

## Manual release with mit-update

Only update after the exact release commit's GitHub workflows have succeeded
and its Docker image has been published. The CI workflows currently publish
images; application tests are also run locally before pushing this release.

**SEVERE — Existing updater can delete live data on a failed source pull:** the repository updater stops the container before
pulling the image, and its failed-`git pull` fallback deletes and re-clones the
source directory. Compose stores `data/` and `.env` relative to that directory.
If that is your live installation directory, the fallback can delete live data
and configuration. This release leaves that existing updater unchanged. Keep a
verified backup **outside** the checkout, and allow a brief maintenance window.
Do not run the updater without that backup.

Before updating, run from your actual installation directory (the directory
containing its Compose file), using your usual Docker permissions:

```bash
set -e
umask 077
backup_dir="$HOME/mitpanel-backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
docker inspect mit-panel > "$backup_dir/container.json"
docker inspect --format '{{.Image}}' mit-panel > "$backup_dir/image-id"
docker compose config > "$backup_dir/compose.yml"
docker exec -i mit-panel uv run python - <<'PYSQL'
import sqlite3
with sqlite3.connect('/app/data/mitpanel.db') as src:
    with sqlite3.connect('/tmp/mitpanel-before-maintenance.db') as dst:
        src.backup(dst)
        assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
PYSQL
docker cp mit-panel:/app/data "$backup_dir/data"
docker cp mit-panel:/tmp/mitpanel-before-maintenance.db "$backup_dir/data/mitpanel.db"
# Remove copied journal sidecars from the BACKUP only; the snapshot is standalone.
rm -f -- "$backup_dir/data/mitpanel.db-wal" "$backup_dir/data/mitpanel.db-shm" "$backup_dir/data/mitpanel.db-journal"
docker cp mit-panel:/app/.env "$backup_dir/.env"
```

Check that every command succeeded. The backup contains private configuration;
keep it private. The database is copied using SQLite's backup API rather than
relying on a copy of an actively written database file. Preserve the current
image locally and pre-pull the new image before the maintenance window:

```bash
docker image tag "$(cat "$backup_dir/image-id")" "liwyd/mit-panel:before-maintenance-$(date -u +%Y%m%dT%H%M%SZ)"
docker pull liwyd/mit-panel:latest
docker image inspect liwyd/mit-panel:latest --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
```

Confirm the printed revision is the tested release commit, then run your existing
update command:

```bash
mit-update
```

Afterward, check container status/logs, dashboard login, the main Telegram bot,
and an ordinary existing payment flow. Confirm every maintenance switch remains
off. Enable just one intended bot first; check its recipient, rate, amount,
service period and invoice delivery before enabling the rest. Use real invoice
cancellation to write off any intentional trial bill, not direct database edits.

### Rollback

If the application fails after updating and its existing data/configuration are
still present, roll back the **image**, keeping the current database (the new
schema is additive). Run these yourself, not while another update is running:

```bash
docker image tag "$(cat "$backup_dir/image-id")" liwyd/mit-panel:latest
docker compose -f "$backup_dir/compose.yml" up -d --pull never --no-deps --force-recreate mit-panel
```

The saved Compose config records the original absolute mount paths. If the
updater deleted the installation directory, do not start a container against
empty mounts: first restore `.env` and the backed-up data directory to the paths
recorded in `container.json`/`compose.yml`, with the service stopped. Do not restore
a database snapshot over a running service or after accepting new payments;
that would lose intervening transactions. A database restore is disaster
recovery, not the normal image rollback. Do not drop the new tables during rollback.
