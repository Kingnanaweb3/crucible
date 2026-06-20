"""A tiny, transparent pipeline runner for the victim workflow.

Agents are 'steps'. A shared 'bus' (a dict) carries data from one step to the next
- this bus IS the message bus Crucible taps. The optional `tap` hook runs before and
after each step and may inspect or MUTATE the bus (output/input corruption) or RAISE
(to simulate a crash/timeout). Tap calls run inside the per-step try, so an injected
fault that raises is recorded as that step's error and the run continues - letting us
observe blast radius. With no tap, the workflow runs clean (the golden run).
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Callable, Optional

StepFn = Callable[[dict], dict]
Tap = Callable[[str, str, dict], None]  # tap(event, step_name, bus); event: before|after


@dataclass
class Step:
    name: str
    run: StepFn


def run_pipeline(steps: list[Step], initial_bus: dict, tap: Optional[Tap] = None) -> dict:
    bus: dict = dict(initial_bus)
    trace: list[dict] = []

    for step in steps:
        started = time.time()
        error = None
        try:
            if tap:
                tap("before", step.name, bus)
            bus.update(step.run(bus))
            if tap:
                tap("after", step.name, bus)
        except Exception as exc:  # an injected fault (or real failure) lands here
            error = f"{type(exc).__name__}: {exc}"
        elapsed_ms = round((time.time() - started) * 1000)

        trace.append(
            {
                "step": step.name,
                "elapsed_ms": elapsed_ms,
                "error": error,
                "bus_snapshot": copy.deepcopy(
                    {k: v for k, v in bus.items() if not k.startswith("_")}
                ),
            }
        )

    bus["_trace"] = trace
    return bus
