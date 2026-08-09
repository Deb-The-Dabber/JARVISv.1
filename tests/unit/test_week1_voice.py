"""Smoke tests for the Week-1 voice/local provider work.

Covers: local_provider module behavior without mlx-lm, hybrid routing
decisions in brain.py (_try_local_routing + voice overrides), and
wakeword.py env configuration.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestLocalProvider:
    def test_ask_local_returns_empty_without_mlx(self):
        from local_provider import ask_local

        try:
            import mlx_lm  # noqa: F401

            pytest.skip("mlx-lm installed; real model path untested here")
        except ImportError:
            assert ask_local("hi there") == ""

    def test_env_flags_parse(self):
        from local_provider import JARVIS_LOCAL_ENABLED, JARVIS_LOCAL_MODEL

        assert isinstance(JARVIS_LOCAL_ENABLED, bool)
        assert "Phi-3" in JARVIS_LOCAL_MODEL or "phi-3" in JARVIS_LOCAL_MODEL


class TestHybridRouting:
    def _import_brain(self):
        os.environ.setdefault("JARVIS_MOCK_PROVIDERS", "1")
        return importlib.import_module("brain")

    def test_use_local_override(self):
        brain = self._import_brain()
        brain.set_local_override(None)
        reply = brain._try_local_routing("use local")
        assert reply is not None and "local" in reply.lower()

    def test_use_cloud_override(self):
        brain = self._import_brain()
        brain.set_local_override(None)
        reply = brain._try_local_routing("use cloud")
        assert reply is not None and "cloud" in reply.lower()

    def test_override_persists_until_reset(self):
        brain = self._import_brain()
        brain._local_override = None
        brain._try_local_routing("use local")
        assert brain._local_override == "local"
        brain.set_local_override(None)
        assert brain._local_override is None

    def test_routing_falls_through_without_local_model(self):
        brain = self._import_brain()
        brain._local_override = None
        try:
            import mlx_lm  # noqa: F401

            pytest.skip("mlx-lm installed; local may be usable")
        except ImportError:
            # No local model → routing should return None (continue to cloud)
            assert brain._try_local_routing("hello there") is None


class TestWakewordConfig:
    def test_env_threshold_parses(self, monkeypatch):
        monkeypatch.setenv("JARVIS_WAKE_THRESHOLD", "0.7")
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "wakeword", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "wakeword.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.SENSITIVITY == 0.7
