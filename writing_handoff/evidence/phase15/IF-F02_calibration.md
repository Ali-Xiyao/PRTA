# Frozen IF-F02 Dev calibration and selective-prediction evidence

Status: `PASS_COMPARATOR_DEV_CALIBRATION_COMPLETE`
Seeds: `[17, 28, 43]`
Rows per seed: `11201`
Cohort: frozen Dev only; Internal-test/protected outcomes were not opened.

## Calibration summary

| State | NLL | Brier | ECE-15 | Adaptive ECE | Classwise ECE | AURC | E-AURC |
|---|---:|---:|---:|---:|---:|---:|---:|
| Uncalibrated | 0.924108 ± 0.002018 | 0.491240 ± 0.000749 | 0.042636 ± 0.008474 | 0.042013 ± 0.009331 | 0.043731 ± 0.001232 | 0.214266 ± 0.000191 | 0.139184 ± 0.000952 |
| 5-fold cross-fitted temperature | 0.923600 ± 0.001147 | 0.493388 ± 0.000898 | 0.055309 ± 0.002109 | 0.054640 ± 0.002821 | 0.045589 ± 0.000648 | 0.214718 ± 0.000038 | 0.139636 ± 0.000837 |

## Interpretation guardrails

- Temperature is fitted out-of-fold at patient level (five folds); each patient is scored only by a temperature fitted without that patient.
- MSP and normalized entropy are reported for every system. PRIOR-derived scores are reported only when the receipt contains the complete frozen intervention set.
- A combined uncertainty score is intentionally absent because no combination was preregistered before inspecting outcomes.
- These are frozen Dev characterization results, not an Internal-test claim.
