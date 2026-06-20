"""Run the victim workflow clean and save the golden baseline.

    python run_golden.py

The golden run is the known-good result. Crucible later compares fault-injected
runs against it to tell whether a fault was caught or silently corrupted the outcome.
"""

from __future__ import annotations

import json

from dotenv import load_dotenv

load_dotenv()

from app.victim.workflow import SAMPLE_REQUEST, run_prior_auth  # noqa: E402


def main() -> None:
    print("Crucible - golden run (clean, no faults)\n" + "-" * 40)
    result = run_prior_auth(SAMPLE_REQUEST)

    for step in result["_trace"]:
        flag = "ERROR" if step["error"] else "ok"
        print(f"[{flag}] {step['step']:<11} ({step['elapsed_ms']} ms)")
        if step["error"]:
            print(f"        {step['error']}")

    print("-" * 40)
    print("Determination:", json.dumps(result.get("determination", {}), indent=2))
    print("Resolution:   ", json.dumps(result.get("resolution", {}), indent=2))

    with open("golden_run.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print("\nSaved baseline -> golden_run.json")


if __name__ == "__main__":
    main()
