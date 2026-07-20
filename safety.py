import datetime
import os
import re
import sqlite3
import threading
import time

from config import SAFETY_PENDING_TTL

DEBUG = os.getenv("JARVIS_DEBUG", "0").lower() in ("1", "true", "yes", "on")

HOME = os.path.expanduser("~")


def _debug(message: str):
    if DEBUG:
        print(f"  [DEBUG] {message}")


AUDIT_DB = os.path.join(HOME, "jarvis_audit.db")

# ─────────────────────────────────────────────
# CAPABILITY SYSTEM
# ─────────────────────────────────────────────
CAPABILITY_REGISTRY = {}


class Capability:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    def __repr__(self):
        return f"Capability({self.name})"


# Define standard capabilities
CAP_FS_READ = Capability("fs:read", "Read files from disk")
CAP_FS_WRITE = Capability("fs:write", "Write files to disk")
CAP_NET_HTTP = Capability("net:http", "Make HTTP requests")
CAP_SYSTEM_EXEC = Capability("system:exec", "Execute system commands")
CAP_SYSTEM_INFO = Capability("system:info", "Read system information")
CAP_BROWSER = Capability("browser:control", "Control browser (navigate, click, type)")
CAP_SPOTIFY = Capability("spotify:control", "Control Spotify playback")
CAP_DISCORD = Capability("discord:messaging", "Send/read Discord messages")
CAP_CALENDAR = Capability("calendar:read", "Read calendar events")
CAP_CALENDAR_WRITE = Capability("calendar:write", "Create calendar events")
CAP_MESSAGING = Capability("messaging:send", "Send iMessages")
CAP_VISION = Capability("vision:capture", "Capture and analyze screen")
CAP_MEMORY = Capability("memory:access", "Read/write Jarvis memory")
CAP_TIMER = Capability("timer:control", "Set/cancel timers")
CAP_SANDBOX = Capability("sandbox:exec", "Run sandboxed code/commands")
CAP_KNOWLEDGE = Capability("knowledge:graph", "Read/write knowledge graph")


def declare_capability(tool_name: str, capability: Capability):
    CAPABILITY_REGISTRY[tool_name] = capability


def get_tool_capability(tool_name: str) -> Capability | None:
    return CAPABILITY_REGISTRY.get(tool_name)


def check_capability(tool_name: str, required: Capability | str) -> bool:
    needed = required if isinstance(required, Capability) else Capability(required)
    actual = get_tool_capability(tool_name)
    return actual is not None and actual.name == needed.name


# ─────────────────────────────────────────────
# PERMISSION TIERS
# ─────────────────────────────────────────────
SAFE = "SAFE"
WARNING = "WARNING"
DANGEROUS = "DANGEROUS"
CRITICAL = "CRITICAL"
BLOCKED = "BLOCKED"

# Tool permission map
TOOL_PERMISSIONS = {
    # SAFE — no confirmation needed
    "get_weather": SAFE,
    "get_weather_detailed": SAFE,
    "web_search": SAFE,
    "get_system_info": SAFE,
    "get_top_processes": SAFE,
    "get_open_apps": SAFE,
    "spotify_play": SAFE,
    "spotify_pause": SAFE,
    "spotify_next": SAFE,
    "spotify_previous": SAFE,
    "spotify_volume_up": SAFE,
    "spotify_volume_down": SAFE,
    "spotify_current": SAFE,
    "spotify_play_song": SAFE,
    "get_calendar_events": SAFE,
    "find_recent_screenshot": SAFE,
    "disk_usage": SAFE,
    "open_in_finder": SAFE,
    "get_largest_files": SAFE,
    "read_screen": SAFE,
    "find_on_screen": SAFE,
    "summarize_screen": SAFE,
    "get_recap": SAFE,
    "get_recent_events": SAFE,
    "cancel_timer": SAFE,
    "open_app": SAFE,
    "focus_app": SAFE,
    "set_timer": SAFE,
    "semantic_search_memory": SAFE,
    "get_own_source": SAFE,
    "list_own_modules": SAFE,
    "diagnose_issue": SAFE,
    "explain_capability": SAFE,
    "get_modification_history": SAFE,
    "extract_entities_relations": SAFE,
    "read_file": SAFE,
    "list_directory": SAFE,
    "get_function_signatures": SAFE,
    "scan_project_structure": SAFE,
    "search_in_files": SAFE,
    # WARNING — confirm once per session
    "browser_current_url": WARNING,
    "browser_navigate": WARNING,
    "browser_quick_search": WARNING,
    "browser_scroll": WARNING,
    "browser_back": WARNING,
    "browser_forward": WARNING,
    "browser_reload": WARNING,
    "discord_open_channel": WARNING,
    "discord_send_message": WARNING,
    "discord_open_and_send": WARNING,
    "browser_new_tab": WARNING,
    "browser_close_tab": WARNING,
    "quit_app": WARNING,
    "move_and_click": WARNING,
    "click_on_screen": WARNING,
    "type_text": WARNING,
    "press_key": WARNING,
    "take_screenshot": SAFE,
    "add_calendar_event": SAFE,
    "organize_downloads": WARNING,
    "create_file": WARNING,
    "write_file": WARNING,
    "append_file": WARNING,
    "add_goal": WARNING,
    "add_goal_progress": WARNING,
    "update_goal_status": WARNING,
    "set_goal_next_check": WARNING,
    "add_to_knowledge_graph": WARNING,
    "backup_file": WARNING,
    "agent_spawn": WARNING,
    "search_my_notes": SAFE,
    "query_my_knowledge_graph": SAFE,
    "get_goal": SAFE,
    "list_goals": SAFE,
    "analyze_image": SAFE,
    "analyze_video": SAFE,
    "ocr_document": SAFE,
    "check_screen_for_alerts": SAFE,
    "warwatch_news": SAFE,
    "save_api_key": WARNING,
    "list_configured_keys": SAFE,
    # New OAuth integrations
    "gmail_search": SAFE,
    "gmail_get_labels": SAFE,
    "gmail_get_message": SAFE,
    "gmail_send": WARNING,
    "gmail_status": SAFE,
    "gmail_auth_url": SAFE,
    "gmail_handle_callback": SAFE,
    "github_list_repos": SAFE,
    "github_get_repo": SAFE,
    "github_search_code": SAFE,
    "github_list_issues": SAFE,
    "github_create_issue": WARNING,
    "github_status": SAFE,
    "github_auth_url": SAFE,
    "github_handle_callback": SAFE,
    # Google Workspace: Drive
    "gdrive_list": SAFE,
    "gdrive_search": SAFE,
    "gdrive_get": SAFE,
    "gdrive_download": SAFE,
    "gdrive_upload": WARNING,
    "gdrive_create_folder": WARNING,
    "gdrive_share": WARNING,
    "gdrive_move": WARNING,
    "gdrive_delete": WARNING,
    "gdrive_status": SAFE,
    "gdrive_auth_url": SAFE,
    "gdrive_handle_callback": SAFE,
    # Google Workspace: Sheets
    "gsheets_get": SAFE,
    "gsheets_read_range": SAFE,
    "gsheets_read_sheet": SAFE,
    "gsheets_get_values": SAFE,
    "gsheets_append": WARNING,
    "gsheets_update_range": WARNING,
    "gsheets_batch_update": WARNING,
    "gsheets_create": WARNING,
    "gsheets_add_sheet": WARNING,
    "gsheets_status": SAFE,
    "gsheets_auth_url": SAFE,
    "gsheets_handle_callback": SAFE,
    # Docs
    "docs_get": SAFE,
    "docs_create": WARNING,
    "docs_append_text": WARNING,
    "docs_search": SAFE,
    "docs_status": SAFE,
    "docs_auth_url": SAFE,
    "docs_handle_callback": SAFE,
    # Slides
    "slides_get": SAFE,
    "slides_create": WARNING,
    "slides_add_slide": WARNING,
    "slides_replace_text": WARNING,
    "slides_search": SAFE,
    "slides_status": SAFE,
    "slides_auth_url": SAFE,
    "slides_handle_callback": SAFE,
    # Forms
    "forms_get": SAFE,
    "forms_create": WARNING,
    "forms_add_question": WARNING,
    "forms_get_responses": SAFE,
    "forms_status": SAFE,
    "forms_auth_url": SAFE,
    "forms_handle_callback": SAFE,
    "reminders_get_lists": SAFE,
    "reminders_list": SAFE,
    "reminders_search": SAFE,
    "reminders_create": WARNING,
    "reminders_complete": WARNING,
    "reminders_delete": WARNING,
    "inspect_capabilities": SAFE,
    # DANGEROUS — always confirm + show details
    "send_imessage": DANGEROUS,
    "run_terminal_command": DANGEROUS,
    "modify_own_tool": DANGEROUS,
    "run_python": DANGEROUS,
    "run_python_sandboxed": DANGEROUS,
    "run_command_sandboxed": DANGEROUS,
    # CRITICAL — blocked by default
    # (populated from BLOCKED_PATTERNS below)
}

# ─────────────────────────────────────────────
# TERMINAL COMMAND BLACKLIST
# ─────────────────────────────────────────────
BLOCKED_PATTERNS = [
    # Destructive file operations
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\*",
    r"rm\s+--no-preserve-root",
    r"sudo\s+rm",
    r"rm\s+-rf",
    r"rm\s+-fr",
    r"rm\s+--recursive",
    # System shutdown/restart
    r"sudo\s+shutdown",
    r"sudo\s+reboot",
    r"sudo\s+halt",
    r"sudo\s+poweroff",
    # Disk operations
    r"mkfs\.",
    r"dd\s+if=",
    r"diskutil\s+eraseDisk",
    r"diskutil\s+eraseVolume",
    # Privilege escalation
    r"sudo\s+su",
    r"sudo\s+-s",
    r"chmod\s+777\s+/",
    r"chown\s+.*\s+/",
    # Network attacks
    r"nmap\s+",
    r"nc\s+-l",
    r"python.*http\.server.*&",
    # Data exfiltration
    r"curl.*\|\s*bash",
    r"wget.*\|\s*sh",
    r"curl.*\|\s*sh",
    # Fork bomb
    r":\(\)\{.*\}",
    r"fork\s*bomb",
    # Keychain/password access
    r"security\s+find-generic-password",
    r"security\s+find-internet-password",
    r"security\s+dump-keychain",
    # SIP/system integrity
    r"csrutil\s+disable",
    r"nvram\s+",
]

DANGEROUS_FLAGS = [
    "--no-preserve-root",
    "-rf /",
    "-rf ~",
    ">/dev/sda",
    "2>/dev/null &",
]

# Commands that are always safe to run
SAFE_COMMANDS = [
    "ls",
    "pwd",
    "echo",
    "cat",
    "grep",
    "find",
    "ps",
    "top",
    "df",
    "du",
    "uptime",
    "whoami",
    "date",
    "cal",
    "which",
    "type",
    "man",
    "open",
    "say",
    "osascript",
    "brew list",
    "pip list",
    "python3 --version",
    "ollama list",
    "ollama ps",
    "sw_vers",
    "system_profiler",
    "networksetup",
    "ifconfig",
    "launchctl list",
]


# ─────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────
def _connect():
    return sqlite3.connect(AUDIT_DB)


def init_audit_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool TEXT NOT NULL,
                args TEXT,
                permission_level TEXT,
                decision TEXT,
                reason TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def get_audit_log(limit: int = 20):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT tool, args, permission_level, decision, created_at FROM audit_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return rows


# ─────────────────────────────────────────────
# SESSION MEMORY (WARNING tools confirmed once)
# ─────────────────────────────────────────────
# Stores {tool_name: expiry_timestamp}
_session_confirmed: dict[str, float] = {}
_session_lock = threading.Lock()


def mark_session_confirmed(tool: str):
    with _session_lock:
        _session_confirmed[tool] = time.time() + SAFETY_PENDING_TTL


def is_session_confirmed(tool: str) -> bool:
    with _session_lock:
        expiry = _session_confirmed.get(tool)
        if expiry is None:
            return False
        if time.time() > expiry:
            del _session_confirmed[tool]
            return False
        return True


def reset_session():
    with _session_lock:
        _session_confirmed.clear()


def _clean_expired_confirmations():
    """Background cleaner that purges expired confirmations every 60s."""
    while True:
        time.sleep(60)
        now = time.time()
        with _session_lock:
            expired = [t for t, e in _session_confirmed.items() if now > e]
            for t in expired:
                del _session_confirmed[t]


_cleaner_thread = threading.Thread(target=_clean_expired_confirmations, daemon=True)
_cleaner_thread.start()


# ─────────────────────────────────────────────
# COMMAND ANALYSIS
# ─────────────────────────────────────────────
def analyze_command(command: str) -> tuple:
    """
    Analyze a terminal command.
    Returns (is_safe, level, reason)
    """
    cmd = command.strip().lower()

    # Check blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False, CRITICAL, f"Blocked pattern detected: {pattern}"

    # Check dangerous flags
    for flag in DANGEROUS_FLAGS:
        if flag.lower() in cmd:
            return False, CRITICAL, f"Dangerous flag detected: {flag}"

    # Check if starts with a known safe command
    for safe_cmd in SAFE_COMMANDS:
        if cmd.startswith(safe_cmd.lower()):
            return True, SAFE, "Known safe command"

    # Default — allow everything unless blocked by explicit dangerous patterns
    return True, SAFE, "Allowed command"


# ─────────────────────────────────────────────
# PERMISSION CHECKER
# ─────────────────────────────────────────────
class PermissionDenied(Exception):
    pass


class NeedsConfirmation(Exception):
    def __init__(self, tool, args, level, message):
        self.tool = tool
        self.args = args
        self.level = level
        self.message = message
        super().__init__(message)


def check_permission(tool: str, args: dict = None) -> bool:
    """
    Check if a tool can run.
    Returns True if safe to proceed.
    Raises PermissionDenied if blocked.
    Raises NeedsConfirmation if user must confirm.
    """
    args = args or {}
    tool = (tool or "").strip()
    level = TOOL_PERMISSIONS.get(tool, SAFE)  # Unknown/plugin tools default to SAFE

    # Special handling for terminal commands
    if tool == "run_terminal_command":
        command = args.get("command", "")
        allowed, cmd_level, reason = analyze_command(command)
        if not allowed:
            log_audit(tool, args, CRITICAL, "BLOCKED", reason)
            raise PermissionDenied(f"Command blocked: {reason}")
        if cmd_level == DANGEROUS:
            level = DANGEROUS

    # Eval mode auto-confirms all non-critical tools
    if os.getenv("JARVIS_EVAL_MODE", "0").lower() in ("1", "true", "yes", "on"):
        if level in (WARNING, DANGEROUS):
            _debug(f"[Safety] EVAL_MODE: auto-confirming {tool} ({level})")
            log_audit(tool, args, level, "ALLOWED", "JARVIS_EVAL_MODE")
            return True

    if level == SAFE:
        _debug(f"[Safety] {tool}: SAFE -> allowed")
        log_audit(tool, args, level, "ALLOWED")
        return True

    if level == WARNING:
        confirmed = is_session_confirmed(tool)
        _debug(f"[Safety] {tool}: WARNING, session_confirmed={confirmed}")
        if confirmed:
            log_audit(tool, args, level, "ALLOWED", "session confirmed")
            return True
        log_audit(tool, args, level, "NEEDS_CONFIRMATION")
        raise NeedsConfirmation(tool, args, level, f"I need your permission to {tool.replace('_', ' ')}. Shall I go ahead?")

    if level == DANGEROUS:
        log_audit(tool, args, level, "NEEDS_CONFIRMATION")
        raise NeedsConfirmation(
            tool,
            args,
            level,
            f"This is a sensitive action: {tool.replace('_', ' ')}. Are you sure you want to proceed?",
        )

    if level == CRITICAL:
        log_audit(tool, args, level, "BLOCKED", "Critical level tool")
        raise PermissionDenied(f"Action '{tool}' is blocked for safety.")

    return True


# ─────────────────────────────────────────────
# SAFE TOOL RUNNER
# ─────────────────────────────────────────────
def run_tool_safely(tool_name: str, tool_fn, args: dict, speak_fn=None, pending_fn=None) -> str:
    """
    Run a tool with permission checking.
    If confirmation needed, sets a pending action and returns a message.
    """
    try:
        check_permission(tool_name, args)
        # Permission granted — run it
        result = tool_fn(**args)
        log_audit(tool_name, args, TOOL_PERMISSIONS.get(tool_name, WARNING), "EXECUTED")
        return result

    except PermissionDenied as e:
        msg = f"I can't do that — it's been blocked for safety. {str(e)}"
        if speak_fn:
            speak_fn(msg)
        log_audit(tool_name, args, CRITICAL, "BLOCKED", str(e))
        return msg

    except NeedsConfirmation as e:
        # Store pending action
        if pending_fn:
            pending_fn(tool_name, tool_fn, args, e.level)
        msg = e.message
        if speak_fn:
            speak_fn(msg)
        return msg


# ─────────────────────────────────────────────
# CAPABILITY DECLARATIONS
# ─────────────────────────────────────────────
declare_capability("get_weather", CAP_SYSTEM_INFO)
declare_capability("get_weather_detailed", CAP_SYSTEM_INFO)
declare_capability("web_search", CAP_NET_HTTP)
declare_capability("get_system_info", CAP_SYSTEM_INFO)
declare_capability("get_open_apps", CAP_SYSTEM_INFO)
declare_capability("disk_usage", CAP_SYSTEM_INFO)
declare_capability("spotify_play", CAP_SPOTIFY)
declare_capability("spotify_pause", CAP_SPOTIFY)
declare_capability("spotify_next", CAP_SPOTIFY)
declare_capability("spotify_previous", CAP_SPOTIFY)
declare_capability("spotify_volume_up", CAP_SPOTIFY)
declare_capability("spotify_volume_down", CAP_SPOTIFY)
declare_capability("spotify_current", CAP_SPOTIFY)
declare_capability("spotify_play_song", CAP_SPOTIFY)
declare_capability("get_calendar_events", CAP_CALENDAR)
declare_capability("add_calendar_event", CAP_CALENDAR_WRITE)
declare_capability("read_screen", CAP_VISION)
declare_capability("find_on_screen", CAP_VISION)
declare_capability("summarize_screen", CAP_VISION)
declare_capability("take_screenshot", CAP_VISION)
declare_capability("set_timer", CAP_TIMER)
declare_capability("cancel_timer", CAP_TIMER)
declare_capability("semantic_search_memory", CAP_MEMORY)
declare_capability("read_file", CAP_FS_READ)
declare_capability("write_file", CAP_FS_WRITE)
declare_capability("create_file", CAP_FS_WRITE)
declare_capability("append_file", CAP_FS_WRITE)
declare_capability("browser_navigate", CAP_BROWSER)
declare_capability("browser_quick_search", CAP_BROWSER)
declare_capability("discord_open_channel", CAP_DISCORD)
declare_capability("discord_send_message", CAP_DISCORD)
declare_capability("discord_open_and_send", CAP_DISCORD)
declare_capability("send_imessage", CAP_MESSAGING)
declare_capability("run_terminal_command", CAP_SYSTEM_EXEC)
declare_capability("run_python", CAP_SYSTEM_EXEC)
declare_capability("run_python_sandboxed", CAP_SANDBOX)
declare_capability("run_command_sandboxed", CAP_SANDBOX)
declare_capability("extract_entities_relations", CAP_KNOWLEDGE)


# ─────────────────────────────────────────────
# AUDIT ALERTING
# ─────────────────────────────────────────────
_last_alert_time = 0
_alert_lock = threading.Lock()
AUDIT_ALERT_COOLDOWN = 60


def fire_audit_alert(tool: str, level: str, decision: str):
    global _last_alert_time
    with _alert_lock:
        now = datetime.datetime.now().timestamp()
        if now - _last_alert_time < AUDIT_ALERT_COOLDOWN:
            return
        _last_alert_time = now
    try:
        from proactive import add_alert

        add_alert(
            alert_type="security",
            message=f"Audit: {tool} → {decision} ({level})",
            priority=5,
        )
    except Exception:
        pass


def log_audit(tool: str, args: dict, level: str, decision: str, reason: str = ""):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO audit_log (tool, args, permission_level, decision, reason, created_at) VALUES (?,?,?,?,?,?)",
            (tool, str(args), level, decision, reason, datetime.datetime.now().isoformat()),
        )
        conn.commit()
    if decision in ("BLOCKED", "DENIED"):
        fire_audit_alert(tool, level, decision)


# Initialize on import
init_audit_db()
