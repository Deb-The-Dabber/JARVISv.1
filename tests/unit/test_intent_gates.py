"""Per-intent confidence gate unit tests (no NN, no LLM — pure env/config logic)."""

import os

os.environ["JARVIS_LOCAL_INTENT_ENABLED"] = "0"
os.environ["JARVIS_LLM_FIRST"] = "0"
os.environ["JARVIS_LOCAL_INTENT_CONFIDENCE"] = "0.85"
os.environ["JARVIS_LOCAL_INTENT_CONFIDENCE_CHAT"] = "0.80"

from brain import JARVIS_LOCAL_INTENT_CONFIDENCE, _local_intent_threshold


def test_per_intent_gate_uses_env():
    assert _local_intent_threshold("chat") == 0.80


def test_per_intent_gate_falls_back_to_global():
    assert _local_intent_threshold("automation") == JARVIS_LOCAL_INTENT_CONFIDENCE
    assert _local_intent_threshold("self_mod") == JARVIS_LOCAL_INTENT_CONFIDENCE


# ---- 2B.2 gate-decision tests (classifiers mocked, no network) ----
import brain  # noqa: E402
from brain import _clear_fine_intent, classify_intent, get_last_classifier_path  # noqa: E402


def _reset():
    brain.conversation_context.intent_cache.clear()
    _clear_fine_intent()


def _mock_nn(monkeypatch, coarse, conf, fine=None, fine_conf=0.0):
    monkeypatch.setattr(brain, "_local_intent_predict", lambda text: (coarse, conf))
    monkeypatch.setattr(brain, "_local_fine_predict", lambda text, c: (fine, fine_conf))
    monkeypatch.setattr(brain, "_local_intent_threshold", lambda intent: 0.85)


def test_confidence_gate_accepts_above_threshold(monkeypatch):
    _reset()
    _mock_nn(monkeypatch, "tool_use", 0.99, fine="browser", fine_conf=0.9)
    assert classify_intent("open safari and search for weather") == "tool_use"
    assert get_last_classifier_path()["path"] == "local_nn"
    assert get_last_classifier_path()["confidence"] == 0.99


def test_confidence_gate_escalates_below_threshold(monkeypatch):
    _reset()
    _mock_nn(monkeypatch, "tool_use", 0.30)
    assert classify_intent("write a python script to parse csv") == "coding"
    assert get_last_classifier_path()["path"] == "keyword"


def test_agreement_gate_escalates_when_fine_withheld(monkeypatch):
    _reset()
    monkeypatch.setattr(brain, "JARVIS_LOCAL_AGREEMENT_GATE", True)
    _mock_nn(monkeypatch, "tool_use", 0.99, fine=None)
    assert classify_intent("write a python script to parse csv") == "coding"
    assert get_last_classifier_path()["path"] == "keyword"


def test_agreement_gate_accepts_when_fine_commits(monkeypatch):
    _reset()
    monkeypatch.setattr(brain, "JARVIS_LOCAL_AGREEMENT_GATE", True)
    _mock_nn(monkeypatch, "tool_use", 0.99, fine="browser", fine_conf=0.95)
    assert classify_intent("open safari and search for weather") == "tool_use"
    assert get_last_classifier_path()["path"] == "local_nn"


def test_agreement_gate_off_accepts_despite_withheld_fine(monkeypatch):
    _reset()
    monkeypatch.setattr(brain, "JARVIS_LOCAL_AGREEMENT_GATE", False)
    _mock_nn(monkeypatch, "tool_use", 0.99, fine=None)
    assert classify_intent("open safari and search for weather") == "tool_use"
    assert get_last_classifier_path()["path"] == "local_nn"


def test_cheap_tool_required_false_escalates(monkeypatch):
    _reset()
    _mock_nn(monkeypatch, None, 0.0)
    monkeypatch.setattr(brain, "JARVIS_ROUTER_CHEAP", True)
    monkeypatch.setattr(brain, "JARVIS_LLM_FIRST", True)
    monkeypatch.setattr(brain, "NVIDIA_NEMOTRON_API_KEY", "")
    monkeypatch.setattr(
        brain, "_cheap_classify",
        lambda text: {"intent": "tool_use", "fine_intent": "browser", "tool_required": False, "confidence": 0.99},
    )
    assert classify_intent("write a python script to parse csv") == "coding"
    assert get_last_classifier_path()["path"] == "keyword"


def test_cheap_tool_required_true_accepts(monkeypatch):
    _reset()
    _mock_nn(monkeypatch, None, 0.0)
    monkeypatch.setattr(brain, "JARVIS_ROUTER_CHEAP", True)
    monkeypatch.setattr(brain, "JARVIS_LLM_FIRST", True)
    monkeypatch.setattr(brain, "NVIDIA_NEMOTRON_API_KEY", "")
    monkeypatch.setattr(
        brain, "_cheap_classify",
        lambda text: {"intent": "tool_use", "fine_intent": "browser", "tool_required": True, "confidence": 0.99},
    )
    assert classify_intent("open safari and search for weather") == "tool_use"
    assert get_last_classifier_path()["path"] == "cheap_groq"
    assert get_last_classifier_path()["confidence"] == 0.99


def test_cheap_agreement_gate_escalates_when_fine_missing(monkeypatch):
    _reset()
    _mock_nn(monkeypatch, None, 0.0)
    monkeypatch.setattr(brain, "JARVIS_LOCAL_AGREEMENT_GATE", True)
    monkeypatch.setattr(brain, "JARVIS_ROUTER_CHEAP", True)
    monkeypatch.setattr(brain, "JARVIS_LLM_FIRST", True)
    monkeypatch.setattr(brain, "NVIDIA_NEMOTRON_API_KEY", "")
    monkeypatch.setattr(
        brain, "_cheap_classify",
        lambda text: {"intent": "coding", "complexity": 2, "tool_required": False, "confidence": 0.9},
    )
    assert classify_intent("write a python script to parse csv") == "coding"
    assert get_last_classifier_path()["path"] == "keyword"
