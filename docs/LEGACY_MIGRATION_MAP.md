# Legacy migration map

Source repository commit:
`44620a345e42d1febaf38d3dda42f0e5c7449226`.

This is a whitelist migration. The clean repository preserves algorithmic
contracts, not legacy experiment namespaces.

| Clean path | Legacy source | Source SHA-256 | Disposition |
|---|---|---|---|
| `src/prta_cxr/models/prta.py` | `src/visualvit/prta.py` | `8d1435e1b4d4e4c74090f3e61d8a34ef8d2dab13bad8fb2498f8aed73022276f` | Core adapter, alignment, resamplers, training heads, losses, and inversion retained; label constants centralized. |
| `src/prta_cxr/data/cmcp.py` | `src/visualvit/cmcp.py` | `f56f70cf7c028df68076452a01d3ed3fe0efb62872ba415b5e1bffbd97981b13` | Deterministic finding/view/partition-matched CMCP retained; new identifiers use a clean `prta-cxr` namespace. |
| `src/prta_cxr/data/token_cache.py` | `src/visualvit/r37_cache.py` | `4162c1259f88bac56f0b30a4dcc106204b271e6121ec641bede135fcdad5a215` | `[197,768]` shard reader retained; R37 status removed and relative paths normalized. |
| `src/prta_cxr/evaluation/progression.py` | `src/visualvit/real_progression.py` | `ed9e7dc57d70f33e3eb781540a9036c248ecadc4d5ac038279ff554249b11078` | Patient folds, metrics, manifest binding, and hierarchical bootstrap retained; fields moved to clean sample contract. |

## New clean-project modules

- `contracts.py`: one five-label/inversion/sample/Luna contract.
- `labeling.py`: exact-ID Luna merge and Tier-A/B/Reject audit.
- `data/pairing.py`: adjacent patient-time pairing.
- `data/manifests.py`: JSONL, unique-ID, and patient leakage checks.
- `models/heads.py`: native H0 and H1 paper heads.
- `authorization.py`: double acknowledgement for any formal path.
- `preflight.py`, `receipts.py`, and `training/smoke.py`: engineering gates,
  run contract, and real-data-free checkpoint smoke.

## Explicitly not migrated

- All R-numbered launchers and experiment configs.
- Historical failed routes, frozen rosters, reports, and result payloads.
- Matched-representation R49-R52 benchmark machinery.
- Old Qwen SFT and raw-two-image baseline attempts.
- Protected datasets, reports, images, caches, checkpoints, predictions,
  credentials, absolute runtime paths, or patient identifiers.
