from __future__ import annotations

import os

FORMAL_ENV_NAME = "PRTA_CXR_ALLOW_FORMAL"
FORMAL_ENV_VALUE = "I_UNDERSTAND_THIS_STARTS_A_FORMAL_RUN"


class FormalExecutionBlocked(RuntimeError):
    """Raised when a formal path lacks the two required acknowledgements."""


def require_formal_authorization(*, formal_flag: bool) -> None:
    if not formal_flag or os.environ.get(FORMAL_ENV_NAME) != FORMAL_ENV_VALUE:
        raise FormalExecutionBlocked(
            "formal execution is blocked; it requires explicit user authority, "
            f"--formal, and {FORMAL_ENV_NAME}={FORMAL_ENV_VALUE}"
        )
