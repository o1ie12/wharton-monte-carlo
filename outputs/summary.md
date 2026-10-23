# Client plan Monte Carlo summary

500,000 simulated paths, seed 20270101, generated 2026-10-16. Real figures are in Jan 2027 dollars (2.4% inflation in 2027, 2.3% from 2028).

**Headline (official): all 10 bills paid on 100.00% of paths** with the Rate rule (1.0%) and the $10,000 backstop; 92.59% without the backstop. Median facility contribution $139,466; example co-sponsor range (method) $91,000 to $139,000 (90% confidence of reaching the low end).

The actual range will be set in 2031 from Laura's real growth bucket value and the actual 2027 ladder cost, using the same percentile method.

Why A2 (1.0% rule, $10,000 backstop) stays official: A4 adds about $1,900 to the median facility but leaves less spare backstop room ($776 / 6.2% vs $1,259 / 12.6% on the worst seed) and less free cushion for Laura ($34,622 vs $36,489). We chose the safer option for client money.

<sup>Footnote, if bought at Oct 2026 WInS prices (purchase-yield risk off): median facility contribution $140,607 and P10 $93,236, vs $139,466 and $91,210 in the official run, which keeps purchase-yield risk on because Laura's money arrives in 2027.</sup>

## Bills: ladder, buffer, then growth bucket

Bills are funded in order: ladder payouts, then the T-bill buffer, then the growth bucket. On Jan 1 2033, before the facility contribution, the growth bucket tops up the T-bill reserve using a rule that needs no knowledge of future rates (Rate rule (1.0%)). Money moved but not needed stays in T-bills and is released to the client's cushion after the Jan 2042 bill.

- **(a) Official: probability all 10 bills are paid, Rate rule (1.0%) + $10,000 backstop: 100.00%** (0 of 500,000 paths fail). The backstop is used on 7.41% of paths; mean returned to the client after Jan 2042: $13,445.
- Without the backstop (whole portfolio, Rate rule (1.0%)): 92.59% (37,073 paths fail; when they do, total unpaid median $2,114, max $8,532).
- **(b) Probability ladder + buffer alone pay all bills, no top-up: 38.3%**
- **(c) Top-up moved in Jan 2033:** median $18,210, P90 $25,304, P99 $27,271, max $28,845. Mean released to the cushion after the Jan 2042 bill: $23,234 (of which unneeded top-up $13,399).
- Reference only, perfect foresight (exact top-up, needs future T-bill rates): all bills paid 100.00%; top-up median $2,197, P90 $19,533, P99 $28,956, max $35,439.
- Bond payout model: **cashflows** (Treasury rungs pay their actual coupons and principal, reinvested at simulated T-bill rates). Under **face** (each Treasury rung pays exactly the bill amount): (a) 99.26%, (b) 62.0%.
- Ladder cost in ladder.csv (priced 2026-10-14 to 2026-10-15): $294,375. Repriced on Jan 1 2027 at unchanged yields: $295,601 against a $300,000 budget; median simulated cost $295,588.
- Sizing check: every Treasury rung holds at least the sizing rule's quantity.
- Probability the ladder costs more than the budget: 36.2% (median shortfall when it does: $7,148, taken from the 2028 contribution). Median buffer at Jan 2027: $4,412.
- Minimum reserve left after any bill (whole portfolio): median $19,003, P5 $0, worst path $0.

### Ladder + buffer by themselves (no top-up, no backstop)

The ladder is not self-sufficient: by itself it leaves at least one bill short on 61.7% of paths, but those gaps are small relative to the $500,000 of bills.

- **Bill-dollar coverage** (bill dollars ladder + buffer pay by themselves / $500,000): median **99.5%**, P10 95.8%, worst path 92.9%.
- **Shortfall size** on the 308,639 paths that fall short: median **$10,488**, P90 $23,970, max $35,521.
- **Bills missed** (how many of the 10 bills are short):

| Bills short | Paths | Share of paths |
|---|---|---|
| 0 | 191361 | 38.27% |
| 1 | 23068 | 4.61% |
| 2 | 36562 | 7.31% |
| 3 | 39343 | 7.87% |
| 4 | 41962 | 8.39% |
| 5 | 33574 | 6.71% |
| 6 | 22042 | 4.41% |
| 7 | 29635 | 5.93% |
| 8 | 34573 | 6.91% |
| 9 | 31289 | 6.26% |
| 10 | 16591 | 3.32% |

Bills short most often:

| Bill # | Bill (Jan 1) | Share of paths short | Median shortfall when short |
|---|---|---|---|
| 10 | 2042 | 50.7% | $3,187 |
| 9 | 2041 | 48.8% | $3,882 |
| 8 | 2040 | 42.6% | $3,274 |
| 7 | 2039 | 36.2% | $3,064 |
| 6 | 2038 | 27.4% | $2,032 |
| 1 | 2033 | 25.2% | $389 |
| 2 | 2034 | 23.4% | $427 |
| 3 | 2035 | 22.9% | $483 |
| 5 | 2037 | 22.8% | $597 |
| 4 | 2036 | 22.7% | $538 |

Full distribution of total ladder-only shortfall (nominal, summed over the 10 bills), on the paths where ladder + buffer fall short:

| Statistic | Total shortfall |
|---|---|
| Paths short | 308,639 of 500,000 (61.7%) |
| Mean | $11,563 |
| P10 | $1,410 |
| P25 | $3,704 |
| P50 | $10,488 |
| P75 | $18,031 |
| P90 | $23,970 |
| P99 | $30,116 |
| Max | $35,521 |

### By bill

| Bill (Jan 1) | Median rung payout | P5 rung payout | Ladder-only: share of paths short | Ladder-only: median shortfall when short | Ladder-only: P90 shortfall when short | Whole portfolio: unpaid (mean) |
|---|---|---|---|---|---|---|
| 2033 | $49,793 | $49,060 | 25.2% | $389 | $868 | $0 |
| 2034 | $49,756 | $48,902 | 23.4% | $427 | $986 | $0 |
| 2035 | $49,720 | $48,747 | 22.9% | $483 | $1,111 | $0 |
| 2036 | $49,689 | $48,590 | 22.7% | $538 | $1,252 | $0 |
| 2037 | $49,654 | $48,438 | 22.8% | $597 | $1,386 | $0 |
| 2038 | $48,998 | $45,565 | 27.4% | $2,032 | $4,070 | $0 |
| 2039 | $47,951 | $44,624 | 36.2% | $3,064 | $5,209 | $0 |
| 2040 | $47,780 | $44,575 | 42.6% | $3,274 | $5,315 | $0 |
| 2041 | $47,290 | $43,800 | 48.8% | $3,882 | $6,099 | $1 |
| 2042 | $48,096 | $44,790 | 50.7% | $3,187 | $5,153 | $168 |

## Jan 2033 top-up rules compared

Same 500,000 paths under each rule. **Rate rule:** move the shortfall assuming all reinvestment from Jan 2033 earns 1.0% and unmatured ETF rungs pay their expected amount. **Fixed rule:** always move $13,400. Perfect foresight is shown for reference only; it is not a rule anyone can follow.

| Metric | Rate rule (1.0%) ★ official | Fixed rule ($13,400) | Perfect foresight (reference) |
|---|---|---|---|
| All bills paid, no further help | 92.59% | 79.38% | 100.00% |
| All bills paid with $10,000 backstop | 100.00% | 94.74% | 100.00% |
| Paths that fail | 37,073 | 103,120 | 0 |
| Top-up moved Jan 2033: median / P90 / max | $18,210 / $25,304 / $28,845 | $13,400 / $13,400 / $13,400 | $2,197 / $19,533 / $35,439 |
| Shortfall when it fails: median / P90 / max | $2,114 / $4,365 / $8,532 | $6,605 / $14,225 / $22,091 | no failures |
| Released to cushion after Jan 2042 bill (mean, nominal) | $23,234 | $22,055 | $9,834 |
| Released to cushion (mean, Jan 2027 dollars) | $16,503 | $15,666 | $6,985 |
| Unneeded top-up within the release (mean, nominal) | $13,399 | $12,221 | $0 |
| Facility P5 | $80,150 | $83,861 | $87,355 |
| Facility P10 | $91,210 | $94,289 | $98,306 |
| Facility P25 | $111,951 | $114,129 | $118,959 |
| Facility P50 | $139,466 | $140,759 | $146,253 |
| Facility P75 | $172,585 | $173,205 | $179,128 |
| Facility P90 | $207,984 | $208,329 | $214,500 |
| Facility P95 | $232,335 | $232,347 | $238,735 |
| Co-sponsor range [P10, P50] | $91,000 – $139,000 | $94,000 – $140,000 | $98,000 – $146,000 |
| Range: P(at or above low end) / P(inside) | 90% / 40% | 90% / 39% | 90% / 40% |

Co-sponsor ranges under the Rate rule (1.0%):

| Range | Low | High | Low (real) | High (real) | P(inside range) | P(at or above low end) |
|---|---|---|---|---|---|---|
| [P25, P75] | $111,000 | $172,000 | $96,749 | $149,917 | 50.5% | 75.8% |
| [P10, P90] | $91,000 | $207,000 | $79,316 | $180,423 | 79.8% | 90.1% |
| [P10, P50] | $91,000 | $139,000 | $79,316 | $121,154 | 39.7% | 90.1% |

Co-sponsor ranges under the Fixed rule ($13,400):

| Range | Low | High | Low (real) | High (real) | P(inside range) | P(at or above low end) |
|---|---|---|---|---|---|---|
| [P25, P75] | $114,000 | $173,000 | $99,363 | $150,788 | 50.0% | 75.1% |
| [P10, P90] | $94,000 | $208,000 | $81,931 | $181,295 | 80.1% | 90.2% |
| [P10, P50] | $94,000 | $140,000 | $81,931 | $122,025 | 39.5% | 90.2% |

## Growth bucket and facility contribution (Jan 2033, Rate rule (1.0%))

Facility contribution = 75% of the Jan 2033 growth-bucket value after the bill top-up. Glide path on.

| Percentile | Jan 2033 value before top-up | Jan 2033 value after top-up (nominal) | Jan 2033 value after top-up (real) | Facility contribution (nominal) | Facility contribution (real) |
|---|---|---|---|---|---|
| P5 | $125,215 | $106,867 | $93,146 | $80,150 | $69,860 |
| P10 | $139,119 | $121,613 | $105,999 | $91,210 | $79,499 |
| P25 | $165,572 | $149,268 | $130,103 | $111,951 | $97,577 |
| P50 | $201,078 | $185,954 | $162,079 | $139,466 | $121,560 |
| P75 | $244,340 | $230,114 | $200,569 | $172,585 | $150,427 |
| P90 | $291,172 | $277,312 | $241,708 | $207,984 | $181,281 |
| P95 | $323,196 | $309,780 | $270,007 | $232,335 | $202,505 |

## Candidate co-sponsor ranges (facility contribution, nominal, Rate rule (1.0%))

| Range | Low | High | Low (real) | High (real) | P(inside range) | P(at or above low end) |
|---|---|---|---|---|---|---|
| [P25, P75] | $111,000 | $172,000 | $96,749 | $149,917 | 50.5% | 75.8% |
| [P10, P90] | $91,000 | $207,000 | $79,316 | $180,423 | 79.8% | 90.1% |
| [P10, P50] | $91,000 | $139,000 | $79,316 | $121,154 | 39.7% | 90.1% |

Example co-sponsor range (method): **[P10, P50] = $91,000 to $139,000**, 90% confidence the contribution reaches the low end. Both endpoints are rounded down to the nearest $1,000 so we never overstate: the low end is at or below the percentile it comes from and the top is at or below the median, so the chance of reaching the low end is at least the percentile's.

The actual range will be set in 2031 from Laura's real growth bucket value and the actual 2027 ladder cost, using the same percentile method.

## Stress tests (fixed paths)

| scenario | ladder_cost | shortfall_from_2028 | topup_2033 | value_2033 | facility_contribution | all_bills_paid | unpaid_bill_dollars | unpaid_pct_of_cushion | unpaid_after_backstop | backstop_left_2042 | rule_rate_needed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| good | $295,601 | $0 | $18,353 | $274,468 | $205,851 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| normal | $295,601 | $0 | $18,353 | $185,314 | $138,985 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| bad | $295,601 | $0 | $18,353 | $124,068 | $93,051 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| zero_growth | $295,601 | $0 | $18,353 | $136,498 | $102,374 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| crash_2028 | $295,601 | $0 | $18,353 | $95,760 | $71,820 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| crash_2032 | $295,601 | $0 | $18,353 | $154,352 | $115,764 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| yields_down_1pt | $321,641 | $21,641 | $23,765 | $150,518 | $112,888 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| yields_down_2pt | $350,454 | $50,454 | $23,765 | $111,396 | $83,547 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| contribution_100k | $295,601 | $0 | $18,353 | $117,425 | $88,069 | yes | $0 | 0.0% | $0 | $13,278 | 3.67% |
| low_rates_2010s | $295,601 | $0 | $22,435 | $176,079 | $132,059 | NO | $661 | 1.5% | $0 | $9,798 | 0.90% |
| low_rates_2010s_p10 | $295,601 | $0 | $22,435 | $116,163 | $87,122 | NO | $661 | 2.3% | $0 | $9,798 | 0.90% |
| combined_low_rates | $350,454 | $50,454 | $26,968 | $104,774 | $78,580 | NO | $661 | 2.5% | $0 | $9,798 | 0.90% |
| combined_low_rates_p10 | $350,454 | $50,454 | $26,968 | $65,011 | $48,759 | NO | $661 | 4.1% | $0 | $9,798 | 0.90% |

value_2033 and facility contribution are after the Jan 2033 top-up (Rate rule (1.0%)). all_bills_paid: whole portfolio, no further help. unpaid_pct_of_cushion: unpaid bills as a share of the cushion kept, growth bucket x (1 - give_pct). rule_rate_needed: highest reinvestment rate the rate rule can assume and still pay every bill on that path. unpaid_after_backstop / backstop_left_2042: after the $10,000 backstop held from the client's cushion.

### Low-rate stress: T-bills at 0.5% every year (2010s-style), Rate rule (1.0%)

- **All bills paid with no further help: NO.** The rule moves $22,435 in Jan 2033; $23,067 was needed.
- **Total shortfall: $661** of unpaid bills (nominal, at the bill dates).
- Median growth outcome: shortfall = **1.5%** of the $44,020 cushion kept (growth bucket x 25%).
- P10 growth outcome: shortfall = **2.3%** of the $29,041 cushion kept (growth bucket x 25%).
- **Reinvestment rate the rule would need: 0.90%.** The rule pays every bill only if it assumes a rate no higher than what T-bills actually earn from 2033; at the 1.0% default it under-funds the reserve.
- Only T-bill rates are stressed here; the ladder is still bought at the sheet's yields.
- With the $10,000 backstop: covered. $10,000 start + $459 T-bill interest (0.5% a year from Jan 2033) - $661 used = $9,798 left after the Jan 2042 bill.

### Combined stress: yields 2 pts lower at purchase AND T-bills at 0.5% every year, Rate rule (1.0%)

- Ladder costs $350,454; $50,454 comes out of the 2028 contribution and there is no 2027 buffer. The rule moves $26,968 in Jan 2033; $27,600 was needed.
- **Shortfall before the backstop: $661** of unpaid bills (nominal).
- **Backstop ($10,000 from the cushion, in T-bills from Jan 2033): covers it.** Used $661. **Left over after the Jan 2042 bill: $9,798**, returned to the client.
- Backstop arithmetic: $10,000 start + $459 T-bill interest (0.5% a year in this scenario, earned from Jan 2033) - $661 used = $9,798 left.
- **Facility contribution, median growth: $78,580** ($68,491 in Jan 2027 dollars); cushion kept $26,193.
- **Facility contribution, P10 growth: $48,759** ($42,498 in Jan 2027 dollars); cushion kept $16,253.
- The bill shortfall equals the low-rate-only scenario: the rule sees the smaller reserve in 2033 and moves more, so its only error is assuming 1.0% reinvestment after that. The costlier ladder shows up as a smaller facility contribution instead.

## Sensitivity: expected stock return +/- 1 point, and Vanguard pessimistic

Vanguard pessimistic (VCMM 6/30/2026): US 5.2%, intl developed 5.5%, EM 3.0% geometric, converted to arithmetic with the base-case volatilities and blended 75/25 for international.

| case | us_mean | intl_mean | p_all_bills_paid | p_ladder_only | topup_median | facility_p10 | facility_p50 | facility_p90 | median_change_vs_base |
|---|---|---|---|---|---|---|---|---|---|
| base | 7.9% | 9.1% | 92.6% | 38.3% | $18,210 | $91,210 | $139,466 | $207,984 | +0.0% |
| -1 pt | 6.9% | 8.1% | 92.6% | 38.3% | $18,210 | $86,992 | $133,839 | $200,480 | -4.0% |
| +1 pt | 8.9% | 10.1% | 92.6% | 38.3% | $18,210 | $95,549 | $145,255 | $215,696 | +4.2% |
| Vanguard pessimistic | 6.5% | 6.4% | 92.6% | 38.3% | $18,210 | $83,105 | $128,634 | $193,515 | -7.8% |

## Assumptions

All 71 assumptions are sourced.

| Assumption | Value | Status | Source | Note |
|---|---|---|---|---|
| simulation.n_sims | 500000 | sourced | Team decision, Oct 13 2026: official run (run_simulation.py writes outputs/ with this many paths). |  |
| simulation.dashboard_n_sims | 10000 | sourced | Team decision, Oct 13 2026: dashboard default; 10,000 paths keeps the median within 1% of 50,000 (tests/test_validation.py). |  |
| simulation.report_n_sims | 500000 | sourced | Team decision, Oct 13 2026: final report numbers only (run_simulation.py --final), and only once no assumption is a placeholder. |  |
| simulation.seed | 20270101 | sourced | Model setting: fixed seed so every run is reproducible. |  |
| simulation.robustness_seeds | [1, 2, 3] | sourced | Team spec (rounds 6-7, Oct 14-16 2026): the official run is repeated on these seeds to show the bill result does not depend on the seed (outputs/end_result.md). |  |
| plan.ladder_purchase_date | 2027-01-01 | sourced | Plan spec (team brief): $300,000 buys the Treasury ladder in Jan 2027. |  |
| plan.ladder_budget | 300000 | sourced | Plan spec (team brief): Jan 2027 ladder funding. |  |
| plan.bill_amount | 50000 | sourced | Plan spec (team brief): ten $50,000 bills, Jan 1 of 2033 through 2042. |  |
| plan.growth_contribution_year | 2028 | sourced | Plan spec (team brief): growth bucket funded Jan 2028. |  |
| plan.growth_contribution | 150000 | sourced | Plan spec (team brief): $150,000 to the growth bucket in Jan 2028. |  |
| plan.valuation_year | 2033 | sourced | Plan spec (team brief): everything is valued at Jan 2033. |  |
| ladder.csv_path | ladder.csv | sourced | WInS fills, Oct 14-15 2026 (data/wins_fills_2026-10.csv; ladder.csv is rebuilt from it by build_ladder.py): quantities, clean fill prices, cash cost excluding commission, accrued WInS charged, and YTMs backed out of the fill prices (outputs/wins_fills.md). Round 6 sheet with estimates kept as data/ladder_round6_estimates.csv. Any row whose data_status contains ESTIMATE is flagged in summary.md and the dashboard. |  |
| ladder.pricing_date | 2026-09-30 | sourced | Fallback quote date for ladder.csv rows without a price_date (rows now carry their own dates: Sep 25-Oct 13, 2026). Used only to check the sheet's costs; the simulation prices the ladder on the Jan 2027 purchase date. |  |
| ladder.bond_payout_model | cashflows | sourced | Team decision (Oct 1 2026): Treasury rungs pay their actual coupons and principal for the ladder.csv quantity, reinvested at simulated T-bill rates. 'face' = plan-spec simplification where each rung pays exactly $50,000. |  |
| ladder.compounding_per_year | 2 | sourced | Market convention: Treasury yields are quoted semiannual bond-equivalent (reproduces ladder.csv costs, see tests). |  |
| ladder.day_count_basis | 365.25 | sourced | Model convention: year fraction = actual days / 365.25. |  |
| ladder.cost_check_slack | 25.0 | sourced | Model setting: $ allowed per rung beyond half a share/bond of rounding when checking ladder.csv costs (sheet rows are priced on different days). |  |
| ladder.share_tolerance | 2 | sourced | Team spec, Oct 13 2026: ETF share counts within 2 shares of the sizing rule (grows to $50,000 at maturity at the row's YTM) are accepted as given. |  |
| ladder.sizing_reinvest_rate | None | sourced | Team spec (round 3), Oct 13 2026: null = use ladder.csv bond quantities (official). A rate resizes the Treasury coupon-bond rungs only, to the smallest whole number of bonds whose coupons and principal reinvested at that rate reach $50,000 by the bill date; used for sizing scenarios. |  |
| ladder.ibonds_instrument_label | iBonds | sourced | ladder.csv: rungs whose security name contains this text get the iBonds payout error. |  |
| ladder.yield_shift_mean | 0.0 | sourced | Team policy: no directional view on rates between now and Jan 2027. | Team policy: no directional view on rates between now and Jan 2027. |
| ladder.yield_shift_sd | 0.005 | sourced | Our calculation: 1-yr std dev of GS10 changes ~1.0 pp (1986-2025, FRED GS10), scaled to ~3 months (Oct 2026 to Jan 2027). | Std dev of the one parallel yield move between now and the Jan 2027 purchase (0.5 pp). |
| ladder.ibonds_fee | 0.0007 | sourced | iShares iBonds Maturity Case Study: 5 matured Treasury iBonds (IBTA-IBTF) realized -0.1% to +1.9% vs net YTM. https://www.ishares.com/us/literature/presentation/ibonds-series-case-study-en-us.pdf | Fee drag: each iBonds payout is reduced by 0.07% per year from the Jan 2027 purchase to maturity. |
| ladder.ibonds_error_mean | 0.0 | sourced | iShares iBonds Maturity Case Study: 5 matured Treasury iBonds (IBTA-IBTF) realized -0.1% to +1.9% vs net YTM. https://www.ishares.com/us/literature/presentation/ibonds-series-case-study-en-us.pdf |  |
| ladder.ibonds_error_sd_per_year | 0.0015 | sourced | iShares iBonds Maturity Case Study: 5 matured Treasury iBonds (IBTA-IBTF) realized -0.1% to +1.9% vs net YTM. https://www.ishares.com/us/literature/presentation/ibonds-series-case-study-en-us.pdf | Payout error std dev = 0.15% x years from the Jan 2027 purchase to maturity, capped at ibonds_error_sd_cap. |
| ladder.ibonds_error_sd_cap | 0.015 | sourced | iShares iBonds Maturity Case Study: 5 matured Treasury iBonds (IBTA-IBTF) realized -0.1% to +1.9% vs net YTM. https://www.ishares.com/us/literature/presentation/ibonds-series-case-study-en-us.pdf | Cap on the payout error std dev (read as a cap on the std dev, not a truncation of the error). |
| tbills.mean | 0.032 | sourced | Fed SEP 9/16/2026 (fed funds longer run 3.2) https://federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm ; CBO Feb 2026 (3.1-3.2 long run) https://www.cbo.gov/system/files/2026-02/61882-Outlook-2026.pdf ; SPF Q1 2026 10-yr bill avg 3.00% | Mean T-bill rate for 2030 onward; earlier years use mean_by_year. |
| tbills.mean_by_year | {"2027": 0.04, "2028": 0.039, "2029": 0.036} | sourced | Fed SEP 9/16/2026 (fed funds median 4.1/3.9/3.6) https://federalreserve.gov/monetarypolicy/fomcprojtabl20260916.htm ; CBO Feb 2026 https://www.cbo.gov/system/files/2026-02/61882-Outlook-2026.pdf ; SPF Q1 2026 | Mean T-bill rate by year before 2030 (2027: 4.0%, 2028: 3.9%, 2029: 3.6%). |
| tbills.sd | 0.015 | sourced | Our calculation: std dev of Dec-to-Dec changes in FRED TB3MS, 1986-2025 https://fred.stlouisfed.org/data/TB3MS.txt | Std dev of year-to-year changes in the T-bill rate. The AR(1) shock size is set so the simulated changes match it: shock sd = sd x sqrt((1 + phi) / 2). |
| tbills.ar1_phi | 0.85 | sourced | Team spec (round 4b), Oct 13 2026: T-bill persistence, rate_t = mean_t + phi x (rate_(t-1) - mean_(t-1)) + shock. |  |
| tbills.ar1_start_deviation | 0.0 | sourced | Model convention: the AR(1) starts on the sourced mean path (deviation 0 before 2027). | Modeling choice to confirm; the floor at 0% is applied to the rate, not to the AR(1) deviation. |
| tbills.floor | 0.0 | sourced | Model convention: T-bill rates are floored at 0%. |  |
| growth.us_weight | 0.6 | sourced | Plan spec (team brief): 60% US stocks. |  |
| growth.intl_weight | 0.4 | sourced | Plan spec (team brief): 40% international stocks. |  |
| growth.us_mean | 0.0794 | sourced | J.P. Morgan 2026 LTCMA, USD matrix, data as of 9/30/2025. https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/ltcma-2026-us-matrix_usd.pdf | Arithmetic annual return (6.70% geometric). |
| growth.us_vol | 0.1647 | sourced | J.P. Morgan 2026 LTCMA |  |
| growth.intl_mean | 0.091 | sourced | J.P. Morgan 2026 LTCMA, 75% EAFE / 25% EM blend (our calculation; EAFE 8.90% arith, EM 9.74% arith) | Arithmetic annual return (~7.5% geometric). |
| growth.intl_vol | 0.179 | sourced | J.P. Morgan 2026 LTCMA, same blend (EAFE 17.63%, EM 20.93%) |  |
| growth.correlation | 0.85 | sourced | J.P. Morgan 2026 LTCMA (US LC vs EAFE 0.87, vs EM 0.73, EAFE vs EM 0.86) |  |
| growth.rebalance_annually | True | sourced | Team policy: yearly rebalance, simple to follow and explain. |  |
| growth_mix.mix | None | sourced | Model setting: null = the official mix from growth.us_weight / growth.intl_weight (60% US / 40% international). Growth-bucket scenarios set a mix over us, intl, small_cap, us_2x and tbills. |  |
| growth_mix.small_cap_mean | 0.0889 | sourced | J.P. Morgan 2026 LTCMA, USD matrix, data as of 9/30/2025. https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/ltcma-2026-us-matrix_usd.pdf U.S. Small Cap row (small cap, value premium not modeled). | Arithmetic annual return (6.90% geometric). Proxy for AVUV: small cap, value premium not modeled. |
| growth_mix.small_cap_vol | 0.211 | sourced | J.P. Morgan 2026 LTCMA, USD matrix, data as of 9/30/2025. https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/ltcma-2026-us-matrix_usd.pdf U.S. Small Cap row. |  |
| growth_mix.small_cap_corr_us | 0.9 | sourced | J.P. Morgan 2026 LTCMA, USD matrix, data as of 9/30/2025. https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/ltcma-2026-us-matrix_usd.pdf U.S. Small Cap vs U.S. Large Cap. |  |
| growth_mix.small_cap_corr_intl | 0.77 | sourced | J.P. Morgan 2026 LTCMA, USD matrix, data as of 9/30/2025. https://am.jpmorgan.com/content/dam/jpm-am-aem/global/en/insights/ltcma-2026-us-matrix_usd.pdf Our calculation: U.S. Small Cap vs the 75% EAFE / 25% EM blend (SC vs EAFE 0.78, SC vs EM 0.66, EAFE vs EM 0.86; vols 17.63 / 20.93). |  |
| growth_mix.us_2x_multiple | 2 | sourced | Team spec (round 5, Oct 13 2026): 2x leveraged US large cap (proxy for SSO). | approximation; daily reset not modeled, real decay likely worse. |
| growth_mix.us_2x_fee | 0.0089 | sourced | Team spec (round 5, Oct 13 2026): SSO fee 0.89% a year. |  |
| growth_mix.scenarios | 10 items (see config.yaml) | sourced | Team spec (round 5, Oct 13 2026): growth-bucket scenarios. VTI = U.S. Large Cap row, VXUS = 75/25 EAFE/EM blend. G5 replaces the planned QQQ case (JPM has no U.S. Large Cap Growth row). G2-V and G3-V added Oct 13 2026: G2 and G3 under the Vanguard pessimistic returns (no G4-V: Vanguard gives no small-cap figure, and G4 already trails G1 at P10). |  |
| glide_path.enabled | True | sourced | Plan spec (team brief): de-risk the growth bucket before 2033. |  |
| glide_path.steps | 2 items (see config.yaml) | sourced | Plan spec (team brief): start of 2031 move 1/3 of stocks to T-bills; start of 2032 move 1/2 of remaining stocks. |  |
| waterfall.topup_rule | rate_rule | sourced | Team decision, Oct 1 2026: rate rule tested against fixed rule and low-rate stress tests; backstop covers combined stress case |  |
| waterfall.rate_rule_rate | 0.01 | sourced | Team policy (Oct 13 2026, option A2 in outputs/hardening_options.md): plan as if cash earns 1% after 2033, below all forecasts of 3.0-3.2%. | Team policy: plan as if cash earns 1% after 2033, below all forecasts of 3.0-3.2%. Locked Oct 16 2026 (round 8): A2 kept over A4; reason in summary.md. |
| waterfall.fixed_rule_amount | 13400 | sourced | Team spec: fixed_rule always moves this amount, about the P99 perfect-foresight top-up (Oct 1 2026 run). |  |
| waterfall.ibonds_margin_sd | 1.0 | sourced | Team spec (round 4b), Oct 13 2026: the rate rule funds each remaining iBonds bill at target + 1 std dev of its payout error (sourced error size: ladder.ibonds_error_sd_per_year, capped at ibonds_error_sd_cap). |  |
| waterfall.backstop_amount | 10000 | sourced | Team decision, Oct 1 2026: rate rule tested against fixed rule and low-rate stress tests; backstop covers combined stress case | Locked Oct 16 2026 (round 8): A2 ($10,000 with the 1.0% rule) kept over A4 ($12,500 with a 1.5% rule); reason in summary.md. |
| facility.give_pct | 0.75 | sourced | Plan spec (team brief): facility contribution = 75% of the Jan 2033 growth value. |  |
| inflation.rate | 0.023 | sourced | SPF Q3 2026 10-yr CPI 2.30%; CBO CPI-U 2.3%; 10-yr breakeven 2.33% (10/9/2026) | Inflation for 2028 onward; earlier years use rate_by_year. |
| inflation.rate_by_year | {"2027": 0.024} | sourced | SPF Q3 2026 10-yr CPI 2.30%; CBO CPI-U 2.3%; 10-yr breakeven 2.33% (10/9/2026) | Inflation by year before 2028 (2027: 2.4%). |
| inflation.base_year | 2027 | sourced | Model convention: inflation-adjusted figures are in Jan 2027 dollars. |  |
| reporting.percentiles | [5, 10, 25, 50, 75, 90, 95] | sourced | Plan spec (team brief): percentile table. |  |
| reporting.cosponsor_ranges | [[25, 75], [10, 90], [10, 50]] | sourced | Plan spec (team brief): candidate co-sponsor ranges [P25,P75], [P10,P90], [P10,P50]. |  |
| reporting.range_rounding | 1000 | sourced | Team policy (Oct 16 2026): range endpoints rounded down to the nearest $1,000 at both ends, so the low end never exceeds P10 and the top never exceeds the median. Replaces inward rounding (Oct 13), which could put the low end above P10. | Team policy: rounded down at both ends so we never overstate. |
| reporting.recommended_range | [10, 50] | sourced | Team policy. | Example co-sponsor range = P10 to median. |
| sensitivity.return_shift | 0.01 | sourced | Plan spec (team brief): expected stock return +/- 1 point (applied to US and international together). |  |
| sensitivity.vanguard_pessimistic | {"us_geo": 0.052, "intl_developed_geo": 0.055, "em_geo": 0.03, "developed_weight": 0.75, "em_weight": 0.25, "developed_vol": 0.1763, "em_vol": 0.2093} | sourced | Vanguard VCMM, 6/30/2026 (US 5.2% geo, intl developed 5.5% geo, EM 3.0% geo); same volatilities as the base case (J.P. Morgan 2026 LTCMA: EAFE 17.63%, EM 20.93%), same 75/25 blend. | Sensitivity case. Geometric returns are converted to arithmetic with each asset's volatility, then blended 75/25 for international. |
| stress_tests.scenarios | 13 items (see config.yaml) | sourced | Plan spec (team brief): fixed-path stress scenarios; low_rates_2010s and combined_low_rates added at team request (Oct 1 2026). Inputs a scenario does not set use their mean values (T-bill mean, yield-shift mean, iBonds error mean). |  |
| scenarios.sizing_rates | {"B": 0.04, "C": 0.03, "D": 0.02, "E": 0.0} | sourced | Team spec (round 3), Oct 13 2026: sizing-rate scenarios for Treasury rungs 6-10 (A = current: each bond's own YTM). |  |
| scenarios.active | ["A", "F"] | sourced | Team decision, Oct 13 2026 (round 4): sizing scenarios B-E rejected; run A (official ladder) and F (STRIPS). |  |
| scenarios.budget | 300000 | sourced | Team spec (round 3), Oct 13 2026: ladder budget for the scenario budget check. |  |
| scenarios.cash_reserve | 500 | sourced | Team spec (round 3), Oct 13 2026: keep $500 in cash; not counted in the SGOV buffer. |  |
| scenarios.fees | 200 | sourced | Team spec (round 3), Oct 13 2026: purchase fees deducted before the SGOV buffer. |  |

## Method notes

- All cash flows occur Jan 1. Each year's T-bill rate and stock return apply Jan 1 to Jan 1.
- Ladder cost = present value on Jan 1 2027 of each rung's cash flows at (sheet YTM + one parallel shift), 2x/year compounding, actual/365.25 years. Repricing on the purchase date (not the sheet date) adds about 3 months of accretion at unchanged yields.
- ETF rungs (and bond rungs in the face model) pay on the bill date; interest between maturity and the bill is ignored (conservative). In the cashflows model, bond coupons and principal earn the path's T-bill rate until the bill date.
- A bill counts as paid only if it is paid in full. The top-up rule uses only information available on the valuation date; the perfect-foresight top-up (exact amount, using the path's future T-bill rates) is reported for reference only.
- Stock returns are correlated lognormal with the configured arithmetic mean and volatility; stocks are rebalanced to target weights each January.
- Stress tests use one fixed path; inputs a scenario does not set use their mean values.
- Sensitivity runs reuse the same random shocks (common random numbers).
