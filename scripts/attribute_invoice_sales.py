"""Book past invoice payments under their panel, from a given date on.

Until the fix in db.invoice_ledger_fields, a paid invoice went into the sales
ledger with no panel unless paying it granted traffic, so the profit report
showed it as «بدون پنل» at 100% profit. This finds each such ledger row's
invoice — same customer, same amount, paid within two minutes of the row — and
copies the invoice's panel (and billed usage GB, if any) onto the row. A row
whose invoice names no panel, or that matches no invoice or more than one, is
left as it is.

Dry run by default; --apply writes. Run inside the panel container:

    python scripts/attribute_invoice_sales.py --since 2026-11-21T20:30:00+00:00
    python scripts/attribute_invoice_sales.py --since 2026-11-21T20:30:00+00:00 --apply
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta

WINDOW = timedelta(minutes=2)


def _when(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def plan(conn: sqlite3.Connection, since: str) -> list[tuple[int, str, float]]:
    """(sale id, panel, gb) for every row that can be attributed for sure."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(invoices)")}
    usage = "usage_gb" if "usage_gb" in cols else "0"
    invoices = conn.execute(
        f"SELECT id, telegram_id, amount, admin_username, {usage}, paid_at FROM invoices "
        "WHERE status = 'paid' AND paid_at IS NOT NULL AND admin_username IS NOT NULL "
        "AND admin_username != ''"
    ).fetchall()
    out = []
    rows = conn.execute(
        "SELECT id, telegram_id, amount, created_at FROM sales "
        "WHERE method = 'invoice' AND (username IS NULL OR username = '') AND created_at >= ?",
        (since,),
    ).fetchall()
    for sale_id, telegram_id, amount, created_at in rows:
        at = _when(created_at)
        found = [
            inv for inv in invoices
            if inv[1] == telegram_id and inv[2] == amount and abs(_when(inv[5]) - at) <= WINDOW
        ]
        if len(found) == 1:
            out.append((sale_id, found[0][3], float(found[0][4] or 0)))
        else:
            print(f"sale #{sale_id}: {len(found)} matching invoices, left as it is")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="data/mitpanel.db")
    parser.add_argument("--since", required=True, help="ISO timestamp (UTC), e.g. the month start")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    changes = plan(conn, args.since)
    for sale_id, panel, gb in changes:
        print(f"sale #{sale_id} -> panel {panel}, gb {gb}")
    if not args.apply:
        print(f"dry run: {len(changes)} row(s) would change; rerun with --apply")
        return
    with conn:
        for sale_id, panel, gb in changes:
            conn.execute(
                "UPDATE sales SET username = ?, gb = ? WHERE id = ? AND method = 'invoice' "
                "AND (username IS NULL OR username = '')",
                (panel, gb, sale_id),
            )
    print(f"applied: {len(changes)} row(s)")


if __name__ == "__main__":
    main()
