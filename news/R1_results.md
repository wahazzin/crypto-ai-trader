# R1 — Crypto news vs returns: results

Rules: `research/NEWS_PREREG.md` (committed before data). 29764 headlines, 8779 coin-days with news, 25 coins.

## DESIGN (→2024-06-30)

- **T1 avg sentiment → next 1d excess return:** pooled IC -0.0009 (n=4464 coin-days), NW t of daily sentiment×return = +0.40 (913 days)
- **T2 cross-sectional, next 1d:** mean daily IC -0.0201, NW t -1.06 (720 days with ≥3 coins)
- **T1 avg sentiment → next 3d excess return:** pooled IC -0.0124 (n=4464 coin-days), NW t of daily sentiment×return = -0.47 (913 days)
- **T2 cross-sectional, next 3d:** mean daily IC -0.0305, NW t -1.61 (720 days with ≥3 coins)
- **T3 attention shocks** (≥3× coin's median news count): 113 shock-days, 75 after declustering (≥10 days apart per coin)
  - next 1d excess, all: mean -0.47% (t -1.57, n=110)
  - next 1d excess, declustered: mean -0.55% (t -1.33, n=73)
    - by sentiment tercile: neg -0.15% (n=24), mid -1.39% (n=24), pos -0.13% (n=25)
  - next 3d excess, all: mean +0.04% (t +0.06, n=110)
  - next 3d excess, declustered: mean +0.44% (t +0.48, n=73)
    - by sentiment tercile: neg -0.62% (n=24), mid -0.23% (n=24), pos +2.10% (n=25)
  - next 7d excess, all: mean -0.71% (t -0.85, n=110)
  - next 7d excess, declustered: mean -0.36% (t -0.31, n=73)
    - by sentiment tercile: neg -1.75% (n=24), mid -0.71% (n=24), pos +1.31% (n=25)

## HOLDOUT (2024-07-01→2026-09-30)

- **T1 avg sentiment → next 1d excess return:** pooled IC -0.0085 (n=4015 coin-days), NW t of daily sentiment×return = -0.53 (787 days)
- **T2 cross-sectional, next 1d:** mean daily IC -0.0078, NW t -0.37 (648 days with ≥3 coins)
- **T1 avg sentiment → next 3d excess return:** pooled IC +0.0183 (n=4015 coin-days), NW t of daily sentiment×return = +0.94 (787 days)
- **T2 cross-sectional, next 3d:** mean daily IC +0.0009, NW t +0.04 (648 days with ≥3 coins)
- **T3 attention shocks** (≥3× coin's median news count): 68 shock-days, 46 after declustering (≥10 days apart per coin)
  - next 1d excess, all: mean +1.11% (t +2.00, n=68)
  - next 1d excess, declustered: mean +0.82% (t +1.33, n=46)
    - by sentiment tercile: neg +0.45% (n=15), mid +1.23% (n=15), pos +0.79% (n=16)
  - next 3d excess, all: mean -0.34% (t -0.41, n=68)
  - next 3d excess, declustered: mean -0.70% (t -0.73, n=46)
    - by sentiment tercile: neg -1.76% (n=15), mid +0.22% (n=15), pos -0.56% (n=16)
  - next 7d excess, all: mean +0.11% (t +0.09, n=68)
  - next 7d excess, declustered: mean -0.49% (t -0.39, n=46)
    - by sentiment tercile: neg -1.04% (n=15), mid -2.40% (n=15), pos +1.83% (n=16)

## Verdict (pre-registered rule: |t|≥2 in design AND same-sign |t|≥2 in holdout AND beats ~1% round trip)

- T1_1d: design t +0.40, holdout t -0.53 → **NO EVIDENCE**
- T2_1d: design t -1.06, holdout t -0.37 → **NO EVIDENCE**
- T1_3d: design t -0.47, holdout t +0.94 → **NO EVIDENCE**
- T2_3d: design t -1.61, holdout t +0.04 → **NO EVIDENCE**
- T3_1d: design t -1.33, holdout t +1.33 → **NO EVIDENCE**
- T3_3d: design t +0.48, holdout t -0.73 → **NO EVIDENCE**
- T3_7d: design t -0.31, holdout t -0.39 → **NO EVIDENCE**

**Overall: NO EVIDENCE → no news arm.**
