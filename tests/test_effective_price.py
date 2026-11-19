"""A reseller's special per-GB price is a ceiling, not a fixed rate.

When the superadmin lowers the global price below a reseller's special price
(e.g. a Black Friday sale), that reseller is charged the lower global price on
new purchases; a reseller whose special price is already below the new global
keeps their own price. Raising the global price back restores the prior state,
because special prices are never mutated — `get_effective_price` just takes the
minimum at charge time.
"""

import pytest


@pytest.fixture()
def prices(ledger):
    """`backend.bot.db` on a temp SQLite (no special prices set yet)."""
    return ledger


def test_no_special_price_uses_the_global(prices):
    prices.set_setting("price_per_gb", "2900")
    assert prices.get_effective_price("sellerA") == 2900


def test_special_above_global_gets_the_sale_price(prices):
    prices.set_setting("price_per_gb", "2300")  # sale on
    prices.set_admin_price("sellerB", 2500)
    assert prices.get_effective_price("sellerB") == 2300


def test_special_below_global_keeps_the_special_price(prices):
    prices.set_setting("price_per_gb", "2300")  # sale on
    prices.set_admin_price("sellerC", 2000)
    assert prices.get_effective_price("sellerC") == 2000


def test_special_below_a_higher_global_is_unchanged(prices):
    prices.set_setting("price_per_gb", "2900")  # normal
    prices.set_admin_price("sellerB", 2500)
    assert prices.get_effective_price("sellerB") == 2500


def test_missing_global_leaves_the_special_price_and_zero_otherwise(prices):
    prices.set_admin_price("sellerB", 2500)
    assert prices.get_effective_price("sellerB") == 2500  # no global configured
    assert prices.get_effective_price("sellerA") == 0.0  # no global, no special


def test_lowering_then_raising_the_global_reverts_everyone(prices):
    prices.set_admin_price("sellerB", 2500)
    prices.set_admin_price("sellerC", 2000)

    prices.set_setting("price_per_gb", "2900")  # before the sale
    assert prices.get_effective_price("sellerA") == 2900
    assert prices.get_effective_price("sellerB") == 2500
    assert prices.get_effective_price("sellerC") == 2000

    prices.set_setting("price_per_gb", "2300")  # sale on
    assert prices.get_effective_price("sellerA") == 2300
    assert prices.get_effective_price("sellerB") == 2300  # gets the sale
    assert prices.get_effective_price("sellerC") == 2000  # already lower

    prices.set_setting("price_per_gb", "2900")  # sale over — automatic revert
    assert prices.get_effective_price("sellerA") == 2900
    assert prices.get_effective_price("sellerB") == 2500
    assert prices.get_effective_price("sellerC") == 2000
