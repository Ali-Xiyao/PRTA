# Luna longitudinal CXR label prompt v1

You receive de-identified candidate pairs identified only by random
`sample_id`. For each pair, decide whether the reports support exactly one
finding-level progression label from:

`Stable`, `Improved`, `Worse`, `New`, `Resolved`.

Use only the supplied prior/current reports and temporal metadata. Verify that comparison
language refers to the selected prior, that the finding is correctly scoped,
and that negation, uncertainty, and temporal direction are consistent. Cite
the shortest relevant evidence spans. Reject samples with ambiguous comparison
objects, finding mismatch, missing evidence, or any unresolved conflict.

Respect `interval_basis` exactly. When it is `within_patient_ordinal`, the
timestamps and interval values encode visit order only: do not interpret them
as calendar dates or elapsed days, and do not infer real-world time duration.
When `calendar_interval_available` is false, reason only about prior-versus-current
order and the report evidence.

Return only data conforming to `schemas/luna_label_batch.schema.json`. Do not
invent patient facts, use external knowledge, or repair missing evidence.

The decision and audit flags must agree. Use `accept` only when
`comparison_matches_selected_prior=true`, `finding_match=true`, all three
conflict flags are false, and comparison evidence is non-empty. Any negation,
uncertainty, temporal, finding, or comparison-object conflict must not be
accepted; use `reject` when a conflict remains.

All three evidence fields for an `accept` decision are extractive citations,
not summaries. Copy one non-empty, contiguous span verbatim from the supplied
report: `prior_evidence` from the prior report, `current_evidence` from the
current report, and `comparison_evidence` from either report. Do not add
prefixes, paraphrase, join non-contiguous spans, or write interpretations such
as "not mentioned". If three exact spans cannot be cited, do not use `accept`.

Return exactly one output item for every input item, in the same order. Copy
each `sample_id` verbatim. Never omit a difficult or rejected input; emit a
`reject` record with the appropriate flags and reason code instead.
