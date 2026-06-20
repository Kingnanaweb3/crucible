"""The prior-authorization victim workflow: intake -> review -> resolution + human gate.

This is the system Crucible tests. Deliberately small and representative.
"""

from __future__ import annotations

from app.victim.agents import intake_agent, resolution_agent, review_agent
from app.victim.pipeline import Step, Tap, run_pipeline


def build_steps() -> list[Step]:
    return [
        Step("intake", lambda bus: {"parsed": intake_agent(bus["request"])}),
        Step("review", lambda bus: {"determination": review_agent(bus["parsed"])}),
        Step("resolution", lambda bus: {"resolution": resolution_agent(bus["determination"])}),
    ]


def run_prior_auth(request: dict, tap: Tap | None = None) -> dict:
    """Run the workflow. With tap=None it runs clean (the golden run)."""
    return run_pipeline(build_steps(), {"request": request}, tap)


# A representative, covered request - the golden input we break later.
SAMPLE_REQUEST = {
    "patient_id": "P-10293",
    "patient_name": "Jordan Avery",
    "procedure_code": "70553",
    "procedure_name": "MRI brain with and without contrast",
    "diagnosis_code": "G43.909",
    "diagnosis": "Migraine, unspecified, not intractable",
    "referring_provider": "Dr. Lena Park",
    "plan": "ACME Health PPO",
}
