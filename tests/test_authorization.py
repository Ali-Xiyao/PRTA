import pytest

from prta_cxr.authorization import (
    FORMAL_ENV_NAME,
    FORMAL_ENV_VALUE,
    FormalExecutionBlocked,
    require_formal_authorization,
)


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
