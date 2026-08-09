"""Tests for the tiny tensor library + intent router."""

import numpy as np
import pytest

from jarvis_local_nn.models.router import INTENTS, build_router, export_weights, load_weights
from jarvis_local_nn.tensor import MLP, Adam, cross_entropy
from jarvis_local_nn.training.data import SYNTHETIC_TEMPLATES, build_dataset

# ── tensor library ──


def test_mlp_trains():
    m = MLP(4, [6], 3, dropout_p=0.1)
    opt = Adam(m.parameters(), lr=0.01)
    rng = np.random.default_rng(0)
    X = rng.normal(size=(32, 4))
    y = rng.integers(0, 3, 32)
    start = float("inf")
    for _ in range(100):
        opt.zero_grad()
        loss = cross_entropy(m(X, training=True), y)
        loss.backward()
        opt.step()
        start = float(loss.data.item())
    assert start < 1.0


def test_autograd_matches_finite_differences():
    m = MLP(4, [6], 3)
    rng = np.random.default_rng(1)
    X = rng.normal(size=(5, 4))
    y = rng.integers(0, 3, 5)
    loss = cross_entropy(m(X), y)
    loss.backward()
    eps = 1e-6
    max_err = 0.0
    for p in m.parameters():
        for idx in np.ndindex(p.data.shape):
            orig = p.data[idx]
            p.data[idx] = orig + eps
            l_plus = cross_entropy(m(X), y).data.item()
            p.data[idx] = orig - eps
            l_minus = cross_entropy(m(X), y).data.item()
            p.data[idx] = orig
            max_err = max(max_err, abs((l_plus - l_minus) / (2 * eps) - p.grad[idx]))
    assert max_err < 1e-5


# ── model save/load ──


def test_export_load_roundtrip(tmp_path):
    m1 = build_router(seed=7)
    path = str(tmp_path / "router.npz")
    export_weights(m1, path)
    loaded = load_weights(path)
    assert loaded["hidden"] == [128]
    assert set(loaded["weights"]) == {"layer0_w", "layer0_b", "head_w", "head_b"}
    assert loaded["weights"]["layer0_w"].shape == (384, 128)
    assert loaded["weights"]["head_w"].shape == (128, len(INTENTS))


def test_load_weights_rejects_wrong_labels(tmp_path):
    import numpy as np

    path = str(tmp_path / "bad.npz")
    np.savez_compressed(
        path,
        arch_in=np.array([384]),
        arch_hidden=np.array([128]),
        arch_out=np.array([6]),
        labels=np.array(["nope", "chat", "tool_use", "reasoning", "self_mod", "automation"]),
        layer0_w=np.zeros((384, 128)),
        layer0_b=np.zeros(128),
        head_w=np.zeros((128, 6)),
        head_b=np.zeros(6),
    )
    with pytest.raises(ValueError):
        load_weights(path)


# ── integration ──


def test_predict_intent_fallback_without_weights(monkeypatch, tmp_path):
    from jarvis_local_nn.integration import local_router as lr

    monkeypatch.setattr(lr, "WEIGHTS_PATH", tmp_path / "missing.npz")
    lr._router = None
    assert lr.predict_intent("open safari") == (None, 0.0)


def test_router_prediction_uses_trained_weights(tmp_path):
    from jarvis_local_nn.integration import local_router as lr

    m = build_router(seed=3)
    path = str(tmp_path / "router.npz")
    export_weights(m, path)
    router = lr.LocalIntentRouter(path)
    intent, conf = router.predict("some random text")
    assert intent in INTENTS
    assert 0.0 <= conf <= 1.0


# ── training data ──


def test_synthetic_templates_cover_long_tail():
    for intent in ("reasoning", "self_mod", "automation"):
        assert len(SYNTHETIC_TEMPLATES[intent]) >= 10


def test_build_dataset_real_only():
    texts, intents = build_dataset(real_examples=[("open safari", "tool_use"), ("hi", "chat")], synth_per_class=0)
    assert texts == ["open safari", "hi"]
    assert intents == ["tool_use", "chat"]


def test_build_dataset_with_synthetic():
    texts, intents = build_dataset(real_examples=[("open safari", "tool_use")], synth_per_class=5, seed=1)
    counts = {i: intents.count(i) for i in set(intents)}
    assert counts["tool_use"] == 1
    assert counts["reasoning"] == 5
    assert counts["self_mod"] == 5
    assert counts["automation"] == 5


def test_build_dataset_with_learned_tools(tmp_path):
    from jarvis_local_nn.training import data as d

    tools_dir = tmp_path / "learned"
    tools_dir.mkdir()
    (tools_dir / "fix_calendar_20260101_120000.py").write_text(
        "# Learned by Jarvis\n# Task: add a calendar event for 5pm\nimport os\n"
    )
    (tools_dir / "other.py").write_text("x = 1\n")
    original = d.LEARNED_TOOLS_DIR
    d.LEARNED_TOOLS_DIR = tools_dir
    try:
        tasks = d.load_learned_tool_tasks()
        assert tasks == ["add a calendar event for 5pm"]
        texts, intents = d.build_dataset(real_examples=[("hi", "chat")], synth_per_class=0, include_learned=True)
        assert "can you learn how to add a calendar event for 5pm" in texts
        assert intents[texts.index("can you learn how to add a calendar event for 5pm")] == "tool_use"
    finally:
        d.LEARNED_TOOLS_DIR = original


def test_offline_provider_canned_replies():
    from brain import ask_local_offline

    chat_reply = ask_local_offline("hello there", [])
    assert "offline" in chat_reply
    weather_reply = ask_local_offline("what's the weather", ["get_weather_detailed: 72F"])
    assert "72F" in weather_reply
    assert ask_local_offline("", [])  # never raises, always returns str


# ── embedding cache ──


def test_embed_cache_hits_avoid_reembedding(tmp_path, monkeypatch):
    import numpy as np

    from jarvis_local_nn.training import data as d

    monkeypatch.setattr(d, "EMBED_CACHE_PATH", tmp_path / "embeddings.npz")
    monkeypatch.setattr(d, "_embed_cache", None)

    calls = {"n": 0}

    class FakeEmbedder:
        def encode(self, texts, normalize_embeddings=True):
            calls["n"] += 1
            return np.array([[1.0 if i == j else 0.0 for i in range(384)] for j in range(len(texts))])

    monkeypatch.setattr(d, "_get_embedder", lambda: FakeEmbedder())

    out1 = d.embed_texts(["hello world", "goodbye world"])
    out2 = d.embed_texts(["hello world"])
    assert calls["n"] == 1  # second call served from cache
    assert out1[0] == out2[0]

    # new text triggers encode; persisted cache still hit for old ones
    out3 = d.embed_texts(["hello world", "brand new"])
    assert calls["n"] == 2
    assert out3[0] == out1[0]
    assert d.EMBED_CACHE_PATH.exists()


def test_embed_cache_key_deterministic():
    from jarvis_local_nn.training.data import _cache_key

    assert _cache_key("set a timer") == _cache_key("set a timer")
    assert _cache_key("set a timer") != _cache_key("set a tomer")


# ── auto-retrain debounce ──


def test_auto_retrain_disabled_is_noop(monkeypatch):
    import jarvis_local_nn.training.auto_retrain as ar

    monkeypatch.setattr(ar, "AUTO_RETRAIN_ENABLED", False)
    monkeypatch.setattr(ar, "_running", False)
    monkeypatch.setattr(ar, "_pending", False)
    ar.schedule_retrain()
    assert not ar._running
    assert not ar._pending


def test_auto_retrain_debounces_within_window(monkeypatch):
    import jarvis_local_nn.training.auto_retrain as ar

    monkeypatch.setattr(ar, "AUTO_RETRAIN_ENABLED", True)
    monkeypatch.setattr(ar, "RETRAIN_MIN_INTERVAL", 100000)
    monkeypatch.setattr(ar, "_running", False)
    monkeypatch.setattr(ar, "_pending", False)
    monkeypatch.setattr(ar, "_last_run", 12345.0)
    monkeypatch.setattr(ar.time, "time", lambda: 12350.0)
    ar.schedule_retrain()
    assert not ar._running
    assert ar._pending  # too soon → queued, not started
