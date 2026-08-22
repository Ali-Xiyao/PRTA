# Frozen TILA8 Dev calibration and selective-prediction evidence

Status: `PASS_COMPARATOR_DEV_CALIBRATION_COMPLETE`
Seeds: `[17, 28, 43]`
Rows per seed: `11201`
Cohort: frozen Dev only; Internal-test/protected outcomes were not opened.

## Calibration summary

| State | NLL | Brier | ECE-15 | Adaptive ECE | Classwise ECE | AURC | E-AURC |
|---|---:|---:|---:|---:|---:|---:|---:|
| Uncalibrated | 0.961183 ± 0.006920 | 0.514942 ± 0.003604 | 0.076238 ± 0.008505 | 0.076237 ± 0.008507 | 0.051665 ± 0.003919 | 0.233481 ± 0.004479 | 0.152071 ± 0.002710 |
| 5-fold cross-fitted temperature | 0.959910 ± 0.007409 | 0.511058 ± 0.004374 | 0.058300 ± 0.002595 | 0.058671 ± 0.002522 | 0.048162 ± 0.005325 | 0.233104 ± 0.004698 | 0.151694 ± 0.002916 |

## Interpretation guardrails

- Temperature is fitted out-of-fold at patient level (five folds); each patient is scored only by a temperature fitted without that patient.
- MSP and normalized entropy are reported for every system. PRIOR-derived scores are reported only when the receipt contains the complete frozen intervention set.
- A combined uncertainty score is intentionally absent because no combination was preregistered before inspecting outcomes.
- These are frozen Dev characterization results, not an Internal-test claim.
