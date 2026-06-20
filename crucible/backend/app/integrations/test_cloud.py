"""UiPath Test Manager write-back for Crucible resilience reports.

Confirmed against the live Test Management Hub OpenAPI spec
({tm_base}/swagger/v2/swagger.json) on staging, project "Crucible". The flow a
Crucible run drives is:

1. POST   /api/v2/{projectId}/testcases                                  - create the test case (once)
2. POST   /api/v2/{projectId}/testsets                                   - create a one-off test set to host the run
3. POST   /api/v2/{projectId}/testsets/{id}/assigntestcases              - attach the test case to it
4. POST   /api/v2/{projectId}/testexecutions                             - create the execution (needs both
                                                                            testSetId AND testCaseIds - the API
                                                                            500s if testCaseIds is omitted even
                                                                            though a testSetId is given)
5. POST   /api/v2/{projectId}/testexecutions/{id}/start
6. GET    /api/v2/{projectId}/testcaselogs/testexecution/{id}?testcaseid=...  - fetch the auto-created log row
7. POST   /api/v2/{projectId}/testcaselogs/{logId}/override-result       - set Passed/Failed + a reason
8. POST   /api/v2/{projectId}/testexecutions/{id}/finish

`source` must be "ThirdParty" with a non-empty `sourceDetails` for executions
created from outside UiPath Orchestrator/Studio - otherwise the API rejects
the request with a validation error naming the missing field.

Run from backend/:  python -m app.integrations.test_cloud
"""

from __future__ import annotations

import httpx

from app.config import settings

PASS_THRESHOLD = 70
SOURCE_DETAILS = "Crucible"


def _org_base() -> str:
    return f"{settings.uipath_base_url.rstrip('/')}/{settings.uipath_org}"


def _tm_base() -> str:
    return f"{_org_base()}/{settings.uipath_tenant}/testmanager_"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _raise_for_status(resp: httpx.Response, action: str) -> None:
    if resp.status_code >= 300:
        print(f"[FAIL] {action}: HTTP {resp.status_code} - {resp.text[:500]}")
        resp.raise_for_status()


def get_project_id(token: str, name: str = "Crucible") -> str:
    """Looks up a Test Manager project's id by exact name (case-insensitive)."""
    url = f"{_tm_base()}/api/v2/projects"
    resp = httpx.get(url, headers=_headers(token), timeout=30.0)
    _raise_for_status(resp, "get_project_id: list projects")
    data = resp.json()
    projects = data if isinstance(data, list) else data.get("data") or []
    for p in projects:
        if (p.get("name") or "").lower() == name.lower():
            return p["id"]
    raise RuntimeError(f"No Test Manager project named '{name}' found")


def ensure_test_case(token: str, project_id: str, name: str, description: str) -> str:
    """Returns the id of an existing test case with this exact name, else creates one."""
    search_url = f"{_tm_base()}/api/v2/{project_id}/testcases"
    resp = httpx.get(
        search_url, headers=_headers(token), params={"search": name}, timeout=30.0
    )
    _raise_for_status(resp, "ensure_test_case: search")
    for tc in resp.json().get("data", []):
        if tc.get("name") == name:
            return tc["id"]

    create_url = f"{_tm_base()}/api/v2/{project_id}/testcases"
    body = {
        "name": name,
        "description": description,
        "projectId": project_id,
        "containerId": project_id,
    }
    resp = httpx.post(create_url, headers=_headers(token), json=body, timeout=30.0)
    _raise_for_status(resp, "ensure_test_case: create")
    return resp.json()["id"]


def push_result(token: str, project_id: str, test_case_id: str, report: dict) -> dict:
    """Logs report (a score_run() dict) as a test execution result in Test Manager.

    resilience_score < PASS_THRESHOLD maps to FAILED, otherwise PASSED.
    Returns {"test_execution_id", "test_case_log_id", "result"}.
    """
    h = _headers(token)
    base = f"{_tm_base()}/api/v2/{project_id}"

    score = report.get("resilience_score", 0)
    result = "Failed" if score < PASS_THRESHOLD else "Passed"
    reason = (
        f"{report.get('verdict', '')} | score={score}/100 "
        f"| detected={report.get('detected')} outcome_changed={report.get('outcome_changed')} "
        f"escalation_failure={report.get('escalation_failure')} blast_radius={report.get('blast_radius')} "
        f"| clean={report.get('clean_final')} chaos={report.get('chaos_final')} "
        f"| judge={report.get('judge', {}).get('explanation', '')}"
    )

    testset_resp = httpx.post(
        f"{base}/testsets",
        headers=h,
        json={
            "name": f"Crucible run - {test_case_id[:8]}",
            "description": "Auto-created by Crucible to host a single resilience run.",
            "projectId": project_id,
            "containerId": project_id,
            "source": "ThirdParty",
            "sourceDetails": SOURCE_DETAILS,
            "enableCoverage": False,
        },
        timeout=30.0,
    )
    _raise_for_status(testset_resp, "push_result: create test set")
    test_set_id = testset_resp.json()["id"]

    assign_resp = httpx.post(
        f"{base}/testsets/{test_set_id}/assigntestcases",
        headers=h,
        json=[test_case_id],
        timeout=30.0,
    )
    _raise_for_status(assign_resp, "push_result: assign test case to test set")

    exec_resp = httpx.post(
        f"{base}/testexecutions",
        headers=h,
        params={"asyncMode": "false"},
        json={
            "projectId": project_id,
            "testSetId": test_set_id,
            "testCaseIds": [test_case_id],
            "source": "ThirdParty",
            "sourceDetails": SOURCE_DETAILS,
            "name": f"Crucible resilience run ({report.get('verdict', '')[:40]})",
        },
        timeout=30.0,
    )
    _raise_for_status(exec_resp, "push_result: create test execution")
    test_execution_id = exec_resp.json()["id"]

    start_resp = httpx.post(
        f"{base}/testexecutions/{test_execution_id}/start", headers=h, timeout=30.0
    )
    _raise_for_status(start_resp, "push_result: start test execution")

    log_resp = httpx.get(
        f"{base}/testcaselogs/testexecution/{test_execution_id}",
        headers=h,
        params={"testcaseid": test_case_id},
        timeout=30.0,
    )
    _raise_for_status(log_resp, "push_result: fetch test case log")
    test_case_log_id = log_resp.json()["id"]

    override_resp = httpx.post(
        f"{base}/testcaselogs/{test_case_log_id}/override-result",
        headers=h,
        json={"currentResult": result, "reason": reason[:1000]},
        timeout=30.0,
    )
    _raise_for_status(override_resp, "push_result: override result")

    finish_resp = httpx.post(
        f"{base}/testexecutions/{test_execution_id}/finish", headers=h, timeout=30.0
    )
    _raise_for_status(finish_resp, "push_result: finish test execution")

    return {
        "test_execution_id": test_execution_id,
        "test_case_log_id": test_case_log_id,
        "result": result,
    }


def main() -> None:
    from app.integrations.uipath import get_token

    token, method = get_token()
    print(f"Auth: token acquired via {method}")
    project_id = get_project_id(token, "Crucible")
    print(f"Project 'Crucible' -> {project_id}")
    test_case_id = ensure_test_case(
        token, project_id, "Crucible: smoke test", "Connectivity check from test_cloud.py"
    )
    print(f"Test case -> {test_case_id}")
    outcome = push_result(
        token,
        project_id,
        test_case_id,
        {
            "resilience_score": 100,
            "verdict": "Resilient - fault surfaced and the outcome held.",
            "detected": True,
            "outcome_changed": False,
            "escalation_failure": False,
            "blast_radius": 0,
            "clean_final": "n/a",
            "chaos_final": "n/a",
            "judge": {"explanation": "smoke test"},
        },
    )
    print(f"Pushed -> {outcome}")


if __name__ == "__main__":
    main()
