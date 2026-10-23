"""Turn broker fills (WInS) into ladder.csv rows: settlement dates, textbook accrued interest,
the accrued interest the broker actually charged, and yields backed out of the fill prices.

Yields use the model's own convention (ladder.compounding_per_year, actual days /
ladder.day_count_basis, cash flows after the settlement date), so the model reprices each row
to its fill: a bond's present value at its yield equals its clean fill price plus textbook
accrued; an iBonds ETF grows from its fill price to the same maturity value as before.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FACE = 1000.0      # one Treasury bond


def settlement_date(trade_date) -> pd.Timestamp:
    """Treasury and ETF trades settle T+1 (next business day)."""
    return pd.Timestamp(trade_date) + pd.offsets.BDay(1)


def coupon_period(maturity, settle) -> tuple[pd.Timestamp, pd.Timestamp]:
    """(last coupon date on or before settle, next coupon date after it), stepping back from
    maturity in 6-month steps (same schedule as Ladder.flows)."""
    mat, settle = pd.Timestamp(maturity), pd.Timestamp(settle)
    i = 0
    while mat - pd.DateOffset(months=6 * i) > settle:
        i += 1
    return mat - pd.DateOffset(months=6 * i), mat - pd.DateOffset(months=6 * (i - 1))


def textbook_accrued(coupon: float, maturity, settle) -> float:
    """Accrued interest per $1,000 bond, actual/actual: half the coupon times days since the
    last coupon over days in the coupon period."""
    prev, nxt = coupon_period(maturity, settle)
    return coupon * FACE / 2.0 * (pd.Timestamp(settle) - prev).days / (nxt - prev).days


def implied_accrued(amount: float, commission: float, quantity: float, price: float) -> float:
    """Accrued per bond the broker charged: (|cash amount| - commission - qty x clean price) / qty.
    Pass commission=0 when the cash amount does not include the commission."""
    return (abs(amount) - commission - quantity * price) / quantity


def accrual_days_act365(accrued: float, coupon: float) -> float:
    """Days of interest an accrued amount represents if it was figured as coupon x days / 365."""
    return accrued / (coupon * FACE) * 365.0


def _bond_flows(coupon: float, maturity, settle) -> tuple[list[pd.Timestamp], np.ndarray]:
    mat, settle = pd.Timestamp(maturity), pd.Timestamp(settle)
    dates, i = [], 0
    while mat - pd.DateOffset(months=6 * i) > settle:
        dates.append(mat - pd.DateOffset(months=6 * i))
        i += 1
    dates = sorted(dates)
    amounts = np.full(len(dates), coupon * FACE / 2.0)
    amounts[-1] += FACE
    return dates, amounts


def bond_value(y: float, coupon: float, maturity, settle, m: float = 2.0, basis: float = 365.25) -> float:
    """Present value per $1,000 bond (clean + accrued) at yield y on `settle`, model convention."""
    dates, amounts = _bond_flows(coupon, maturity, settle)
    t = np.array([(d - pd.Timestamp(settle)).days / basis for d in dates])
    return float((amounts / (1.0 + y / m) ** (m * t)).sum())


def bond_ytm(dirty: float, coupon: float, maturity, settle, m: float = 2.0, basis: float = 365.25) -> float:
    """Yield at which bond_value equals `dirty` (per $1,000), by bisection."""
    lo, hi = -0.05, 0.50
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if bond_value(mid, coupon, maturity, settle, m, basis) > dirty:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def etf_ytm(ref_price: float, ref_ytm: float, ref_date, price: float, price_date, maturity,
            m: float = 2.0, basis: float = 365.25) -> float:
    """New yield of a term ETF from a new price, holding its maturity value fixed: the old price
    grown at the old yield to maturity is the value per share at maturity; the new yield is the
    rate that grows the new price to that same value."""
    mat = pd.Timestamp(maturity)
    t0 = (mat - pd.Timestamp(ref_date)).days / basis
    t1 = (mat - pd.Timestamp(price_date)).days / basis
    value = ref_price * (1.0 + ref_ytm / m) ** (m * t0)
    return float(m * ((value / price) ** (1.0 / (m * t1)) - 1.0))
