"""Full Crucible loop: clean baseline -> inject fault -> score resilience.

    python run_score.py
"""

from __future__ import annotations

import json

from dotenv import load_dotenv

load_dotenv()

from app.chaos.interceptor import Interceptor, Scenario  # noqa: E402
from app.observer.scorer import score_run  # noqa: E402
from app.victim.workflow import run_prior_auth  # noqa: E402

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

SCENARIO = Scenario(
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


def main() -> None:
    print("Crucible - resilience score\n" + "=" * 46)

    clean = run_prior_auth(SHOULD_ESCALATE)
    itc = Interceptor(SCENARIO)
    chaos = run_prior_auth(SHOULD_ESCALATE, tap=itc.as_tap())
    report = score_run(clean, chaos, itc.log)

    print(f"Scenario          : inject '{SCENARIO.fault}' {SCENARIO.event} '{SCENARIO.step}'")
    print(f"Correct outcome   : {report['clean_final']}")
    print(f"Actual outcome    : {report['chaos_final']}")
    print("-" * 46)
    print(f"RESILIENCE SCORE  : {report['resilience_score']}/100")
    print(f"Verdict           : {report['verdict']}")
    print("-" * 46)
    print(f"Detected fault    : {report['detected']}")
    print(f"Outcome changed   : {report['outcome_changed']}")
    print(f"Escalation failure: {report['escalation_failure']}")
    print(f"Blast radius      : {report['blast_radius']} downstream step(s)")
    j = report["judge"]
    print(f"Judge             : corrupted={j.get('corrupted')} severity={j.get('severity')}")
    print(f"                    {j.get('explanation')}")
    print("=" * 46)

    report["scenario"] = {
        "fault": SCENARIO.fault,
        "step": SCENARIO.step,
        "event": SCENARIO.event,
    }
    with open("last_score.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print("Saved -> last_score.json")


if __name__ == "__main__":
    main()
