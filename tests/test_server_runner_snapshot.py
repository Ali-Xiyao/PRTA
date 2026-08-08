from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "scripts/sues_hpc_run_dev_search_arm.sh"


def test_server_runner_supports_isolated_source_and_runtime_roots() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert "DEFAULT_PROJECT_ROOT=/ipfs/" in text
    assert "PROJECT_ROOT=${PRTA_CXR_PROJECT_ROOT:-${DEFAULT_PROJECT_ROOT}}" in text
    assert "RUNTIME_ROOT=${PRTA_CXR_RUNTIME_ROOT:-${PROJECT_ROOT}/data/runtime}" in text
    assert 'cd "${PROJECT_ROOT}"' in text
    assert "python scripts/07_train.py" in text
