# PRTA-CXR SUES HPC Deployment Record

**Status:** PASS for engineering readiness; no formal launch authorized

## Scope and authority

- Remote project root: `<private-server-workspace>`.
- Deployable project: the clean `PRTA-CXR` repository under that root, not the
  historical top-level VisualVIT experiment repository.
- The execution manual and experiment plan in `docs/` remain authoritative.
- Current scientific boundary: `HOLD_DEVELOPMENT_GATE`. This deployment does
  not authorize retraining, tuning, cache building, evaluation, or reads of
  Internal-test or Gold outcomes.

## Deployment contract

1. Preserve the current working-tree contents, including the final documents,
   manifests, results, and audit receipts; exclude VCS internals and disposable
   local caches.
2. Create `/050_VisualVIT/PRTA-CXR` without altering the pre-existing
   `/050_VisualVIT/incoming` or `/050_VisualVIT/releases` directories.
3. Create a project-specific Python 3.11 environment because the platform's
   shared `dl310` environment is Python 3.10 while `pyproject.toml` requires
   Python 3.11 or newer.
4. Validate installation and a synthetic preflight only. The formal lock stays
   unset and no Slurm training job is submitted by this deployment.

## Environment and GPU probe

The project environment is named `prta-cxr311`. It uses Python 3.11 and a
CUDA 12.6 PyTorch wheel, which is compatible with the platform's A800 driver
stack. From the project root, install it with:

```bash
source ~/miniforge3/etc/profile.d/conda.sh
conda activate prta-cxr311
python -m pip install --upgrade pip
python -m pip install torch==2.6.0 torchvision==0.21.0 \
  --index-url https://download.pytorch.org/whl/cu126
python -m pip install -e '.[dev,vision,data,audit]'
```

The engineering-only probe was executed with `srun --jobid=4161 --overlap`
inside the user's existing retained allocation, not by submitting another job.
It passed on `gpu01` with NVIDIA A800 80GB PCIe, driver 590.48.01,
torch 2.6.0+cu126, CUDA available, clean `pip check`, and
`PASS_PRTA_CXR_ENGINEERING_PREFLIGHT`. It left `PRTA_CXR_ALLOW_FORMAL` unset.

The checked-in `environment/sues_hpc_paths.env.template` now supplies the
project runtime, frozen Train/Dev manifest, cleaned-split receipt, minimal
cache, text-cache, output-root, and BiomedCLIP-weight paths. Source-image and
private-label variables remain commented and are not needed by cached
Train/Dev training.

## Data boundary

- The exact physician-cleaned Train/Dev manifest is already present remotely:
  SHA-256
  `45985f4ff5373715fbfaf7a3af1e3820dc8800ae123d3a98e6086f9b62e38f89`,
  with its freeze and aggregate receipts byte-matching local sources.
- The BiomedCLIP weight is present remotely (783,705,670 bytes) with SHA-256
  `52cc993c5c5ff962bd0c60931874bc001e7e9b41666a385530f4a036294576be`.
- The only pending large asset is the 44.2 GB consolidated Train/Dev feature
  store and its small manifest/inventory/text-cache receipts. Duplicate shard
  files are intentionally omitted because the loader uses the consolidated
  store.
- A previously started broad SFTP batch was stopped when its directory scope
  was found to exceed this minimum boundary. Existing partial files were not
  deleted. The replacement batch contains no audit, label, Internal-test, or
  Gold directory.
- `scripts/sues_hpc_train_dev_asset_probe.py` refuses protected path markers,
  validates frozen hashes and 80,402/11,201 row counts, reads a small feature
  probe, and emits only aggregate engineering evidence.

## Completion evidence

- The final local BS arm ended with a valid early-stop receipt and every local
  exploratory training process is now stopped.
- The resumable minimal-cache upload completed at exactly 44,211,717,120 bytes.
  Store, cache manifest, text cache, Train/Dev manifest/freeze, and weight
  SHA-256 values all match their frozen local receipts.
- The Train/Dev asset probe passed inside retained allocation 4161 with
  80,402/11,201 rows, 146,110 cache rows, feature shape `[8, 197, 768]`,
  protected read count zero, and formal experiment started false.
- The Git-safe readiness receipt is
  `docs/operations/2026-08-06_SUES_HPC_READINESS_RECEIPT.json`. Formal training
  remains a separate authorization and must use a newly frozen Linux queue.

## SSH connection recovery

For future SUES-HPC banner/handshake timeouts, follow
[`SUES_HPC_SSH连接恢复手册_CN.md`](SUES_HPC_SSH连接恢复手册_CN.md) before trying a
different client, restarting a network adapter, or issuing concurrent retries.
The repository-standard recovery is an identity-checked stale-client cleanup
followed by one forced-TTY IPv4 connection with `IPQoS=none` and SSH
multiplexing disabled. It must not signal workloads or create refresh-time
Slurm steps.
