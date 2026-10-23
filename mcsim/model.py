"""Simulation engine: ladder pricing, random draws, and the path simulation.

Every Monte Carlo run and every fixed-path stress test goes through `simulate`,
so the two can never disagree about the cash-flow mechanics.

Timing convention: all cash flows happen at the start of a calendar year.
Each year's T-bill rate and stock return apply from Jan 1 to the next Jan 1.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .config import Assumptions, parse_fraction

LADDER_COLUMNS = ["bill_number", "bill_date", "bill_amount", "security", "type", "maturity_date",
                  "price", "accrued_per_100", "ytm", "rung_cost", "quantity"]
BOND_FACE_PER_UNIT = 1000.0  # ladder.csv quantity for bonds = number of $1,000-face bonds
PAYOUT_MODELS = ("face", "cashflows")
RUNG_TYPES = ("etf", "bond", "strips")   # ladder.csv `type` column, case-insensitive
TOPUP_RULES = ("rate_rule", "fixed_rule", "foresight")


# ---------------------------------------------------------------- ladder ----

@dataclass(frozen=True)
class Flow:
    """Cash flows of one rung: dates and dollar amounts."""
    dates: tuple[pd.Timestamp, ...]
    amounts: np.ndarray


@dataclass(frozen=True)
class Ladder:
    table: pd.DataFrame
    bill_years: tuple[int, ...]
    bill_amount: np.ndarray        # (R,)
    yields: np.ndarray             # (R,) decimal YTM from the sheet
    maturity: tuple[pd.Timestamp, ...]
    coupon: np.ndarray             # (R,) annual coupon rate (0 for ETF rungs)
    is_bond: np.ndarray            # (R,) bool: coupon Treasury
    is_strips: np.ndarray          # (R,) bool: zero-coupon Treasury (STRIPS), pays face at maturity
    is_ibond: np.ndarray           # (R,) bool: gets the iBonds payout error
    quantity: np.ndarray           # (R,)
    unit_cost: np.ndarray          # (R,) sheet cost of one share / one bond, incl. accrued
    sheet_cost: np.ndarray         # (R,)
    unverified: tuple[str, ...]    # rows whose data_status contains "ESTIMATE"
    price_dates: tuple[pd.Timestamp, ...]  # date each row's price/YTM is quoted for
    sizing_rate: float | None = None       # set when bond quantities were resized (scenarios)

    @property
    def n_rungs(self) -> int:
        return len(self.bill_amount)

    @property
    def is_treasury(self) -> np.ndarray:
        """Rungs priced and paid as actual Treasury cash flows ($1,000 face units)."""
        return self.is_bond | self.is_strips

    def price_date_label(self) -> str:
        lo, hi = min(self.price_dates), max(self.price_dates)
        return lo.date().isoformat() if lo == hi else f"{lo.date().isoformat()} to {hi.date().isoformat()}"

    def flows(self, settle: pd.Timestamp, model: str) -> list[Flow]:
        """Cash flows after `settle`.

        face:      every rung pays its bill amount at maturity (plan spec: each rung
                   pays about $50,000 just before its bill).
        cashflows: bond rungs pay their actual semiannual coupons and principal for
                   the sheet quantity; STRIPS rungs pay their face value at maturity and
                   nothing before; ETF rungs still pay the bill amount at maturity.
        """
        if model not in PAYOUT_MODELS:
            raise ValueError(f"ladder.bond_payout_model must be one of {PAYOUT_MODELS}")
        out = []
        for k in range(self.n_rungs):
            mat = self.maturity[k]
            if model == "face" or not self.is_treasury[k]:
                out.append(Flow((mat,), np.array([self.bill_amount[k]])))
                continue
            face = self.quantity[k] * BOND_FACE_PER_UNIT
            if self.is_strips[k]:
                out.append(Flow((mat,), np.array([face])))
                continue
            dates, d, i = [], mat, 0
            while d > settle:
                dates.append(d)
                i += 1
                d = mat - pd.DateOffset(months=6 * i)
            dates = sorted(dates)
            amounts = np.full(len(dates), face * self.coupon[k] / 2.0)
            amounts[-1] += face
            out.append(Flow(tuple(dates), amounts))
        return out


def sheet_date_costs(ladder: "Ladder", a: Assumptions) -> np.ndarray:
    """Each rung priced at its sheet YTM on its own price_date, for checking ladder.csv
    costs. Shape (R,)."""
    out = np.empty(ladder.n_rungs)
    for d in set(ladder.price_dates):
        cost = ladder_costs(ladder, [0.0], a, settle=d)[0]
        for k, dk in enumerate(ladder.price_dates):
            if dk == d:
                out[k] = cost[k]
    return out


def _coupon_from_name(name: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", name)
    if not m:
        raise ValueError(f"cannot read a coupon rate from bond name '{name}'")
    return float(m.group(1)) / 100.0


def load_ladder(a: Assumptions) -> Ladder:
    df = pd.read_csv(a.path("ladder.csv_path"))
    missing = set(LADDER_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"ladder.csv is missing columns: {sorted(missing)}")
    df = df.sort_values("bill_date").reset_index(drop=True)
    purchase = pd.Timestamp(a["plan.ladder_purchase_date"])
    maturity = pd.to_datetime(df["maturity_date"])
    bill = pd.to_datetime(df["bill_date"])
    if (maturity > bill).any():
        raise ValueError("every rung must mature on or before its bill date")
    if (maturity <= purchase).any():
        raise ValueError("every rung must mature after the ladder purchase date")
    if not np.allclose(df["bill_amount"], a["plan.bill_amount"]):
        raise ValueError("ladder.csv bill_amount must match plan.bill_amount in config.yaml")
    fallback = pd.Timestamp(a["ladder.pricing_date"])
    if "price_date" in df:
        price_dates = tuple(pd.Timestamp(x) if pd.notna(x) and str(x).strip() else fallback
                            for x in df["price_date"])
    else:
        price_dates = (fallback,) * len(df)
    bill_years = tuple(int(y) for y in bill.dt.year)
    if len(set(bill_years)) != len(bill_years):
        raise ValueError("ladder.csv must have exactly one rung per bill year")

    kind = df["type"].astype(str).str.strip().str.lower()
    unknown = sorted(set(kind) - set(RUNG_TYPES))
    if unknown:
        raise ValueError(f"ladder.csv type must be one of {RUNG_TYPES}, got {unknown}")
    is_bond = kind.eq("bond").to_numpy(bool)
    is_strips = kind.eq("strips").to_numpy(bool)
    label = str(a["ladder.ibonds_instrument_label"]).lower()
    price = df["price"].to_numpy(float)
    accrued = df["accrued_per_100"].fillna(0).to_numpy(float)
    unit_cost = np.where(is_bond | is_strips, (price + accrued) / 100.0 * BOND_FACE_PER_UNIT, price)
    status = df["data_status"].fillna("") if "data_status" in df else pd.Series([""] * len(df))
    unverified = tuple(f"Bill {int(n)} ({sec}): {st}" for n, sec, st in
                       zip(df["bill_number"], df["security"], status)
                       if "ESTIMATE" in str(st).upper())
    ladder = Ladder(
        table=df,
        bill_years=bill_years,
        bill_amount=df["bill_amount"].to_numpy(float),
        yields=df["ytm"].to_numpy(float),
        maturity=tuple(maturity),
        coupon=np.array([_coupon_from_name(n) if b else 0.0 for n, b in zip(df["security"], is_bond)]),
        is_bond=is_bond,
        is_strips=is_strips,
        is_ibond=df["security"].str.lower().str.contains(label, regex=False).to_numpy(bool),
        quantity=df["quantity"].to_numpy(float),
        unit_cost=unit_cost,
        sheet_cost=df["rung_cost"].to_numpy(float),
        unverified=unverified,
        price_dates=price_dates,
    )
    rate = a.values.get("ladder.sizing_reinvest_rate")
    return ladder if rate is None else resize_bond_rungs(a, ladder, float(rate))


def _constant_rate_draws(ladder: "Ladder", tl: "Timeline", rate: float) -> "Draws":
    """One path where T-bills earn `rate` every year and iBonds pay exactly their target."""
    return Draws(
        yield_shift=np.zeros(1),
        tbill=np.full((1, len(tl.tbill_years)), float(rate)),
        us=np.zeros((1, len(tl.growth_years))),
        intl=np.zeros((1, len(tl.growth_years))),
        ibond_error=np.zeros((1, ladder.n_rungs)),
        contribution=np.zeros(1),
    )


def value_per_bond_at_bill(a: Assumptions, ladder: "Ladder", k: int, rate: float) -> float:
    """Cash one $1,000 bond of rung k delivers by its Jan 1 bill date: coupons received after
    the purchase date plus principal, each reinvested at `rate` until the bill date, including
    principal from a May maturity held until Jan 1. Same convention as the simulation."""
    a = a.override({"ladder.bond_payout_model": "cashflows"})
    tl = make_timeline(a, ladder)
    one = replace(ladder, quantity=np.ones(ladder.n_rungs))
    return float(rung_payouts(a, one, tl, _constant_rate_draws(ladder, tl, rate))[0, k])


def size_bond_quantity(a: Assumptions, ladder: "Ladder", k: int, rate: float) -> int:
    """Smallest whole number of bonds whose cash at the bill date, reinvested at `rate`,
    covers the bill."""
    per_bond = value_per_bond_at_bill(a, ladder, k, rate)
    return int(np.ceil(ladder.bill_amount[k] / per_bond - 1e-9))


def resize_bond_rungs(a: Assumptions, ladder: "Ladder", rate: float) -> "Ladder":
    """Coupon-bond rungs resized at `rate` (ladder.sizing_reinvest_rate). ETF and STRIPS rungs
    keep their ladder.csv quantities. Costs use the sheet's clean price + accrued."""
    qty = ladder.quantity.copy()
    for k in np.flatnonzero(ladder.is_bond):
        qty[k] = size_bond_quantity(a, ladder, k, rate)
    return replace(ladder, quantity=qty, sheet_cost=qty * ladder.unit_cost, sizing_rate=rate)


def ladder_costs(ladder: Ladder, yield_shift: np.ndarray, a: Assumptions,
                 settle: pd.Timestamp | str | None = None) -> np.ndarray:
    """Price of each rung at (sheet YTM + shift) on `settle` (default: purchase date).
    Shape (n, R). Discounting is compounded `compounding_per_year` times a year."""
    settle = pd.Timestamp(settle or a["plan.ladder_purchase_date"])
    m = float(a["ladder.compounding_per_year"])
    basis = float(a["ladder.day_count_basis"])
    shift = np.asarray(yield_shift, float)
    out = np.empty((len(shift), ladder.n_rungs))
    for k, flow in enumerate(ladder.flows(settle, a["ladder.bond_payout_model"])):
        t = np.array([(d - settle).days / basis for d in flow.dates])
        y = ladder.yields[k] + shift[:, None]
        out[:, k] = (flow.amounts[None, :] / (1.0 + y / m) ** (m * t[None, :])).sum(axis=1)
    return out


# -------------------------------------------------------------- timeline ----

@dataclass(frozen=True)
class Timeline:
    purchase_year: int
    contribution_year: int
    valuation_year: int
    bill_years: tuple[int, ...]

    @property
    def tbill_years(self) -> tuple[int, ...]:
        """Years with a T-bill rate: purchase year through the year before the last bill."""
        return tuple(range(self.purchase_year, self.bill_years[-1]))

    @property
    def growth_years(self) -> tuple[int, ...]:
        """Years with a stock return: contribution year through the year before valuation."""
        return tuple(range(self.contribution_year, self.valuation_year))

    @property
    def buffer_years(self) -> tuple[int, ...]:
        return tuple(range(self.purchase_year, self.bill_years[-1] + 1))


def make_timeline(a: Assumptions, ladder: Ladder) -> Timeline:
    t = Timeline(
        purchase_year=pd.Timestamp(a["plan.ladder_purchase_date"]).year,
        contribution_year=int(a["plan.growth_contribution_year"]),
        valuation_year=int(a["plan.valuation_year"]),
        bill_years=ladder.bill_years,
    )
    if not t.purchase_year < t.contribution_year < t.valuation_year <= t.bill_years[0]:
        raise ValueError("expected purchase < contribution < valuation <= first bill year")
    return t


# ------------------------------------------------------ year-by-year paths ----

def tbill_mean_path(a: Assumptions, tl: Timeline) -> np.ndarray:
    """Mean T-bill rate for each simulated year: tbills.mean_by_year where given, else tbills.mean."""
    by_year = {int(y): float(r) for y, r in (a.values.get("tbills.mean_by_year") or {}).items()}
    return np.array([by_year.get(y, float(a["tbills.mean"])) for y in tl.tbill_years])


def inflation_deflator(a: Assumptions, year: int) -> float:
    """Price level on Jan 1 of `year` relative to Jan 1 of inflation.base_year."""
    by_year = {int(y): float(r) for y, r in (a.values.get("inflation.rate_by_year") or {}).items()}
    base = int(a["inflation.base_year"])
    return float(np.prod([1.0 + by_year.get(y, float(a["inflation.rate"])) for y in range(base, year)]))


def tbill_shock_sd(a: Assumptions) -> float:
    """AR(1) shock size that makes the std dev of year-to-year changes equal tbills.sd.
    For x_t = phi x_(t-1) + e_t (stationary), Var(x_t - x_(t-1)) = 2 Var(e) / (1 + phi)."""
    phi = float(a["tbills.ar1_phi"])
    return float(a["tbills.sd"]) * np.sqrt((1.0 + phi) / 2.0)


def tbill_deviations(z: np.ndarray, phi: float, shock_sd: float, start: float = 0.0) -> np.ndarray:
    """AR(1) deviations from the mean path along axis 1: x_t = phi x_(t-1) + shock_sd z_t,
    with x before the first year equal to `start`."""
    x = np.empty_like(z, dtype=float)
    prev = np.full(z.shape[0], float(start))
    for t in range(z.shape[1]):
        prev = phi * prev + shock_sd * z[:, t]
        x[:, t] = prev
    return x


def ibond_years_to_maturity(a: Assumptions, ladder: "Ladder") -> np.ndarray:
    settle = pd.Timestamp(a["plan.ladder_purchase_date"])
    return np.array([(m - settle).days / float(a["ladder.day_count_basis"]) for m in ladder.maturity])


def ibond_error_sd(a: Assumptions, ladder: "Ladder") -> np.ndarray:
    """Payout error std dev per rung: per-year std dev x years to maturity, capped (iBonds rungs only)."""
    sd = np.minimum(float(a["ladder.ibonds_error_sd_per_year"]) * ibond_years_to_maturity(a, ladder),
                    float(a["ladder.ibonds_error_sd_cap"]))
    return np.where(ladder.is_ibond, sd, 0.0)


def ibond_fee_factor(a: Assumptions, ladder: "Ladder") -> np.ndarray:
    """Expected share of the target an iBonds rung pays after its fee: (1 - fee)^years."""
    f = (1.0 - float(a["ladder.ibonds_fee"])) ** ibond_years_to_maturity(a, ladder)
    return np.where(ladder.is_ibond, f, 1.0)


# ----------------------------------------------------------------- draws ----

@dataclass(frozen=True)
class Draws:
    """One row per path. Returns and rates are simple (not log) decimals."""
    yield_shift: np.ndarray   # (n,)
    tbill: np.ndarray         # (n, len(tbill_years))
    us: np.ndarray            # (n, len(growth_years))
    intl: np.ndarray          # (n, len(growth_years))
    ibond_error: np.ndarray   # (n, R)
    contribution: np.ndarray  # (n,)
    extra: dict = field(default_factory=dict)   # extra growth assets: name -> (n, G) simple returns


def lognormal_params(mean: float, vol: float) -> tuple[float, float]:
    """Log-space (mu, sigma) such that 1+R is lognormal with E[R]=mean, sd(R)=vol."""
    sigma2 = np.log1p((vol / (1.0 + mean)) ** 2)
    return float(np.log1p(mean) - sigma2 / 2.0), float(np.sqrt(sigma2))


def log_correlation(rho: float, mean1: float, vol1: float, mean2: float, vol2: float) -> float:
    """Correlation of log returns that reproduces correlation `rho` of simple returns."""
    _, s1 = lognormal_params(mean1, vol1)
    _, s2 = lognormal_params(mean2, vol2)
    if s1 == 0.0 or s2 == 0.0:
        return 0.0
    cov = np.log1p(rho * (vol1 / (1.0 + mean1)) * (vol2 / (1.0 + mean2)))
    return float(np.clip(cov / (s1 * s2), -1.0, 1.0))


def stock_log_params(a: Assumptions) -> dict[str, float]:
    mu_us, s_us = lognormal_params(a["growth.us_mean"], a["growth.us_vol"])
    mu_in, s_in = lognormal_params(a["growth.intl_mean"], a["growth.intl_vol"])
    rho = log_correlation(a["growth.correlation"], a["growth.us_mean"], a["growth.us_vol"],
                          a["growth.intl_mean"], a["growth.intl_vol"])
    return {"mu_us": mu_us, "s_us": s_us, "mu_intl": mu_in, "s_intl": s_in, "rho": rho}


MIX_ASSETS = ("us", "intl", "small_cap", "us_2x", "tbills")
MONTHS = 12


def growth_mix(a: Assumptions) -> dict[str, float]:
    """Growth-bucket weights. Official (growth_mix.mix = null): growth.us_weight / growth.intl_weight."""
    mix = a.values.get("growth_mix.mix")
    if mix is None:
        mix = {"us": float(a["growth.us_weight"]), "intl": float(a["growth.intl_weight"])}
    mix = {str(k): float(v) for k, v in mix.items()}
    unknown = set(mix) - set(MIX_ASSETS)
    if unknown:
        raise ValueError(f"unknown growth assets {sorted(unknown)}; allowed {MIX_ASSETS}")
    if abs(sum(mix.values()) - 1.0) > 1e-9 or min(mix.values()) < 0:
        raise ValueError(f"growth mix weights must be non-negative and sum to 1, got {mix}")
    return mix


def growth_log_corr(a: Assumptions) -> np.ndarray:
    """Correlation of annual log returns for [us, intl, small_cap] (from simple-return correlations)."""
    m_us, v_us = a["growth.us_mean"], a["growth.us_vol"]
    m_in, v_in = a["growth.intl_mean"], a["growth.intl_vol"]
    m_sc, v_sc = a["growth_mix.small_cap_mean"], a["growth_mix.small_cap_vol"]
    r_ui = log_correlation(a["growth.correlation"], m_us, v_us, m_in, v_in)
    r_us = log_correlation(a["growth_mix.small_cap_corr_us"], m_us, v_us, m_sc, v_sc)
    r_is = log_correlation(a["growth_mix.small_cap_corr_intl"], m_in, v_in, m_sc, v_sc)
    return np.array([[1.0, r_ui, r_us], [r_ui, 1.0, r_is], [r_us, r_is, 1.0]])


def extra_normals(seed: int, n: int, G: int) -> tuple[np.ndarray, np.ndarray]:
    """Shocks for the growth-scenario assets, from their own stream (seed, 2028) so the official
    draws are untouched: small cap's own annual shock (n, G) and monthly bridge shocks
    (n, G, 12, 3) for [us, intl, small_cap]."""
    rng = np.random.default_rng([int(seed), 2028])
    return rng.standard_normal((n, G)), rng.standard_normal((n, G, MONTHS, 3))


def monthly_log_returns(annual_log: np.ndarray, sigma: float, e: np.ndarray) -> np.ndarray:
    """Brownian bridge: 12 monthly log returns that add up exactly to each annual log return,
    with monthly volatility sigma / sqrt(12). annual_log (n, G), e (n, G, 12) -> (n, G, 12)."""
    return annual_log[..., None] / MONTHS + sigma / np.sqrt(MONTHS) * (e - e.mean(axis=-1, keepdims=True))


def leveraged_monthly_returns(us_monthly: np.ndarray, tbill_annual: np.ndarray, multiple: float,
                              fee: float) -> np.ndarray:
    """Monthly return of a leveraged fund: multiple x monthly US return - (multiple - 1) x the
    monthly T-bill rate - fee / 12, floored at -100%. us_monthly (n, G, 12) simple returns,
    tbill_annual (n, G) annual rates."""
    borrow = (1.0 + tbill_annual) ** (1.0 / MONTHS) - 1.0
    r = multiple * us_monthly - (multiple - 1.0) * borrow[..., None] - fee / MONTHS
    return np.maximum(r, -1.0)


def draw_extra_assets(a: Assumptions, draws: "Draws", z_us: np.ndarray, z_ind: np.ndarray, tl: "Timeline",
                      seed: int, needed: set[str]) -> dict:
    n, G = z_us.shape
    z_sc, bridge = extra_normals(seed, n, G)
    out = {}
    if "small_cap" in needed:
        L = np.linalg.cholesky(growth_log_corr(a))
        mu, s = lognormal_params(a["growth_mix.small_cap_mean"], a["growth_mix.small_cap_vol"])
        out["small_cap"] = np.expm1(mu + s * (L[2, 0] * z_us + L[2, 1] * z_ind + L[2, 2] * z_sc))
    if "us_2x" in needed:
        p = stock_log_params(a)
        us_m = np.expm1(monthly_log_returns(np.log1p(draws.us), p["s_us"], bridge[..., 0]))
        tcol = [tl.tbill_years.index(y) for y in tl.growth_years]
        lev = leveraged_monthly_returns(us_m, draws.tbill[:, tcol], float(a["growth_mix.us_2x_multiple"]),
                                        float(a["growth_mix.us_2x_fee"]))
        out["us_2x"] = np.prod(1.0 + lev, axis=-1) - 1.0
    return out


def draw_random(a: Assumptions, ladder: Ladder, n: int, seed: int) -> Draws:
    """Random draws. Standard normals are drawn first, independent of the
    assumptions, so changing a mean or volatility reuses the same shocks
    (common random numbers) and comparisons are not blurred by noise."""
    tl = make_timeline(a, ladder)
    T, G, R = len(tl.tbill_years), len(tl.growth_years), ladder.n_rungs
    rng = np.random.default_rng(seed)
    z_shift = rng.standard_normal(n)
    z_tbill = rng.standard_normal((n, T))
    z_us = rng.standard_normal((n, G))
    z_ind = rng.standard_normal((n, G))
    z_ibond = rng.standard_normal((n, R))

    p = stock_log_params(a)
    z_intl = p["rho"] * z_us + np.sqrt(1.0 - p["rho"] ** 2) * z_ind
    draws = Draws(
        yield_shift=a["ladder.yield_shift_mean"] + a["ladder.yield_shift_sd"] * z_shift,
        tbill=np.maximum(tbill_mean_path(a, tl)[None, :]
                         + tbill_deviations(z_tbill, float(a["tbills.ar1_phi"]), tbill_shock_sd(a),
                                            float(a["tbills.ar1_start_deviation"])),
                         a["tbills.floor"]),
        us=np.expm1(p["mu_us"] + p["s_us"] * z_us),
        intl=np.expm1(p["mu_intl"] + p["s_intl"] * z_intl),
        ibond_error=a["ladder.ibonds_error_mean"] + ibond_error_sd(a, ladder)[None, :] * z_ibond,
        contribution=np.full(n, float(a["plan.growth_contribution"])),
    )
    needed = set(growth_mix(a)) & {"small_cap", "us_2x"}
    if needed:
        draws = replace(draws, extra=draw_extra_assets(a, draws, z_us, z_ind, tl, seed, needed))
    return draws


# --------------------------------------------------------------- results ----

@dataclass(frozen=True)
class Results:
    timeline: Timeline
    # ladder and buffer
    ladder_cost: np.ndarray          # (n,)
    shortfall: np.ndarray            # (n,) ladder cost above budget, taken from 2028 contribution
    unfunded: np.ndarray             # (n,) shortfall the 2028 contribution could not cover
    buffer_start: np.ndarray         # (n,) Jan 2027 leftover cash
    rung_payout: np.ndarray          # (n, R) cash each rung delivers by its bill date
    bill_amount: float
    ladder_only_paid: np.ndarray     # (n, R) bill dollars ladder + buffer pay with no top-up
    topup_rule: str                  # rate_rule | fixed_rule | foresight (reference only)
    topup_needed: np.ndarray         # (n,) perfect-foresight top-up: exact amount needed on this path
    topup_target: np.ndarray         # (n,) amount the rule asks to move at Jan valuation_year
    topup: np.ndarray                # (n,) amount actually moved (capped at the growth bucket)
    excess_topup_final: np.ndarray   # (n,) unneeded top-up, grown in T-bills to after the last bill
    backstop_start: np.ndarray       # (n,) backstop set aside from the client's cushion at Jan valuation_year
    backstop_draw: np.ndarray        # (n, R) backstop dollars used for each bill
    backstop_left: np.ndarray        # (n,) backstop left after the last bill, returned to the client
    backstop_interest: np.ndarray    # (n,) T-bill interest the backstop earned, valuation year to last bill
    bill_paid: np.ndarray            # (n, R) bill dollars paid by the whole portfolio
    buffer_path: np.ndarray          # (n, len(buffer_years)) reserve each Jan 1 after that day's flows
    # growth bucket
    growth_contribution: np.ndarray  # (n,)
    growth_path: np.ndarray          # (n, G+1) market value each Jan 1, before the top-up
    give_pct: float
    deflator: float                  # nominal -> base-year dollars at valuation_year

    @property
    def n(self) -> int:
        return len(self.ladder_cost)

    # Bills -------------------------------------------------------------------
    @property
    def bills_fully_paid(self) -> np.ndarray:
        """(n, R) bill paid in full by the whole portfolio."""
        return self.bill_paid >= self.bill_amount - 1e-6

    @property
    def all_paid(self) -> np.ndarray:
        """Every bill paid by the whole portfolio (ladder -> buffer -> growth bucket)."""
        return self.bills_fully_paid.all(axis=1)

    @property
    def ladder_only_shortfall(self) -> np.ndarray:
        """(n, R) unpaid dollars per bill if ladder + buffer had to pay alone."""
        return np.maximum(self.bill_amount - self.ladder_only_paid, 0.0)

    @property
    def ladder_only_total_shortfall(self) -> np.ndarray:
        return self.ladder_only_shortfall.sum(axis=1)

    @property
    def ladder_only_all_paid(self) -> np.ndarray:
        return (self.ladder_only_shortfall <= 1e-6).all(axis=1)

    @property
    def ladder_only_coverage(self) -> np.ndarray:
        """Share of all bill dollars that ladder + buffer pay by themselves (no top-up, no backstop)."""
        return self.ladder_only_paid.sum(axis=1) / (self.bill_amount * self.ladder_only_paid.shape[1])

    @property
    def ladder_only_bills_short(self) -> np.ndarray:
        """Number of bills (0-10) that ladder + buffer alone leave short."""
        return (self.ladder_only_shortfall > 1e-6).sum(axis=1)

    @property
    def failed(self) -> np.ndarray:
        """Some bill not paid in full even after the rule's top-up (no further help)."""
        return ~self.all_paid

    @property
    def rule_capped(self) -> np.ndarray:
        """The growth bucket could not supply the amount the rule asked for."""
        return self.topup_target > self.value_before_topup + 1e-6

    @property
    def foresight_all_paid(self) -> np.ndarray:
        """Reference: all bills paid if the exact top-up were known in advance."""
        return self.topup_needed <= self.value_before_topup + 1e-6

    @property
    def unpaid_after_backstop(self) -> np.ndarray:
        return np.maximum(self.unpaid - self.backstop_draw.sum(axis=1), 0.0)

    @property
    def all_paid_with_backstop(self) -> np.ndarray:
        return self.unpaid_after_backstop <= 1e-6

    @property
    def backstop_used(self) -> np.ndarray:
        return self.backstop_draw.sum(axis=1)

    @property
    def cushion_kept(self) -> np.ndarray:
        """Client's share of the growth bucket after the top-up: value x (1 - give_pct)."""
        return self.value * (1.0 - self.give_pct)

    @property
    def cushion_release(self) -> np.ndarray:
        """Reserve left after the final bill, released to the client's cushion (nominal)."""
        return np.maximum(self.final_buffer, 0.0)

    @property
    def unpaid(self) -> np.ndarray:
        """Total bill dollars the whole portfolio failed to pay."""
        return np.maximum(self.bill_amount - self.bill_paid, 0.0).sum(axis=1)

    @property
    def post_bill_buffer(self) -> np.ndarray:
        idx = [self.timeline.buffer_years.index(y) for y in self.timeline.bill_years]
        return self.buffer_path[:, idx]

    @property
    def min_buffer(self) -> np.ndarray:
        """Lowest reserve left after any bill is paid."""
        return self.post_bill_buffer.min(axis=1)

    @property
    def final_buffer(self) -> np.ndarray:
        return self.buffer_path[:, -1]

    # Growth bucket and facility ------------------------------------------------
    @property
    def value_before_topup(self) -> np.ndarray:
        return self.growth_path[:, -1]

    @property
    def value(self) -> np.ndarray:
        """Growth bucket at Jan valuation_year after the reserve top-up."""
        return self.value_before_topup - self.topup

    @property
    def growth_path_after_topup(self) -> np.ndarray:
        path = self.growth_path.copy()
        path[:, -1] = self.value
        return path

    @property
    def facility(self) -> np.ndarray:
        return self.give_pct * self.value

    @property
    def value_real(self) -> np.ndarray:
        return self.value / self.deflator

    @property
    def facility_real(self) -> np.ndarray:
        return self.facility / self.deflator


# ------------------------------------------------------------ simulation ----

def rung_payouts(a: Assumptions, ladder: Ladder, tl: Timeline, draws: Draws) -> np.ndarray:
    """Cash each rung delivers by its bill date. Shape (n, R).

    ETF / face-model rungs pay their bill amount just before the bill (no interest
    between maturity and bill, which is conservative); iBonds rungs lose their fee
    ((1 - fee)^years to maturity) and carry the payout error. In the "cashflows" model
    Treasury rungs (coupon bonds and STRIPS) pay their actual cash flows, reinvested in
    T-bills at the path's simulated rates until the bill date.
    """
    settle = pd.Timestamp(a["plan.ladder_purchase_date"])
    model = a["ladder.bond_payout_model"]
    tcol = {y: i for i, y in enumerate(tl.tbill_years)}
    n = len(draws.yield_shift)
    out = np.empty((n, ladder.n_rungs))
    fee = ibond_fee_factor(a, ladder)
    for k, flow in enumerate(ladder.flows(settle, model)):
        if model == "face" or not ladder.is_treasury[k]:
            err = draws.ibond_error[:, k] if ladder.is_ibond[k] else 0.0
            out[:, k] = flow.amounts.sum() * fee[k] * (1.0 + err)
            continue
        total = np.zeros(n)
        for d, amount in zip(flow.dates, flow.amounts):
            year_end = pd.Timestamp(year=d.year + 1, month=1, day=1)
            frac = (year_end - d).days / (366 if d.is_leap_year else 365)
            growth = 1.0 + draws.tbill[:, tcol[d.year]] * frac
            for y in range(d.year + 1, tl.bill_years[k]):
                growth = growth * (1.0 + draws.tbill[:, tcol[y]])
            total += amount * growth
        out[:, k] = total
    return out


def _reserve_pass(start: np.ndarray, payout: np.ndarray, tbill: np.ndarray, tl: Timeline, bill: float,
                  topup: np.ndarray | None = None, clip: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Roll the T-bill reserve from the purchase year through the last bill.

    Each Jan 1: grow at last year's T-bill rate, add the top-up (valuation year
    only), add that year's rung payout, pay the bill. With clip=False the bill is
    always paid and the reserve may go negative, which measures the deficit.
    Returns (reserve path after each Jan 1, bill dollars paid).
    """
    tcol = {y: i for i, y in enumerate(tl.tbill_years)}
    bill_idx = {y: k for k, y in enumerate(tl.bill_years)}
    reserve = start.astype(float).copy()
    path = np.empty((len(reserve), len(tl.buffer_years)))
    paid = np.zeros_like(payout)
    for j, year in enumerate(tl.buffer_years):
        if year > tl.purchase_year:
            reserve = reserve * (1.0 + tbill[:, tcol[year - 1]])
        if topup is not None and year == tl.valuation_year:
            reserve = reserve + topup
        if year in bill_idx:
            k = bill_idx[year]
            available = reserve + payout[:, k]
            paid[:, k] = np.clip(available, 0.0, bill) if clip else bill
            reserve = available - paid[:, k]
        path[:, j] = reserve
    return path, paid


def _backstop_pass(start: np.ndarray, unpaid: np.ndarray, tbill: np.ndarray,
                   tl: Timeline) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hold the backstop in T-bills from Jan 1 of the valuation year; on each bill date
    pay whatever the reserve left unpaid, as far as the backstop reaches.
    Returns (dollars drawn per bill, backstop left after the last bill, interest earned)."""
    tcol = {y: i for i, y in enumerate(tl.tbill_years)}
    bill_idx = {y: k for k, y in enumerate(tl.bill_years)}
    backstop = start.astype(float).copy()
    draw = np.zeros_like(unpaid)
    interest = np.zeros_like(backstop)
    for year in range(tl.valuation_year, tl.bill_years[-1] + 1):
        if year > tl.valuation_year:
            earned = backstop * tbill[:, tcol[year - 1]]
            interest += earned
            backstop = backstop + earned
        if year in bill_idx:
            k = bill_idx[year]
            draw[:, k] = np.minimum(np.maximum(unpaid[:, k], 0.0), backstop)
            backstop = backstop - draw[:, k]
    return draw, backstop, interest


def _required_topup(start: np.ndarray, payout: np.ndarray, tbill: np.ndarray, tl: Timeline,
                    bill: float) -> np.ndarray:
    """Smallest amount added to the reserve on Jan 1 of the valuation year so every bill
    is paid, given these payouts and T-bill rates. Runs the reserve without the cap at
    zero, then X = max over bills of (deficit after bill k) / (growth of $1 to bill k)."""
    n = len(start)
    unclipped, _ = _reserve_pass(start, payout, tbill, tl, bill, clip=False)
    unit, _ = _reserve_pass(np.zeros(n), np.zeros_like(payout), tbill, tl, 0.0,
                            topup=np.ones(n), clip=False)
    cols = [tl.buffer_years.index(y) for y in tl.bill_years]
    return np.maximum((-unclipped[:, cols] / unit[:, cols]).max(axis=1), 0.0)


def _rate_rule_topup(a: Assumptions, ladder: Ladder, tl: Timeline, draws: Draws,
                     start: np.ndarray, bill: float) -> np.ndarray:
    """No-foresight rule A. On Jan 1 of the valuation year Laura knows the reserve and
    every cash flow received so far. She assumes all reinvestment from then on earns
    the conservative rate, that bonds pay their scheduled coupons and principal, and that
    each iBonds rung not yet matured pays its target less its fee less a safety margin of
    `waterfall.ibonds_margin_sd` std devs of its payout error; she moves the shortfall."""
    rate = float(a["waterfall.rate_rule_rate"])
    tbill = draws.tbill.copy()
    future = [i for i, y in enumerate(tl.tbill_years) if y >= tl.valuation_year]
    tbill[:, future] = rate
    val_date = pd.Timestamp(year=tl.valuation_year, month=1, day=1)
    matured = np.array([m < val_date for m in ladder.maturity])
    margin = float(a["waterfall.ibonds_margin_sd"]) * ibond_error_sd(a, ladder)
    err = np.where(matured[None, :], draws.ibond_error,
                   float(a["ladder.ibonds_error_mean"]) - margin[None, :])
    projected = rung_payouts(a, ladder, tl, replace(draws, tbill=tbill, ibond_error=err))
    return _required_topup(start, projected, tbill, tl, bill)


def simulate(a: Assumptions, draws: Draws, ladder: Ladder | None = None) -> Results:
    ladder = ladder or load_ladder(a)
    tl = make_timeline(a, ladder)
    tbill_col = {y: i for i, y in enumerate(tl.tbill_years)}
    bill = float(a["plan.bill_amount"])
    budget = float(a["plan.ladder_budget"])

    # Jan 2027: buy the ladder at shifted yields; leftover cash is the buffer.
    cost = ladder_costs(ladder, draws.yield_shift, a).sum(axis=1)
    shortfall = np.maximum(cost - budget, 0.0)
    buffer = np.maximum(budget - cost, 0.0)

    # Jan 2028: shortfall comes out of the growth contribution first. Anything
    # the contribution cannot cover is carried as a negative buffer (borrowed
    # at the T-bill rate) so the ladder is still bought in full.
    contribution = draws.contribution - shortfall
    unfunded = np.maximum(-contribution, 0.0)
    contribution = np.maximum(contribution, 0.0)
    buffer = buffer - unfunded
    buffer_start = buffer.copy()

    payout = rung_payouts(a, ladder, tl, draws)

    # Growth bucket: stocks (any mix) rebalanced among themselves each January; a T-bill
    # sleeve (cautious mixes) and the glide-path moves sit in T-bills.
    mix = growth_mix(a)
    asset_returns = {"us": draws.us, "intl": draws.intl, **draws.extra}
    stock_w = {k: w for k, w in mix.items() if k != "tbills" and w > 0}
    missing = set(stock_w) - set(asset_returns)
    if missing:
        raise ValueError(f"no simulated returns for growth assets {sorted(missing)}")
    total_stock_w = sum(stock_w.values())
    glide = {}
    if a["glide_path.enabled"]:
        glide = {int(s["year"]): parse_fraction(s["fraction_of_stocks"]) for s in a["glide_path.steps"]}
    rebalance = bool(a["growth.rebalance_annually"])

    hold = {k: w * contribution for k, w in stock_w.items()}
    tbills = mix.get("tbills", 0.0) * contribution
    growth_path = [contribution.copy()]
    for g, year in enumerate(tl.growth_years):
        stocks = sum(hold.values())
        if rebalance and total_stock_w > 0:
            hold = {k: (w / total_stock_w) * stocks for k, w in stock_w.items()}
        f = glide.get(year, 0.0)
        if f:
            hold = {k: v * (1 - f) for k, v in hold.items()}
            tbills = tbills + f * stocks
        hold = {k: v * (1.0 + asset_returns[k][:, g]) for k, v in hold.items()}
        tbills = tbills * (1.0 + draws.tbill[:, tbill_col[year]])
        growth_path.append(sum(hold.values()) + tbills)

    growth_path = np.column_stack(growth_path)

    # Bills-first waterfall: ladder payouts -> buffer -> growth bucket.
    n = len(cost)
    value_pre = growth_path[:, -1]
    # Ladder + buffer alone, no top-up.
    _, ladder_only_paid = _reserve_pass(buffer_start, payout, draws.tbill, tl, bill)
    # Reference: perfect-foresight top-up, the exact amount this path needs.
    topup_needed = _required_topup(buffer_start, payout, draws.tbill, tl, bill)
    # The rule Laura follows on Jan 1 of the valuation year, knowing only the past.
    rule = a["waterfall.topup_rule"]
    if rule == "rate_rule":
        topup_target = _rate_rule_topup(a, ladder, tl, draws, buffer_start, bill)
    elif rule == "fixed_rule":
        topup_target = np.full(n, float(a["waterfall.fixed_rule_amount"]))
    elif rule == "foresight":
        topup_target = topup_needed
    else:
        raise ValueError(f"waterfall.topup_rule must be one of {TOPUP_RULES}")
    topup = np.minimum(topup_target, value_pre)
    buffer_path, bill_paid = _reserve_pass(buffer_start, payout, draws.tbill, tl, bill, topup=topup)
    # Growth of $1 moved at the valuation date through the final bill, for the excess.
    unit, _ = _reserve_pass(np.zeros(n), np.zeros_like(payout), draws.tbill, tl, 0.0,
                            topup=np.ones(n), clip=False)
    excess_topup_final = np.maximum(topup - topup_needed, 0.0) * unit[:, -1]

    # Backstop: set aside from the client's cushion, held in T-bills, used only for unpaid bills.
    give = float(a["facility.give_pct"])
    cushion = (value_pre - topup) * (1.0 - give)
    backstop_start = np.minimum(float(a["waterfall.backstop_amount"]), np.maximum(cushion, 0.0))
    backstop_draw, backstop_left, backstop_interest = _backstop_pass(backstop_start, bill - bill_paid, draws.tbill, tl)

    deflator = inflation_deflator(a, tl.valuation_year)
    return Results(
        timeline=tl,
        ladder_cost=cost,
        shortfall=shortfall,
        unfunded=unfunded,
        buffer_start=buffer_start,
        rung_payout=payout,
        bill_amount=bill,
        ladder_only_paid=ladder_only_paid,
        topup_rule=rule,
        topup_needed=topup_needed,
        topup_target=topup_target,
        topup=topup,
        excess_topup_final=excess_topup_final,
        backstop_start=backstop_start,
        backstop_draw=backstop_draw,
        backstop_left=backstop_left,
        backstop_interest=backstop_interest,
        bill_paid=bill_paid,
        buffer_path=buffer_path,
        growth_contribution=contribution,
        growth_path=growth_path,
        give_pct=float(a["facility.give_pct"]),
        deflator=float(deflator),
    )


def run_monte_carlo(a: Assumptions, n: int | None = None, seed: int | None = None) -> Results:
    ladder = load_ladder(a)
    n = int(n if n is not None else a["simulation.n_sims"])
    seed = int(seed if seed is not None else a["simulation.seed"])
    return simulate(a, draw_random(a, ladder, n, seed), ladder)
