# WInS fills check (Round 7)

Built by `build_ladder.py` from `data/wins_fills_2026-10.csv`. ladder.csv rows are labelled "WInS fill, Oct 14-15 2026".

## Accrued interest WInS charged, per trade (per $1,000 bond)

| Bill | Bond | Trade | Settles | Textbook accrued (act/act) | WInS: amount - $10 - qty x price | WInS: amount - qty x price | = coupon x days / 365 | WInS minus textbook, whole trade |
|---|---|---|---|---|---|---|---|---|
| 6 | 4.750% Feb 15 2037 | 29 @ 965.58276 on 2026-10-14 | 2026-10-15 | $7.87 (61 days) | $7.20 | $7.55 | 58.0 days | $-9.45 |
| 6 | 4.750% Feb 15 2037 | 1 @ 967.81053 on 2026-10-15 | 2026-10-16 | $8.00 (62 days) | $-2.32 | $7.68 | 59.0 days | $-0.32 |
| 7 | 4.500% May 15 2038 | 29 @ 937.02140 on 2026-10-14 | 2026-10-15 | $18.71 (153 days) | $6.81 | $7.15 | 58.0 days | $-335.20 |
| 8 | 4.375% Nov 15 2039 | 28 @ 906.86057 on 2026-10-14 | 2026-10-15 | $18.19 (153 days) | $17.50 | $17.86 | 149.0 days | $-9.24 |
| 9 | 4.250% Nov 15 2040 | 26 @ 884.36175 on 2026-10-14 | 2026-10-15 | $17.67 (153 days) | $17.08 | $17.47 | 150.0 days | $-5.30 |
| 9 | 4.250% Nov 15 2040 | 1 @ 884.36175 on 2026-10-14 | 2026-10-15 | $17.67 (153 days) | $7.47 | $17.47 | 150.0 days | $-0.20 |
| 10 | 3.125% Nov 15 2041 | 29 @ 755.92395 on 2026-10-14 | 2026-10-15 | $12.99 (153 days) | $12.50 | $12.84 | 150.0 days | $-4.35 |
| 10 | 3.125% Nov 15 2041 | 1 @ 755.92395 on 2026-10-14 | 2026-10-15 | $12.99 (153 days) | $2.85 | $12.85 | 150.0 days | $-0.15 |

- **Textbook** = actual/actual to the T+1 settlement date.
- **The $10 commission is not inside the bond amounts.** Two lots at the same price and date (Nov 2040 26 + 1, Nov 2041 29 + 1) give the same accrued per bond only if the amount holds $0.00 of commission, and the account reconciles to exactly $300,000.00 only with the commissions charged on top (table below). Subtracting $10 from the amount is what makes the 1-bond Feb 2037 trade look like negative accrued: without it, that trade's accrued is +$7.68, one day more than the 29-bond trade the day before ($7.55), as it should be.
- **WInS figures accrued as coupon x days / 365**, counting to Oct 12 for the Oct 14 trades (Oct 13 for the Oct 15 trade), not actual/actual to settlement. So it charged a little less than textbook on every trade.
- **May 2038 (912810PX0) stands out**: WInS charged 58 days of interest, as if the last coupon were Aug 15. The bond pays May 15 / Nov 15, so textbook is 153 days. Laura paid about $335 less accrued than textbook on that trade. Nov 2039 is charged one day less than the other May/Nov bonds (149 vs 150 days, about $3).

## Yields backed out of the fills

| Bill | Security | Price we had | Yield we had | Fill price | Yield at fill | Change |
|---|---|---|---|---|---|---|
| 1 | IBTM | 21.78 (2026-10-13) | 5.08% | 21.67 (2026-10-14) | 5.166% | +8.6 bp |
| 2 | IBTO | 23.03 (2026-10-13) | 5.13% | 22.89 (2026-10-14) | 5.219% | +8.9 bp |
| 3 | IBTP | 24.07 (2026-10-09) | 5.16% | 23.97 (2026-10-14) | 5.221% | +6.1 bp |
| 4 | IBTQ | 23.67 (2026-10-09) | 5.20% | 23.56 (2026-10-14) | 5.260% | +6.0 bp |
| 5 | IBTR | 23.46 (2026-10-09) | 5.23% | 23.36 (2026-10-14) | 5.280% | +5.0 bp |
| 6 | 912810PT9 (29) | 96.98 (per 100, 2026-10-13) | 5.13% | 96.55828 (per 100, settles 2026-10-15) | 5.182% | +5.2 bp |
| 6 | 912810PT9 (1) | 96.98 (per 100, 2026-10-13) | 5.13% | 96.78105 (per 100, settles 2026-10-16) | 5.153% | +2.3 bp |
| 6 | 912810PT9 (ladder.csv row) |  |  | 96.56570 (weighted, settles 2026-10-15) | 5.181% | +5.1 bp |
| 7 | 912810PX0 (29) | 94.09 (per 100, 2026-10-13) | 5.18% | 93.70214 (per 100, settles 2026-10-15) | 5.233% | +5.3 bp |
| 8 | 912810QD3 (28) | 91.06 (per 100, 2026-10-13) | 5.33% | 90.68606 (per 100, settles 2026-10-15) | 5.375% | +4.5 bp |
| 9 | 912810QL5 (26) | 88.31 (per 100, 2026-10-13) | 5.45% | 88.43618 (per 100, settles 2026-10-15) | 5.435% | -1.5 bp |
| 9 | 912810QL5 (1) | 88.31 (per 100, 2026-10-13) | 5.45% | 88.43618 (per 100, settles 2026-10-15) | 5.435% | -1.5 bp |
| 10 | 912810QT8 (29) | 75.79 (per 100, 2026-10-13) | 5.51% | 75.59239 (per 100, settles 2026-10-15) | 5.532% | +2.2 bp |
| 10 | 912810QT8 (1) | 75.79 (per 100, 2026-10-13) | 5.51% | 75.59239 (per 100, settles 2026-10-15) | 5.532% | +2.2 bp |

- **Bonds:** the yield at which the bond's remaining coupons and principal, discounted from the settlement date, equal the clean fill price plus textbook accrued. Model convention: semiannual compounding, actual days / 365.25 (the same convention the simulation reprices with). Bill 6 was bought in two lots; its ladder.csv row uses the quantity-weighted clean price at the larger lot's settlement date.
- **iBonds ETFs:** the price and yield we had imply a value per share at the fund's maturity (old price grown at the old yield, semiannual). Holding that maturity value fixed, the yield at fill is the rate that grows the fill price to the same value by Dec 15 of the fund's year. A lower fill price means a higher yield.

## Where the $300,000 went

| Item | Amount |
|---|---|
| ETF rungs | $164,493.44 |
| Bond rungs | $129,881.78 |
| SGOV buffer (48 sh) | $4,825.92 |
| Commissions (ETF + SGOV trades) | $175.00 |
| Commissions (bond trades) | $80.00 |
| Cash | $543.86 |
| **Total** | **$300,000.00** |

Budget $300,000; difference $0.00.
