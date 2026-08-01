# Luna conflict verifier prompt v1

Review only samples previously marked conflict, uncertain, Tier-B, or Reject.
Re-evaluate the selected-prior match, finding scope, evidence spans, negation,
uncertainty, and temporal direction using the same five fixed labels and the
same JSON schema. Do not see the first pass rationale beyond its structured
fields. A missing or ambiguous fact remains rejected; never fill it by guess.
