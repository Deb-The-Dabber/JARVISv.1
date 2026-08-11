"""Gate for 2A.0: no dead coding providers may appear in the ACTIVE routing
path. DeepSeek v4 Flash (deepseek-ai/deepseek-v4-flash) is EOL on NVIDIA NIM
(verified), so it must not be selectable or referenced by active constants."""

import inspect

import brain
import routing_policy


def test_no_dead_coding_provider_in_active_candidates():
    assert "deepseek" not in (getattr(brain, "DEEPSEEK_MODEL", "") or "").lower(), (
        "dead provider constant still active"
    )
    assert "deepseek" not in routing_policy.PROVIDER_PROFILES, (
        "dead provider still has a capability profile"
    )
    assert not hasattr(brain, "ask_deepseek"), (
        "dead ask_deepseek function still present and reachable"
    )


def _code_without_docstring(fn) -> str:
    src = inspect.getsource(fn)
    try:
        node = inspect.unwrap(fn).__doc__ or ""
        if node:
            src = src.replace(f'"""{node}"""', "").replace(f"'''{node}'''", "")
    except Exception:
        pass
    return src


def test_deepseek_not_in_primary_select_options():
    src = _code_without_docstring(brain._select_primary_provider)
    assert "deepseek" not in src.lower()


def test_deepseek_not_in_arbitration_or_fallback_branch():
    src = _code_without_docstring(brain.ask_with_tools)
    assert "deepseek" not in src.lower()
    assert "DEEPSEEK" not in src.upper()
