"""HTTP layer for Crucible: lets UiPath (and later a dashboard) trigger a
resilience run and read back the score, without either caller needing to
know about the chaos/observer/test_cloud internals.

Run from backend/:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.chaos.faults import FAULTS
from app.chaos.interceptor import Interceptor, Scenario
from app.integrations import test_cloud
from app.integrations.uipath import get_token
from app.observer.scorer import score_run
from app.victim.workflow import run_prior_auth

app = FastAPI(title="Crucible", description="Resilience-tester for AI agent workflows.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STEPS = ["intake", "review", "resolution"]
EVENTS = ["before", "after"]

SAMPLES: dict[str, dict] = {
    "covered": {
        "patient_id": "P-10293",
        "patient_name": "Jordan Avery",
        "procedure_code": "70553",
        "procedure_name": "MRI brain with and without contrast",
        "diagnosis_code": "G43.909",
        "diagnosis": "Migraine, unspecified, not intractable",
        "referring_provider": "Dr. Lena Park",
        "plan": "ACME Health PPO",
    },
    "missing_info": {
        "patient_id": "P-77781",
        "patient_name": "Sam Rivera",
        "procedure_code": "70553",
        "procedure_name": "MRI brain with and without contrast",
        "diagnosis_code": "",
        "diagnosis": "",
        "referring_provider": "Dr. Lena Park",
        "plan": "ACME Health PPO",
    },
    "not_covered": {
        "patient_id": "P-55512",
        "patient_name": "Casey Nguyen",
        "procedure_code": "15780",
        "procedure_name": "Dermabrasion (cosmetic)",
        "diagnosis_code": "L57.0",
        "diagnosis": "Actinic keratosis (cosmetic indication)",
        "referring_provider": "Dr. Omar Sayed",
        "plan": "ACME Health PPO",
    },
}
DEFAULT_SAMPLE = "missing_info"


class ScenarioIn(BaseModel):
    fault: str
    step: str
    event: Literal["before", "after"] = "after"
    params: dict = Field(default_factory=dict)


class RunRequest(BaseModel):
    scenario: ScenarioIn
    request: dict | None = None
    sample: str = DEFAULT_SAMPLE
    push_to_test_cloud: bool = False


def _resolve_request(body: RunRequest) -> dict:
    if body.request is not None:
        return body.request
    if body.sample not in SAMPLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown sample '{body.sample}'. Choices: {list(SAMPLES)}",
        )
    return SAMPLES[body.sample]


def _summary(run_bus: dict) -> dict[str, Any]:
    return {
        "determination": run_bus.get("determination"),
        "resolution": run_bus.get("resolution"),
    }


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/faults")
def faults() -> dict:
    return {"faults": list(FAULTS), "steps": STEPS, "events": EVENTS}


@app.get("/samples")
def samples() -> dict:
    return SAMPLES


@app.post("/run")
def run(body: RunRequest) -> dict:
    if body.scenario.fault not in FAULTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fault '{body.scenario.fault}'. Choices: {list(FAULTS)}",
        )
    if body.scenario.step not in STEPS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown step '{body.scenario.step}'. Choices: {STEPS}",
        )

    request_payload = _resolve_request(body)
    scenario = Scenario(
        fault=body.scenario.fault,
        step=body.scenario.step,
        event=body.scenario.event,
        params=body.scenario.params,
    )

    clean = run_prior_auth(request_payload)
    interceptor = Interceptor(scenario)
    chaos = run_prior_auth(request_payload, tap=interceptor.as_tap())
    report = score_run(clean, chaos, interceptor.log)

    result: dict[str, Any] = {
        "scenario": {
            "fault": scenario.fault,
            "step": scenario.step,
            "event": scenario.event,
            "params": scenario.params,
        },
        "clean": _summary(clean),
        "chaos": _summary(chaos),
        "report": report,
        "injected": interceptor.log,
        "test_cloud": None,
    }

    if body.push_to_test_cloud:
        try:
            token, _ = get_token()
            project_id = test_cloud.get_project_id(token, "Crucible")
            name = f"Crucible: {scenario.fault} {scenario.event} {scenario.step}"
            test_case_id = test_cloud.ensure_test_case(
                token,
                project_id,
                name,
                f"Auto-managed by Crucible. Pass threshold: resilience_score >= {test_cloud.PASS_THRESHOLD}.",
            )
            outcome = test_cloud.push_result(token, project_id, test_case_id, report)
            ui_link = (
                f"https://staging.uipath.com/kingnana/DefaultTenant/testmanager_/"
                f"projects/{project_id}/testcases/{test_case_id}"
            )
            result["test_cloud"] = {
                "test_case_id": test_case_id,
                "execution_id": outcome["test_execution_id"],
                "ui_link": ui_link,
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Test Cloud push failed: {exc}")

    return result
