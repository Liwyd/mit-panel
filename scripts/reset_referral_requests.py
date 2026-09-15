#!/usr/bin/env python3
"""Reset all pending referral requests so users can re-submit.

SAFETY: This ONLY touches the referral_requests table and ONLY deletes
rows where status = 'pending'. All other tables and data are untouched.

Usage (inside Docker container):
    docker exec -it mit-panel python /app/scripts/reset_referral_requests.py
"""

import os
import sqlite3
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "mitpanel.db")


def main():
    if not os.path.isfile(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    print(f"📂 Database: {DB_PATH}")
    print(f"📊 Size: {os.path.getsize(DB_PATH):,} bytes")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='referral_requests'"
    ).fetchone()

    if not table_exists:
        print("ℹ️  Table 'referral_requests' does not exist yet. Nothing to clean.")
        conn.close()
        return

    total = conn.execute("SELECT COUNT(*) FROM referral_requests").fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM referral_requests WHERE status = 'pending'"
    ).fetchone()[0]
    approved = conn.execute(
        "SELECT COUNT(*) FROM referral_requests WHERE status = 'approved'"
    ).fetchone()[0]
    rejected = conn.execute(
        "SELECT COUNT(*) FROM referral_requests WHERE status = 'rejected'"
    ).fetchone()[0]

    print(f"\n📊 Current referral_requests:")
    print(f"   Total:    {total}")
    print(f"   Pending:  {pending}")
    print(f"   Approved: {approved}")
    print(f"   Rejected: {rejected}")

    if pending == 0:
        print("\n✅ No pending requests to clean.")
        conn.close()
        return

    rows = conn.execute(
        "SELECT id, telegram_id, username, status, created_at "
        "FROM referral_requests WHERE status = 'pending'"
    ).fetchall()
    print(f"\n🔍 Pending requests to delete:")
    for row in rows:
        print(f"   #{row['id']} | tg_id={row['telegram_id']} | @{row['username']} | {row['created_at']}")

    cursor = conn.execute(
        "DELETE FROM referral_requests WHERE status = 'pending'"
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    print(f"\n✅ Deleted {deleted} pending referral request(s).")
    print(f"   Approved/rejected requests preserved.")


if __name__ == "__main__":
    main()
