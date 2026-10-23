# Hardening scenario A against persistent low T-bill rates

500,000 paths per option, same seed, official settings otherwise (AR(1) T-bills, iBonds margin). Laura's cushion = growth bucket after the top-up x (1 - give_pct); the backstop is set aside from it and returned after the last bill. Official config.yaml is unchanged.

| Option | Rule rate / backstop | All paid with / without backstop | Paths failing with backstop | Max shortfall with / without backstop | Top-up median / P90 | Median facility (vs A0) | Co-sponsor range | Laura's median cushion (free after backstop) | Worst stress shortfall / backstop left |
|---|---|---|---|---|---|---|---|---|---|
| A0: 2% rule, $10k backstop (official until Oct 13) | 2.0% / $10,000 | 99.20% / 80.50% | 3,991 | $4,369 / $14,369 | $12,374 / $19,467 | $143,110 (+$0) | $95,000 - $143,000 | $47,703 ($37,703) | $6,759 / $3,694 |
| A1: rule assumes 1.5% | 1.5% / $10,000 | 100.00% / 86.72% | 22 | $1,515 / $11,515 | $15,227 / $22,321 | $141,367 (-$1,743) | $93,000 - $141,000 | $47,122 ($37,122) | $3,781 / $6,678 |
| A2: rule assumes 1.0% (official) | 1.0% / $10,000 | 100.00% / 92.59% | 0 | $0 / $8,532 | $18,210 / $25,304 | $139,466 (-$3,644) | $91,000 - $139,000 | $46,489 ($36,489) | $661 / $9,798 |
| A3: backstop $12,500 (2% rule) | 2.0% / $12,500 | 99.99% / 80.50% | 61 | $1,869 / $14,369 | $12,374 / $19,467 | $143,110 (+$0) | $95,000 - $143,000 | $47,703 ($35,203) | $6,759 / $6,308 |
| A4: rule assumes 1.5% + backstop $12,500 | 1.5% / $12,500 | 100.00% / 86.72% | 0 | $0 / $11,515 | $15,227 / $22,321 | $141,367 (-$1,743) | $93,000 - $141,000 | $47,122 ($34,622) | $3,781 / $9,293 |

With the backstop, 2 of 5 options pay every bill on all 500,000 paths: A2 (rule assumes 1.0% (official)), A4 (rule assumes 1.5% + backstop $12,500). Among them, median facility contribution and Laura's median free cushion after the backstop: A2 $139,466 and $36,489; A4 $141,367 and $34,622. Paths failing with the backstop for the others: A0 3,991, A1 22, A3 61.

## A2 vs A4 on 4 seeds

500,000 paths per seed. Spare room = backstop minus the largest draw on any path. Free cushion = Laura's cushion minus the backstop held until the last bill.

| Option | Seed | Paths failing with backstop | Largest backstop draw | Spare backstop room | Median facility | Laura's median free cushion |
|---|---|---|---|---|---|---|
| A2: $10,000 backstop | 20270101 | 0 | $8,532 | $1,468 (14.7%) | $139,466 | $36,489 |
| A2: $10,000 backstop | 1 | 0 | $8,392 | $1,608 (16.1%) | $139,448 | $36,483 |
| A2: $10,000 backstop | 2 | 0 | $8,412 | $1,588 (15.9%) | $139,410 | $36,470 |
| A2: $10,000 backstop | 3 | 0 | $8,741 | $1,259 (12.6%) | $139,410 | $36,470 |
| A4: $12,500 backstop | 20270101 | 0 | $11,515 | $985 (7.9%) | $141,367 | $34,622 |
| A4: $12,500 backstop | 1 | 0 | $11,375 | $1,125 (9.0%) | $141,381 | $34,627 |
| A4: $12,500 backstop | 2 | 0 | $11,396 | $1,104 (8.8%) | $141,339 | $34,613 |
| A4: $12,500 backstop | 3 | 0 | $11,724 | $776 (6.2%) | $141,335 | $34,612 |

- A2: largest draw on any seed $8,741 (seed 3), leaving $1,259 (12.6%) of the $10,000 backstop; paths failing with the backstop on all seeds: 0.
- A4: largest draw on any seed $11,724 (seed 3), leaving $776 (6.2%) of the $12,500 backstop; paths failing with the backstop on all seeds: 0.
