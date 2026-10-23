# Treasury rung sizing scenarios (reinvestment risk)

100,000 paths per scenario, same seed. Scenarios never modify ladder.csv: A is the official sheet, B-E are config overrides, F is a separate scenario sheet. Costs use current clean price + accrued; SGOV buffer = $300,000 budget - ladder cost - $500 cash - $200 fees. Ladder alone = no top-up, no backstop.

| Scenario | Bonds, rungs 6-10 | Extra cost vs A | Ladder cost | SGOV buffer | Fits $300k? | Ladder alone pays all | Coverage median / P10 / worst | Top-up median / P90 | All paid with / without backstop | Median facility | Co-sponsor range | Worst stress shortfall / backstop left | Vanguard pessimistic: median / P10 facility | Vanguard pessimistic: co-sponsor range | Vanguard pessimistic: all paid with / without backstop |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A (official): each bond's own YTM, sized from Jan 2027 | 30/29/28/27/30 | - | $294,375 | $4,925 | yes | 38.4% | 99.49% / 95.76% / 93.10% | $18,220 / $25,320 | 100.00% / 92.77% | $139,362 | $90,000 - $139,000 | $661 / $9,798 | $128,524 / $82,602 | $82,000 - $128,000 | 100.00% / 92.77% |
| F: STRIPS for rungs 6-10 (ESTIMATE, STRIPS availability in WInS unconfirmed.) | STRIPS 50k face each † | -$5,944 † | $288,432 † | $10,868 † | yes † | 70.0% † | 100.00% / 99.59% / 98.59% † | $0 / $3,991 † | 100.00% / 99.37% † | $150,524 † | $103,000 - $150,000 † | $0 / $10,459 † | $139,655 / $95,087 † | $95,000 - $139,000 † | 100.00% / 99.37% † |

† ESTIMATE, STRIPS availability in WInS unconfirmed. STRIPS priced from the Treasury par yield curve of 2026-10-09 (bootstrapped zero rates); rungs 6-10 swapped for STRIPS maturing Nov 15 of the year before each bill, $50,000 face each.

No scenario reaches 90% for "ladder alone pays all bills" (best: F (STRIPS, estimate) at 70.0%), because an iBonds bill (1-5) is already short on 38.6% of paths, which no change to rungs 6-10 can fix. The best option within budget, F (STRIPS, estimate), costs $5,944 less than A, takes the SGOV buffer from $4,925 to $10,868, moves ladder-alone success from 38.4% to 70.0%, and raises the median facility contribution by $11,162. No scenario is both over budget and dominated by a cheaper one.
