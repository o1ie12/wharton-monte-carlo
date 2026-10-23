# End result

**Laura's $450,000 pays all 10 of her $50,000 bills in every one of 500,000 simulated futures (checked on 4 separate runs) and gives the facility about $139,000 in 2033; even in the worst case we tested, the bills are still paid and the facility gets $48,759.**

## Money in

- $300,000 in 2027 (bond ladder and cash buffer)
- $150,000 in 2028 (growth bucket)
- Total $450,000

## Money out

Typical = median future; bad case = 1 in 10 futures does worse. 500,000 futures, nominal dollars (not adjusted for inflation or discounted).

| | Typical | Bad case (1 in 10) | |
|---|---|---|---|
| Bills paid, 2033–2042 (of $500,000) | $500,000 | $500,000 | all bills paid on every seed: seed 20270101: 100.00% (0 fail); seed 1: 100.00% (0 fail); seed 2: 100.00% (0 fail); seed 3: 100.00% (0 fail) |
| Facility contribution, Jan 2033 | $139,466 | $91,210 | example co-sponsor range $91,000 to $139,000 |
| Laura's cushion, Jan 2033 (not added to the total) | $46,489 | $30,403 | includes the $10,000 backstop, which is counted once below: what it pays is in bills paid, what is left is in the amount returned after the last bill |
| Laura's free cushion after the $10,000 backstop | $36,489 | $20,403 |  |
| Returned to Laura after 2042 | $33,477 | $12,270 | unused reserve (typical $20,173) + unused backstop with its T-bill interest since 2033 (typical $13,285) |
| **Total value delivered** | $712,910 | $641,286 | see the formula below |

**Total value delivered = bills paid + facility contribution + Laura's free cushion + returned to Laura after the last bill**, added up future by future (so the typical total is a real future's total, not a sum of typical rows). Each dollar is counted once: the backstop is left out of the free cushion, and its unused part, with interest, is in the amount returned.

## Worst stress case tested

Treasury yields 2 pts lower at the Jan 2027 purchase AND T-bills at 0.5% every year 2027-2042; bad-case (1 in 10) stock returns: bills paid in full (the backstop covers $661, with $9,798 left); the facility receives $48,759.

<!-- Generated 2026-10-16 by run_simulation.py from outputs/metrics.json: seed 20270101, inputs sha256 a9d68603fb04a314. -->
