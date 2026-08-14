from prta_cxr.wave047_resource_amendment import (
    EXPECTED_MANIFESTS,
    EXPECTED_PREPARATION,
    EXPECTED_SOURCE,
    _relocate_queue_rows,
)


def test_wave047_resource_amendment_pins_authoritative_v2_identities():
    assert len(EXPECTED_SOURCE) == 40
    assert len(EXPECTED_PREPARATION) == 64
    assert set(EXPECTED_MANIFESTS) == {"3066", "9929"}
    assert all(len(value) == 64 for value in EXPECTED_MANIFESTS.values())


def test_wave047_resource_amendment_relocates_staging_config_paths(tmp_path):
    rows = [{"experiment_id": "W047-TILA8-S17", "config_path": "staging/x.json"}]
    final = tmp_path / "final" / "local_gpu0"
    relocated = _relocate_queue_rows(rows, final)
    assert relocated[0]["config_path"] == str((final / "configs/x.json").resolve())
    assert rows[0]["config_path"] == "staging/x.json"
