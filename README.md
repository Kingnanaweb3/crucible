# Crucible

**A resilience fire drill for AI agent workflows.**

Crucible injects realistic faults into a *running* system of agents and measures one thing that nothing else does: when something goes wrong inside the workflow, does the system **catch and escalate it**, or does it **silently do the wrong thing** and let it flow downstream?

* **Live API:** https://crucible-production-314a.up.railway.app
* **Repo:** https://github.com/Kingnanaweb3/crucible
* **Governance:** resilience tests run as governed executions in **UiPath Test Cloud**

## The problem

AI agents do not fail loudly. They rarely crash. Instead they **confidently produce a wrong answer that looks fine**, and in a workflow of several agents, one agent's output becomes the next agent's trusted input. So a single hallucinated, dropped, or injected value can propagate into a real decision with **no error, no alert, and no human in the loop**.

Functional tests only ask: *"Does it work when everything is fine?"*

Almost nobody tests the question that actually matters in production: *"Does it fail **safely** when something goes wrong inside?"*

That blind spot, **silent failure**, is exactly what Crucible attacks.

## What Crucible does

Crucible is a chaos engineering layer for agentic workflows. It:

1. Runs your agent workflow **once clean** to establish the correct outcome.
2. Runs it again with a **fault injected** between agents (a hallucination, a crash, dropped data, a prompt injection, a refusal, added latency).
3. **Compares the two runs** and scores how resilient the workflow was: did it detect the fault, did the outcome change, did it fail to escalate?
4. Surfaces a **verdict** (for example `SILENT CORRUPTION`) with an LLM judge's explanation of the real stakes.
5. Publishes each check as a **governed pass/fail test in UiPath Test Cloud**, so resilience can be gated on every release the same way functional tests are.

The wedge is not *"did it error."* It is *"did it quietly do the wrong thing, and nobody noticed."*

## See it in action

The reference workflow is a **healthcare prior authorization pipeline** (administrative coverage decisions only, never clinical advice). The case below is missing required diagnosis info, so it should be sent to a human. Watch what happens when a hallucination is injected into the review agent:


<img width="1672" height="941" alt="image" src="https://github.com/user-attachments/assets/97b566e3-4134-4505-9019-d6fa1ff9d018" />



A case that legally needed human review got **silently approved automatically**, because the hallucinated values (high confidence, low risk) all landed in the workflow's "safe to approve" zone. Nothing errored. That gap is the whole point.

You can reproduce this exact run in about 10 seconds. See the Quickstart section below.

## How it works

Crucible has four decoupled layers. Only the first is specific to the workflow; the rest are reusable across any workflow (see the section on using Crucible on your own agents).

```
            ┌─────────────────────────────────────────────┐
            │  VICTIM WORKFLOW  (the agents under test)    │
            │  intake → review → resolution (shared bus)   │
            └───────────────┬─────────────────────────────┘
                            │  every handoff between agents
                            ▼
            ┌─────────────────────────────────────────────┐
            │  CHAOS INTERCEPTOR  (the "tap")              │
            │  injects a fault at a chosen step or event   │
            └───────────────┬─────────────────────────────┘
                            ▼
            ┌─────────────────────────────────────────────┐
            │  SCORER / OBSERVER                           │
            │  clean vs chaos → resilience score + verdict │
            └───────────────┬─────────────────────────────┘
                            ▼
            ┌─────────────────────────────────────────────┐
            │  FastAPI service  →  UiPath Test Cloud       │
            │  run, score, and govern as a real test       │
            └─────────────────────────────────────────────┘
```

**Victim workflow** is the agent system being tested. The reference implementation is a pipeline of three agents: an **intake** agent ingests the request, a **review** agent applies the coverage policy and returns a determination (`approve`, `needs_info`, or `deny`, with a risk score and confidence), and a **resolution** agent acts as a deterministic human gate: it escalates to a person when info is missing, confidence is low, or risk is high, otherwise it finalizes automatically. The agents share a single state "bus" that passes down the pipeline.

**Chaos interceptor** is a "tap" that sits on every handoff between agents. You hand it a *scenario* (`fault`, `step`, `event`, `params`) and it injects the fault at exactly that point: overwriting an agent's output, dropping a field, raising a crash, and so on. Because Crucible owns the pipeline, the tap is clean and surgical.

**Scorer and observer** compares the clean run's outcome against the chaos run's outcome and grades resilience across three axes (below), then asks an LLM judge to confirm corruption and rate severity.

**Service and UiPath** is a FastAPI service that exposes the whole thing over HTTP, and a UiPath coded test that calls it and asserts on the score, turning each resilience check into a **governed Test Cloud execution**.

## The resilience score

`resilience_score` runs from 0 to 100, composed of three weighted parts:

* **Outcome integrity** (weight 40): did the injected fault change the final outcome?
* **Detection** (weight 30): did anything in the workflow notice something was wrong?
* **Escalation** (weight 30): did a case that should have reached a human still reach one?

Plus a verdict and metadata: `verdict`, `detected`, `outcome_changed`, `escalation_failure`, `blast_radius`, and a `judge` block (`corrupted`, `severity`, `explanation`).

The score is **not** rigged to be zero. If the workflow had caught the fault (say the corruption lowered confidence and resolution escalated anyway) it would score high. A `0` means the workflow is completely blind to that failure mode.

## Fault library

Crucible ships with six fault types, injectable at any step and either `before` or `after` an agent runs:

* `ai_hallucinate`: an agent confidently emitting a fabricated, plausible output.
* `ai_refuse`: an agent refusing, or returning an empty or guardrail response.
* `data_drop_field`: a field silently missing from the shared state.
* `data_prompt_injection`: malicious instructions smuggled into the data an agent reads.
* `infra_crash`: a step throwing, or a service going down mid run.
* `infra_latency`: a slow dependency (timeouts, degraded responses).

## Quickstart

### Option A: run against the live API, no setup

Save this as `crucible_demo.sh` and run `bash crucible_demo.sh`. It calls the live API and narrates a clean versus chaos run end to end:

```bash
#!/usr/bin/env bash
API="https://crucible-production-314a.up.railway.app"
PAYLOAD='{"scenario":{"fault":"ai_hallucinate","step":"review","event":"after","params":{"key":"determination","payload":{"decision":"approve","rationale":"ok","risk_score":5,"confidence":0.98}}},"sample":"missing_info"}'

curl -s -f "$API/health" >/dev/null && echo "API live: $API"
RESPONSE=$(curl -s -X POST "$API/run" -H "Content-Type: application/json" -d "$PAYLOAD")

CRUCIBLE_JSON="$RESPONSE" python3 - <<'PY'
import os, json
d = json.loads(os.environ["CRUCIBLE_JSON"])
c, x, r = d["clean"], d["chaos"], d["report"]
print("CLEAN :", c["determination"]["decision"], "then", c["resolution"]["final_decision"])
print("CHAOS :", x["determination"]["decision"], "then", x["resolution"]["final_decision"])
print("SCORE :", r["resilience_score"], "/100", r["verdict"])
print("JUDGE :", r["judge"]["explanation"])
PY
```

Change `"sample"` to `covered` or `not_covered`, or `"fault"` to `ai_refuse` or `infra_crash`, to explore other cases and failure modes.

### Option B: run it locally

```bash
git clone https://github.com/Kingnanaweb3/crucible.git
cd crucible/backend
pip install -r requirements.txt

# the victim and judge agents run on Groq
export GROQ_API_KEY=your_key_here

uvicorn app.main:app --reload
# open http://127.0.0.1:8000/docs
```

### API reference

* `GET /health` is a liveness check.
* `GET /faults` lists available fault types.
* `GET /samples` returns built in prior authorization cases (`covered`, `missing_info`, `not_covered`).
* `POST /run` runs a clean and chaos pass and returns the full scored report.

`POST /run` body:

```json
{
  "scenario": {
    "fault": "ai_hallucinate",
    "step": "review",
    "event": "after",
    "params": { "key": "determination", "payload": { "decision": "approve", "rationale": "ok", "risk_score": 5, "confidence": 0.98 } }
  },
  "sample": "missing_info",
  "push_to_test_cloud": false
}
```

Set `push_to_test_cloud` to `true` to also record the result as an execution in UiPath Test Cloud.

## Using Crucible on your own agents

**Yes, Crucible is a reusable stack, not a one off demo.** The healthcare pipeline is a *reference implementation*; the chaos engine underneath it is independent of any specific workflow.

Here is the separation:

* **Victim workflow** (`app/victim/`): your agents and the policy or logic they apply. This is the layer you swap.
* **Pipeline runner**: a generic executor, a sequence of steps over a shared bus, with a tap hook on every handoff. Reuse it unchanged.
* **Chaos interceptor** (`app/chaos/`): the fault library and the injection tap. Reuse it unchanged.
* **Scorer** (`app/observer/`): generic clean versus chaos scoring and the LLM judge. Reuse it unchanged.
* **Service** (`app/main.py`): the HTTP surface. Reuse it unchanged.

**To test your own agent workflow, you only replace the first item.** You express your workflow as a list of pipeline steps. Each step is just a function that reads the shared bus, does its work (calls an LLM, an API, whatever), and writes back. Point the runner at your steps and **the tap, the fault library, the scorer, and the API all work unchanged.** Crucible then injects faults between *your* agents and scores *your* workflow's resilience.

The design goal: **bring your workflow, get resilience testing for free.** Faults are a registry you can extend with your own, the scorer is generic, and the whole thing is exposed over an API that any system, or a UiPath test, can call.

**Honest scope, current state:** today you adapt Crucible by implementing your workflow in its lightweight pipeline format, a few functions. It is **not yet** a drop in adapter that ingests an arbitrary LangChain, CrewAI, or AutoGen graph from config. That is on the roadmap. So think of it as a **reusable resilience framework with a reference workflow**, with native adapters as the next step.

## UiPath integration

Crucible plugs into the **UiPath Platform** as its governance and execution layer:

* **UiPath Test Cloud and Test Manager**: each resilience check is recorded as a test execution. A coded UiPath test case (`CrucibleResilienceGate`) calls Crucible's `/run` endpoint and asserts the resilience score meets a threshold. When a workflow silently corrupts, the score is `0` and the test **fails on purpose**. That failing governed execution *is* the finding.
* **UiPath for Coding Agents**: the entire UiPath test project was scaffolded, built, packed, and deployed using a coding agent (Claude Code) driving the `uip` CLI, with UiPath becoming the deployment, governance, and runtime layer underneath.
* **Validate external agents**: because Crucible tests *external* agent workflows from the outside and reports findings into Test Cloud, it maps directly to the Test Cloud track's goal of validating agents built outside UiPath.

This means resilience becomes a **release gate**: teams can require "survives chaos" the same way they require "passes functional tests," governed in the same control plane.

## Tech stack

* **Language:** Python
* **API:** FastAPI and Uvicorn
* **LLMs:** Groq (workflow agents and the resilience judge)
* **Governance:** UiPath Test Cloud and Test Manager, via UiPath for Coding Agents (`uip` CLI)
* **Deployment:** Railway

## Roadmap

* Native **adapters** for LangChain, CrewAI, and AutoGen graphs, to test them with zero rewrite.
* A **visual dashboard** that lets you inject a fault and *watch* the corruption propagate in real time.
* The **full fault matrix** run automatically across every step of a workflow, producing a resilience heatmap.
* **Red teaming Crucible against itself**, with adversarial faults that target the detector.
* More reference workflows beyond healthcare prior authorization.

## A note on the healthcare example

The prior authorization pipeline models **administrative coverage decisions only** (does a request meet documented policy criteria), never clinical or medical advice. It exists to demonstrate why silent failure is dangerous in high stakes workflows that keep a human in the loop. It is not a medical device and makes no clinical determinations.

## License

MIT. See the `LICENSE` file.
