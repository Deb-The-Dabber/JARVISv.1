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
