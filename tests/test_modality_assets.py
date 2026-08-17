from prta_cxr.modality_assets import finding_intervention_prompts


def test_finding_intervention_prompts_are_complete_and_deterministic():
    prompts = finding_intervention_prompts(["Edema", "Pleural Effusion"])
    assert set(prompts) == {
        "generic",
        "clinical_semantic_alternative",
        "typo",
        "paraphrase",
    }
    assert all(
        set(values) == {"Edema", "Pleural Effusion"} for values in prompts.values()
    )
    assert prompts["clinical_semantic_alternative"]["Edema"] == (
        "chest x-ray finding: pulmonary fluid overload"
    )
    assert prompts == finding_intervention_prompts(["Pleural Effusion", "Edema"])
