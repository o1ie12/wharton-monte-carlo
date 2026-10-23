"""WInS fills -> ladder.csv: hand-checked accrued interest and yields, and the rebuilt ladder
matches the fills."""
from __future__ import annotations

import pandas as pd
import pytest

from mcsim import fills
from mcsim.config import load_config
from mcsim.model import load_ladder


def test_settlement_is_next_business_day():
    assert fills.settlement_date("2026-10-14") == pd.Timestamp("2026-10-15")      # Wed -> Thu
    assert fills.settlement_date("2026-10-16") == pd.Timestamp("2026-10-19")      # Fri -> Mon


def test_textbook_accrued_by_hand():
    # 4.75% Feb 15 2037 settling Oct 15 2026: 61 of 184 days since Aug 15 -> 23.75 x 61/184
    assert fills.textbook_accrued(0.0475, "2037-02-15", "2026-10-15") == pytest.approx(23.75 * 61 / 184)
    # 3.125% Nov 15 2041: 153 of 184 days since May 15
    assert fills.textbook_accrued(0.03125, "2041-11-15", "2026-10-15") == pytest.approx(15.625 * 153 / 184)


def test_implied_accrued_and_day_count():
    # 1 bond of 3.125% Nov 2041 at 755.92395 for $768.77: $12.85 accrued, 150 days at coupon x days / 365
    acc = fills.implied_accrued(768.77, 0.0, 1, 755.92395)
    assert acc == pytest.approx(12.84605)
    assert fills.accrual_days_act365(acc, 0.03125) == pytest.approx(150.0, abs=0.05)


def test_bond_yield_round_trip_and_par():
    y = fills.bond_ytm(965.0 + 7.0, 0.0475, "2037-02-15", "2026-10-15")
    assert fills.bond_value(y, 0.0475, "2037-02-15", "2026-10-15") == pytest.approx(972.0, abs=1e-6)
    # on a coupon date a bond priced at par yields about its coupon (365.25 day basis: within 1bp)
    assert fills.bond_ytm(1000.0, 0.05, "2036-05-15", "2026-05-15") == pytest.approx(0.05, abs=1e-4)


def test_etf_yield_keeps_maturity_value():
    y1 = fills.etf_ytm(21.78, 0.0508, "2026-10-13", 21.67, "2026-10-14", "2032-12-15")
    t0 = (pd.Timestamp("2032-12-15") - pd.Timestamp("2026-10-13")).days / 365.25
    t1 = (pd.Timestamp("2032-12-15") - pd.Timestamp("2026-10-14")).days / 365.25
    assert 21.67 * (1 + y1 / 2) ** (2 * t1) == pytest.approx(21.78 * (1 + 0.0508 / 2) ** (2 * t0))
    assert y1 > 0.0508                                                           # lower price, higher yield


def test_ladder_matches_the_fills():
    a = load_config()
    ladder = load_ladder(a)
    trades = pd.read_csv(a.base_dir / "data" / "wins_fills_2026-10.csv")
    rungs = trades.dropna(subset=["bill_number"])
    qty = rungs.groupby("bill_number")["quantity"].sum()
    assert list(ladder.quantity) == list(qty.astype(float))                       # 1686 ... 30 bonds
    assert list(ladder.quantity[5:]) == [30, 29, 28, 27, 30]
    assert not ladder.unverified                                                  # no estimate rows left
    assert set(ladder.table["data_status"]) == {"WInS fill, Oct 14-15 2026"}
    # cost: ETFs qty x price, bonds the cash amount (the $10 commission is charged separately)
    bonds = rungs[rungs["type"] == "Bond"]
    assert ladder.sheet_cost[5:].sum() == pytest.approx(bonds["amount"].abs().sum(), abs=0.01)
    etf = rungs[rungs["type"] == "ETF"]
    assert ladder.sheet_cost[:5].sum() == pytest.approx((etf["quantity"] * etf["price"]).sum(), abs=0.01)


def test_account_reconciles_to_the_budget():
    from build_ladder import build
    _, info = build()
    assert sum(info["recon"].values()) == pytest.approx(300_000.0, abs=0.005)
