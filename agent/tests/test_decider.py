import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cascade import make_cascade, rules
from models import Action, Reading


def r(temp, rssi=-50, heap=100_000):
    return Reading(device_id="x", temperature_c=temp, rssi=rssi, free_heap=heap)


def test_rules_bands():
    assert rules(r(40)) == Action.ignore
    assert rules(r(65)) == Action.log
    assert rules(r(80)) == Action.alert
    assert rules(r(40, heap=10_000)) == Action.alert
    assert rules(r(95)) == Action.shutdown


def test_no_models_uses_rules():
    d = make_cascade()(r(80))
    assert d.action == Action.alert and d.source == "rules-fallback"


def test_hard_limit_skips_models():
    called = []
    jev = lambda x: called.append(1) or (Action.ignore, 0.99)
    d = make_cascade(jev)(r(95))
    assert d.action == Action.shutdown and d.source == "local-rule" and not called


def test_confident_jev_wins():
    d = make_cascade(lambda x: (Action.log, 0.95))(r(80))
    assert d.action == Action.log and d.source == "jev" and not d.escalated


def test_low_confidence_escalates_to_llm():
    d = make_cascade(lambda x: (Action.log, 0.4), lambda x: Action.alert)(r(65))
    assert d.action == Action.alert and d.source == "llm" and d.escalated


def test_missing_confidence_escalates():
    d = make_cascade(lambda x: (Action.log, None), lambda x: Action.alert)(r(65))
    assert d.source == "llm"


def test_low_confidence_without_llm_falls_back_to_rules():
    d = make_cascade(lambda x: (Action.ignore, 0.3))(r(80))
    assert d.action == Action.alert and d.source == "rules-fallback" and d.escalated


def test_jev_exception_falls_back_to_rules():
    def boom(x):
        raise RuntimeError("down")
    d = make_cascade(boom)(r(80))
    assert d.action == Action.alert and d.source == "rules-fallback"
