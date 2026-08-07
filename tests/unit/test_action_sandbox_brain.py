import os

import pytest

import action_sandbox as ax
import brain
import file_sandbox as fs
import safety


@pytest.fixture(autouse=True)
def _cleanup(monkeypatch):
    brain._turn_memo_cache.clear()
    brain.clear_pending_safe()
    fs.clear_pending()
    ax.clear_typed_pending()
    safety.reset_session()
    monkeypatch.setattr("tts.speak", lambda *a, **k: None)
    monkeypatch.setattr(ax, "auto_proceed", lambda timeout=3.0: True)
    yield
    brain._turn_memo_cache.clear()
    brain.clear_pending_safe()
    fs.clear_pending()
    ax.clear_typed_pending()
    safety.reset_session()


BRAIN_PATH = os.path.join(ax.JARVIS_ROOT, "brain.py")


def test_selfmod_gutted_brain_refused():
    before = open(BRAIN_PATH).read()
    result = brain._execute_tool(
        "modify_own_tool",
        {"tool_file": "brain.py", "change_description": "replace with stub", "new_code": "print('x')"},
    )
    assert "refused" in result.lower()
    assert not ax.has_typed_pending()
    assert open(BRAIN_PATH).read() == before


def test_selfmod_write_noop_returns_no_change(tmp_path):
    result = brain._execute_tool("write_file", {"path": BRAIN_PATH, "content": open(BRAIN_PATH).read()})
    assert "No change needed" in result
    assert not ax.has_typed_pending()


def test_selfmod_write_stages_typed_confirm(tmp_path):
    before = open(BRAIN_PATH).read()
    content = before + "\n# sandbox test marker\n"
    result = brain._execute_tool("write_file", {"path": BRAIN_PATH, "content": content})
    assert "Type: confirm self-modify brain.py" in result
    assert ax.has_typed_pending()
    assert open(BRAIN_PATH).read() == before
    ax.clear_typed_pending()
    brain.clear_pending_safe()


def test_run_python_preview_then_real_execution():
    msg = brain._execute_tool("run_python", {"code": "print(2+2)"})
    assert "run it for real" in msg
    assert brain.has_pending_safe()
    out = brain.execute_pending_safe()
    assert "4" in out


def test_run_terminal_blocked_before_preview():
    msg = brain._execute_tool("run_terminal_command", {"command": "rm -rf /"})
    assert "Command blocked" in msg
    assert not brain.has_pending_safe()
    assert not ax.has_typed_pending()


def test_run_terminal_sandboxed_executes_for_real():
    msg = brain._execute_tool("run_terminal_command", {"command": "echo sandbox-outside-ok"})
    assert "run it for real" in msg
    assert brain.has_pending_safe()
    out = brain.execute_pending_safe()
    assert "sandbox-outside-ok" in out


def test_intent_preview_confirms_then_executes(monkeypatch):
    calls = []

    def fake_navigate(url, browser="default"):
        calls.append(url)
        return f"navigated to {url}"

    brain.TOOL_REGISTRY["browser_navigate"] = fake_navigate
    try:
        msg = brain._execute_tool("browser_navigate", {"url": "https://example.com"})
        assert "proceed for real" in msg
        assert brain.has_pending_safe()
        out = brain.execute_pending_safe()
        assert out == "navigated to https://example.com"
        assert calls == ["https://example.com"]
        out2 = brain._execute_tool("browser_navigate", {"url": "https://example.org"})
        assert out2 == "navigated to https://example.org"
        assert calls == ["https://example.com", "https://example.org"]
    finally:
        brain.TOOL_REGISTRY.pop("browser_navigate", None)


def test_file_write_diff_sandbox(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("old content\n")
    msg = brain._execute_tool("write_file", {"path": str(target), "content": "new content\n"})
    assert "awaits your approval" in msg
    assert fs.has_pending()
    assert brain.has_pending_safe()
    out = brain.execute_pending_safe()
    assert target.read_text() == "new content\n"
    assert "Wrote" in out


def test_process_typed_confirm_applies(monkeypatch):
    target = os.path.join(ax.JARVIS_ROOT, "notes_tmp_test.py")
    base = "x = 1\n" * 50
    open(target, "w").write(base)
    confirmation = ax.confirm_text_for(target)
    ax.stage_typed(
        "modify_own_tool", lambda: None, {"tool_file": target}, confirmation, "PREVIEW",
        {"target": target, "new_code": base + "# applied\n"},
    )
    brain._last_user_message = "original request"
    monkeypatch.setattr(brain, "ask_with_tools", lambda msg: "DONE after re-run")
    brain.conversation[:] = []
    try:
        reply = brain.process(confirmation)
        assert reply == "DONE after re-run"
        assert open(target).read().endswith("# applied\n")
        assert not ax.has_typed_pending()
    finally:
        os.remove(target)


def test_process_typed_deny_cancels(monkeypatch):
    target = os.path.join(ax.JARVIS_ROOT, "notes_tmp_test.py")
    base = "x = 1\n" * 50
    open(target, "w").write(base)
    ax.stage_typed(
        "modify_own_tool", lambda: None, {"tool_file": target}, ax.confirm_text_for(target),
        "PREVIEW", {"target": target, "new_code": base + "# applied\n"},
    )
    try:
        reply = brain.process("no")
        assert "cancel" in reply.lower()
        assert open(target).read() == base
        assert not ax.has_typed_pending()
    finally:
        os.remove(target)


def test_process_yes_without_typed_pending_refused(monkeypatch):
    brain.set_pending_safe("modify_own_tool", lambda: None, {"tool_file": "brain.py"}, "DANGEROUS")
    brain._last_user_message = "modify brain.py"
    monkeypatch.setattr(brain, "ask_with_tools", lambda msg: "SHOULD NOT RUN")
    brain.conversation[:] = []
    reply = brain.process("yes")
    assert "typed confirmation" in reply.lower()
    assert not brain.has_pending_safe()
