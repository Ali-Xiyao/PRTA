import subprocess

import pytest

from prta_cxr.provenance import SOURCE_COMMIT_ENV, resolve_source_commit


def test_source_commit_uses_explicit_archive_pin_without_git(monkeypatch, tmp_path):
    commit = "a" * 40
    monkeypatch.setenv(SOURCE_COMMIT_ENV, commit)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(subprocess, "run", fail)
    assert resolve_source_commit(tmp_path) == commit


def test_source_commit_rejects_missing_archive_pin(monkeypatch, tmp_path):
    monkeypatch.delenv(SOURCE_COMMIT_ENV, raising=False)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="source provenance is unavailable"):
        resolve_source_commit(tmp_path)
