# PRTA-CXR internal checkpoints

This directory is reserved for the three final `PRTA-CXR` / `Slim-S1`
checkpoints (`S17`, `S28`, and `S43`) plus their exact frozen configs and
training receipts. Model binaries are deliberately excluded from Git by
`.gitignore`.

The tracked identity of each local-only file is recorded in
`manifests/final_prta_cxr_checkpoints.json`. Only `best.pt` is retained for
each Seed; `last.pt`, optimizer state, caches, patient-level predictions, and
raw logs are not part of the final internal package.

The tracked release-equivalent configuration is
`configs/final/prta_cxr_slim_s1.json`. It omits the five legacy loss keys whose
frozen weights were exactly zero. The exact historical checkpoint-bound config
files remain beside the local checkpoints and are hash-bound in the manifest.
