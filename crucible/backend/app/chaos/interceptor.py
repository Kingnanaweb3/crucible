"""The Crucible interceptor.

Turns a chaos SCENARIO into a `tap` for the victim pipeline. The tap watches for the
target step + event and applies the fault there, recording exactly what it did so the
observer/scorer can analyze it. The victim agents are never modified - Crucible only
sits on the bus between them, which is what makes it workflow-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.chaos.faults import FAULTS


@dataclass
class Scenario:
    fault: str                 # key in FAULTS
    step: str                  # step to target, e.g. "review"
    event: str = "after"       # "before" (corrupt input) or "after" (corrupt output)
    params: dict = field(default_factory=dict)


@dataclass
class Interceptor:
    scenario: Scenario
    log: list = field(default_factory=list)

    def tap(self, event: str, step_name: str, bus: dict) -> None:
        if step_name == self.scenario.step and event == self.scenario.event:
            entry = {
                "step": step_name,
                "event": event,
                "fault": self.scenario.fault,
            }
            self.log.append(entry)
            # may raise (crash faults); the pipeline records that as the step error
            entry["detail"] = FAULTS[self.scenario.fault](bus, self.scenario.params)

    def as_tap(self):
        return self.tap
