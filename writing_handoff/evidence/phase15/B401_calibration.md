# Frozen B401 Dev calibration and selective-prediction evidence

Status: `PASS_COMPARATOR_DEV_CALIBRATION_COMPLETE`
Seeds: `[17, 28, 43]`
Rows per seed: `11201`
Cohort: frozen Dev only; Internal-test/protected outcomes were not opened.

## Calibration summary

| State | NLL | Brier | ECE-15 | Adaptive ECE | Classwise ECE | AURC | E-AURC |
|---|---:|---:|---:|---:|---:|---:|---:|
| Uncalibrated | 1.132242 ± 0.006463 | 0.593051 ± 0.003811 | 0.069479 ± 0.020876 | 0.069596 ± 0.020528 | 0.061288 ± 0.001430 | 0.283571 ± 0.005784 | 0.151660 ± 0.004181 |
| 5-fold cross-fitted temperature | 1.125360 ± 0.013357 | 0.587090 ± 0.006608 | 0.038903 ± 0.009697 | 0.041662 ± 0.010079 | 0.056326 ± 0.005596 | 0.284382 ± 0.005212 | 0.152471 ± 0.003613 |

## Interpretation guardrails

- Temperature is fitted out-of-fold at patient level (five folds); each patient is scored only by a temperature fitted without that patient.
- MSP and normalized entropy are reported for every system. PRIOR-derived scores are reported only when the receipt contains the complete frozen intervention set.
- A combined uncertainty score is intentionally absent because no combination was preregistered before inspecting outcomes.
- These are frozen Dev characterization results, not an Internal-test claim.
