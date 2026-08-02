from prta_cxr.formal_outcome_session import _evaluation_specs


def test_evaluation_specs_include_formal_runs_and_prta_aliases(tmp_path):
    queue = [
        {"experiment_id": "B401-S17"},
        {"experiment_id": "A501-S17"},
    ]
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(__import__("json").dumps(queue), encoding="utf-8")
    freeze = {
        "input_paths": {"formal_queue": str(queue_path)},
        "prta_aliases": {"B404-S17": "M304-S17", "A500-S17": "M304-S17"},
    }
    registry = {
        "B401-S17": {},
        "A501-S17": {},
        "M304-S17": {},
    }
    specs = _evaluation_specs(freeze, registry)
    assert [value["evaluation_id"] for value in specs] == [
        "A501-S17",
        "B401-S17",
        "B404-S17",
    ]
