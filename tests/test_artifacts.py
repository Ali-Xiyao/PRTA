from pathlib import Path

from prta_cxr import artifacts


def test_replace_json_atomic_retries_transient_permission_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "state.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    original_replace = Path.replace
    attempts = 0
    sleeps: list[float] = []

    def flaky_replace(source: Path, destination: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("transient sharing violation")
        return original_replace(source, destination)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr(artifacts.time, "sleep", sleeps.append)

    artifacts.replace_json_atomic(target, {"new": True})

    assert attempts == 3
    assert sleeps == [0.05, 0.1]
    assert target.read_text(encoding="utf-8") == '{\n  "new": true\n}\n'
