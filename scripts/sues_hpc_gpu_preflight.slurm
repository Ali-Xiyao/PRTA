#!/bin/bash
#SBATCH --job-name=prta-cxr-preflight
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --account=dqxy
#SBATCH --output=logs/%j.out
#SBATCH --error=logs/%j.err

# Engineering-only GPU environment probe. It must not be used to start a
# formal PRTA run and does not set PRTA_CXR_ALLOW_FORMAL.
set -euo pipefail

PROJECT_ROOT=/ipfs/inspurfileset/home/dqxy/dqxy11/projects/xiyaowang/050_VisualVIT/PRTA-CXR
source ~/miniforge3/etc/profile.d/conda.sh
conda activate prta-cxr311
cd "$PROJECT_ROOT"
mkdir -p logs

echo "job_id=${SLURM_JOB_ID} host=$(hostname)"
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
python - <<'PY'
import torch

print("torch=", torch.__version__)
print("cuda_available=", torch.cuda.is_available())
if not torch.cuda.is_available():
    raise SystemExit("CUDA is not available inside the allocated GPU job")
print("device=", torch.cuda.get_device_name(0))
PY
python -m pip check
python scripts/00_preflight.py
