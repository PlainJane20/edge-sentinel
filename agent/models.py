"""Shared types."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Action(str, Enum):
    ignore = "ignore"
    log = "log"
    alert = "alert"
    shutdown = "shutdown"


class Reading(BaseModel):
    device_id: str
    temperature_c: float
    rssi: int = 0
    uptime_s: int = 0
    free_heap: int = 0


class Decision(BaseModel):
    action: Action
    anomalous: bool
    source: str  # local-rule | jev | llm | rules-fallback
    confidence: float | None = None
    escalated: bool = False
