"""Show silent corruption: one fault turns a 'needs human review' case into a
silent auto-approval. Clean run vs chaos run, side by side.

    python run_chaos.py
"""

from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from app.chaos.interceptor import Interceptor, Scenario  # noqa: E402
from app.victim.workflow import run_prior_auth  # noqa: E402

# A request that SHOULD go to a human: an MRI with the diagnosis missing.
SHOULD_ESCALATE = {
    "patient_id": "P-77781",
    "patient_name": "Sam Rivera",
    "procedure_code": "70553",
    "procedure_name": "MRI brain with and without contrast",
    "diagnosis_code": "",
    "diagnosis": "",
    "referring_provider": "Dr. Lena Park",
    "plan": "ACME Health PPO",
}


def summarize(result: dict) -> dict:
    det = result.get("determination", {})
    res = result.get("resolution", {})
    return {
        "review_decision": det.get("decision"),
        "final_decision": res.get("final_decision"),
        "escalated_to_human": res.get("escalated"),
    }


def main() -> None:
    print("Crucible - silent corruption demo\n" + "=" * 44)

    clean = run_prior_auth(SHOULD_ESCALATE)
    print("CLEAN (no fault):")
    print("  ", summarize(clean))

    scenario = Scenario(
        fault="ai_hallucinate",
        step="review",
        event="after",
        params={
            "key": "determination",
            "payload": {
                "decision": "approve",
                "rationale": "Approved - documentation sufficient.",
                "risk_score": 5,
                "confidence": 0.98,
            },
        },
    )
    interceptor = Interceptor(scenario)
    chaos = run_prior_auth(SHOULD_ESCALATE, tap=interceptor.as_tap())
    print("\nCHAOS (hallucinated 'approve' injected after review):")
    print("  ", summarize(chaos))
    print("   injected:", interceptor.log)

    print("\n" + "=" * 44)
    clean_ok = clean.get("resolution", {}).get("escalated") is True
    chaos_silently_approved = chaos.get("resolution", {}).get("final_decision") == "approve"
    if clean_ok and chaos_silently_approved:
        print("RESULT: SILENT CORRUPTION. Clean run escalated to a human; one")
        print("        injected fault made the same case auto-approve with no flag.")
        print("        This is exactly the failure Crucible is built to catch.")
    else:
        print("RESULT: contrast not as expected this run (LLM variance) - rerun.")


if __name__ == "__main__":
    main()
