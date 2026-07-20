import datetime
import os
import sqlite3

DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_watchlog.db")


def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                event TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS screen_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                frontmost_app TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def log_event(category: str, event: str, detail: str = None):
    """Log any event Jarvis notices."""
    with _connect() as conn:
        conn.execute("INSERT INTO events (category, event, detail, created_at) VALUES (?, ?, ?, ?)", (category, event, detail, datetime.datetime.now().isoformat()))
        conn.commit()


def log_screen(description: str, frontmost_app: str = None):
    """Log a screen snapshot description."""
    with _connect() as conn:
        conn.execute("INSERT INTO screen_snapshots (description, frontmost_app, created_at) VALUES (?, ?, ?)", (description, frontmost_app, datetime.datetime.now().isoformat()))
        conn.commit()


def get_events_since(hours: int = 8):
    """Get all events from the last N hours."""
    since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat()
    with _connect() as conn:
        rows = conn.execute("SELECT category, event, detail, created_at FROM events WHERE created_at > ? ORDER BY created_at ASC", (since,)).fetchall()
    return rows


def get_screen_snapshots_since(hours: int = 8):
    """Get screen snapshots from last N hours."""
    since = (datetime.datetime.now() - datetime.timedelta(hours=hours)).isoformat()
    with _connect() as conn:
        rows = conn.execute("SELECT description, frontmost_app, created_at FROM screen_snapshots WHERE created_at > ? ORDER BY created_at ASC", (since,)).fetchall()
    return rows


def build_recap(hours: int = 8) -> str:
    """Build a recap string of everything that happened."""
    events = get_events_since(hours)
    snapshots = get_screen_snapshots_since(hours)

    if not events and not snapshots:
        return f"Nothing notable happened in the last {hours} hours."

    lines = []

    if events:
        lines.append(f"Events in the last {hours} hours:")
        for category, event, detail, ts in events:
            time_str = ts[11:16]  # HH:MM
            line = f"  [{time_str}] {category}: {event}"
            if detail:
                line += f" — {detail}"
            lines.append(line)

    if snapshots:
        lines.append(f"\nScreen activity ({len(snapshots)} snapshots):")
        # Just show first and last to keep it concise
        if snapshots:
            first = snapshots[0]
            last = snapshots[-1]
            lines.append(f"  [{first[2][11:16]}] {first[1] or 'Unknown'}: {first[0][:100]}")
            if len(snapshots) > 1:
                lines.append(f"  [{last[2][11:16]}] {last[1] or 'Unknown'}: {last[0][:100]}")
            if len(snapshots) > 2:
                lines.append(f"  ...and {len(snapshots) - 2} more snapshots")

    return "\n".join(lines)


def clear_old_logs(days: int = 7):
    """Clean up logs older than N days."""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM screen_snapshots WHERE created_at < ?", (cutoff,))
        conn.commit()


# Initialize on import
init_db()
