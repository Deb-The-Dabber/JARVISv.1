import os
import sqlite3
import threading
from datetime import datetime

PUSH_DB = os.path.expanduser("~/.jarvis_push.db")
_devices: list[dict] = []
_devices_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(PUSH_DB), exist_ok=True)
    conn = sqlite3.connect(PUSH_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                platform TEXT NOT NULL DEFAULT 'web',
                name TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                priority INTEGER DEFAULT 3,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                sent_at TEXT,
                error TEXT
            )
        """)
        conn.commit()


def register_device(token: str, platform: str = "web", name: str = "") -> dict:
    with _devices_lock:
        with _get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO devices
                   (token, platform, name, created_at, last_seen)
                   VALUES (?, ?, ?, ?, ?)""",
                (token, platform, name, datetime.now().isoformat(), datetime.now().isoformat()),
            )
            conn.commit()
        return {"status": "registered", "token": token, "platform": platform}


def unregister_device(token: str):
    with _devices_lock:
        with _get_conn() as conn:
            conn.execute("DELETE FROM devices WHERE token = ?", (token,))
            conn.commit()


def get_devices() -> list[dict]:
    with _devices_lock:
        with _get_conn() as conn:
            rows = conn.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
            return [dict(r) for r in rows]


def enqueue_message(message: str, priority: int = 3):
    with _devices_lock:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO outbox (message, priority, status, created_at) VALUES (?, ?, 'pending', ?)",
                (message, priority, datetime.now().isoformat()),
            )
            conn.commit()


def get_pending_messages(limit: int = 20) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM outbox WHERE status = 'pending' ORDER BY priority DESC, created_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_sent(message_id: int, error: str = ""):
    with _get_conn() as conn:
        conn.execute(
            "UPDATE outbox SET status = ?, sent_at = ?, error = ? WHERE id = ?",
            ("sent" if not error else "failed", datetime.now().isoformat(), error, message_id),
        )
        conn.commit()


def send_notification(title: str, body: str, device_token: str = "") -> bool:
    try:
        import requests as req
        response = req.post(
            "https://exp.host/--/api/v2/push/send",
            json={
                "to": device_token or "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
                "title": title[:100],
                "body": body[:200],
                "priority": "high",
            },
            timeout=10,
        )
        return response.status_code == 200
    except Exception:
        return False


def send_pending():
    pending = get_pending_messages()
    devices = get_devices()
    if not pending or not devices:
        return
    for msg in pending:
        for device in devices:
            title = "Jarvis Alert"
            body = msg["message"]
            ok = send_notification(title, body, device["token"])
            mark_sent(msg["id"], error="" if ok else "send failed")
        _flush_old_outbox()


def _flush_old_outbox(max_age_days: int = 7):
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
    with _get_conn() as conn:
        conn.execute("DELETE FROM outbox WHERE created_at < ?", (cutoff,))
        conn.commit()


init_db()
