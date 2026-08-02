from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence
from pathlib import Path


def _prepare() -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    sys.path.insert(0, str(source))


def dispatch(
    function_name: str,
    argv: Sequence[str] | None = None,
    *,
    module_name: str = "prta_cxr.cli",
) -> int:
    _prepare()
    module = importlib.import_module(module_name)
    function = getattr(module, function_name)
    return int(function(argv))


def dispatch_gated(step: str, argv: Sequence[str] | None = None) -> int:
    _prepare()
    module = importlib.import_module("prta_cxr.cli")
    return int(module.gated_step_main(step, argv))
