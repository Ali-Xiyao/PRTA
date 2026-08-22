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
