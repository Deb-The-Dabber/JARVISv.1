import datetime
import os
import queue
import sqlite3
import threading
import time

DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_priority.db")

# ─────────────────────────────────────────────
# PRIORITY LEVELS
# ─────────────────────────────────────────────
CRITICAL = 10  # Always speak, interrupt if needed
HIGH     = 7   # Speak if user active
MEDIUM   = 4   # Speak max once per hour
LOW      = 1   # Silent, mention in recap only

# Base priorities for each alert type
BASE_PRIORITIES = {
    # CRITICAL — time sensitive
    "calendar_5min":     CRITICAL,
    "calendar_15min":    CRITICAL,
    "security":          CRITICAL,
    "internet_down":     HIGH,

    # HIGH — important but not urgent
    "cpu_spike":         HIGH,
    "ram_high":          HIGH,
    "disk_low":          HIGH,
    "rain_incoming":     HIGH,
    "storm_incoming":    CRITICAL,

    # MEDIUM — useful but not urgent
    "app_open_long":     MEDIUM,
    "evening_summary":   MEDIUM,
    "startup_briefing":  MEDIUM,

    # LOW — background noise
    "downloads_large":   LOW,
    "desktop_clutter":   LOW,
    "weather_update":    LOW,
}

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _connect() as conn:
        # Alert history — track what was spoken and if user responded
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                priority INTEGER NOT NULL,
                spoken INTEGER DEFAULT 0,
                acknowledged INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        # Notifications inbox — all alerts persist here; MEDIUM/LOW are pull-only
        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                priority INTEGER NOT NULL,
                read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        # Learned priorities — adjusted based on user behavior
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_priorities (
                alert_type TEXT PRIMARY KEY,
                base_priority INTEGER NOT NULL,
                adjusted_priority REAL NOT NULL,
                ignore_count INTEGER DEFAULT 0,
                ack_count INTEGER DEFAULT 0,
                last_updated TEXT NOT NULL
            )
        """)
        conn.commit()


def log_alert(alert_type: str, message: str, priority: int, spoken: bool = False):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO alert_history (alert_type, message, priority, spoken, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (alert_type, message, priority, int(spoken),
             datetime.datetime.now().isoformat())
        )
        conn.commit()


def add_notification(alert_type: str, message: str, priority: int):
    """Persist an alert to the notifications inbox."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO notifications (alert_type, message, priority, read, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (alert_type, message, priority, datetime.datetime.now().isoformat())
        )
        conn.commit()


def get_notifications(unread_only: bool = True, limit: int = 50) -> list[dict]:
    """Fetch notifications from the inbox."""
    with _connect() as conn:
        if unread_only:
            rows = conn.execute(
                "SELECT id, alert_type, message, priority, read, created_at "
                "FROM notifications WHERE read = 0 ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, alert_type, message, priority, read, created_at "
                "FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
    return [
        {"id": r[0], "alert_type": r[1], "message": r[2],
         "priority": r[3], "read": bool(r[4]), "created_at": r[5]}
        for r in rows
    ]


def mark_notification_read(notification_id: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE notifications SET read = 1 WHERE id = ?",
            (notification_id,)
        )
        conn.commit()


def mark_all_notifications_read():
    with _connect() as conn:
        conn.execute("UPDATE notifications SET read = 1 WHERE read = 0")
        conn.commit()


def mark_acknowledged(alert_type: str):
    """Call this when user responds to an alert."""
    with _connect() as conn:
        # Mark most recent of this type as acknowledged
        conn.execute("""
            UPDATE alert_history SET acknowledged = 1
            WHERE alert_type = ? AND spoken = 1
            AND id = (SELECT MAX(id) FROM alert_history WHERE alert_type = ? AND spoken = 1)
        """, (alert_type, alert_type))
        # Update learned priorities
        conn.execute("""
            INSERT INTO learned_priorities
                (alert_type, base_priority, adjusted_priority, ack_count, last_updated)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(alert_type) DO UPDATE SET
                ack_count = ack_count + 1,
                adjusted_priority = MIN(10, adjusted_priority + 0.5),
                last_updated = excluded.last_updated
        """, (alert_type,
              BASE_PRIORITIES.get(alert_type, MEDIUM),
              BASE_PRIORITIES.get(alert_type, MEDIUM),
              datetime.datetime.now().isoformat()))
        conn.commit()


def mark_ignored(alert_type: str):
    """Call this when an alert was spoken but user didn't respond."""
    with _connect() as conn:
        conn.execute("""
            INSERT INTO learned_priorities
                (alert_type, base_priority, adjusted_priority, ignore_count, last_updated)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(alert_type) DO UPDATE SET
                ignore_count = ignore_count + 1,
                adjusted_priority = MAX(0.5, adjusted_priority - 0.3),
                last_updated = excluded.last_updated
        """, (alert_type,
              BASE_PRIORITIES.get(alert_type, MEDIUM),
              BASE_PRIORITIES.get(alert_type, MEDIUM),
              datetime.datetime.now().isoformat()))
        conn.commit()


def get_effective_priority(alert_type: str) -> float:
    """Get the current effective priority — base adjusted by learning."""
    base = BASE_PRIORITIES.get(alert_type, MEDIUM)
    with _connect() as conn:
        row = conn.execute(
            "SELECT adjusted_priority FROM learned_priorities WHERE alert_type = ?",
            (alert_type,)
        ).fetchone()
    if row:
        return float(row[0])
    return float(base)


def get_priority_stats() -> list:
    """Get all learned priorities for display."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT alert_type, base_priority, adjusted_priority, "
            "ignore_count, ack_count FROM learned_priorities "
            "ORDER BY adjusted_priority DESC"
        ).fetchall()
    return rows


def was_recently_spoken(alert_type: str, minutes: int = 60) -> bool:
    """Check if this alert type was spoken recently."""
    since = (datetime.datetime.now() -
             datetime.timedelta(minutes=minutes)).isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM alert_history "
            "WHERE alert_type = ? AND spoken = 1 AND created_at > ?",
            (alert_type, since)
        ).fetchone()
    return row[0] > 0

# ─────────────────────────────────────────────
# ALERT QUEUE
# ─────────────────────────────────────────────
# Priority queue — higher priority = spoken first
# Items: (-priority, timestamp, alert_type, message)
_alert_queue = queue.PriorityQueue()
_alert_lock = threading.Lock()
_last_spoken_time = 0.0
_current_alert_type = None  # Track what's pending acknowledgment

# Dedup: map message text -> timestamp, avoid identical alerts in quick succession
_recent_messages = {}
RECENT_MESSAGE_TTL = 120  # seconds — skip same message within this window

MIN_SECONDS_BETWEEN_ALERTS = 30  # Never fire more than 1 alert per 30s

def queue_alert(alert_type: str, message: str, force: bool = False):
    """
    Add an alert to the priority queue.
    force=True bypasses all checks (for CRITICAL alerts).
    CRITICAL/HIGH → push (speak). MEDIUM/LOW → pull (inbox only).
    """
    now = time.time()

    priority = get_effective_priority(alert_type)

    # MEDIUM/LOW → inbox only (pull)
    if priority < HIGH and not force:
        add_notification(alert_type, message, int(priority))
        log_alert(alert_type, message, int(priority), spoken=False)
        return

    # Dedup: skip if exact same message was queued recently
    if not force:
        last_seen = _recent_messages.get(message)
        if last_seen and (now - last_seen) < RECENT_MESSAGE_TTL:
            return

    _recent_messages[message] = now
    # Prune stale entries
    stale = [m for m, t in _recent_messages.items() if now - t > RECENT_MESSAGE_TTL]
    for m in stale:
        _recent_messages.pop(m, None)

    # Skip LOW priority alerts entirely — just log them
    if priority < LOW + 0.5 and not force:
        log_alert(alert_type, message, int(priority), spoken=False)
        return

    # Don't re-queue if spoken recently
    cooldowns = {
        CRITICAL: 5,    # 5 min cooldown for critical
        HIGH: 60,       # 1 hour for high
        MEDIUM: 120,    # 2 hours for medium
        LOW: 480,       # 8 hours for low
    }
    cooldown_mins = cooldowns.get(
        int(priority) if int(priority) in cooldowns else MEDIUM, 60
    )
    if not force and was_recently_spoken(alert_type, minutes=cooldown_mins):
        return

    # Add to queue — negative priority so highest goes first
    timestamp = time.time()
    _alert_queue.put((-priority, timestamp, alert_type, message))


def _should_speak(priority: float, user_active: bool) -> bool:
    """Decide if we should actually speak this alert right now.
    CRITICAL/HIGH → push (speak). MEDIUM/LOW → pull (inbox only)."""
    if priority >= CRITICAL:
        return True
    if priority >= HIGH:
        return True
    return False

# ─────────────────────────────────────────────
# ALERT PROCESSOR
# ─────────────────────────────────────────────
_speak_fn = None
_user_active_fn = None
_processing = False


def init(speak_fn, user_active_fn=None):
    global _speak_fn, _user_active_fn
    _speak_fn = speak_fn
    _user_active_fn = user_active_fn


def _process_queue():
    """Run continuously — fires one alert at a time from queue."""
    global _last_spoken_time, _current_alert_type, _processing
    _processing = True

    while _processing:
        time.sleep(1)  # Check every second

        # Enforce minimum gap between alerts
        if time.time() - _last_spoken_time < MIN_SECONDS_BETWEEN_ALERTS:
            continue

        if _alert_queue.empty():
            continue

        # Get highest priority alert
        try:
            neg_priority, timestamp, alert_type, message = _alert_queue.get_nowait()
        except queue.Empty:
            continue

        priority = -neg_priority

        # Check if user is active
        user_active = True
        if _user_active_fn:
            try:
                user_active = bool(_user_active_fn())
            except Exception:
                pass

        if not _should_speak(priority, user_active):
            # Log as unspoken and skip
            log_alert(alert_type, message, int(priority), spoken=False)
            # Re-queue if high priority — try again later
            if priority >= HIGH:
                _alert_queue.put((neg_priority, timestamp, alert_type, message))
            continue

        # Speak it!
        if _speak_fn:
            try:
                log_alert(alert_type, message, int(priority), spoken=True)
                _speak_fn(message)
                _last_spoken_time = time.time()
                with _alert_lock:
                    _current_alert_type = alert_type

                # Schedule ignore check — if no response in 60s, mark ignored
                def _check_ignored(atype):
                    global _current_alert_type
                    time.sleep(60)
                    with _alert_lock:
                        # If still the current alert type, user ignored it
                        if _current_alert_type == atype:
                            mark_ignored(atype)

                threading.Thread(
                    target=_check_ignored,
                    args=(alert_type,),
                    daemon=True
                ).start()

            except Exception as e:
                print(f"  Priority engine speak error: {e}")


def start():
    """Start the priority alert processor."""
    t = threading.Thread(target=_process_queue, daemon=True)
    t.start()
    print("  Priority engine started.")


def stop():
    global _processing
    _processing = False


def acknowledge(alert_type: str = None):
    """Call when user responds to Jarvis — marks current alert acknowledged."""
    global _current_alert_type
    with _alert_lock:
        target = alert_type or _current_alert_type
        if target:
            mark_acknowledged(target)
            _current_alert_type = None


# Initialize DB on import
init_db()
