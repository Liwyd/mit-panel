"""SQLite persistence for top-up requests: audit trail + idempotency guard.

A single small table, plain sqlite3 (no ORM needed). The request must survive
bot restarts because manual card-to-card review can take hours/days, and the
atomic pending->approved/rejected flip is what stops a double-tapped Approve
button from double-crediting an admin's traffic balance.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.bot.config import bot_config


def _connect() -> sqlite3.Connection:
    directory = os.path.dirname(bot_config.sqlite_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(bot_config.sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    """Add a column to an already-created table. There are no migrations here,
    so this is what lets an existing deployment pick up new columns on restart."""
    existing = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS topup_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_telegram_id INTEGER NOT NULL,
                admin_username TEXT,
                requested_gb REAL NOT NULL,
                toman_amount INTEGER NOT NULL,
                receipt_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by INTEGER,
                reject_reason TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS password_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_telegram_id INTEGER NOT NULL,
                admin_username TEXT,
                new_password TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                applied_at TEXT,
                applied_by INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_payment (
                username TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS wallets (
                telegram_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS debts (
                username TEXT PRIMARY KEY,
                telegram_id INTEGER,
                amount INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                description TEXT,
                due_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                paid_at TEXT,
                last_reminded_date TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS traffic_history (
                username TEXT NOT NULL,
                date TEXT NOT NULL,
                traffic_bytes INTEGER NOT NULL,
                initial_bytes INTEGER NOT NULL,
                PRIMARY KEY (username, date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS traffic_warnings (
                username TEXT PRIMARY KEY,
                last_bucket TEXT NOT NULL,
                notified_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tutorials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content_type TEXT NOT NULL,
                text TEXT,
                file_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_prices (
                admin_username TEXT PRIMARY KEY,
                price_per_gb REAL NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS panel_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                panel_name TEXT NOT NULL,
                traffic_gb REAL NOT NULL,
                receipt_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reject_reason TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                reviewed_at TEXT,
                reviewed_by INTEGER,
                referral_code_id INTEGER,
                desired_username TEXT,
                desired_password TEXT
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referral_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_telegram_id INTEGER NOT NULL,
                code TEXT NOT NULL UNIQUE,
                bonus_percent REAL NOT NULL DEFAULT 12.0,
                price_per_gb REAL NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referral_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER NOT NULL,
                buyer_telegram_id INTEGER NOT NULL,
                buyer_username TEXT,
                traffic_gb REAL NOT NULL,
                bonus_granted_gb REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )

        # Columns added after the tables above first shipped.
        _ensure_column(conn, "topup_requests", "kind", "TEXT NOT NULL DEFAULT 'topup'")
        _ensure_column(conn, "bot_users", "is_linked", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "tutorials", "source_chat_id", "INTEGER")
        _ensure_column(conn, "tutorials", "source_message_id", "INTEGER")
        _ensure_column(conn, "debts", "overdue_since", "TEXT")
        _ensure_column(conn, "topup_requests", "invoice_id", "INTEGER")
        # When a non-payment warning was last sent for a bill.
        _ensure_column(conn, "invoices", "last_warned_at", "TEXT")
        _ensure_column(conn, "debts", "last_warned_at", "TEXT")
        _ensure_column(conn, "panel_requests", "desired_username", "TEXT")
        _ensure_column(conn, "panel_requests", "desired_password", "TEXT")


@dataclass
class TopupRequest:
    id: int
    admin_telegram_id: int
    admin_username: str | None
    requested_gb: float
    toman_amount: int
    receipt_path: str
    status: str
    reviewed_by: int | None
    reject_reason: str | None
    created_at: str
    reviewed_at: str | None
    kind: str = "topup"
    invoice_id: int | None = None


def create_request(
    *,
    admin_telegram_id: int,
    admin_username: str | None,
    requested_gb: float,
    toman_amount: int,
    receipt_path: str,
    kind: str = "topup",
    invoice_id: int | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO topup_requests
                (admin_telegram_id, admin_username, requested_gb, toman_amount, receipt_path,
                 status, created_at, kind, invoice_id)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                admin_telegram_id,
                admin_username,
                requested_gb,
                toman_amount,
                receipt_path,
                now,
                kind,
                invoice_id,
            ),
        )
        return cur.lastrowid


def get_request(request_id: int) -> TopupRequest | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM topup_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return TopupRequest(**dict(row)) if row else None


def mark_reviewed(
    request_id: int, *, status: str, reviewed_by: int, reason: str | None = None
) -> bool:
    """Atomically flip a pending request to approved/rejected.

    Returns False (no-op) if the request was already handled — this is the
    guard against a redelivered/double-tapped callback double-crediting traffic.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE topup_requests
            SET status = ?, reviewed_by = ?, reviewed_at = ?, reject_reason = ?
            WHERE id = ? AND status = 'pending'
            """,
            (status, reviewed_by, now, reason, request_id),
        )
        return cur.rowcount == 1


def revert_to_pending(request_id: int) -> None:
    """Roll back to pending if the panel API call failed after approval was recorded locally."""
    with _connect() as conn:
        conn.execute(
            "UPDATE topup_requests SET status = 'pending', reviewed_by = NULL, reviewed_at = NULL WHERE id = ?",
            (request_id,),
        )


def user_exists(telegram_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM bot_users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row is not None


def upsert_user(telegram_id: int, username: str | None, full_name: str | None) -> None:
    """Record/refresh a bot user's info — needed so a superadmin can message them later."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_users (telegram_id, username, full_name, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_seen = excluded.last_seen
            """,
            (telegram_id, username, full_name, now, now),
        )


def ensure_user(telegram_id: int) -> None:
    """Make sure a row exists without touching a name we may already know."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_users (telegram_id, username, full_name, first_seen, last_seen)
            VALUES (?, NULL, NULL, ?, ?)
            ON CONFLICT(telegram_id) DO NOTHING
            """,
            (telegram_id, now, now),
        )


def list_pending_requests() -> list[TopupRequest]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM topup_requests WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [TopupRequest(**dict(row)) for row in rows]


def get_setting(key: str) -> str | None:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def get_admin_price(admin_username: str) -> float | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT price_per_gb FROM admin_prices WHERE admin_username = ?",
            (admin_username,),
        ).fetchone()
        return row["price_per_gb"] if row else None


def set_admin_price(admin_username: str, price_per_gb: float) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO admin_prices (admin_username, price_per_gb) VALUES (?, ?)",
            (admin_username, price_per_gb),
        )


def remove_admin_price(admin_username: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM admin_prices WHERE admin_username = ?", (admin_username,))


def get_effective_price(admin_username: str) -> float:
    per_admin = get_admin_price(admin_username)
    if per_admin is not None:
        return per_admin
    raw = get_setting("price_per_gb")
    return float(raw) if raw else 0.0


@dataclass
class PasswordRequest:
    id: int
    admin_telegram_id: int
    admin_username: str | None
    new_password: str
    status: str
    created_at: str
    applied_at: str | None
    applied_by: int | None


def create_password_request(
    *, admin_telegram_id: int, admin_username: str | None, new_password: str
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO password_requests
                (admin_telegram_id, admin_username, new_password, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
            """,
            (admin_telegram_id, admin_username, new_password, now),
        )
        return cur.lastrowid


def get_password_request(request_id: int) -> PasswordRequest | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM password_requests WHERE id = ?", (request_id,)
        ).fetchone()
        return PasswordRequest(**dict(row)) if row else None


def mark_password_applied(request_id: int, *, applied_by: int | None) -> bool:
    """Atomically flip a pending password request to applied."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE password_requests
            SET status = 'applied', applied_at = ?, applied_by = ?
            WHERE id = ? AND status = 'pending'
            """,
            (now, applied_by, request_id),
        )
        return cur.rowcount == 1


def revert_password_request(request_id: int) -> None:
    """Roll back to pending if the panel API call failed after being marked applied."""
    with _connect() as conn:
        conn.execute(
            "UPDATE password_requests SET status = 'pending', applied_at = NULL, applied_by = NULL WHERE id = ?",
            (request_id,),
        )


def get_wallet_balance(telegram_id: int) -> int:
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row["balance"] if row else 0


def add_wallet_balance(telegram_id: int, amount: int) -> int:
    """Credit the wallet and return the new balance."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO wallets (telegram_id, balance, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                balance = balance + excluded.balance,
                updated_at = excluded.updated_at
            """,
            (telegram_id, amount, now),
        )
        row = conn.execute(
            "SELECT balance FROM wallets WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row["balance"]


def spend_wallet(telegram_id: int, amount: int) -> bool:
    """Deduct the full amount, or nothing at all if the balance won't cover it."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE wallets SET balance = balance - ?, updated_at = ? "
            "WHERE telegram_id = ? AND balance >= ?",
            (amount, now, telegram_id, amount),
        )
        return cur.rowcount == 1


def drain_wallet(telegram_id: int, up_to: int) -> int:
    """Spend as much of `up_to` as the wallet holds; returns the amount taken."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance FROM wallets WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        available = row["balance"] if row else 0
        taken = min(available, up_to)
        if taken > 0:
            conn.execute(
                "UPDATE wallets SET balance = balance - ?, updated_at = ? WHERE telegram_id = ?",
                (taken, now, telegram_id),
            )
        return taken


def is_weekly_enabled(username: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT enabled FROM weekly_payment WHERE username = ?", (username,)
        ).fetchone()
        return bool(row["enabled"]) if row else False


def set_weekly_enabled(username: str, enabled: bool) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO weekly_payment (username, enabled) VALUES (?, ?)
            ON CONFLICT(username) DO UPDATE SET enabled = excluded.enabled
            """,
            (username, 1 if enabled else 0),
        )


def list_weekly_enabled() -> list[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT username FROM weekly_payment WHERE enabled = 1").fetchall()
        return [r["username"] for r in rows]


def get_debt(username: str) -> int:
    with _connect() as conn:
        row = conn.execute("SELECT amount FROM debts WHERE username = ?", (username,)).fetchone()
        return row["amount"] if row else 0


def add_debt(username: str, telegram_id: int, amount: int) -> int:
    """Add to what this panel owes and return the new total."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO debts (username, telegram_id, amount, updated_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                amount = amount + excluded.amount,
                telegram_id = excluded.telegram_id,
                updated_at = excluded.updated_at
            """,
            (username, telegram_id, amount, now),
        )
        row = conn.execute("SELECT amount FROM debts WHERE username = ?", (username,)).fetchone()
        return row["amount"]


def reduce_debt(username: str, amount: int) -> int:
    """Pay part of a debt down (never below zero); returns what's still owed."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE debts SET amount = MAX(0, amount - ?), updated_at = ? WHERE username = ?",
            (amount, now, username),
        )
        conn.execute(
            "UPDATE debts SET overdue_since = NULL WHERE username = ? AND amount <= 0", (username,)
        )
        row = conn.execute("SELECT amount FROM debts WHERE username = ?", (username,)).fetchone()
        return row["amount"] if row else 0


def clear_debt(username: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE debts SET amount = 0, overdue_since = NULL, updated_at = ? WHERE username = ?",
            (now, username),
        )


def mark_overdue(username: str) -> None:
    """Stamp a debt as past due."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE debts SET overdue_since = ? WHERE username = ? AND overdue_since IS NULL",
            (now, username),
        )


def list_outstanding_debts() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT username, telegram_id, amount, overdue_since, updated_at, last_warned_at "
            "FROM debts "
            "WHERE amount > 0 ORDER BY username"
        ).fetchall()
        return [dict(r) for r in rows]


@dataclass
class Invoice:
    id: int
    telegram_id: int
    amount: int
    description: str | None
    due_at: str | None
    status: str
    created_at: str
    paid_at: str | None
    last_reminded_date: str | None
    last_warned_at: str | None = None


def create_invoice(
    *, telegram_id: int, amount: int, description: str | None, due_at: str | None
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO invoices (telegram_id, amount, description, due_at, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (telegram_id, amount, description, due_at, now),
        )
        return cur.lastrowid


def get_invoice(invoice_id: int) -> Invoice | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        return Invoice(**dict(row)) if row else None


def list_pending_invoices(telegram_id: int | None = None) -> list[Invoice]:
    query = "SELECT * FROM invoices WHERE status = 'pending'"
    params: tuple = ()
    if telegram_id is not None:
        query += " AND telegram_id = ?"
        params = (telegram_id,)
    query += " ORDER BY created_at"
    with _connect() as conn:
        return [Invoice(**dict(r)) for r in conn.execute(query, params).fetchall()]


def mark_invoice_paid(invoice_id: int) -> bool:
    """Atomically settle a pending invoice; False if it was already handled."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE invoices SET status = 'paid', paid_at = ? WHERE id = ? AND status = 'pending'",
            (now, invoice_id),
        )
        return cur.rowcount == 1


def cancel_invoice(invoice_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE invoices SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
            (invoice_id,),
        )
        return cur.rowcount == 1


def set_invoice_reminded(invoice_id: int, date_stamp: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE invoices SET last_reminded_date = ? WHERE id = ?",
            (date_stamp, invoice_id),
        )


def mark_invoice_warned(invoice_id: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("UPDATE invoices SET last_warned_at = ? WHERE id = ?", (now, invoice_id))


def mark_debt_warned(username: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute("UPDATE debts SET last_warned_at = ? WHERE username = ?", (now, username))


def get_debt_record(username: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT username, telegram_id, amount, overdue_since, updated_at, last_warned_at "
            "FROM debts WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


def has_billing_account(telegram_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM bot_users WHERE telegram_id = ? AND is_linked = 1
            UNION ALL SELECT 1 FROM invoices WHERE telegram_id = ?
            UNION ALL SELECT 1 FROM debts WHERE telegram_id = ?
            LIMIT 1
            """,
            (telegram_id, telegram_id, telegram_id),
        ).fetchone()
        return row is not None


def record_traffic_snapshot(
    username: str, date_stamp: str, traffic_bytes: int, initial_bytes: int
) -> None:
    """Store today's reading, overwriting any earlier one for the same day."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO traffic_history (username, date, traffic_bytes, initial_bytes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username, date) DO UPDATE SET
                traffic_bytes = excluded.traffic_bytes,
                initial_bytes = excluded.initial_bytes
            """,
            (username, date_stamp, traffic_bytes, initial_bytes),
        )


def get_traffic_history(username: str, since_date: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date, traffic_bytes, initial_bytes FROM traffic_history "
            "WHERE username = ? AND date >= ? ORDER BY date",
            (username, since_date),
        ).fetchall()
        return [dict(r) for r in rows]


def prune_traffic_history(before_date: str) -> None:
    """Only a rolling window is ever used, so older rows are dead weight."""
    with _connect() as conn:
        conn.execute("DELETE FROM traffic_history WHERE date < ?", (before_date,))


def list_requests_for(telegram_id: int, limit: int = 10) -> list[TopupRequest]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM topup_requests WHERE admin_telegram_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (telegram_id, limit),
        ).fetchall()
        return [TopupRequest(**dict(r)) for r in rows]


def deduct_wallet(telegram_id: int, amount: int) -> int:
    """Superadmin correction: take up to `amount`, never past zero."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE wallets SET balance = MAX(0, balance - ?), updated_at = ? WHERE telegram_id = ?",
            (amount, now, telegram_id),
        )
        row = conn.execute(
            "SELECT balance FROM wallets WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return row["balance"] if row else 0


def get_warning_bucket(username: str) -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_bucket FROM traffic_warnings WHERE username = ?", (username,)
        ).fetchone()
        return row["last_bucket"] if row else None


def set_warning_bucket(username: str, bucket: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO traffic_warnings (username, last_bucket, notified_at) VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                last_bucket = excluded.last_bucket,
                notified_at = excluded.notified_at
            """,
            (username, bucket, now),
        )


def clear_warning_bucket(username: str) -> None:
    """Called once a panel is topped back up, so the next drop warns again."""
    with _connect() as conn:
        conn.execute("DELETE FROM traffic_warnings WHERE username = ?", (username,))


def set_user_linked(telegram_id: int, linked: bool) -> None:
    """Mark that this account owns a panel. Deliberately one-way."""
    with _connect() as conn:
        conn.execute(
            "UPDATE bot_users SET is_linked = MAX(is_linked, ?) WHERE telegram_id = ?",
            (1 if linked else 0, telegram_id),
        )


def get_user(telegram_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT telegram_id, username, full_name FROM bot_users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return dict(row) if row else None


def is_user_linked(telegram_id: int) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT is_linked FROM bot_users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return bool(row["is_linked"]) if row else False


def list_known_users() -> list[int]:
    """Telegram IDs of everyone who has ever started the bot."""
    with _connect() as conn:
        rows = conn.execute("SELECT telegram_id FROM bot_users").fetchall()
        return [r["telegram_id"] for r in rows]


@dataclass
class Tutorial:
    id: int
    title: str
    content_type: str
    text: str | None
    file_id: str | None
    created_at: str
    source_chat_id: int | None = None
    source_message_id: int | None = None


def add_tutorial(
    *,
    title: str,
    content_type: str,
    text: str | None,
    file_id: str | None,
    source_chat_id: int | None = None,
    source_message_id: int | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO tutorials
                (title, content_type, text, file_id, created_at, source_chat_id, source_message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, content_type, text, file_id, now, source_chat_id, source_message_id),
        )
        return cur.lastrowid


def delete_tutorial(tutorial_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM tutorials WHERE id = ?", (tutorial_id,))
        return cur.rowcount == 1


def list_tutorials() -> list[Tutorial]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM tutorials ORDER BY created_at").fetchall()
        return [Tutorial(**dict(row)) for row in rows]


def get_tutorial(tutorial_id: int) -> Tutorial | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tutorials WHERE id = ?", (tutorial_id,)
        ).fetchone()
        return Tutorial(**dict(row)) if row else None


# ---------------------------------------------------------------------------
# Panel requests (shop purchases)
# ---------------------------------------------------------------------------

def create_panel_request(
    telegram_id: int,
    panel_name: str,
    traffic_gb: float,
    receipt_path: str,
    referral_code_id: int | None = None,
    desired_username: str | None = None,
    desired_password: str | None = None,
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO panel_requests (telegram_id, panel_name, traffic_gb, receipt_path, referral_code_id, desired_username, desired_password) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (telegram_id, panel_name, traffic_gb, receipt_path, referral_code_id, desired_username, desired_password),
        )
        return cur.lastrowid


def get_panel_request(request_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM panel_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row) if row else None


def list_pending_panel_requests() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM panel_requests WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_panel_request_reviewed(
    request_id: int, status: str, reviewed_by: int, reason: str | None = None
) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE panel_requests SET status = ?, reject_reason = ?, reviewed_at = datetime('now'), reviewed_by = ? WHERE id = ? AND status = 'pending'",
            (status, reason, reviewed_by, request_id),
        )
        return cur.rowcount == 1


# ---------------------------------------------------------------------------
# Referral codes
# ---------------------------------------------------------------------------

def get_referral_code(code_str: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM referral_codes WHERE code = ? AND enabled = 1", (code_str,)
        ).fetchone()
        return dict(row) if row else None


def get_referral_code_by_owner(telegram_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM referral_codes WHERE owner_telegram_id = ? AND enabled = 1",
            (telegram_id,),
        ).fetchone()
        return dict(row) if row else None


def create_referral_code(telegram_id: int, code: str, bonus_percent: float, price_per_gb: float) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO referral_codes (owner_telegram_id, code, bonus_percent, price_per_gb) VALUES (?, ?, ?, ?)",
            (telegram_id, code, bonus_percent, price_per_gb),
        )
        return cur.lastrowid


def disable_referral_code(code_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE referral_codes SET enabled = 0 WHERE id = ?", (code_id,)
        )
        return cur.rowcount == 1


def list_referral_codes() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM referral_codes ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]


def create_referral_usage(
    code_id: int, buyer_tg_id: int, buyer_username: str | None, traffic_gb: float, bonus_gb: float
) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO referral_usage (code_id, buyer_telegram_id, buyer_username, traffic_gb, bonus_granted_gb) VALUES (?, ?, ?, ?, ?)",
            (code_id, buyer_tg_id, buyer_username, traffic_gb, bonus_gb),
        )
        return cur.lastrowid


def get_referral_owner(code_id: int) -> int | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT owner_telegram_id FROM referral_codes WHERE id = ?", (code_id,)
        ).fetchone()
        return row["owner_telegram_id"] if row else None
