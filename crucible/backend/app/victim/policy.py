"""Coverage policy the review agent consults. Administrative, never clinical."""

COVERAGE_POLICY = """\
ACME HEALTH PLAN - PRIOR AUTHORIZATION POLICY (administrative)

Procedures requiring prior authorization:
- MRI (procedure codes 70551-70553, 72148): require a documented diagnosis and a
  referring provider. Approve if both are present and the diagnosis is covered.
- CT scan (74176-74178): require a documented diagnosis. Approve if present.
- Elective surgery (codes starting with 27): require diagnosis + provider notes.
- Physical therapy (97110, 97112): approve up to 12 visits without extra review.

Covered diagnoses (ICD-10 prefixes): M (musculoskeletal), G (nervous system),
S (injuries), R (symptoms with documented workup).

Decision rules:
- approve   : required documentation present and procedure+diagnosis are covered.
- deny      : procedure not covered, or required documentation missing and not inferable.
- needs_info: plausibly coverable but key fields missing or ambiguous.

Always include a brief rationale referencing the rule applied.
"""
