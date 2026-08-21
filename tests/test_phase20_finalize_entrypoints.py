from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _assert_help(script_name: str) -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / script_name), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_phase20_training_finalizer_script_dispatches_to_own_module() -> None:
    _assert_help("122_finalize_phase20_training.py")


def test_phase20_comparator_finalizer_script_dispatches_to_own_module() -> None:
    _assert_help("123_finalize_phase20_comparators.py")


def test_phase20_b2_statistics_script_dispatches_to_own_module() -> None:
    _assert_help("124_run_phase20_b2_statistics.py")


def test_phase20_b2_preparer_script_dispatches_to_own_module() -> None:
    _assert_help("125_prepare_phase20_b2.py")


def test_phase20_evidence_finalizer_script_dispatches_to_own_module() -> None:
    _assert_help("126_finalize_phase20_evidence.py")
