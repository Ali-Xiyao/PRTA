import json

import pytest

from prta_cxr.contracts import sha256_file
from prta_cxr.protocol_freeze import validate_protocol_freeze


def test_validate_protocol_freeze_detects_changed_input(tmp_path):
    input_path = tmp_path / "input.json"
    input_path.write_text("{}\n", encoding="utf-8")
    receipt_path = tmp_path / "freeze.json"
    receipt = {
        "status": "PASS_PROTOCOL_FROZEN__FORMAL_OUTCOMES_CLOSED",
        "input_paths": {"data": str(input_path)},
        "input_hashes": {"data": sha256_file(input_path)},
    }
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    validate_protocol_freeze(receipt, receipt_path=receipt_path)
    input_path.write_text("{\"changed\": true}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="input changed"):
        validate_protocol_freeze(receipt, receipt_path=receipt_path)
