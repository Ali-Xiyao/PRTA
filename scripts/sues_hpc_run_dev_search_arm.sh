#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: $0 CONFIG CONFIG_SHA256 OUTPUT RUN_REGISTRY EXPECTED_ALLOCATION" >&2
  exit 2
fi

CONFIG=$1
CONFIG_SHA256=$2
OUTPUT=$3
RUN_REGISTRY=$4
EXPECTED_ALLOCATION=$5

PROJECT_ROOT=/ipfs/inspurfileset/home/dqxy/dqxy11/projects/xiyaowang/050_VisualVIT/PRTA-CXR
RUNTIME_ROOT=${PROJECT_ROOT}/data/runtime
CACHE_ROOT=${RUNTIME_ROOT}/formal_program_v1/cache/full_repartition_v1
SPLIT_MANIFEST=${RUNTIME_ROOT}/formal_cleaned_split_v1_1/manifests/train_dev_cleaned_v1.jsonl
CLEANED_SPLIT_FREEZE=${RUNTIME_ROOT}/formal_cleaned_split_v1_1/cleaned_split_freeze_receipt.json
WEIGHTS=/ipfs/inspurfileset/home/dqxy/dqxy11/projects/xiyaowang/model/biomedclip/open_clip_pytorch_model.bin
QUALITY_AUDIT=${RUNTIME_ROOT}/server_runs/continuous_lightweight_dev_search_v1/inputs/human_silver_accuracy_audit.json

for VALUE in "${CONFIG}" "${OUTPUT}" "${RUN_REGISTRY}" "${SPLIT_MANIFEST}"; do
  LOWER=$(printf '%s' "${VALUE}" | tr '[:upper:]' '[:lower:]')
  if [[ "${LOWER}" == *internal_test* || "${LOWER}" == *gold* ]]; then
    echo "protected path marker rejected: ${VALUE}" >&2
    exit 3
  fi
done

if [[ "${SLURM_JOB_ID:-}" != "${EXPECTED_ALLOCATION}" ]]; then
  echo "allocation mismatch: expected ${EXPECTED_ALLOCATION}, got ${SLURM_JOB_ID:-unset}" >&2
  exit 4
fi
if [[ ! -f "${CONFIG}" ]]; then
  echo "missing frozen config: ${CONFIG}" >&2
  exit 5
fi
ACTUAL_CONFIG_SHA256=$(sha256sum "${CONFIG}" | awk '{print $1}')
if [[ "${ACTUAL_CONFIG_SHA256}" != "${CONFIG_SHA256}" ]]; then
  echo "frozen config hash mismatch" >&2
  exit 6
fi
if [[ -e "${OUTPUT}" ]]; then
  echo "refusing to overwrite run output: ${OUTPUT}" >&2
  exit 7
fi
if [[ ! -f "${QUALITY_AUDIT}" ]]; then
  echo "missing Train/Silver quality audit" >&2
  exit 8
fi
if [[ ! "${PRTA_CXR_SOURCE_COMMIT:-}" =~ ^[0-9a-f]{40,64}$ ]]; then
  echo "PRTA_CXR_SOURCE_COMMIT is not an exact commit hash" >&2
  exit 9
fi

source "${HOME}/miniforge3/etc/profile.d/conda.sh"
conda activate prta-cxr311
cd "${PROJECT_ROOT}"
export PRTA_CXR_ALLOW_FORMAL=I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN
export PYTHONUNBUFFERED=1

python scripts/07_train.py \
  --mode formal \
  --formal \
  --config "${CONFIG}" \
  --split-manifest "${SPLIT_MANIFEST}" \
  --cleaned-split-freeze "${CLEANED_SPLIT_FREEZE}" \
  --cleaned-split-platform-root "${RUNTIME_ROOT}/formal_cleaned_split_v1_1" \
  --cache-root "${CACHE_ROOT}" \
  --text-cache "${CACHE_ROOT}/text_cache.pt" \
  --weights "${WEIGHTS}" \
  --label-quality-audit "${QUALITY_AUDIT}" \
  --run-registry "${RUN_REGISTRY}" \
  --owner "Codex continuous Train/Dev search" \
  --device cuda:0 \
  --output "${OUTPUT}"
