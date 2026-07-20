import datetime
import json
import logging
import os
import re
import sqlite3
import threading
import time

from tools import TOOL_REGISTRY

DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_triggers.db")
_LOG = logging.getLogger("triggers")

_triggers = {}
_scheduler_thread: threading.Thread | None = None
_scheduler_stop = threading.Event()
_scheduler_lock = threading.Lock()
_initialized = False


def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                trigger_type TEXT NOT NULL CHECK(trigger_type IN ('cron','interval','once','event')),
                schedule TEXT NOT NULL,
                action_type TEXT NOT NULL CHECK(action_type IN ('workflow','tool','prompt')),
                action_target TEXT NOT NULL,
                action_params TEXT NOT NULL DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1,
                last_fired TEXT,
                last_error TEXT,
                next_fire TEXT,
                fire_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trigger_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_id INTEGER NOT NULL,
                triggered_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                error TEXT,
                duration_ms INTEGER,
                FOREIGN KEY (trigger_id) REFERENCES triggers(id)
            );
        """)
        conn.commit()


def _row_to_dict(row: tuple, cols: list[str]) -> dict:
    return {col: val for col, val in zip(cols, row)}


def _load_triggers():
    global _triggers
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM triggers").fetchall()
        _triggers = {r["id"]: dict(r) for r in rows}


def create_trigger(name: str, trigger_type: str, schedule: str, action_type: str, action_target: str, action_params: dict | None = None, description: str = "") -> dict:
    now = datetime.datetime.now().isoformat()
    params = json.dumps(action_params or {})
    with _connect() as conn:
        try:
            cur = conn.execute(
                """INSERT INTO triggers (name, description, trigger_type, schedule,
                   action_type, action_target, action_params, next_fire, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (name, description, trigger_type, schedule, action_type, action_target, params, _compute_next_fire(trigger_type, schedule), now),
            )
            trigger_id = cur.lastrowid
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Trigger name '{name}' already exists") from e
    _load_triggers()
    return get_trigger(trigger_id)


def get_trigger(trigger_id: int) -> dict | None:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM triggers WHERE id=?", (trigger_id,)).fetchone()
    return dict(row) if row else None


def list_triggers(enabled_only: bool = False) -> list[dict]:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        if enabled_only:
            rows = conn.execute("SELECT * FROM triggers WHERE enabled=1 ORDER BY name").fetchall()
        else:
            rows = conn.execute("SELECT * FROM triggers ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def update_trigger(trigger_id: int, **kwargs) -> dict:
    allowed = {"name", "description", "trigger_type", "schedule", "action_type", "action_target", "action_params", "enabled"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return get_trigger(trigger_id)

    if "schedule" in updates or "trigger_type" in updates:
        t = get_trigger(trigger_id)
        typ = updates.get("trigger_type", t["trigger_type"])
        sched = updates.get("schedule", t["schedule"])
        updates["next_fire"] = _compute_next_fire(typ, sched)

    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [trigger_id]
    with _connect() as conn:
        conn.execute(f"UPDATE triggers SET {sets} WHERE id=?", values)
        conn.commit()
    _load_triggers()
    return get_trigger(trigger_id)


def delete_trigger(trigger_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM triggers WHERE id=?", (trigger_id,))
        conn.execute("DELETE FROM trigger_history WHERE trigger_id=?", (trigger_id,))
        conn.commit()
    _load_triggers()
    return cur.rowcount > 0


def _parse_interval(s: str) -> int:
    s = s.strip().lower()
    m = re.match(r"^(\d+)\s*(s|sec|second|seconds|m|min|minute|minutes|h|hour|hours|d|day|days)?$", s)
    if not m:
        raise ValueError(f"Invalid interval: {s!r} (use e.g. '30s', '5m', '2h', '1d')")
    val = int(m.group(1))
    unit = (m.group(2) or "s")[0]
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * multipliers[unit]


def _parse_cron(expr: str) -> list:
    parts = expr.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression: {expr!r} (need 5 fields: minute hour day month weekday)")
    return parts


def _cron_field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    parts = field.split(",")
    for p in parts:
        if "/" in p:
            base, step = p.split("/", 1)
            start = int(base) if base != "*" else 0
            if (value - start) % int(step) == 0 and value >= start:
                return True
        elif "-" in p:
            lo, hi = p.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        else:
            if int(p) == value:
                return True
    return False


def _cron_matches(expr: list, dt: datetime.datetime) -> bool:
    min_ok = _cron_field_matches(expr[0], dt.minute)
    hr_ok = _cron_field_matches(expr[1], dt.hour)
    day_ok = _cron_field_matches(expr[2], dt.day)
    mon_ok = _cron_field_matches(expr[3], dt.month)
    cron_wday = (dt.weekday() + 1) % 7
    wday_ok = _cron_field_matches(expr[4], cron_wday)
    return min_ok and hr_ok and day_ok and mon_ok and wday_ok


def _compute_next_fire(trigger_type: str, schedule: str) -> str | None:
    now = datetime.datetime.now()
    if trigger_type == "interval":
        seconds = _parse_interval(schedule)
        return (now + datetime.timedelta(seconds=seconds)).isoformat()
    elif trigger_type == "once":
        try:
            dt = datetime.datetime.fromisoformat(schedule)
            if dt > now:
                return dt.isoformat()
        except ValueError:
            pass
        return None
    elif trigger_type == "cron":
        expr = _parse_cron(schedule)
        for minutes_ahead in range(1, 525600):
            candidate = now + datetime.timedelta(minutes=minutes_ahead)
            if _cron_matches(expr, candidate):
                return candidate.isoformat()
        return None
    return None


def _execute_workflow(name: str, params: dict) -> dict:
    from workflow_engine import run_workflow

    return run_workflow(name, params)


def _execute_tool(tool_name: str, args: dict) -> dict:
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Unknown tool: {tool_name}")
    fn = TOOL_REGISTRY[tool_name]
    result = fn(**args)
    return {"ok": True, "result": str(result) if result is not None else ""}


def _execute_prompt(prompt_text: str) -> dict:
    try:
        from brain import process

        reply = process(prompt_text)
        return {"ok": True, "result": reply}
    except Exception:
        raise


def fire_trigger(trigger_id: int) -> dict:
    trig = get_trigger(trigger_id)
    if not trig:
        raise ValueError(f"Trigger {trigger_id} not found")
    if not trig["enabled"]:
        raise ValueError(f"Trigger {trigger_id} is disabled")

    started = time.time()
    action_params = json.loads(trig["action_params"]) if trig["action_params"] else {}
    error = None
    result = None

    try:
        if trig["action_type"] == "workflow":
            r = _execute_workflow(trig["action_target"], action_params)
            result = r.get("result") or r.get("output") or json.dumps(r)
        elif trig["action_type"] == "tool":
            r = _execute_tool(trig["action_target"], action_params)
            result = r["result"]
        elif trig["action_type"] == "prompt":
            r = _execute_prompt(trig["action_target"])
            result = r["result"]
        else:
            raise ValueError(f"Unknown action type: {trig['action_type']}")
        status = "done"
    except Exception as e:
        status = "error"
        error = str(e)
        result = str(e) if not result else result

    duration_ms = int((time.time() - started) * 1000)
    now = datetime.datetime.now().isoformat()
    next_fire = _compute_next_fire(trig["trigger_type"], trig["schedule"])
    if trig["trigger_type"] == "once":
        enabled = 0
    else:
        enabled = trig["enabled"]

    with _connect() as conn:
        conn.execute(
            """UPDATE triggers SET last_fired=?, last_error=?, next_fire=?,
               enabled=?, fire_count=fire_count+1 WHERE id=?""",
            (now, error, next_fire, enabled, trigger_id),
        )
        conn.execute(
            """INSERT INTO trigger_history (trigger_id, triggered_at, status, result, error, duration_ms)
               VALUES (?,?,?,?,?,?)""",
            (trigger_id, now, status, result, error, duration_ms),
        )
        conn.commit()

    _load_triggers()
    return {"ok": status == "done", "status": status, "result": result, "error": error, "duration_ms": duration_ms, "trigger_id": trigger_id}


def get_trigger_history(trigger_id: int | None = None, limit: int = 50) -> list[dict]:
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        if trigger_id is not None:
            rows = conn.execute("SELECT * FROM trigger_history WHERE trigger_id=? ORDER BY triggered_at DESC LIMIT ?", (trigger_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM trigger_history ORDER BY triggered_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def enable_trigger(trigger_id: int) -> dict:
    return update_trigger(trigger_id, enabled=1)


def disable_trigger(trigger_id: int) -> dict:
    return update_trigger(trigger_id, enabled=0)


def fire_event(event_name: str, event_data: dict | None = None) -> list[dict]:
    results = []
    for trig in list_triggers(enabled_only=True):
        if trig["trigger_type"] == "event" and trig["schedule"] == event_name:
            try:
                result = fire_trigger(trig["id"])
                results.append(result)
            except Exception as e:
                results.append({"ok": False, "error": str(e), "trigger_id": trig["id"]})
    return results


def _scheduler_loop():
    while not _scheduler_stop.is_set():
        try:
            now = datetime.datetime.now()
            for trig in list_triggers(enabled_only=True):
                if trig["trigger_type"] == "event":
                    continue
                if trig["next_fire"]:
                    next_dt = datetime.datetime.fromisoformat(trig["next_fire"])
                    if now >= next_dt:
                        _LOG.info("Firing trigger %s (%s)", trig["id"], trig["name"])
                        try:
                            fire_trigger(trig["id"])
                        except Exception as e:
                            _LOG.error("Trigger %s failed: %s", trig["id"], e)
        except Exception as e:
            _LOG.error("Scheduler error: %s", e)
        _scheduler_stop.wait(15)


def start():
    global _scheduler_thread, _initialized
    if _initialized:
        return
    init_db()
    _load_triggers()
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="trigger-scheduler")
    _scheduler_thread.start()
    _initialized = True
    _LOG.info("Trigger scheduler started")


def stop():
    _scheduler_stop.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
    _LOG.info("Trigger scheduler stopped")
