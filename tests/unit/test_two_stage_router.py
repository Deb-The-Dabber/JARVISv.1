"""Two-stage fine-grained router unit tests (no NN training, no LLM)."""

import os

os.environ["JARVIS_LOCAL_INTENT_ENABLED"] = "0"
os.environ["JARVIS_LLM_FIRST"] = "0"
os.environ["JARVIS_FINE_CONFIDENCE_TIMER_SET"] = "0.99"
os.environ["JARVIS_FINE_CONFIDENCE_APP_OPEN"] = "0.99"

import numpy as np
import pytest

from jarvis_local_nn.integration import specialist_router as sr
from jarvis_local_nn.models.specialists import export_specialist


@pytest.fixture(autouse=True)
def _reset_router_cache():
    sr.reload_specialists()
    yield
    sr.reload_specialists()


# ── thresholds ──


def test_threshold_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "THRESHOLDS_PATH", tmp_path / "thresholds.json")
    (tmp_path / "thresholds.json").write_text('{"tool_use": {"timer_set": 0.3}}')
    sr.reload_specialists()
    # env JARVIS_FINE_CONFIDENCE_TIMER_SET=0.99 overrides the JSON 0.3
    assert sr.fine_threshold("tool_use", "timer_set") == 0.99


def test_threshold_falls_back_to_bucket_default(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "THRESHOLDS_PATH", tmp_path / "missing.json")
    sr.reload_specialists()
    assert sr.fine_threshold("tool_use", "app_open") == 0.99  # env
    assert sr.fine_threshold("tool_use", "no_such_class") == pytest.approx(0.85)
    assert sr.fine_threshold("self_mod", "fix_own_code") == pytest.approx(0.90)


# ── prediction without weights ──


def test_predict_fine_missing_weights(monkeypatch, tmp_path):
    monkeypatch.setattr(sr, "WEIGHTS_DIR", tmp_path / "missing")
    sr.reload_specialists()
    assert sr.predict_fine("tool_use", "open safari") == (None, 0.0)
    assert sr.predict_fine_gated("tool_use", "open safari") == (None, 0.0)


# ── gating logic ──


def _make_specialist(tmp_path, labels):
    """Train a trivial specialist on random data so weights load & predict."""
    from jarvis_local_nn.tensor import MLP, Adam, cross_entropy

    rng = np.random.default_rng(0)
    X = rng.normal(size=(64, 384))
    y = rng.integers(0, len(labels), 64)
    m = MLP(384, [32], len(labels))
    opt = Adam(m.parameters(), lr=0.05)
    for _ in range(300):
        opt.zero_grad()
        loss = cross_entropy(m(X, training=True), y)
        loss.backward()
        opt.step()
    path = tmp_path / "tool_use.npz"
    export_specialist(m, labels, str(path))
    return path


def test_predict_fine_gated_withholds_low_confidence(tmp_path, monkeypatch):
    _make_specialist(tmp_path, ["timer_set", "app_open"])
    monkeypatch.setattr(sr, "WEIGHTS_DIR", tmp_path)
    monkeypatch.setattr(sr, "THRESHOLDS_PATH", tmp_path / "none.json")
    sr.reload_specialists()

    emb = np.zeros(384)
    emb[:4] = 1.0
    monkeypatch.setattr(sr, "embed_single", lambda text: emb)

    fine, conf = sr.predict_fine_gated("tool_use", "anything")
    assert fine is None or conf >= 0.99  # gated at env 0.99 for both classes
    raw_fine, raw_conf = sr.predict_fine("tool_use", "anything")
    assert raw_fine in ("timer_set", "app_open")
    assert raw_conf > 0.0


def test_gated_accepts_above_threshold(tmp_path, monkeypatch):
    os.environ["JARVIS_FINE_CONFIDENCE_TIMER_SET"] = "0.5"
    os.environ["JARVIS_FINE_CONFIDENCE_APP_OPEN"] = "0.5"
    try:
        _make_specialist(tmp_path, ["timer_set", "app_open"])
        monkeypatch.setattr(sr, "WEIGHTS_DIR", tmp_path)
        monkeypatch.setattr(sr, "THRESHOLDS_PATH", tmp_path / "none.json")
        sr.reload_specialists()

        emb = np.zeros(384)
        emb[:4] = 1.0
        monkeypatch.setattr(sr, "embed_single", lambda text: emb)

        fine, conf = sr.predict_fine_gated("tool_use", "anything")
        assert fine in ("timer_set", "app_open")
        assert conf >= 0.5
    finally:
        os.environ.pop("JARVIS_FINE_CONFIDENCE_TIMER_SET", None)
        os.environ.pop("JARVIS_FINE_CONFIDENCE_APP_OPEN", None)


# ── brain integration ──


def test_classify_clears_fine_intent_between_calls():
    import brain

    brain.classify_intent("some text that falls through to keywords")
    assert brain.get_last_fine_intent() == (None, 0.0)


def test_get_last_fine_intent_not_stale_after_clear():
    from brain import _clear_fine_intent, _local_fine_predict

    _local_fine_predict("open safari", "tool_use")
    _clear_fine_intent()
    assert brain_get_last_fine() is None


def brain_get_last_fine():
    import brain

    return brain.get_last_fine_intent()[0]


def test_local_fine_predict_bad_bucket_is_safe():
    import brain

    fine, conf = brain._local_fine_predict("open safari", "not_a_bucket")
    assert fine is None
    assert conf == 0.0
    assert brain.get_last_fine_intent() == (None, 0.0)


def test_fine_prefetch_mapping_only_safe_tools():
    from brain import _FINE_PREFETCH

    assert set(_FINE_PREFETCH) == {"weather_current", "sys_info", "disk_usage"}
