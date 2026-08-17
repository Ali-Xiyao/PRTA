import sys
from pathlib import Path

from prta_cxr.phase16_queue_runner import dependency_decision, render_command


def test_dependency_decision():
    assert dependency_decision([]) == "RUN"
    assert dependency_decision(["PASS", "PASS"]) == "RUN"
    assert dependency_decision(["PASS", "PENDING"]) == "WAIT"
    assert dependency_decision(["PASS", "FAILED"]) == "SKIP"
    assert dependency_decision(["SKIPPED"]) == "SKIP"


def test_render_command(tmp_path):
    command = render_command(
        [
            "{python}",
            "{source}/scripts/run.py",
            "{runtime_root}/inputs.json",
            "{output_root}/run",
            "--device={device}",
        ],
        source=tmp_path / "src",
        runtime_root=tmp_path / "runtime",
        output_root=tmp_path / "output",
        device="cuda:0",
    )
    assert command[0] == sys.executable
    assert Path(command[1]) == tmp_path / "src" / "scripts" / "run.py"
    assert Path(command[2]) == tmp_path / "runtime" / "inputs.json"
    assert Path(command[3]) == tmp_path / "output" / "run"
    assert command[4] == "--device=cuda:0"
