import ast
import datetime
import os
import shutil
import sqlite3
from pathlib import Path

JARVIS_DIR = os.path.expanduser("~/Jarvis")
SELF_LOG_PATH = os.path.expanduser("~/jarvis_self_log.db")

CORE_FILES = [
    "brain.py",
    "agent.py",
    "memory.py",
    "vector_memory.py",
    "graph_memory.py",
    "rag_memory.py",
    "associative_memory.py",
    "procedural_memory.py",
    "safety.py",
    "proactive.py",
    "priority.py",
    "learner.py",
    "tts.py",
    "stt.py",
    "wakeword.py",
    "watchlog.py",
    "server.py",
    "terminal.py",
    "tools/init.py",
    "tools/system_tools.py",
    "tools/code_tools.py",
    "tools/calendar_tools.py",
    "tools/file_tools.py",
    "tools/spotify_tools.py",
    "tools/vision_tools.py",
    "tools/computer_tools.py",
    "tools/browser_tools.py",
    "tools/communication_tools.py",
]


def _connect():
    return sqlite3.connect(SELF_LOG_PATH)


def _init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS self_modifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file TEXT NOT NULL,
                change_description TEXT NOT NULL,
                backup_path TEXT,
                success INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def _candidate_paths(module_name: str) -> list[Path]:
    name = module_name if module_name.endswith(".py") else f"{module_name}.py"
    return [
        Path(JARVIS_DIR) / module_name,
        Path(JARVIS_DIR) / name,
        Path(JARVIS_DIR) / "tools" / module_name,
        Path(JARVIS_DIR) / "tools" / name,
    ]


def get_own_source(module_name: str) -> str:
    for path in _candidate_paths(module_name):
        if path.exists() and path.is_file():
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                shown = lines[:150]
                output = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(shown))
                if len(lines) > 150:
                    output += f"\n... truncated: showing 150 of {len(lines)} lines."
                return output or "(empty file)"
            except Exception as e:
                return f"Could not read {path}: {e}"
    return f"Module not found: {module_name}"


def list_own_modules() -> str:
    rows = []
    for rel in CORE_FILES:
        path = Path(JARVIS_DIR) / rel
        if not path.exists():
            rows.append(f"[missing] {rel}")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            rows.append(f"{rel}: {len(text.splitlines())} lines, {path.stat().st_size} bytes")
        except Exception as e:
            rows.append(f"{rel}: error reading file ({e})")
    return "\n".join(rows)


def _keywords(text: str) -> list[str]:
    words = []
    for raw in text.lower().replace("_", " ").split():
        word = "".join(ch for ch in raw if ch.isalnum())
        if len(word) >= 4 and word not in {"jarvis", "problem", "issue", "error"}:
            words.append(word)
    return sorted(set(words))[:8]


def diagnose_issue(description: str) -> str:
    lines = [f"Diagnosis for: {description}"]
    keywords = _keywords(description)
    since = (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat()

    try:
        from watchlog import get_events_since

        events = get_events_since(2)
        errors = [e for e in events if "error" in " ".join(str(x).lower() for x in e)]
        lines.append(f"Recent watchlog errors: {len(errors)}")
        for event in errors[:5]:
            lines.append(f"- {event}")
    except Exception as e:
        lines.append(f"Could not read watchlog: {e}")

    try:
        from safety import get_audit_log

        audit = get_audit_log(50)
        blocked = [row for row in audit if row[3] in ("BLOCKED", "DENIED_BY_USER")]
        lines.append(f"Recent blocked/denied actions: {len(blocked)}")
        for row in blocked[:5]:
            lines.append(f"- {row[4]} {row[0]} -> {row[3]}")
    except Exception as e:
        lines.append(f"Could not read audit log: {e}")

    env_checks = {
        "gemini": "GOOGLE_GENAI_API_KEY",
        "google": "GOOGLE_GENAI_API_KEY",
        "nvidia": "NVIDIA_API_KEY",
        "nim": "NVIDIA_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "huggingface": "HUGGINGFACE_TOKEN",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "voice": "ELEVENLABS_API_KEY",
        "rag": "RAG_FOLDER",
    }
    for key, env_name in env_checks.items():
        if key in description.lower():
            lines.append(f"{env_name}: {'set' if os.getenv(env_name) else 'missing'}")

    mentions = []
    for rel in CORE_FILES[:8]:
        path = Path(JARVIS_DIR) / rel
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(k in text for k in keywords):
                mentions.append(rel)
        except Exception:
            pass
    lines.append("Relevant core files: " + (", ".join(mentions) if mentions else "none found"))
    return "\n".join(lines)


def explain_capability(question: str) -> str:
    try:
        from tools import TOOL_REGISTRY

        names = sorted(TOOL_REGISTRY.keys())
    except Exception as e:
        return f"Could not inspect tools: {e}"

    keywords = _keywords(question)
    relevant = [name for name in names if any(k in name.lower() for k in keywords)]
    if not relevant:
        relevant = names
    lines = [
        f"Jarvis has {len(names)} registered tools.",
        "Relevant tools:",
    ]
    lines.extend(f"- {name}" for name in relevant[:30])
    return "\n".join(lines)


def backup_file(path: str) -> str:
    src = Path(os.path.expanduser(path)).resolve()
    if not src.exists() or not src.is_file():
        return f"Backup failed: file not found: {src}"
    backup_dir = Path(os.path.expanduser("~/jarvis_backups"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"{src.name}.{stamp}.bak"
    shutil.copy2(src, backup)
    return str(backup)


def _log_modification(file: str, change_description: str, backup_path: str, success: bool):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO self_modifications (file, change_description, backup_path, success, created_at) VALUES (?,?,?,?,?)",
            (file, change_description, backup_path, int(success), datetime.datetime.now().isoformat()),
        )
        conn.commit()


def modify_own_tool(tool_file: str, change_description: str, new_code: str) -> str:
    target = Path(JARVIS_DIR) / tool_file
    if not target.exists():
        target = Path(JARVIS_DIR) / "tools" / tool_file
    if not str(target.resolve()).startswith(str(Path(JARVIS_DIR).resolve())):
        return "Modification rejected: target must be inside ~/Jarvis."

    try:
        ast.parse(new_code)
    except SyntaxError as e:
        _log_modification(str(target), change_description, "", False)
        return f"Modification rejected: syntax error on line {e.lineno}: {e.msg}"

    backup = backup_file(str(target))
    if backup.startswith("Backup failed"):
        _log_modification(str(target), change_description, "", False)
        return backup

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_code, encoding="utf-8")
        _log_modification(str(target), change_description, backup, True)
        return f"Modified {target}. Backup saved to {backup}."
    except Exception as e:
        _log_modification(str(target), change_description, backup, False)
        return f"Modification failed after backup {backup}: {e}"


def get_modification_history() -> str:
    with _connect() as conn:
        rows = conn.execute("SELECT file, change_description, backup_path, success, created_at FROM self_modifications ORDER BY created_at DESC LIMIT 10").fetchall()
    if not rows:
        return "No self-modifications logged yet."
    return "\n".join(f"{created_at}: {'OK' if success else 'FAILED'} {file} — {desc} (backup: {backup or 'none'})" for file, desc, backup, success, created_at in rows)


SELF_TOOLS = {
    "get_own_source": get_own_source,
    "list_own_modules": list_own_modules,
    "diagnose_issue": diagnose_issue,
    "explain_capability": explain_capability,
    "backup_file": backup_file,
    "modify_own_tool": modify_own_tool,
    "get_modification_history": get_modification_history,
}


SELF_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_own_source",
            "description": "Read Jarvis source code for a module and return the first 150 lines.",
            "parameters": {"type": "object", "properties": {"module_name": {"type": "string"}}, "required": ["module_name"]},
        },
    },
    {
        "type": "function",
        "function": {"name": "list_own_modules", "description": "List Jarvis core source files with line counts and sizes.", "parameters": {"type": "object", "properties": {}, "required": []}},
    },
    {
        "type": "function",
        "function": {
            "name": "diagnose_issue",
            "description": "Diagnose a Jarvis issue using logs, audit history, env vars, and relevant source files.",
            "parameters": {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_capability",
            "description": "Explain Jarvis capabilities by inspecting registered tools relevant to a question.",
            "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "backup_file",
            "description": "Create a timestamped backup of a file in ~/jarvis_backups.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_own_tool",
            "description": "Validate, back up, and replace a Jarvis tool/source file with new Python code.",
            "parameters": {
                "type": "object",
                "properties": {"tool_file": {"type": "string"}, "change_description": {"type": "string"}, "new_code": {"type": "string"}},
                "required": ["tool_file", "change_description", "new_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {"name": "get_modification_history", "description": "Return the last 10 logged self-modifications.", "parameters": {"type": "object", "properties": {}, "required": []}},
    },
]


_init_db()
