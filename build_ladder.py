"""Rebuild ladder.csv from the WInS fills and write the fill check (outputs/wins_fills.md).

    python build_ladder.py

Reads data/wins_fills_2026-10.csv (one row per trade, with the price and yield we had before the
fill in the ref_ columns) and the static columns of ladder.csv
(bill dates, security names, maturities). Writes, per rung: quantity, clean fill price
(quantity-weighted when a rung was bought in two lots), price_date (the bond's settlement date,
or the ETF's trade date), cost, the accrued interest WInS charged, and the yield backed out of
the fill price.
"""
from __future__ import annotations

import pandas as pd

from mcsim import fills
from mcsim.analysis import md_table
from mcsim.config import load_config
from mcsim.model import _coupon_from_name

FILLS = "data/wins_fills_2026-10.csv"
SOURCE_LABEL = "WInS fill, Oct 14-15 2026"
BUDGET = 300_000.0

# The bond cash amounts do NOT include the $10 commission: two lots bought at the same price on
# the same day (Nov 2040 26 + 1, Nov 2041 29 + 1) imply the same accrued per bond only if the
# amount holds $0.00 of commission, and the account reconciles to exactly $300,000 only with
# the commissions charged on top. So each rung's cost (excluding commission) is |amount|.
BOND_AMOUNT_INCLUDES_COMMISSION = False


def build() -> tuple[pd.DataFrame, dict]:
    a = load_config()
    m, basis = float(a["ladder.compounding_per_year"]), float(a["ladder.day_count_basis"])
    old = pd.read_csv(a.path("ladder.csv_path"))
    trades = pd.read_csv(FILLS)
    rows, trade_rows, yield_rows = [], [], []
    for _, r in old.sort_values("bill_number").iterrows():
        lots = trades[trades["bill_number"] == r["bill_number"]]
        qty = int(lots["quantity"].sum())
        out = r.copy()
        out["quantity"] = qty
        out["data_status"] = SOURCE_LABEL
        if str(r["type"]).lower() == "etf":
            lot = lots.iloc[0]
            ytm = fills.etf_ytm(lot["ref_price"], lot["ref_ytm"], lot["ref_price_date"], lot["price"],
                                lot["trade_date"], r["maturity_date"], m, basis)
            out.update({"price_date": lot["trade_date"], "price": lot["price"], "accrued_per_100": 0.0,
                        "ytm": round(ytm, 6), "rung_cost": round(qty * lot["price"], 2)})
            yield_rows.append({"Bill": int(r["bill_number"]), "Security": r["ticker_or_cusip"],
                               "Price we had": f"{lot['ref_price']:.2f} ({lot['ref_price_date']})",
                               "Yield we had": f"{lot['ref_ytm']:.2%}",
                               "Fill price": f"{lot['price']:.2f} ({lot['trade_date']})",
                               "Yield at fill": f"{ytm:.3%}", "Change": f"{(ytm - lot['ref_ytm']) * 1e4:+.1f} bp"})
            rows.append(out)
            continue
        coupon = _coupon_from_name(r["security"])
        commission = lots["commission"] if BOND_AMOUNT_INCLUDES_COMMISSION else 0.0 * lots["commission"]
        cost = float((lots["amount"].abs() - commission).sum())
        clean = float((lots["quantity"] * lots["price"]).sum() / qty)               # per $1,000 bond
        main = lots.loc[lots["quantity"].idxmax()]
        settle = fills.settlement_date(main["trade_date"])
        ytm = fills.bond_ytm(clean + fills.textbook_accrued(coupon, r["maturity_date"], settle), coupon,
                             r["maturity_date"], settle, m, basis)
        out.update({"price_date": settle.date().isoformat(), "price": round(clean / 10.0, 6),
                    "accrued_per_100": round((cost / qty - clean) / 10.0, 6), "ytm": round(ytm, 6),
                    "rung_cost": round(cost, 2)})
        rows.append(out)
        for _, lot in lots.iterrows():
            s = fills.settlement_date(lot["trade_date"])
            text = fills.textbook_accrued(coupon, r["maturity_date"], s)
            as_given = fills.implied_accrued(lot["amount"], lot["commission"], lot["quantity"], lot["price"])
            no_comm = fills.implied_accrued(lot["amount"], 0.0, lot["quantity"], lot["price"])
            prev, _ = fills.coupon_period(r["maturity_date"], s)
            trade_rows.append({
                "Bill": int(r["bill_number"]), "Bond": r["security"].replace("US Treasury ", ""),
                "Trade": f"{int(lot['quantity'])} @ {lot['price']:.5f} on {lot['trade_date']}",
                "Settles": s.date().isoformat(),
                "Textbook accrued (act/act)": f"${text:,.2f} ({(s - prev).days} days)",
                "WInS: amount - $10 - qty x price": f"${as_given:,.2f}",
                "WInS: amount - qty x price": f"${no_comm:,.2f}",
                "= coupon x days / 365": f"{fills.accrual_days_act365(no_comm, coupon):.1f} days",
                "WInS minus textbook, whole trade": f"${(no_comm - text) * lot['quantity']:,.2f}"})
            y_lot = fills.bond_ytm(lot["price"] + text, coupon, r["maturity_date"], s, m, basis)
            yield_rows.append({"Bill": int(r["bill_number"]), "Security": f"{r['ticker_or_cusip']} ({lot['quantity']:.0f})",
                               "Price we had": f"{lot['ref_price']:.2f} (per 100, {lot['ref_price_date']})",
                               "Yield we had": f"{lot['ref_ytm']:.2%}",
                               "Fill price": f"{lot['price'] / 10:.5f} (per 100, settles {s.date()})",
                               "Yield at fill": f"{y_lot:.3%}", "Change": f"{(y_lot - lot['ref_ytm']) * 1e4:+.1f} bp"})
        if len(lots) > 1 and lots["price"].nunique() > 1:
            yield_rows.append({"Bill": int(r["bill_number"]), "Security": f"{r['ticker_or_cusip']} (ladder.csv row)",
                               "Price we had": "", "Yield we had": "",
                               "Fill price": f"{clean / 10:.5f} (weighted, settles {settle.date()})",
                               "Yield at fill": f"{ytm:.3%}", "Change": f"{(ytm - main['ref_ytm']) * 1e4:+.1f} bp"})
    ladder = pd.DataFrame(rows)[old.columns]
    trades_buffer = trades[trades["type"] == "Buffer"]
    sgov = float((trades_buffer["quantity"] * trades_buffer["price"]).sum())
    cash = float(trades.loc[trades["type"] == "Cash", "amount"].sum())
    bond_comm = float(trades.loc[trades["type"] == "Bond", "commission"].sum())
    etf_comm = float(trades.loc[trades["type"].isin(["ETF", "Buffer"]), "commission"].sum())
    recon = {"ETF rungs": float(ladder.loc[ladder["type"] == "ETF", "rung_cost"].sum()),
             "Bond rungs": float(ladder.loc[ladder["type"] == "Bond", "rung_cost"].sum()),
             "SGOV buffer (48 sh)": sgov, "Commissions (ETF + SGOV trades)": etf_comm,
             "Commissions (bond trades)": bond_comm, "Cash": cash}
    return ladder, {"trades": pd.DataFrame(trade_rows), "yields": pd.DataFrame(yield_rows), "recon": recon}


def report(ladder: pd.DataFrame, info: dict) -> str:
    recon = info["recon"]
    total = sum(recon.values())
    lines = [
        "# WInS fills check (Round 7)",
        "",
        f"Built by `build_ladder.py` from `{FILLS}`. ladder.csv rows are labelled \"{SOURCE_LABEL}\".",
        "",
        "## Accrued interest WInS charged, per trade (per $1,000 bond)",
        "",
        md_table(info["trades"]),
        "",
        "- **Textbook** = actual/actual to the T+1 settlement date.",
        "- **The $10 commission is not inside the bond amounts.** Two lots at the same price and date "
        "(Nov 2040 26 + 1, Nov 2041 29 + 1) give the same accrued per bond only if the amount holds $0.00 "
        "of commission, and the account reconciles to exactly $300,000.00 only with the commissions charged "
        "on top (table below). Subtracting $10 from the amount is what makes the 1-bond Feb 2037 trade look "
        "like negative accrued: without it, that trade's accrued is +$7.68, one day more than the 29-bond "
        "trade the day before ($7.55), as it should be.",
        "- **WInS figures accrued as coupon x days / 365**, counting to Oct 12 for the Oct 14 trades "
        "(Oct 13 for the Oct 15 trade), not actual/actual to settlement. So it charged a little less than "
        "textbook on every trade.",
        "- **May 2038 (912810PX0) stands out**: WInS charged 58 days of interest, as if the last coupon "
        "were Aug 15. The bond pays May 15 / Nov 15, so textbook is 153 days. Laura paid about $335 less "
        "accrued than textbook on that trade. Nov 2039 is charged one day less than the other May/Nov "
        "bonds (149 vs 150 days, about $3).",
        "",
        "## Yields backed out of the fills",
        "",
        md_table(info["yields"]),
        "",
        "- **Bonds:** the yield at which the bond's remaining coupons and principal, discounted from the "
        "settlement date, equal the clean fill price plus textbook accrued. Model convention: semiannual "
        "compounding, actual days / 365.25 (the same convention the simulation reprices with). Bill 6 was "
        "bought in two lots; its ladder.csv row uses the quantity-weighted clean price at the larger lot's "
        "settlement date.",
        "- **iBonds ETFs:** the price and yield we had imply a value per share at the fund's maturity "
        "(old price grown at the old yield, semiannual). Holding that maturity value fixed, the yield at "
        "fill is the rate that grows the fill price to the same value by Dec 15 of the fund's year. A lower "
        "fill price means a higher yield.",
        "",
        "## Where the $300,000 went",
        "",
        md_table(pd.DataFrame([{"Item": k, "Amount": f"${v:,.2f}"} for k, v in recon.items()]
                              + [{"Item": "**Total**", "Amount": f"**${total:,.2f}**"}])),
        "",
        f"Budget ${BUDGET:,.0f}; difference ${total - BUDGET:,.2f}.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    ladder, info = build()
    a = load_config()
    ladder.to_csv(a.path("ladder.csv_path"), index=False)
    out = a.base_dir / "outputs" / "wins_fills.md"
    out.write_text(report(ladder, info))
    print(ladder.drop(columns=["security", "bill_date", "bill_amount"]).to_string(index=False))
    print(f"\nwrote ladder.csv and {out.relative_to(a.base_dir)}")
