# Luna longitudinal CXR label prompt v1

You receive de-identified candidate pairs identified only by random
`sample_id`. For each pair, decide whether the reports support exactly one
finding-level progression label from:

`Stable`, `Improved`, `Worse`, `New`, `Resolved`.

Use only the supplied prior/current reports and dates. Verify that comparison
language refers to the selected prior, that the finding is correctly scoped,
and that negation, uncertainty, and temporal direction are consistent. Cite
the shortest relevant evidence spans. Reject samples with ambiguous comparison
objects, finding mismatch, missing evidence, or any unresolved conflict.

Return only data conforming to `schemas/luna_label_batch.schema.json`. Do not
invent patient facts, use external knowledge, or repair missing evidence.
