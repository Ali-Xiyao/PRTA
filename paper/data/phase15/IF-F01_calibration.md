# Frozen IF-F01 Dev calibration and selective-prediction evidence

Status: `PASS_COMPARATOR_DEV_CALIBRATION_COMPLETE`
Seeds: `[17, 28, 43]`
Rows per seed: `11201`
Cohort: frozen Dev only; Internal-test/protected outcomes were not opened.

## Calibration summary

| State | NLL | Brier | ECE-15 | Adaptive ECE | Classwise ECE | AURC | E-AURC |
|---|---:|---:|---:|---:|---:|---:|---:|
| Uncalibrated | 0.925081 ± 0.004819 | 0.496799 ± 0.001658 | 0.060154 ± 0.002853 | 0.060154 ± 0.002853 | 0.046303 ± 0.000193 | 0.215670 ± 0.001931 | 0.139118 ± 0.000548 |
| 5-fold cross-fitted temperature | 0.924403 ± 0.005363 | 0.494397 ± 0.001996 | 0.045506 ± 0.003720 | 0.045506 ± 0.003720 | 0.043909 ± 0.001023 | 0.215402 ± 0.001908 | 0.138851 ± 0.000590 |

## Interpretation guardrails

- Temperature is fitted out-of-fold at patient level (five folds); each patient is scored only by a temperature fitted without that patient.
- MSP and normalized entropy are reported for every system. PRIOR-derived scores are reported only when the receipt contains the complete frozen intervention set.
- A combined uncertainty score is intentionally absent because no combination was preregistered before inspecting outcomes.
- These are frozen Dev characterization results, not an Internal-test claim.
