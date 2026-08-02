import zipfile
from xml.sax.saxutils import escape

import pytest

from prta_cxr.cli_labeling import synthetic_samples
from prta_cxr.contracts import ContractError
from prta_cxr.human_review import (
    HUMAN_REVIEW_HEADERS,
    SENIOR_LUNA_REVIEW_HEADERS,
    finalize_human_review,
    read_human_review_xlsx,
)
from prta_cxr.luna_primary import (
    apply_training_patient_quarantine,
    select_gold_audit_roster,
)


def _silver_pool():
    templates = synthetic_samples()
    rows = []
    for source in ("mimic", "chexpert"):
        for patient in range(150):
            row = templates[patient % 5].copy()
            row["sample_id"] = f"{source}-{patient}"
            row["patient_id_hash"] = f"{source}-patient-{patient}"
            row["source"] = source
            row["label_source"] = "luna_primary_report_label"
            row["label_tier"] = "Silver"
            rows.append(row)
    return rows


def _responses(roster):
    return [
        {
            "case_no": index,
            "review_id": row["review_id"],
            "source": row["source"],
            "finding": row["finding"],
            "prior_report": row["prior_report"],
            "current_report": row["current_report"],
            "human_label": row["luna_label"],
            "unusable_reason": "",
            "reviewer_id": "reviewer",
            "review_date": "2026-08-02",
            "notes_optional": "",
        }
        for index, row in enumerate(roster, start=1)
    ]


def test_finalize_human_review_freezes_decisive_gold_and_keeps_quarantine():
    silver = _silver_pool()
    roster, quarantine, _ = select_gold_audit_roster(silver)
    training, held, _ = apply_training_patient_quarantine(silver, quarantine)
    responses = _responses(roster)
    responses[0]["human_label"] = "Unclear"
    responses[1]["human_label"] = "Unusable"
    responses[1]["unusable_reason"] = "Not comparable"
    responses[2]["human_label"] = (
        "Improved" if roster[2]["luna_label"] != "Improved" else "Worse"
    )
    validated, comparisons, gold, excluded, audit = finalize_human_review(
        roster,
        responses,
        silver,
        quarantine,
        training,
        workbook_sha256="a" * 64,
    )
    assert len(validated) == 250
    assert len(comparisons) == 250
    assert len(gold) == 248
    assert len(excluded) == 2
    assert all(row["label_tier"] == "Gold" for row in gold)
    assert all(row["training_eligible"] is False for row in gold)
    assert audit["gold_rows"] == 248
    assert audit["excluded_human_label_counts"] == {"Unclear": 1, "Unusable": 1}
    assert audit["quarantined_patients_retained"] == 250
    assert audit["quarantined_silver_rows"] == len(held)
    assert audit["gold_training_patient_overlap"] == 0
    assert audit["unique_reviewer_ids"] == 1
    assert audit["unique_review_dates"] == 1
    assert audit["single_human_reviewer_reference"] is True
    assert audit["formal_training_authorized"] is False


def test_finalize_human_review_rejects_missing_unusable_reason():
    silver = _silver_pool()
    roster, quarantine, _ = select_gold_audit_roster(silver)
    training, _, _ = apply_training_patient_quarantine(silver, quarantine)
    responses = _responses(roster)
    responses[0]["human_label"] = "Unusable"
    with pytest.raises(ContractError, match="unusable_reason"):
        finalize_human_review(
            roster,
            responses,
            silver,
            quarantine,
            training,
            workbook_sha256="b" * 64,
        )


def _inline_cell(reference, value):
    if isinstance(value, int):
        return f'<c r="{reference}"><v>{value}</v></c>'
    return (
        f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">'
        f"{escape(value)}</t></is></c>"
    )


def _column_name(index):
    result = ""
    value = index + 1
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _write_review_xlsx(path):
    rows = []
    rows.append(
        '<row r="1">'
        + "".join(
            _inline_cell(f"{_column_name(index)}1", header)
            for index, header in enumerate(HUMAN_REVIEW_HEADERS)
        )
        + "</row>"
    )
    for index in range(1, 251):
        values = [
            index,
            f"review_{index - 1:04d}",
            "mimic",
            "Edema",
            "prior report",
            "current report",
            "Stable",
            "",
            "reviewer",
            "2026-08-02",
            "",
            "完成",
        ]
        cells = "".join(
            _inline_cell(f"{_column_name(column)}{index + 1}", value)
            for column, value in enumerate(values)
        )
        rows.append(f'<row r="{index + 1}">{cells}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="人工复核" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def test_read_human_review_xlsx_without_optional_excel_dependency(tmp_path):
    path = tmp_path / "review.xlsx"
    _write_review_xlsx(path)
    rows = read_human_review_xlsx(path)
    assert len(rows) == 250
    assert rows[0]["review_id"] == "review_0000"
    assert rows[-1]["review_id"] == "review_0249"
    assert rows[0]["human_label"] == "Stable"
    assert rows[0]["review_date"] == "2026-08-02"
    assert rows[0]["review_mode"] == "blind_v1"


def test_read_senior_luna_assisted_workbook(tmp_path):
    path = tmp_path / "senior_review.xlsx"
    rows = []
    rows.append(
        '<row r="1">'
        + "".join(
            _inline_cell(f"{_column_name(index)}1", header)
            for index, header in enumerate(SENIOR_LUNA_REVIEW_HEADERS)
        )
        + "</row>"
    )
    for index in range(1, 251):
        values = [
            index,
            f"review_{index - 1:04d}",
            "mimic",
            "Edema",
            "prior report",
            "current report",
            "Stable",
            "Stable",
            "",
            "senior-reviewer",
            "2026-08-02",
            "",
            "完成",
        ]
        cells = "".join(
            _inline_cell(f"{_column_name(column)}{index + 1}", value)
            for column, value in enumerate(values)
        )
        rows.append(f'<row r="{index + 1}">{cells}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="资深医生复核" sheetId="1" '
        'r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    parsed = read_human_review_xlsx(path)
    assert len(parsed) == 250
    assert parsed[0]["displayed_luna_label"] == "Stable"
    assert parsed[0]["human_label"] == "Stable"
    assert parsed[0]["review_mode"] == "luna_assisted_senior_v2"
