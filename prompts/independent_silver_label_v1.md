# Independent longitudinal CXR label prompt v1

For every input item, independently classify the change in the target
`finding` from `prior_report` to `current_report` as exactly one of:

`Improved`, `Worse`, `New`, `Resolved`, `Stable`, `Unclear`.

Use only the supplied target finding and the two reports. `prior_report` is the
earlier report and `current_report` is the later report. Choose `Unclear` when
the finding, comparison target, negation, uncertainty, or temporal direction
does not support one unambiguous class.

Return exactly one output item for every input item, in the same order. Copy
each short `sample_id` exactly. Output only `sample_id` and `ai_label`; do not
provide reasoning, confidence, quotations, evidence, or additional fields.

No candidate or rule label is supplied. Do not infer that an answer is expected
from the way an item was selected.
