# Client plan Monte Carlo

Monte Carlo model of the client's Jan 2027 Treasury ladder (10 bills of $50k, 2033–2042)
and Jan 2028 growth bucket (facility contribution valued Jan 2033).

```
config.yaml          every assumption: value, source (citation/URL), status (sourced | placeholder)
ladder.csv           team allocation sheet (rungs, YTMs, prices, quantities, price_date, data_status)
mcsim/               simulation package (config, model, analysis, plots)
run_simulation.py    writes outputs/: headline.md, metrics.json, summary.md, stress_tests.csv,
                     sensitivity.csv and charts, all from one run
app.py               Streamlit dashboard (imports mcsim; no model logic of its own)
run_scenarios.py     reinvestment-risk sizing scenarios A-F -> outputs/sizing_scenarios.md (+ .csv),
                     outputs/reinvestment_diagnosis.md; never modifies ladder.csv
run_growth.py        growth-bucket mix scenarios G1-G8 -> outputs/growth_scenarios.md (+ .csv, .png)
run_hardening.py     options to harden scenario A against low T-bill rates -> outputs/hardening_options.md
data/                Treasury par yield curve (Oct 9 2026, home.treasury.gov) used to price STRIPS;
                     J.P. Morgan 2026 LTCMA USD matrix (source for stock assumptions)
check_deploy.py      deploy gate: fails while placeholders, estimate rows or stale outputs remain
DEPLOY.md            Streamlit Community Cloud steps (do not deploy until check_deploy.py passes)
tests/               validation and dashboard tests
```

## Run

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python run_simulation.py            # official run: simulation.n_sims (100,000) paths
.venv/bin/python run_simulation.py --final    # final report: report_n_sims (500,000); needs zero placeholders
.venv/bin/streamlit run app.py                # dashboard: dashboard_n_sims (10,000) paths
```

`outputs/headline.md` holds the five numbers for the IPS and presentation. They are
rendered from `outputs/metrics.json`, written by the same run as everything else in
`outputs/`; a test checks them against the other outputs and against the current inputs.

## Deploy (Streamlit Community Cloud)

See `DEPLOY.md`. Not before `check_deploy.py` passes (zero placeholder assumptions).
`requirements.txt` pins the tested versions; they need Python 3.12 or newer.

## Model choices worth knowing

- **Ladder pricing date.** Each ladder.csv row is quoted on its own `price_date` (Oct 9–13
  2026). The simulation reprices every rung on the Jan 1 2027 purchase date at (sheet YTM +
  random shift), which at unchanged yields costs a little more than the sheet (accretion to
  Jan 2027). The ladder-cost test checks the formula against each row on its own date.
- **T-bill rates** follow an AR(1) around the sourced mean path (4.0/3.9/3.6%, then 3.2%):
  rate_t = mean_t + 0.85 x (rate_(t-1) - mean_(t-1)) + shock, with the shock sized so year-to-year
  changes have a 1.5 pp std dev (FRED TB3MS). Rates are floored at 0%; the AR(1) starts on the
  mean path.
- **Top-up rule iBonds margin** (`waterfall.ibonds_margin_sd`, 1.0): the 2033 rate rule assumes
  each iBonds rung not yet matured pays its target less fee less 1 std dev of its payout error.
- **Growth-mix scenarios** (`growth_mix.*`, official mix = null = 60/40). Assets: us (J.P. Morgan
  U.S. Large Cap), intl (75/25 EAFE/EM), small_cap (U.S. Small Cap; value premium not modeled),
  us_2x (2x U.S. Large Cap built monthly: 2 x month - T-bill - 0.89%/yr; daily reset not modeled)
  and tbills. The model steps yearly; for drawdowns and the 2x fund each year is split into 12
  months by a Brownian bridge that compounds back to exactly the annual return.
- **Sizing scenarios** (`ladder.sizing_reinvest_rate`, official: empty = ladder.csv quantities).
  A rate resizes only the Treasury coupon-bond rungs to the smallest whole number of bonds whose
  coupons and principal, reinvested at that rate from the Jan 2027 purchase to the Jan 1 bill,
  reach $50,000. ladder.csv also accepts `type: STRIPS` (zero-coupon, pays face at maturity).
- **iBonds share counts** don't change the simulated payout: each iBonds rung is modelled as
  paying its $50,000 target × (1 + payout error). A test checks every share count is within
  `ladder.share_tolerance` (2) shares of the sizing rule, so the target is realistic.
- **Treasury rung payouts** (`ladder.bond_payout_model`). Official: `cashflows` — bonds pay
  their real coupons and principal for the sheet quantity, reinvested at simulated T-bill
  rates. `face` is the plan-spec simplification (each rung pays exactly $50k).
- **Bills-first waterfall.** Bills are funded ladder payouts → T-bill buffer → growth bucket.
  On Jan 1 2033 the growth bucket tops up the reserve with a rule that uses only what is
  known that day (`waterfall.topup_rule`):
  - `rate_rule` (default, pending client choice): move the shortfall assuming all
    reinvestment from 2033 earns `rate_rule_rate` (2.0%) and unmatured iBonds rungs pay
    their expected amount.
  - `fixed_rule`: always move `fixed_rule_amount` ($13,400).
  Money moved but not needed stays in T-bills and is released to the client's cushion after
  the 2042 bill. The facility contribution is give_pct × the growth bucket after the top-up.
  `foresight` (the exact amount, which requires knowing future T-bill rates) is computed on
  every path as a reference line only.
- **Backstop** (`waterfall.backstop_amount`, $10,000): set aside from the client's cushion
  (growth bucket × (1 − give_pct)) in Jan 2033, held in T-bills, used only for bills the
  reserve leaves unpaid; the rest is returned after the 2042 bill. It does not reduce the
  facility contribution.
- **ladder.csv** holds quotes dated Sep 25–Oct 13, 2026 (`price_date` column); bills 3 and
  6–10 were replaced with verified data on Oct 13. Any row whose data_status contains
  "ESTIMATE" is flagged in summary.md and on the dashboard.
- Stock returns are correlated lognormal with arithmetic mean/vol from config, rebalanced
  to 60/40 each January. Random shocks are drawn independently of the assumptions, so
  sensitivity runs and dashboard comparisons use the same shocks.
