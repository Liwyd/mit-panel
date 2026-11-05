"""Quota and Friday invoice accounting for consumption-credit grants."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from backend.bot import db, texts
from backend.bot.units import bytes_to_gb


@dataclass(frozen=True)
class UserState:
    generation: str
    limit: int
    used: int
    earlier_usage: int = 0


@dataclass(frozen=True)
class Settlement:
    allocated: int
    discount: int
    invoice_id: int | None
    amount: int = 0
    telegram_id: int | None = None
    due_at: str | None = None


class BillingDeferred(Exception):
    """The reseller's data must stay available for a later attempt."""


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    # The bot and panel use the same SQLite file. Acquire the writer lock
    # before reading a balance, without holding it across Marzban requests.
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        yield conn


def account(conn: sqlite3.Connection, admin_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM consumption_accounts WHERE admin_id = ?", (admin_id,)
    ).fetchone()


def _admin(conn: sqlite3.Connection, admin_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM admins WHERE id = ?", (admin_id,)).fetchone()
    tracked = account(conn, admin_id)
    if row is None or tracked is None or (
        row["username"], row["panel"]
    ) != (tracked["username"], tracked["panel"]):
        raise BillingDeferred("Reseller identity changed")
    return row


def enroll(conn: sqlite3.Connection, admin_id: int, users: dict[str, UserState]) -> None:
    conn.execute(
        """INSERT INTO consumption_accounts (admin_id, username, panel)
           SELECT id, username, panel FROM admins WHERE id = ?""",
        (admin_id,),
    )
    _admin(conn, admin_id)
    for username, state in users.items():
        _save_user(conn, admin_id, username, state)
        _add_allocation(conn, admin_id, username, "ordinary", state.limit)


def grant(conn: sqlite3.Connection, admin_id: int, amount: int) -> None:
    admin = _admin(conn, admin_id)
    if amount <= 0:
        raise ValueError("Consumption grant must be positive")
    # An existing ordinary debt is separate from quota bought on weekly credit.
    if int(admin["traffic"] or 0) < account(conn, admin_id)["available_bytes"]:
        raise BillingDeferred("Clear the existing quota deficit before adding weekly credit")
    conn.execute(
        """UPDATE admins SET traffic = COALESCE(traffic, 0) + ?,
           initial_traffic = COALESCE(initial_traffic, 0) + ? WHERE id = ?""",
        (amount, amount, admin_id),
    )
    _change_available(conn, admin_id, amount)
    bump_revision(conn, admin_id)


def bump_revision(conn: sqlite3.Connection, admin_id: int) -> None:
    conn.execute(
        "UPDATE consumption_accounts SET revision = revision + 1 WHERE admin_id = ?", (admin_id,)
    )


def _change_available(conn: sqlite3.Connection, admin_id: int, amount: int) -> None:
    conn.execute(
        "UPDATE consumption_accounts SET available_bytes = available_bytes + ? WHERE admin_id = ?",
        (amount, admin_id),
    )


def user_state(conn: sqlite3.Connection, admin_id: int, username: str) -> UserState | None:
    row = conn.execute(
        "SELECT generation, limit_bytes, used_bytes, earlier_usage FROM consumption_users "
        "WHERE admin_id = ? AND username = ?",
        (admin_id, username),
    ).fetchone()
    return UserState(*row) if row else None


def _save_user(
    conn: sqlite3.Connection, admin_id: int, username: str, state: UserState,
) -> None:
    conn.execute(
        """INSERT INTO consumption_users VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(admin_id, username) DO UPDATE SET generation = excluded.generation,
             limit_bytes = excluded.limit_bytes, used_bytes = excluded.used_bytes,
             earlier_usage = excluded.earlier_usage""",
        (admin_id, username, state.generation, state.limit, state.used, state.earlier_usage),
    )


def _add_allocation(
    conn: sqlite3.Connection, admin_id: int, username: str, state: str, amount: int,
) -> None:
    if not amount:
        return
    conn.execute(
        """INSERT INTO consumption_allocations
           (admin_id, sequence, username, state, active_bytes, billable_bytes)
           SELECT ?, COALESCE(MAX(sequence), 0) + 1, ?, ?, ?, ?
           FROM consumption_allocations WHERE admin_id = ?""",
        (admin_id, username, state, amount, amount if state == "open" else 0, admin_id),
    )


def _allocate(
    conn: sqlite3.Connection, admin_id: int, username: str, amount: int,
) -> None:
    if not amount:
        return
    admin = _admin(conn, admin_id)
    available = account(conn, admin_id)["available_bytes"]
    ordinary = min(amount, max(int(admin["traffic"] or 0) - available, 0))
    weekly = min(amount - ordinary, available)
    # A direct Marzban mutation can exceed the quota. Keep that excess in the
    # ordinary balance deficit and out of the consumption invoice.
    _add_allocation(conn, admin_id, username, "ordinary", amount - weekly)
    _add_allocation(conn, admin_id, username, "open", weekly)
    _change_available(conn, admin_id, -weekly)
    deficit = amount - ordinary - weekly
    if deficit:
        conn.execute(
            "UPDATE consumption_accounts SET unbilled_deficit_bytes = unbilled_deficit_bytes + ? "
            "WHERE admin_id = ?", (deficit, admin_id),
        )
    conn.execute(
        "UPDATE admins SET traffic = COALESCE(traffic, 0) - ? WHERE id = ?", (amount, admin_id)
    )


def _live_allocations(conn: sqlite3.Connection, admin_id: int, username: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM consumption_allocations
           WHERE admin_id = ? AND username = ? AND active_bytes > 0
           ORDER BY (state <> 'ordinary'), sequence, portion""",
        (admin_id, username),
    ).fetchall()


def _release(
    conn: sqlite3.Connection,
    admin_id: int,
    allocations: Iterator[sqlite3.Row],
    amount: int,
    *,
    unused: bool,
    return_ordinary: bool = False,
) -> None:
    """Detach used bytes from a reset, or remove unused bytes from the newest lots."""
    weekly_return = ordinary_return = 0
    for row in allocations:
        if not amount:
            break
        size = min(amount, row["active_bytes"])
        amount -= size
        state = row["state"]
        reduction = size if unused and state == "open" else 0
        conn.execute(
            """UPDATE consumption_allocations
               SET active_bytes = active_bytes - ?, billable_bytes = billable_bytes - ?
               WHERE admin_id = ? AND sequence = ? AND portion = ?""",
            (size, reduction, admin_id, row["sequence"], row["portion"]),
        )
        if not unused:
            continue
        if state == "ordinary":
            ordinary_return += size if return_ordinary else 0
            continue
        weekly_return += size
        if state in ("invoiced", "credit"):
            conn.execute(
                "INSERT INTO consumption_returns (admin_id, invoice_id, available_bytes) "
                "VALUES (?, ?, ?)",
                (admin_id, row["invoice_id"], size),
            )

    if weekly_return or ordinary_return:
        _change_available(conn, admin_id, weekly_return)
        conn.execute(
            "UPDATE admins SET traffic = COALESCE(traffic, 0) + ? WHERE id = ?",
            (weekly_return + ordinary_return, admin_id),
        )


def observe(
    conn: sqlite3.Connection, admin_id: int, username: str, current: UserState | None,
    *, force_reset: bool = False, ordinary_returns: bool = True,
) -> None:
    """Apply a verified observation. The caller commits the transaction."""
    previous = user_state(conn, admin_id, username)
    if previous == current and not force_reset:
        return
    if (
        previous and current and not force_reset
        and (previous.generation, previous.limit, previous.earlier_usage)
        == (current.generation, current.limit, current.earlier_usage)
        and current.used >= previous.used
    ):
        _save_user(conn, admin_id, username, current)
        bump_revision(conn, admin_id)
        return
    admin = _admin(conn, admin_id)
    if previous is not None and (
        current is None or previous.generation != current.generation
    ):
        lots = _live_allocations(conn, admin_id, username)
        active = sum(row["active_bytes"] for row in lots)
        unused = max(0, min(active, previous.limit) - previous.used)
        _release(conn, admin_id, reversed(lots), unused, unused=True,
                 return_ordinary=ordinary_returns and bool(admin["delete_return_traffic"]))
        conn.execute(
            "UPDATE consumption_allocations SET active_bytes = 0 "
            "WHERE admin_id = ? AND username = ? AND active_bytes > 0",
            (admin_id, username),
        )
        conn.execute(
            "DELETE FROM consumption_users WHERE admin_id = ? AND username = ?",
            (admin_id, username),
        )
        previous = None

    if current is not None:
        reset = previous is not None and (
            force_reset or current.used < previous.used or current.earlier_usage > previous.earlier_usage
        )
        if reset:
            reset_bytes = max(previous.used, current.earlier_usage - previous.earlier_usage)
            _release(conn, admin_id, iter(_live_allocations(conn, admin_id, username)),
                     reset_bytes, unused=False)
        lots = _live_allocations(conn, admin_id, username)
        active = sum(row["active_bytes"] for row in lots)
        unused = max(0, active - max(current.limit, current.used))
        if unused:
            _release(conn, admin_id, reversed(lots), unused, unused=True,
                     return_ordinary=ordinary_returns and bool(admin["update_return_traffic"]))
        if previous is not None and not reset and current.limit > previous.limit:
            # An already-used overage is not a fresh quota purchase.
            overage = max(0, min(current.limit, previous.used) - active)
            _add_allocation(conn, admin_id, username, "ordinary", overage)
            active += overage
        _allocate(conn, admin_id, username, max(0, current.limit - active))
        _save_user(conn, admin_id, username, current)

    # Used bytes on open allocations still have to be billed after deletion.
    conn.execute(
        "DELETE FROM consumption_allocations WHERE admin_id = ? AND username = ? "
        "AND active_bytes = 0 AND (state <> 'open' OR billable_bytes = 0)",
        (admin_id, username),
    )
    bump_revision(conn, admin_id)


def _apply_discount(
    conn: sqlite3.Connection, lot: sqlite3.Row, covered: int, invoice_id: int | None,
) -> None:
    admin_id, sequence = lot["admin_id"], lot["sequence"]
    billed = lot["billable_bytes"] - covered
    if covered:
        consumed = lot["billable_bytes"] - lot["active_bytes"]
        active_covered = max(covered - consumed, 0)
        conn.execute(
            """UPDATE consumption_allocations SET state = 'credit', active_bytes = ?,
               billable_bytes = 0 WHERE admin_id = ? AND sequence = ? AND portion = 0""",
            (active_covered, admin_id, sequence),
        )
        if billed and lot["active_bytes"] > active_covered:
            conn.execute(
                """INSERT INTO consumption_allocations
                   (admin_id, sequence, portion, username, state, active_bytes, invoice_id)
                   VALUES (?, ?, 1, ?, 'invoiced', ?, ?)""",
                (admin_id, sequence, lot["username"], lot["active_bytes"] - active_covered, invoice_id),
            )
    else:
        conn.execute(
            """UPDATE consumption_allocations SET state = 'invoiced', invoice_id = ?,
               billable_bytes = 0 WHERE admin_id = ? AND sequence = ? AND portion = 0""",
            (invoice_id, admin_id, sequence),
        )


def settle(
    conn: sqlite3.Connection, admin_id: int, stamp: str, now: datetime, price: float,
) -> Settlement | None:
    admin = _admin(conn, admin_id)
    if conn.execute(
        "SELECT 1 FROM consumption_settlements WHERE admin_id = ? AND week_stamp = ?",
        (admin_id, stamp),
    ).fetchone():
        return None
    if conn.execute(
        "SELECT 1 FROM consumption_mutations WHERE admin_id = ?", (admin_id,)
    ).fetchone():
        raise BillingDeferred("An upstream mutation still needs verification")
    lots = conn.execute(
        "SELECT * FROM consumption_allocations WHERE admin_id = ? AND state = 'open' "
        "AND billable_bytes > 0 ORDER BY sequence",
        (admin_id,),
    ).fetchall()
    credits = conn.execute(
        """SELECT r.id, r.available_bytes FROM consumption_returns r
           LEFT JOIN invoices i ON i.id = r.invoice_id
           WHERE r.admin_id = ? AND r.available_bytes > 0
             AND (r.invoice_id IS NULL OR i.status = 'paid')
           ORDER BY r.id""",
        (admin_id,),
    ).fetchall()
    allocated = sum(lot["billable_bytes"] for lot in lots)
    discount = min(allocated, sum(credit["available_bytes"] for credit in credits))
    net = allocated - discount
    invoice_id = due_at = None
    amount = 0
    if net:
        telegram_id = admin["telegram_id"]
        amount = round(bytes_to_gb(net) * price) if math.isfinite(price) and price > 0 else 0
        if not telegram_id or amount <= 0:
            raise BillingDeferred("Missing recipient or payable price")
        if conn.execute(
            "SELECT 1 FROM invoices WHERE admin_username = ? AND week_stamp = ?",
            (admin["username"], stamp),
        ).fetchone():
            raise BillingDeferred("A legacy invoice already exists for this week")
        due_at = (now + timedelta(days=7)).isoformat()
        invoice_id = db.insert_invoice(
            conn, telegram_id=telegram_id, amount=amount, due_at=due_at, week_stamp=stamp,
            admin_username=admin["username"],
            description=texts.CONSUMPTION_LEDGER_DESCRIPTION.format(
                username=admin["username"], stamp=stamp, allocated=bytes_to_gb(allocated),
                discount=bytes_to_gb(discount), payable=bytes_to_gb(net),
            ),
        )

    remaining = discount
    for credit in credits:
        used = min(credit["available_bytes"], remaining)
        if not used:
            break
        conn.execute(
            "UPDATE consumption_returns SET available_bytes = available_bytes - ? WHERE id = ?",
            (used, credit["id"]),
        )
        remaining -= used

    remaining = discount
    for lot in lots:
        covered = min(lot["billable_bytes"], remaining)
        _apply_discount(conn, lot, covered, invoice_id)
        remaining -= covered
    conn.execute(
        "DELETE FROM consumption_allocations WHERE admin_id = ? "
        "AND active_bytes = 0 AND state <> 'open'",
        (admin_id,),
    )
    conn.execute(
        """INSERT INTO consumption_settlements
           (admin_id, week_stamp, cutoff, allocated_bytes, discount_bytes, invoice_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (admin_id, stamp, now.isoformat(), allocated, discount, invoice_id),
    )
    return Settlement(allocated, discount, invoice_id, amount, admin["telegram_id"], due_at)
