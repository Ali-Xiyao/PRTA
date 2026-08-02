import pytest

from prta_cxr.authorization import (
    FORMAL_ENV_NAME,
    FORMAL_ENV_VALUE,
    FormalExecutionBlocked,
    require_formal_authorization,
)
from prta_cxr.cli import train_main
from prta_cxr.cli_cache import cache_main
from prta_cxr.cli_evaluate import evaluate_main


def test_formal_requires_flag_and_exact_environment(monkeypatch):
    monkeypatch.delenv(FORMAL_ENV_NAME, raising=False)
    with pytest.raises(FormalExecutionBlocked):
        require_formal_authorization(formal_flag=False)
    with pytest.raises(FormalExecutionBlocked):
        require_formal_authorization(formal_flag=True)
    monkeypatch.setenv(FORMAL_ENV_NAME, FORMAL_ENV_VALUE)
    with pytest.raises(FormalExecutionBlocked):
        require_formal_authorization(formal_flag=False)
    require_formal_authorization(formal_flag=True)


@pytest.mark.parametrize(
    ("entrypoint", "arguments"),
    (
        (cache_main, ["--mode", "formal", "--formal"]),
        (train_main, ["--mode", "formal", "--formal"]),
        (
            evaluate_main,
            ["--mode", "formal", "--formal", "--open-internal-test"],
        ),
    ),
)
def test_formal_entrypoints_block_before_opening_inputs(
    monkeypatch, entrypoint, arguments
):
    monkeypatch.delenv(FORMAL_ENV_NAME, raising=False)
    with pytest.raises(FormalExecutionBlocked):
        entrypoint(arguments)
