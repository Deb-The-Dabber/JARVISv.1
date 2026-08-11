"""Unit tests for the self-test oracle + agent (no providers, no network)."""

import json

# ─────────────────────────────────────────────
# findings store
# ─────────────────────────────────────────────


def test_findings_crud(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SELF_TEST_DIR", str(tmp_path))
    from self_test import findings as store

    f = store.Finding(
        severity="warning",
        category="timeout",
        title="Slow response",
        detail="took 130s",
        source="log",
        evidence={"latency": 130.0},
    )
    fid = store.add_finding(f)
    assert len(fid) == 12
    got = store.get_finding(fid)
    assert got["id"] == fid
    assert got["severity"] == "warning"
    assert got["status"] == "open"
    assert len(store.list_findings()) == 1
    assert store.update_finding_status(fid, "confirmed")
    assert store.get_finding(fid)["status"] == "confirmed"
    assert not store.update_finding_status("does-not-exist", "confirmed")
    assert not store.update_finding_status(fid, "bogus")
    assert len(store.list_findings(status="confirmed")) == 1
    assert len(store.list_findings(status="open")) == 0


def test_findings_severity_normalized():
    from self_test.findings import Finding

    assert Finding("bogus", "x", "t").severity == "info"
    assert Finding("critical", "x", "t").severity == "critical"


def test_findings_persist_across_reload(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SELF_TEST_DIR", str(tmp_path))
    from self_test import findings as store

    fid = store.add_finding(store.Finding("info", "empty_reply", "Empty reply", source="log"))
    f2 = store.Finding.from_dict(store.get_finding(fid))
    assert f2.id == fid
    assert f2.title == "Empty reply"


# ─────────────────────────────────────────────
# oracle: heuristic detectors
# ─────────────────────────────────────────────


def test_detect_provider_error():
    from self_test import oracle

    entries = [
        {"ts": "2026-08-09T10:00:00", "type": None, "provider": "gemini", "intent": "chat",
         "error": "503 rate limited", "latency_seconds": 2.0}
    ]
    findings = oracle.detect_from_entries(entries)
    cats = [f.category for f in findings]
    assert "provider_error" in cats


def test_detect_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SELF_TEST_TIMEOUT_SECONDS", "10")
    from self_test import oracle

    assert oracle.timeout_threshold() == 10.0
    entries = [{"ts": "2026-08-09T10:00:00", "provider": "groq", "intent": "chat", "latency_seconds": 42.0}]
    findings = oracle.detect_from_entries(entries)
    assert any(f.category == "timeout" for f in findings)
    assert findings[0].evidence["latency_seconds"] == 42.0


def test_detect_tool_call_error():
    from self_test import oracle

    entries = [
        {"ts": "2026-08-09T10:00:00", "type": "tool_call", "tool": "get_weather", "error": "no such device"}
    ]
    findings = oracle.detect_from_entries(entries)
    assert any(f.category == "tool_error" for f in findings)
    assert "get_weather" in findings[0].title


def test_detect_empty_reply_for_tool_intent():
    from self_test import oracle

    entries = [
        {"ts": "2026-08-09T10:00:00", "intent": "tool_use", "provider": "nemotron_ultra",
         "latency_seconds": 3.0, "reply_preview": ""}
    ]
    findings = oracle.detect_from_entries(entries)
    assert any(f.category == "empty_reply" for f in findings)


def test_load_entries_time_window(tmp_path):
    from datetime import datetime, timedelta

    from self_test import oracle

    p = tmp_path / "jarvis.jsonl"
    with open(p, "w") as f:
        f.write(json.dumps({"ts": "2020-01-01T00:00:00", "intent": "chat"}) + "\n")
        recent = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
        f.write(json.dumps({"ts": recent, "intent": "tool_use"}) + "\n")
    entries = oracle.load_entries(hours=24, path=str(p))
    assert len(entries) == 1
    assert entries[0]["intent"] == "tool_use"


# ─────────────────────────────────────────────
# oracle: LLM triage
# ─────────────────────────────────────────────


def test_llm_parse_issues(monkeypatch):
    from self_test import oracle

    def fake_ask(prompt):
        assert "junk@example.com" not in prompt  # PII redacted
        return "[warning] get_weather returned empty data\n[critical] timeout in ask_with_tools\nnoise line\n"

    monkeypatch.setattr(oracle, "_ask_llm", fake_ask)
    entries = [
        {"ts": "2026-08-09T10:00:00", "intent": "chat", "provider": "x",
         "user_message_preview": "hi junk@example.com", "reply_preview": "hello"}
    ]
    findings = oracle.analyze_with_llm(entries, hours=24)
    assert len(findings) == 2
    assert findings[0].category == "llm_review"
    assert findings[0].severity == "warning"
    assert findings[1].severity == "critical"


def test_llm_no_issues(monkeypatch):
    from self_test import oracle

    monkeypatch.setattr(oracle, "_ask_llm", lambda prompt: "NO ISSUES")
    entries = [{"ts": "2026-08-09T10:00:00", "intent": "chat", "provider": "x"}]
    assert oracle.analyze_with_llm(entries) == []


def test_llm_unparsed_fallback(monkeypatch):
    from self_test import oracle

    monkeypatch.setattr(oracle, "_ask_llm", lambda prompt: "everything is fine")
    entries = [{"ts": "2026-08-09T10:00:00", "intent": "chat", "provider": "x"}]
    findings = oracle.analyze_with_llm(entries)
    assert len(findings) == 1
    assert findings[0].title.startswith("LLM review")


def test_llm_error_handled(monkeypatch):
    from self_test import oracle

    def boom(prompt):
        raise RuntimeError("provider down")

    monkeypatch.setattr(oracle, "_ask_llm", boom)
    entries = [{"ts": "2026-08-09T10:00:00", "intent": "chat", "provider": "x"}]
    findings = oracle.analyze_with_llm(entries)
    assert len(findings) == 1
    assert "unavailable" in findings[0].title


# ─────────────────────────────────────────────
# agent: command parsing + status
# ─────────────────────────────────────────────


def test_handle_command_unknown():
    from self_test.agent import handle_command

    assert "Self-test commands" in handle_command("test the mic")


def test_handle_command_status_no_run(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SELF_TEST_DIR", str(tmp_path))
    from self_test.agent import handle_command

    out = handle_command("test status")
    assert "Idle" in out


def test_handle_command_start(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SELF_TEST_DIR", str(tmp_path))
    import self_test.agent as agent_mod

    called = {}

    def fake_run(self, hours=None, use_llm=None):
        called["hours"] = hours
        called["use_llm"] = use_llm
        return "started"

    monkeypatch.setattr(agent_mod.SelfTestAgent, "run", fake_run)
    assert "started" in agent_mod.handle_command("test yourself")
    assert "started" in agent_mod.handle_command("run a self test")
    assert "started" in agent_mod.handle_command("check your code for bugs")
    out = agent_mod.handle_command("test logs")
    assert called["use_llm"] is False
    assert "started" in out


def test_handle_command_confirm(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_SELF_TEST_DIR", str(tmp_path))
    import self_test.agent as agent_mod
    from self_test.findings import Finding, add_finding, get_finding

    fid = add_finding(Finding("warning", "timeout", "Slow", source="log"))
    assert "confirmed" in agent_mod.handle_command(f"confirm bug {fid}")
    assert get_finding(fid)["status"] == "confirmed"
    assert "dismissed" in agent_mod.handle_command(f"test dismiss {fid}")
    assert get_finding(fid)["status"] == "dismissed"


def test_report_formatting(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SELF_TEST_DIR", str(tmp_path))
    import self_test.agent as agent_mod
    from self_test.findings import Finding, add_finding, add_run

    add_finding(Finding("warning", "timeout", "Slow response", source="log"))
    add_run(
        {"run_id": "abc", "entries_scanned": 5, "findings": 1, "heuristic": 1, "llm": 0,
         "started_at": "2026-08-09T10:00:00"}
    )
    report = agent_mod.get_agent().report()
    assert "Self-test report" in report
    assert "Slow response" in report
    hist = agent_mod.get_agent().history_text()
    assert "abc" in hist
