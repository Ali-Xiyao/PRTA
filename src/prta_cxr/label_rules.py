from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from prta_cxr.contracts import PROGRESSION_LABELS

RULESET_VERSION = "prta-cxr-report-transition-v1"

FINDING_ALIASES: dict[str, tuple[str, ...]] = {
    "Atelectasis": (r"\batelecta(?:sis|tic)\b",),
    "Cardiomegaly": (
        r"\bcardiomegaly\b",
        r"\benlargement of (?:the )?(?:cardiac|cardiomediastinal) silhouette\b",
    ),
    "Consolidation": (
        r"\bconsolidation\b",
        r"\bairspace (?:disease|consolidation)\b",
    ),
    "Edema": (
        r"\b(?:pulmonary |interstitial )?edema\b",
        r"\bvascular congestion\b",
    ),
    "Enlarged Cardiomediastinum": (
        r"\bcardiomediastinal silhouette\b",
        r"\bmediastinal widening\b",
    ),
    "Fracture": (r"\bfracture[sd]?\b",),
    "Lung Lesion": (
        r"\b(?:lung |pulmonary )?(?:nodule|nodules|mass|masses)\b",
    ),
    "Lung Opacity": (
        r"\b(?:lung |pulmonary |airspace |parenchymal )?"
        r"(?:opacity|opacities|infiltrate|infiltrates)\b",
    ),
    "Pleural Effusion": (r"\b(?:pleural )?effusion[sd]?\b",),
    "Pleural Other": (r"\bpleural (?:thickening|scar|scarring)\b",),
    "Pneumonia": (r"\bpneumonia\b",),
    "Pneumothorax": (r"\bpneumothora(?:x|ces)\b",),
}

CUE_PATTERNS: dict[str, tuple[str, ...]] = {
    "New": (
        r"\bnew(?:ly)?\b",
        r"\binterval development of\b",
        r"\bhas developed\b",
    ),
    "Resolved": (
        r"\b(?:has |have )?resolved\b",
        r"\binterval resolution of\b",
        r"\bno longer (?:seen|present|visualized)\b",
        r"\b(?:has |have )?(?:cleared|disappeared)\b",
    ),
    "Improved": (
        r"\b(?:almost|nearly|largely|essentially)(?: completely)? "
        r"(?:resolved|cleared)\b",
        r"\bimprov(?:ed|ing)\b",
        r"\bdecreas(?:ed|ing)\b",
        r"\bdiminish(?:ed|ing)\b",
        r"\b(?:slightly )?smaller (?:than|compared (?:to|with)|since)\b",
        r"\bless (?:prominent|conspicuous|severe|extensive)\b",
        r"\bresolving\b",
    ),
    "Worse": (
        r"\bworsen(?:ed|ing)\b",
        r"\bincreas(?:ed|ing)\b",
        r"\bprogress(?:ed|ing|ion)\b",
        r"\b(?:slightly )?larger (?:than|compared (?:to|with)|since)\b",
        r"\bmore prominent\b",
    ),
    "Stable": (
        r"\bunchanged\b",
        r"\bstable\b",
        r"\bsimilar (?:to|in appearance)\b",
        r"\bno significant (?:interval )?change\b",
        r"\bnot substantially changed\b",
    ),
}

SECTION_PATTERN = re.compile(
    r"(?im)^\s*(FINDINGS?|IMPRESSION|CONCLUSION|INDICATION|HISTORY|"
    r"CLINICAL HISTORY|REASON FOR EXAM|COMPARISON|EXAMINATION|TECHNIQUE)"
    r"\s*:\s*"
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])(?:\s+|(?=[A-Z]))")
CLAUSE_SPLIT = re.compile(
    r";\s*|,\s*(?:but|while|whereas|with)\s+|"
    r"\s+(?:and|or|but|while|whereas|with|without|due to|secondary to|"
    r"suggesting|compatible with|consistent with)\s+",
    re.I,
)
NEGATED_NEW = re.compile(
    r"\b(?:no|without)\b.{0,72}\b(?:new(?:ly)?|interval development)\b", re.I
)
NEGATED_CHANGE = re.compile(
    r"\b(?:no|without)\s+(?:significant\s+)?"
    r"(?:increase|decrease|improvement|worsening|progression|resolution)\b|"
    r"\bnot\s+(?:improved|improving|worsened|worsening|resolved|cleared)\b",
    re.I,
)
NON_ASSERTION = re.compile(
    r"\b(?:evaluate|evaluation|assess|assessment|question|rule out|"
    r"progression vs|resolution vs|improvement/worsening|scheduled for)\b|\?",
    re.I,
)
UNCERTAINTY = re.compile(
    r"\b(?:may|might|could|possible|possibly|potential(?:ly)?|suggest(?:s|ing)?|"
    r"suggestion of|concerning for|worrisome for|question of|versus|vs\.?)\b",
    re.I,
)
AMBIGUOUS_ALTERNATIVE = re.compile(
    r"\b(?:stable|unchanged|improved|worsened|smaller|larger)\s+or\s+"
    r"(?:stable|unchanged|improved|worsened|increasing|decreasing|resolved)\b",
    re.I,
)
TECHNIQUE_ARTIFACT = re.compile(
    r"\b(?:portable technique|projectional|positioning|rotation|"
    r"body habitus|technique creating|artifact)\b",
    re.I,
)


def _matches(patterns: Iterable[str], text: str) -> list[re.Match[str]]:
    result = []
    for pattern in patterns:
        result.extend(re.finditer(pattern, text, flags=re.I))
    return result


def report_sections(text: str) -> list[tuple[str, str]]:
    normalized = text.replace("\x00", " ")
    matches = list(SECTION_PATTERN.finditer(normalized))
    if not matches:
        return [("UNSECTIONED", normalized)]
    sections = []
    for index, match in enumerate(matches):
        name = match.group(1).upper()
        name = "FINDINGS" if name == "FINDING" else name
        name = "IMPRESSION" if name == "CONCLUSION" else name
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(normalized)
        )
        if name in {"FINDINGS", "IMPRESSION"}:
            sections.append((name, normalized[match.end() : end]))
    return sections


def extract_sentence_annotations(
    sentence: str, *, section: str
) -> list[dict[str, str]]:
    compact = " ".join(sentence.split())
    if (
        len(compact) < 8
        or NON_ASSERTION.search(compact)
        or AMBIGUOUS_ALTERNATIVE.search(compact)
        or TECHNIQUE_ARTIFACT.search(compact)
        or UNCERTAINTY.search(compact)
    ):
        return []
    lowered = compact.lower()
    cues = [
        (label, match)
        for label, patterns in CUE_PATTERNS.items()
        for match in _matches(patterns, lowered)
    ]
    annotations = []
    for finding, aliases in FINDING_ALIASES.items():
        for finding_match in _matches(aliases, lowered):
            finding_center = (finding_match.start() + finding_match.end()) // 2
            nearby = []
            for label, cue in cues:
                cue_center = (cue.start() + cue.end()) // 2
                distance = abs(cue_center - finding_center)
                if distance <= 72:
                    nearby.append((distance, label, cue))
            if not nearby:
                continue
            distance, label, cue = min(
                nearby, key=lambda item: (item[0], PROGRESSION_LABELS.index(item[1]))
            )
            start = max(0, min(cue.start(), finding_match.start()) - 32)
            end = min(len(lowered), max(cue.end(), finding_match.end()) + 24)
            local = lowered[start:end]
            if label == "New" and NEGATED_NEW.search(local):
                continue
            if label in {"Improved", "Worse", "Resolved"} and (
                NEGATED_CHANGE.search(local)
            ):
                continue
            annotations.append(
                {
                    "finding": finding,
                    "label": label,
                    "section": section,
                    "cue": cue.group(0),
                    "sentence": compact,
                    "distance": str(distance),
                }
            )
    unique = {}
    for item in annotations:
        key = (item["finding"], item["label"], item["sentence"])
        if key not in unique or int(item["distance"]) < int(unique[key]["distance"]):
            unique[key] = item
    return list(unique.values())


def extract_report_annotations(text: str) -> list[dict[str, str]]:
    by_finding: dict[str, list[dict[str, str]]] = defaultdict(list)
    for section, content in report_sections(text):
        for sentence in SENTENCE_SPLIT.split(" ".join(content.split())):
            for clause in CLAUSE_SPLIT.split(sentence):
                for item in extract_sentence_annotations(clause, section=section):
                    by_finding[item["finding"]].append(item)
    accepted = []
    for _finding, items in by_finding.items():
        preferred = [item for item in items if item["section"] == "IMPRESSION"]
        candidates = preferred or items
        if len({item["label"] for item in candidates}) != 1:
            continue
        selected = dict(
            min(
                candidates,
                key=lambda item: (
                    int(item["distance"]),
                    item["sentence"],
                    item["cue"],
                ),
            )
        )
        selected.pop("distance")
        accepted.append(selected)
    return sorted(accepted, key=lambda item: (item["finding"], item["label"]))


def candidate_samples(
    pairs: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    samples = []
    no_candidate = 0
    for pair in pairs:
        annotations = extract_report_annotations(str(pair["current_report"]))
        if not annotations:
            no_candidate += 1
        for annotation in annotations:
            identity = "|".join(
                (
                    str(pair["pair_id"]),
                    annotation["finding"],
                    annotation["label"],
                )
            )
            samples.append(
                {
                    "sample_id": hashlib.sha256(identity.encode()).hexdigest(),
                    "patient_id_hash": str(pair["patient_id_hash"]),
                    "source": str(pair["source"]),
                    "prior_study_id": str(pair["prior_study_id"]),
                    "current_study_id": str(pair["current_study_id"]),
                    "prior_image_path": str(pair["prior_image_path"]),
                    "current_image_path": str(pair["current_image_path"]),
                    "prior_report": str(pair["prior_report"]),
                    "current_report": str(pair["current_report"]),
                    "prior_datetime": str(pair["prior_datetime"]),
                    "current_datetime": str(pair["current_datetime"]),
                    "interval_days": float(pair["interval_days"]),
                    "prior_view": str(pair["prior_view"]),
                    "current_view": str(pair["current_view"]),
                    "finding": annotation["finding"],
                    "progression_label": annotation["label"],
                    "label_source": RULESET_VERSION,
                    "label_tier": "Tier-B",
                }
            )
    samples.sort(key=lambda row: row["sample_id"])
    return samples, {
        "schema": "prta-cxr.rule-candidate-audit.v1",
        "ruleset_version": RULESET_VERSION,
        "pairs": len(pairs),
        "pairs_without_candidate": no_candidate,
        "candidate_samples": len(samples),
        "labels": {
            label: sum(row["progression_label"] == label for row in samples)
            for label in PROGRESSION_LABELS
        },
    }
