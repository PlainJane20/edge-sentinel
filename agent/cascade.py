"""Decision cascade.

1. Local hard limits decide critical readings with no model in the loop.
2. Jev (fast, typed) decides the rest. If its confidence is below the threshold
   or unavailable, the reading is escalated.
3. Escalation goes to an LLM when configured, otherwise to the rule-based result.

A failure in any model layer degrades to the rules, never to "no decision".
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from models import Action, Decision, Reading

log = logging.getLogger("edge-sentinel.cascade")

# Single source of truth: the rules, the local hard limit and the model prompt
# all read these, so they cannot drift apart. Jev needs the policy spelled out
# in its question; without it, it guesses with near-uniform probabilities.
TEMP_SHUTDOWN_C = 90
TEMP_ALERT_C = 75
HEAP_ALERT_B = 20_000
TEMP_LOG_C = 60
RSSI_LOG_DBM = -85

INSTRUCTIONS = (
    "You monitor an ESP32 sensor node. Given a reading as JSON, decide the action: "
    "ignore (normal), log (slightly unusual), alert (needs a human), "
    "shutdown (hardware at risk). "
    f"Rules: shutdown if temperature_c >= {TEMP_SHUTDOWN_C}. "
    f"alert if temperature_c >= {TEMP_ALERT_C} or free_heap < {HEAP_ALERT_B}. "
    f"log if temperature_c >= {TEMP_LOG_C} or rssi < {RSSI_LOG_DBM}. "
    "Otherwise ignore."
)

JevFn = Callable[[Reading], "tuple[Action, float | None]"]
LlmFn = Callable[[Reading], Action]


def hard_limit(r: Reading) -> Action | None:
    """Deterministic safety floor. Mirrors the threshold compiled into firmware."""
    return Action.shutdown if r.temperature_c >= TEMP_SHUTDOWN_C else None


def rules(r: Reading) -> Action:
    if r.temperature_c >= TEMP_SHUTDOWN_C:
        return Action.shutdown
    if r.temperature_c >= TEMP_ALERT_C or (r.free_heap and r.free_heap < HEAP_ALERT_B):
        return Action.alert
    if r.temperature_c >= TEMP_LOG_C or r.rssi < RSSI_LOG_DBM:
        return Action.log
    return Action.ignore


def _decision(action: Action, source: str, conf=None, escalated=False) -> Decision:
    return Decision(
        action=action,
        anomalous=action in (Action.alert, Action.shutdown),
        source=source,
        confidence=conf,
        escalated=escalated,
    )


def make_cascade(jev: JevFn | None = None, llm: LlmFn | None = None,
                 threshold: float = 0.8) -> Callable[[Reading], Decision]:
    def decide(r: Reading) -> Decision:
        floor = hard_limit(r)
        if floor:
            return _decision(floor, "local-rule", 1.0)

        if jev is None:
            return _decision(rules(r), "rules-fallback")

        try:
            action, conf = jev(r)
        except Exception:
            log.exception("jev failed; using rules")
            return _decision(rules(r), "rules-fallback", escalated=True)

        if conf is not None and conf >= threshold:
            return _decision(action, "jev", conf)

        if llm is not None:
            try:
                return _decision(llm(r), "llm", conf, escalated=True)
            except Exception:
                log.exception("llm failed; using rules")
        return _decision(rules(r), "rules-fallback", conf, escalated=True)

    return decide


def _extract_confidence(result) -> float | None:
    """Read Jev's confidence from the Pydantic AI response.

    The docs show `response.provider_details['confidence']`; the exact value shape
    is unverified, so accept a number or a dict of numbers (use the minimum).
    """
    details = getattr(getattr(result, "response", None), "provider_details", None) or {}
    c = details.get("confidence")
    if isinstance(c, (int, float)):
        return float(c)
    if isinstance(c, dict):
        vals = [v for v in c.values() if isinstance(v, (int, float))]
        return float(min(vals)) if vals else None
    return None


def build_jev(model: str = "jev-latest") -> JevFn:
    from pydantic_ai import Agent
    from pydantic_ai.models.typesafe import TypeSafeModel

    agent = Agent(TypeSafeModel(model), output_type=Action, instructions=INSTRUCTIONS)

    def jev(r: Reading):
        result = agent.run_sync(r.model_dump_json())
        return result.output, _extract_confidence(result)

    return jev


def build_llm(model: str) -> LlmFn:
    from pydantic_ai import Agent

    agent = Agent(model, output_type=Action, instructions=INSTRUCTIONS)
    return lambda r: agent.run_sync(r.model_dump_json()).output


def build_default() -> Callable[[Reading], Decision]:
    jev = llm = None
    try:
        if os.getenv("TYPESAFE_API_KEY"):
            jev = build_jev()
        if os.getenv("ANTHROPIC_API_KEY"):
            llm = build_llm("anthropic:claude-haiku-4-5-20251001")
    except ImportError:
        log.warning("pydantic-ai not installed; running rules only")
    return make_cascade(jev, llm, float(os.getenv("JEV_CONFIDENCE_THRESHOLD", "0.8")))
