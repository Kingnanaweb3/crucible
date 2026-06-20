"""Push the latest Crucible resilience report to UiPath Test Manager.

Loads last_score.json (written by run_score.py), ensures a matching test
case exists in the "Crucible" Test Manager project, and logs the result as
a test execution.

    python push_to_test_cloud.py
"""

from __future__ import annotations

import json
import sys

from dotenv import load_dotenv

load_dotenv()

from app.integrations.test_cloud import (  # noqa: E402
    PASS_THRESHOLD,
    ensure_test_case,
    get_project_id,
    push_result,
)
from app.integrations.uipath import get_token  # noqa: E402

REPORT_PATH = "last_score.json"


def _test_case_name(report: dict) -> str:
    scenario = report.get("scenario", {})
    fault = scenario.get("fault", "fault")
    event = scenario.get("event", "event")
    step = scenario.get("step", "step")
    return f"Crucible: {fault} {event} {step}"


def main() -> None:
    try:
        with open(REPORT_PATH) as f:
            report = json.load(f)
    except FileNotFoundError:
        print(f"[FAIL] {REPORT_PATH} not found - run `python run_score.py` first.")
        sys.exit(1)

    print("Crucible -> UiPath Test Manager write-back")
    print("=" * 46)

    token, method = get_token()
    print(f"Auth: token acquired via {method}")

    project_id = get_project_id(token, "Crucible")
    print(f"Project 'Crucible' -> {project_id}")

    name = _test_case_name(report)
    description = (
        f"Auto-managed by Crucible. Verdict: {report.get('verdict', '')}. "
        f"Pass threshold: resilience_score >= {PASS_THRESHOLD}."
    )
    test_case_id = ensure_test_case(token, project_id, name, description)
    print(f"Test case '{name}' -> {test_case_id}")

    outcome = push_result(token, project_id, test_case_id, report)
    print("-" * 46)
    print(f"Result            : {outcome['result']}")
    print(f"Test execution id : {outcome['test_execution_id']}")
    print(f"Test case log id  : {outcome['test_case_log_id']}")

    ui_link = (
        f"https://staging.uipath.com/kingnana/DefaultTenant/testmanager_/"
        f"projects/{project_id}/testcases/{test_case_id}"
    )
    print(f"Test Manager UI   : {ui_link}")
    print("=" * 46)


if __name__ == "__main__":
    main()
