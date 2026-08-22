# Data, checkpoint, and artifact availability

The MIT license in this repository applies to the repository's software and
documentation only. It does not grant rights to any third-party dataset,
medical image, report, patient-level record, feature cache, prediction export,
or model checkpoint.

## Data

The experiments use governed copies of MIMIC-CXR-JPG and CheXpert Plus under
their respective access terms. This repository does not redistribute images,
reports, patient identifiers, or derived patient-level tables. Users must
obtain the source datasets independently and comply with the applicable data
use agreements, ethics approvals, and local governance requirements.

The public, patient-safe description of source filtering, longitudinal pairing,
split construction, and archive boundaries is recorded in
`writing_handoff/11_数据来源筛选与归档边界_CN.md`.

## Checkpoints

The three frozen PRTA-CXR checkpoints are internal research artifacts and are
not included in ordinary GitHub. Their byte sizes and SHA256 identities are
recorded in `manifests/final_prta_cxr_checkpoints.json`. Any later checkpoint
release requires a separate artifact license and a documented review of the
training-data terms; the MIT software license must not be assumed to cover it.

## Aggregate evidence

Only Git-safe aggregate metrics, configuration contracts, and provenance
receipts are included. Patient-level predictions and raw runtime logs are not
published. Bidirectional source-held evaluation is reported as cross-source
generalization, not as independent external clinical validation.

Figure 5 uses native post-softmax attention from two preselected governed
MIMIC-CXR-JPG cases. The public repository includes the export/render code,
artifact hashes, tensor shapes, and two-case aggregate attention maps. It does
not include the source radiographs, per-case attention tensors, probabilities,
routes, or rendered pixel-bearing figure. Those artifacts require a separate
affirmative publication and redistribution review.

Supplemental Figure S3 uses native attention-flow maps from all reportable
multi-finding development pairs and a qualitative pair frozen before image or
attention inspection. The public repository includes aggregate between-query
and between-seed Jensen-Shannon divergence statistics with patient-clustered
confidence intervals, checkpoint/artifact hashes, and exact generation code.
It excludes source pixels, per-row maps, patient-level divergence units, and
the rendered pixel-bearing figure pending the same affirmative review.
