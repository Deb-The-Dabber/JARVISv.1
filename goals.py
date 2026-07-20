import datetime
import os
import sqlite3
import threading
from difflib import SequenceMatcher

DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_memory.db")

# ─────────────────────────────────────────────
# STATUS VALUES
# ─────────────────────────────────────────────
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

VALID_STATUSES = {STATUS_ACTIVE, STATUS_PAUSED, STATUS_COMPLETED, STATUS_FAILED}

_lock = threading.Lock()


def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                priority INTEGER NOT NULL DEFAULT 5,
                progress_notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_checked TEXT,
                next_check_at TEXT
            )
        """)
        conn.commit()


# ─────────────────────────────────────────────
# CORE CRUD
# ─────────────────────────────────────────────


def _find_similar_goal(title: str, threshold: float = 0.85) -> int | None:
    """Return goal_id if a similar active goal title exists, else None."""
    with _connect() as conn:
        rows = conn.execute("SELECT id, title FROM goals WHERE status = 'active'").fetchall()
        for goal_id, existing_title in rows:
            similarity = SequenceMatcher(None, title.lower(), existing_title.lower()).ratio()
            if similarity >= threshold:
                return goal_id
    return None


def add_goal(title: str, description: str = "", priority: int = 5) -> str:
    """
    Add a new persistent goal.
    priority: 1 (low) to 10 (critical). Default 5.
    Returns a confirmation string with the new goal ID.
    """
    title = (title or "").strip()
    if not title:
        return "Goal title cannot be empty."

    existing_id = _find_similar_goal(title)
    if existing_id:
        return f"Goal #{existing_id} already exists with similar title: '{title}'"

    priority = max(1, min(10, int(priority)))
    now = datetime.datetime.now().isoformat()
    with _lock:
        with _connect() as conn:
            cursor = conn.execute(
                """INSERT INTO goals
                   (title, description, status, priority, progress_notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (title, description or "", STATUS_ACTIVE, priority, "", now, now),
            )
            goal_id = cursor.lastrowid
            conn.commit()
    return f"Goal #{goal_id} added: '{title}' (priority {priority})."


def list_goals(status: str = "active") -> str:
    """
    List goals filtered by status. Pass 'all' to see every goal.
    Returns a formatted string suitable for speaking or displaying.
    """
    with _connect() as conn:
        if status == "all":
            rows = conn.execute("SELECT id, title, status, priority, progress_notes, updated_at FROM goals ORDER BY priority DESC, updated_at DESC").fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, status, priority, progress_notes, updated_at FROM goals WHERE status = ? ORDER BY priority DESC, updated_at DESC",
                (status,),
            ).fetchall()

    if not rows:
        label = "any" if status == "all" else status
        return f"No {label} goals found."

    lines = []
    for goal_id, title, gstatus, priority, notes, updated_at in rows:
        date = updated_at[:10] if updated_at else "?"
        line = f"#{goal_id} [{gstatus}] P{priority} — {title} (updated {date})"
        if notes and notes.strip():
            last_note = notes.strip().split("\n")[-1]
            line += f"\n    → {last_note[:120]}"
        lines.append(line)

    header = f"{len(rows)} goal(s)" + (f" with status '{status}'" if status != "all" else " total")
    return header + ":\n" + "\n".join(lines)


def get_goal(goal_id: int) -> str:
    """
    Get full details for a single goal by ID.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, description, status, priority, progress_notes, created_at, updated_at, last_checked, next_check_at FROM goals WHERE id = ?",
            (int(goal_id),),
        ).fetchone()

    if not row:
        return f"No goal found with ID #{goal_id}."

    gid, title, desc, status, priority, notes, created, updated, last_checked, next_check = row
    lines = [
        f"Goal #{gid}: {title}",
        f"Status: {status} | Priority: {priority}",
        f"Created: {created[:10]} | Updated: {updated[:10]}",
    ]
    if desc:
        lines.append(f"Description: {desc}")
    if last_checked:
        lines.append(f"Last checked: {last_checked[:16]}")
    if next_check:
        lines.append(f"Next check: {next_check[:16]}")
    if notes and notes.strip():
        lines.append("Progress notes:")
        for note in notes.strip().split("\n")[-5:]:  # last 5 notes
            lines.append(f"  - {note}")
    return "\n".join(lines)


def update_goal_status(goal_id: int, status: str) -> str:
    """
    Update the status of a goal. Valid statuses: active, paused, completed, failed.
    """
    status = (status or "").strip().lower()
    if status not in VALID_STATUSES:
        return f"Invalid status '{status}'. Use: {', '.join(sorted(VALID_STATUSES))}."

    now = datetime.datetime.now().isoformat()
    with _lock:
        with _connect() as conn:
            rows_affected = conn.execute(
                "UPDATE goals SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, int(goal_id)),
            ).rowcount
            conn.commit()

    if rows_affected == 0:
        return f"No goal found with ID #{goal_id}."
    return f"Goal #{goal_id} marked as {status}."


def add_goal_progress(goal_id: int, note: str) -> str:
    """
    Append a timestamped progress note to a goal.
    """
    note = (note or "").strip()
    if not note:
        return "Progress note cannot be empty."

    now = datetime.datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    stamped_note = f"[{timestamp}] {note}"

    with _lock:
        with _connect() as conn:
            row = conn.execute(
                "SELECT progress_notes FROM goals WHERE id = ?",
                (int(goal_id),),
            ).fetchone()
            if not row:
                return f"No goal found with ID #{goal_id}."

            existing = (row[0] or "").strip()
            updated_notes = (existing + "\n" + stamped_note).strip()
            conn.execute(
                "UPDATE goals SET progress_notes = ?, last_checked = ?, updated_at = ? WHERE id = ?",
                (updated_notes, now.isoformat(), now.isoformat(), int(goal_id)),
            )
            conn.commit()

    return f"Progress noted on goal #{goal_id}."


def set_goal_next_check(goal_id: int, next_check_at: str) -> str:
    """
    Set when this goal should next be reviewed. next_check_at: ISO datetime string.
    """
    now = datetime.datetime.now().isoformat()
    with _lock:
        with _connect() as conn:
            rows_affected = conn.execute(
                "UPDATE goals SET next_check_at = ?, updated_at = ? WHERE id = ?",
                (next_check_at, now, int(goal_id)),
            ).rowcount
            conn.commit()
    if rows_affected == 0:
        return f"No goal found with ID #{goal_id}."
    return f"Goal #{goal_id} scheduled for review at {next_check_at[:16]}."


def get_goals_due_for_check() -> list:
    """
    Return goals that are active and whose next_check_at has passed (or is null).
    Used by the proactive engine / scheduled tasks later.
    Returns list of dicts.
    """
    now = datetime.datetime.now().isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT id, title, description, priority, progress_notes, next_check_at
               FROM goals
               WHERE status = 'active'
               AND (next_check_at IS NULL OR next_check_at <= ?)
               ORDER BY priority DESC""",
            (now,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "description": r[2],
            "priority": r[3],
            "progress_notes": r[4],
            "next_check_at": r[5],
        }
        for r in rows
    ]


def get_goals_summary() -> str:
    """
    Return a brief summary of goal counts by status. Used in system prompt injection.
    """
    with _connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM goals GROUP BY status").fetchall()
    if not rows:
        return ""
    parts = [f"{count} {status}" for status, count in rows]
    return "Goals: " + ", ".join(parts) + "."


# ─────────────────────────────────────────────
# TOOL REGISTRY
# ─────────────────────────────────────────────

GOAL_TOOLS = {
    "add_goal": add_goal,
    "list_goals": list_goals,
    "get_goal": get_goal,
    "update_goal_status": update_goal_status,
    "add_goal_progress": add_goal_progress,
    "set_goal_next_check": set_goal_next_check,
}

GOAL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "add_goal",
            "description": "Add a new persistent background goal for Jarvis to track. Use for any ongoing objective.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short goal title"},
                    "description": {"type": "string", "description": "Optional longer description of the goal"},
                    "priority": {"type": "integer", "description": "Priority 1-10, default 5. 10 = most important."},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_goals",
            "description": "List goals. Pass status='active', 'paused', 'completed', 'failed', or 'all'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "active/paused/completed/failed/all (default: active)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_goal",
            "description": "Get full details for a specific goal by its ID number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "integer", "description": "The goal's ID number"},
                },
                "required": ["goal_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_goal_status",
            "description": "Change the status of a goal. Valid: active, paused, completed, failed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "integer", "description": "The goal ID"},
                    "status": {"type": "string", "description": "New status: active, paused, completed, or failed"},
                },
                "required": ["goal_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_goal_progress",
            "description": "Add a timestamped progress note to a goal. Use on user progress or Jarvis step completion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "integer", "description": "The goal ID"},
                    "note": {"type": "string", "description": "Progress update text"},
                },
                "required": ["goal_id", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_goal_next_check",
            "description": "Schedule when a goal should next be reviewed by Jarvis.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "integer", "description": "The goal ID"},
                    "next_check_at": {"type": "string", "description": "ISO datetime, e.g. '2026-06-10T09:00:00'"},
                },
                "required": ["goal_id", "next_check_at"],
            },
        },
    },
]


# Initialize on import
init_db()
