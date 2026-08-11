"""Unit tests for the Phase 2A routing policy (pure, no network)."""


import routing_policy as rp


def _candidates(extra=None):
    cands = [
        {"provider": "nemotron_ultra", "health": 100, "latency_ms": 1500},
        {"provider": "gemini", "health": 100, "latency_ms": 900},
        {"provider": "groq", "health": 100, "latency_ms": 350},
        {"provider": "nvidia_nim_tier_6", "health": 100, "latency_ms": 2000},
        {"provider": "openrouter", "health": 100, "latency_ms": 4000},
        {"provider": "pollinations", "health": 100, "latency_ms": 5000},
    ]
    if extra:
        cands.extend(extra)
    return cands


# ── Hard eligibility gates ──

class TestHardGates:
    def test_unavailable_provider_is_invalid(self):
        cands = [{"provider": "groq", "health": 100, "available": False}]
        out = rp.score_candidates("coding", cands)
        assert out[0]["status"] == "INVALID"
        assert out[0]["reason"] == "unavailable"

    def test_low_health_provider_is_invalid(self):
        cands = [{"provider": "groq", "health": 20}]
        out = rp.score_candidates("coding", cands)
        assert out[0]["status"] == "INVALID"
        assert out[0]["reason"].startswith("health")

    def test_health_threshold_boundary(self):
        cands = [
            {"provider": "groq", "health": 30},
            {"provider": "gemini", "health": 29.9},
        ]
        out = rp.score_candidates("coding", cands)
        by = {e["provider"]: e["status"] for e in out}
        assert by["groq"] == "eligible"
        assert by["gemini"] == "INVALID"

    def test_all_invalid_when_everyone_gated(self):
        cands = [{"provider": "groq", "health": 5, "available": True}]
        out = rp.score_candidates("coding", cands)
        assert out[0]["status"] == "INVALID"


# ── Scoring determinism / explainability ──

class TestScoring:
    def test_deterministic_order(self):
        out1 = rp.score_candidates("coding", _candidates())
        out2 = rp.score_candidates("coding", _candidates())
        assert [e["provider"] for e in out1] == [e["provider"] for e in out2]

    def test_every_eligible_has_explainable_components(self):
        out = rp.score_candidates("coding", _candidates())
        for e in out:
            if e["status"] == "eligible":
                assert {"capability_fit", "latency_factor", "cost_factor", "health_factor"} <= set(
                    e["components"]
                )
                assert e["score"] > 0

    def test_tie_break_is_alpha_ascending(self):
        cands = [
            {"provider": "aaa", "health": 100, "latency_ms": 500, "price": (10, 10)},
            {"provider": "zzz", "health": 100, "latency_ms": 500, "price": (10, 10)},
            {"provider": "mmm", "health": 100, "latency_ms": 500, "price": (10, 10)},
        ]
        out = rp.score_candidates("chat", cands)
        eligible = [e["provider"] for e in out if e["status"] == "eligible"]
        assert eligible == sorted(eligible)

    def test_scores_are_intent_aware(self):
        far = {"provider": "nvidia_nim_tier_6", "health": 100, "latency_ms": 50000}
        chat_groq = {"provider": "groq", "health": 100, "latency_ms": 100}
        for intent in ("coding", "chat", "tool_use"):
            out = rp.score_candidates(intent, [far, chat_groq])
            scores = {e["provider"]: e["score"] for e in out}
            # both eligible; scores differ per intent
            assert scores["nvidia_nim_tier_6"] != scores["groq"]

    def test_unknown_latency_not_penalized(self):
        a = rp.score_candidates("coding", [{"provider": "groq", "health": 100, "latency_ms": None}])
        assert a[0]["components"]["latency_factor"] == 1.0

    def test_budget_warning_penalizes_paid_providers_only(self):
        cands = _candidates([{"provider": "pollinations", "health": 100, "latency_ms": 5000}])
        normal = {e["provider"]: e["score"] for e in rp.score_candidates("chat", cands)}
        warned = {e["provider"]: e["score"] for e in rp.score_candidates("chat", cands, budget_warning=True)}
        assert normal["nemotron_ultra"] > warned["nemotron_ultra"]
        assert normal["pollinations"] == warned["pollinations"]


# ── Cheap classifier output contract ──

class TestClassifierContract:
    def test_valid_payload_parses(self):
        out = rp.parse_classifier_output(
            '{"intent": "coding", "fine_intent": "debug_code", "complexity": 2, "tool_required": false}'
        )
        assert out == {
            "intent": "coding",
            "fine_intent": "debug_code",
            "complexity": 2,
            "tool_required": False,
        }

    def test_provider_key_is_rejected(self):
        # THE boundary: the cheap classifier must NEVER be able to pick a provider.
        out = rp.parse_classifier_output('{"intent": "coding", "provider": "gemini"}')
        assert out is None

    def test_extra_unknown_keys_rejected(self):
        assert rp.parse_classifier_output('{"intent": "coding", "fine_intent": "x", "bogus": 1}') is None

    def test_garbage_rejected(self):
        assert rp.parse_classifier_output("not json at all") is None
        assert rp.parse_classifier_output("") is None
        assert rp.parse_classifier_output('{"fine_intent": "debug_code"}') is None  # missing intent

    def test_missing_optional_fields_get_defaults(self):
        out = rp.parse_classifier_output('{"intent": "coding", "fine_intent": "debug_code"}')
        assert out["complexity"] == 3
        assert out["tool_required"] is False

    def test_non_json_complexity_coerced(self):
        assert rp.parse_classifier_output(
            '{"intent": "coding", "fine_intent": "x", "complexity": "high"}'
        )["complexity"] == 3


def test_capability_fit_bounds():
    for intent in ("coding", "reasoning", "tool_use", "chat", "automation", "self_mod", "bogus"):
        for profile in rp.PROVIDER_PROFILES.values():
            fit = rp.capability_fit(intent, profile)
            assert 0.0 <= fit <= 1.0
