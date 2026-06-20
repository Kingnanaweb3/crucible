"""Resilience scorer for Crucible.

Compares a fault-injected run against the clean baseline and produces a resilience
score plus the evidence behind it: did the workflow DETECT the fault, did the final
OUTCOME stay correct, did it ESCALATE when it should have, and how far did the fault
spread (BLAST RADIUS). The gpt-oss-120b judge adds a severity rating and a plain
explanation of any corruption.
"""

from __future__ import annotations

import json

from app.integrations.llm import ask


def _safe_json(text: str, fallback: dict) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b != -1 and b > a:
        t = t[a : b + 1]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return fallback


def _judge_corruption(clean_resolution: dict, chaos_resolution: dict, injected: list) -> dict:
    system = (
        "You are a QA judge for an AI workflow. You are given the CORRECT outcome and "
        "the ACTUAL outcome after a fault was injected. Decide whether the actual outcome "
        "is a harmful corruption of the correct one. Respond with ONLY a JSON object: "
        '{"corrupted": true|false, "severity": "none|low|medium|high", '
        '"explanation": "one sentence"}.'
    )
    prompt = (
        f"FAULT INJECTED: {json.dumps(injected)}\n\n"
        f"CORRECT (clean) outcome: {json.dumps(clean_resolution)}\n"
        f"ACTUAL (after fault) outcome: {json.dumps(chaos_resolution)}"
    )
    raw = ask("judge", prompt, system=system, temperature=0)
    return _safe_json(
        raw, {"corrupted": None, "severity": "unknown", "explanation": raw[:200]}
    )


def _blast_radius(clean: dict, chaos: dict, injected_step: str | None) -> int:
    chaos_steps = [t["step"] for t in chaos.get("_trace", [])]
    clean_snaps = {t["step"]: t.get("bus_snapshot") for t in clean.get("_trace", [])}
    chaos_snaps = {t["step"]: t.get("bus_snapshot") for t in chaos.get("_trace", [])}
    if injected_step in chaos_steps:
        downstream = chaos_steps[chaos_steps.index(injected_step) + 1 :]
    else:
        downstream = chaos_steps
    return sum(1 for s in downstream if clean_snaps.get(s) != chaos_snaps.get(s))


def _verdict(score: int, outcome_changed: bool, detected: bool, esc_fail: bool) -> str:
    if outcome_changed and not detected and esc_fail:
        return "SILENT CORRUPTION - wrong outcome, no detection, no escalation."
    if outcome_changed and not detected:
        return "Silent outcome change - the fault altered the result without surfacing."
    if detected and not outcome_changed:
        return "Resilient - fault surfaced and the outcome held."
    if score >= 70:
        return "Mostly resilient."
    return "Degraded - review the breakdown."


def score_run(clean: dict, chaos: dict, injected: list) -> dict:
    clean_res = clean.get("resolution", {})
    chaos_res = chaos.get("resolution", {})
    chaos_trace = chaos.get("_trace", [])
    injected_step = injected[0]["step"] if injected else None

    detected = any(t.get("error") for t in chaos_trace)

    clean_final = clean_res.get("final_decision")
    chaos_final = chaos_res.get("final_decision")
    outcome_changed = clean_final != chaos_final

    clean_escalated = bool(clean_res.get("escalated"))
    chaos_escalated = bool(chaos_res.get("escalated"))
    escalation_failure = clean_escalated and not chaos_escalated

    blast = _blast_radius(clean, chaos, injected_step)
    judge = _judge_corruption(clean_res, chaos_res, injected)

    integrity = 0 if outcome_changed else 40
    detection = 30 if detected else 0
    escalation = 0 if escalation_failure else 30
    score = integrity + detection + escalation

    return {
        "resilience_score": score,
        "verdict": _verdict(score, outcome_changed, detected, escalation_failure),
        "detected": detected,
        "outcome_changed": outcome_changed,
        "escalation_failure": escalation_failure,
        "blast_radius": blast,
        "clean_final": clean_final,
        "chaos_final": chaos_final,
        "judge": judge,
        "breakdown": {
            "outcome_integrity": integrity,
            "detection": detection,
            "escalation": escalation,
        },
    }
