"""Unit tests for backup, healthcheck, self-mod audit, and cost budget."""

import os

import pytest

# ─────────────────────────────────────────────
# backup
# ─────────────────────────────────────────────


def test_backup_copies_state(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "data.bin").write_bytes(b"x" * 100)
    monkeypatch.setattr("backup.backup_root", lambda: str(tmp_path / "backups"))
    monkeypatch.setattr("backup._sources", lambda: [("data", str(src))])

    import backup

    result = backup.run_backup(label="test")
    assert result["copied"] == ["data"]
    assert os.path.exists(os.path.join(result["backup_dir"], "data", "data.bin"))
    assert result["size_bytes"] == 100


def test_backup_skips_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("backup.backup_root", lambda: str(tmp_path / "backups"))
    monkeypatch.setattr("backup._sources", lambda: [("missing", str(tmp_path / "nope"))])

    import backup

    result = backup.run_backup(label="test")
    assert result["copied"] == []
    assert result["skipped"] == ["missing"]


def test_backup_retention(tmp_path, monkeypatch):
    monkeypatch.setattr("backup.backup_root", lambda: str(tmp_path / "backups"))
    monkeypatch.setattr("backup._sources", lambda: [])
    monkeypatch.setattr("backup.keep_count", lambda: 2)

    import backup

    backup.run_backup(label="a")
    backup.run_backup(label="b")
    backup.run_backup(label="c")
    remaining = backup.list_backups()
    assert len(remaining) == 2
    assert remaining[0]["name"].endswith("_c")


# ─────────────────────────────────────────────
# healthcheck
# ─────────────────────────────────────────────


def test_healthcheck_reports_failures(tmp_path, monkeypatch):
    import healthcheck

    monkeypatch.setattr("healthcheck._check_watchlog", lambda: {"name": "watchlog_db", "ok": True, "detail": "ok"})
    monkeypatch.setattr("healthcheck._check_vector_db", lambda: {"name": "vector_db", "ok": True, "detail": "ok"})
    monkeypatch.setattr(
        "healthcheck._check_weights", lambda: {"name": "nn_weights", "ok": False, "detail": "missing router"}
    )
    monkeypatch.setattr("healthcheck._check_api_keys", lambda: {"name": "api_keys", "ok": True, "detail": "1/5"})
    monkeypatch.setattr("healthcheck._check_rag_folder", lambda: {"name": "rag_folder", "ok": True, "detail": "ok"})
    monkeypatch.setattr(
        "healthcheck._check_self_test_store", lambda: {"name": "self_test_store", "ok": True, "detail": "ok"}
    )
    monkeypatch.setattr("healthcheck._check_internet", lambda: {"name": "internet", "ok": True, "detail": "ok"})
    monkeypatch.setattr("healthcheck.CACHE_SECONDS", 0)

    result = healthcheck.run_healthcheck()
    assert result["ok"] is False
    assert any(not c["ok"] for c in result["checks"])
    text = healthcheck.report_text()
    assert "ISSUES FOUND" in text
    assert "nn_weights" in text


def test_healthcheck_all_ok(tmp_path, monkeypatch):
    import healthcheck

    ok_checks = {
        "_check_watchlog": lambda: {"name": "w", "ok": True, "detail": ""},
        "_check_vector_db": lambda: {"name": "v", "ok": True, "detail": ""},
        "_check_weights": lambda: {"name": "n", "ok": True, "detail": ""},
        "_check_api_keys": lambda: {"name": "k", "ok": True, "detail": ""},
        "_check_rag_folder": lambda: {"name": "r", "ok": True, "detail": ""},
        "_check_self_test_store": lambda: {"name": "s", "ok": True, "detail": ""},
        "_check_internet": lambda: {"name": "i", "ok": True, "detail": ""},
    }
    for name, fn in ok_checks.items():
        monkeypatch.setattr(f"healthcheck.{name}", fn)
    monkeypatch.setattr("healthcheck.CACHE_SECONDS", 0)
    assert healthcheck.run_healthcheck()["ok"] is True


# ─────────────────────────────────────────────
# self-mod audit
# ─────────────────────────────────────────────


def test_self_mod_audit_written(tmp_path, monkeypatch):
    import action_sandbox

    monkeypatch.setattr("action_sandbox.SELF_MOD_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    action_sandbox._log_self_mod_audit("/tmp/some/target.py", "/tmp/backup.bak", "applied")
    entries = action_sandbox.get_self_mod_audit()
    assert len(entries) == 1
    assert entries[0]["target"].endswith("target.py")
    assert entries[0]["outcome"] == "applied"
    assert entries[0]["backup"] == "/tmp/backup.bak"


def test_self_mod_audit_empty(tmp_path, monkeypatch):
    import action_sandbox

    monkeypatch.setattr("action_sandbox.SELF_MOD_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    assert action_sandbox.get_self_mod_audit() == []


# ─────────────────────────────────────────────
# daily cost ledger
# ─────────────────────────────────────────────


def test_daily_cost_ledger(tmp_path, monkeypatch):
    import jarvis_logger

    monkeypatch.setattr("jarvis_logger.COST_DAILY_FILE", str(tmp_path / "cost.jsonl"))
    jarvis_logger.record_daily_cost("2026-08-09", 0.123456)
    jarvis_logger.record_daily_cost("2026-08-09", 0.5)
    jarvis_logger.record_daily_cost("2026-08-08", 0.1)
    assert jarvis_logger.get_daily_cost("2026-08-09") == pytest.approx(0.623456)
    assert jarvis_logger.get_daily_cost("2026-08-08") == pytest.approx(0.1)
    assert jarvis_logger.get_daily_cost("2020-01-01") == 0.0
    days = jarvis_logger.get_cost_by_day(days=7)
    assert days.get("2026-08-09") == pytest.approx(0.6235)


def test_daily_cost_no_file(tmp_path, monkeypatch):
    import jarvis_logger

    monkeypatch.setattr("jarvis_logger.COST_DAILY_FILE", str(tmp_path / "missing.jsonl"))
    assert jarvis_logger.get_daily_cost() == 0.0
    assert jarvis_logger.get_cost_by_day() == {}


def test_daily_budget_exceeded_logic(monkeypatch):
    import brain

    monkeypatch.setattr("brain.JARVIS_DAILY_BUDGET_USD", 1.0)
    monkeypatch.setattr("brain._budget_warned", False)
    monkeypatch.setattr("jarvis_logger.get_daily_cost", lambda *a, **k: 2.0)

    exceeded, spent, limit = brain._daily_budget_exceeded()
    assert exceeded is True
    assert spent == 2.0
    assert limit == 1.0

    monkeypatch.setattr("brain.JARVIS_DAILY_BUDGET_USD", 0.0)
    exceeded, spent, limit = brain._daily_budget_exceeded()
    assert exceeded is False
