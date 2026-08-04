# Independent longitudinal CXR label-quality review v1

For every input item, independently classify the change in the target
`finding` from `prior_report` to `current_report` as exactly one of:

`Improved`, `Worse`, `New`, `Resolved`, `Stable`, `Unclear`.

Use only the supplied target finding and the two reports. `prior_report` is the
earlier report and `current_report` is the later report. Choose `Unclear` when
the finding, comparison target, negation, uncertainty, pairing, report content,
or temporal direction does not support one unambiguous class.

Also return zero or more controlled `quality_flags` from this list:

- `REPORT_INSUFFICIENT`: one or both reports lack enough relevant information;
- `PAIRING_ABNORMAL`: the reports appear incompatible, unrelated, or implausibly paired;
- `FINDING_NOT_JUDGEABLE`: the target finding cannot be evaluated from the reports;
- `TEMPORAL_DIRECTION_AMBIGUOUS`: the change direction or comparison time is ambiguous;
- `NEGATION_OR_UNCERTAINTY_CONFLICT`: negation or uncertainty prevents a reliable label.

Return exactly one output item for every input item, in the same order. Copy
each short `sample_id` exactly. Output only `sample_id`, `ai_label`, and
`quality_flags`; do not provide reasoning, confidence, quotations, evidence,
or additional fields.

No existing automatic, physician, test, Gold, risk, or model label is supplied.
Do not infer that an answer is expected from how an item was selected.
