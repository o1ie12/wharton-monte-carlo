# Reinvestment diagnosis: Treasury rungs (bills 6-10)

100,000 paths, official settings. Ladder alone = ladder + buffer with no top-up and no backstop. "P10 outcome" = the 90th-percentile shortfall (bad tail).

| Bill | Bond | Bonds held | Face at maturity | Coupons from Jan 2027 | Reinvestment interest needed for $50k | YTM | Payout if reinvested at YTM | Median simulated T-bill rate over life | Rung payout, median | Rung payout, P10 | Share of paths short (ladder alone) | Shortfall, median (ladder alone) | Shortfall, P10 outcome (ladder alone) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 6 | 4.750% Feb 15 2037 | 30 | $30,000 | $14,962 | $5,038 | 5.18% | $51,739 | 3.38% | $49,015 | $46,058 | 27.49% | $0 | $2,616 |
| 7 | 4.500% May 15 2038 | 29 | $29,000 | $15,008 | $5,992 | 5.23% | $50,776 | 3.37% | $47,963 | $45,115 | 36.21% | $0 | $4,182 |
| 8 | 4.375% Nov 15 2039 | 28 | $28,000 | $15,925 | $6,075 | 5.38% | $50,872 | 3.36% | $47,797 | $45,044 | 42.59% | $0 | $4,572 |
| 9 | 4.250% Nov 15 2040 | 27 | $27,000 | $16,065 | $6,935 | 5.43% | $50,848 | 3.35% | $47,305 | $44,309 | 48.63% | $0 | $5,461 |
| 10 | 3.125% Nov 15 2041 | 30 | $30,000 | $14,062 | $5,938 | 5.53% | $51,715 | 3.34% | $48,099 | $45,275 | 50.55% | $134 | $4,624 |

| Case | Ladder alone pays all bills | Bills 6-10 short (% of paths) | Any of bills 1-5 short |
|---|---|---|---|
| official | 38.4% | 27.5% / 36.2% / 42.6% / 48.6% / 50.5% | 38.6% |
| bonds pay exactly $50k | 61.8% | 0.0% / 0.0% / 0.0% / 0.0% / 0.0% | 38.2% |
| T-bills earn ~bond YTM (5.35%) | 55.1% | 9.8% / 14.0% / 16.7% / 19.1% / 18.5% | 38.0% |

Reinvestment drives the bill 6-10 failures: when the bonds pay exactly $50k they are never short, and when T-bills earn about the bonds' YTM the failure rates collapse. The small remainder (bills 8 and 10 fall short even at their YTM) is sizing timing: ladder.csv sized them from the quote date, counting the Nov 2026 coupon, but the ladder is bought Jan 1 2027.

Resizing bills 6-10 cannot lift "ladder alone pays all bills" above about 61%: an iBonds bill (1-5) is already short on 38.6% of paths (placeholder iBonds payout error plus a thin buffer).
