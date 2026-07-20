import datetime
import json
import os
import re
import sqlite3
import threading

import yaml

from tools import TOOL_REGISTRY

WORKFLOW_DIR = os.path.expanduser("~/.jarvis/workflows")
DB_PATH = os.path.expanduser("~/.jarvis_workflows.db")

_workflow_lock = threading.Lock()


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
def _connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_name TEXT NOT NULL,
                params TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                error TEXT,
                started_at TEXT,
                finished_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS node_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                output TEXT,
                error TEXT,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY (run_id) REFERENCES workflow_runs(id)
            )
        """)
        conn.commit()


def _create_run(name: str, params: dict) -> int:
    with _connect() as conn:
        cur = conn.execute("INSERT INTO workflow_runs (workflow_name, params, status, started_at) VALUES (?, ?, ?, ?)", (name, json.dumps(params), "running", datetime.datetime.now().isoformat()))
        conn.commit()
        return cur.lastrowid


def _finish_run(run_id: int, status: str, result: str = None, error: str = None):
    with _connect() as conn:
        conn.execute("UPDATE workflow_runs SET status=?, result=?, error=?, finished_at=? WHERE id=?", (status, result, error, datetime.datetime.now().isoformat(), run_id))
        conn.commit()


def _checkpoint_node(run_id: int, node_id: str, output: str = None, error: str = None):
    status = "error" if error else "done"
    with _connect() as conn:
        existing = conn.execute("SELECT id FROM node_runs WHERE run_id=? AND node_id=?", (run_id, node_id)).fetchone()
        if existing:
            conn.execute("UPDATE node_runs SET status=?, output=?, error=?, finished_at=? WHERE id=?", (status, output, error, datetime.datetime.now().isoformat(), existing[0]))
        else:
            conn.execute(
                "INSERT INTO node_runs (run_id, node_id, status, output, error, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, node_id, status, output, error, datetime.datetime.now().isoformat(), datetime.datetime.now().isoformat()),
            )
        conn.commit()


def _get_latest_checkpoint(run_id: int) -> set[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT node_id FROM node_runs WHERE run_id=? AND status='done'", (run_id,)).fetchall()
    return {r[0] for r in rows}


def get_run_history(limit: int = 20) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, workflow_name, params, status, result, error, started_at, finished_at FROM workflow_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [
        {
            "id": r[0],
            "workflow": r[1],
            "params": r[2],
            "status": r[3],
            "result": (r[4] or "")[:200],
            "error": r[5],
            "started": r[6],
            "finished": r[7],
        }
        for r in rows
    ]


def get_run_detail(run_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT id, workflow_name, params, status, result, error, started_at, finished_at FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            return None
        nodes = conn.execute("SELECT node_id, status, output, error, started_at, finished_at FROM node_runs WHERE run_id=? ORDER BY id", (run_id,)).fetchall()
    return {
        "id": row[0],
        "workflow": row[1],
        "params": row[2],
        "status": row[3],
        "result": row[4],
        "error": row[5],
        "started": row[6],
        "finished": row[7],
        "nodes": [{"id": n[0], "status": n[1], "output": (n[2] or "")[:300], "error": n[3], "started": n[4], "finished": n[5]} for n in nodes],
    }


# ─────────────────────────────────────────────
# WORKFLOW LOADING
# ─────────────────────────────────────────────
def _ensure_dir():
    os.makedirs(WORKFLOW_DIR, exist_ok=True)


BUILTIN_WORKFLOWS = {
    "research_and_save": {
        "name": "research_and_save",
        "description": "Search the web, summarize findings, save to memory",
        "nodes": [
            {
                "id": "search",
                "type": "tool_call",
                "tool": "web_search",
                "args": {"query": "{query}"},
            },
            {
                "id": "summarize",
                "type": "llm",
                "prompt": "Summarize these search results in 2-3 sentences:\n{search.output}",
            },
            {
                "id": "save",
                "type": "tool_call",
                "tool": "save_memory",
                "args": {"content": "Research on {query}: {summarize.output}"},
                "depends_on": ["search", "summarize"],
            },
        ],
    },
    "system_report": {
        "name": "system_report",
        "description": "Gather system info, weather, and calendar into one report",
        "nodes": [
            {
                "id": "sysinfo",
                "type": "tool_call",
                "tool": "get_system_info",
                "args": {},
            },
            {
                "id": "weather",
                "type": "tool_call",
                "tool": "get_weather_detailed",
                "args": {},
            },
            {
                "id": "compile",
                "type": "llm",
                "prompt": "Compile this into a 2-3 sentence briefing:\nSystem: {sysinfo.output}\nWeather: {weather.output}",
                "depends_on": ["sysinfo", "weather"],
            },
        ],
    },
    "code_review": {
        "name": "code_review",
        "description": "Scan a project, analyze structure, suggest improvements",
        "nodes": [
            {
                "id": "scan",
                "type": "tool_call",
                "tool": "scan_project_structure",
                "args": {"path": "{path}"},
            },
            {
                "id": "review",
                "type": "llm",
                "prompt": "Review this project structure and suggest 3 improvements:\n{scan.output}",
                "depends_on": ["scan"],
            },
        ],
    },
}


def list_workflows() -> list[dict]:
    _ensure_dir()
    workflows = {}
    for name, wf in BUILTIN_WORKFLOWS.items():
        workflows[name] = {"name": name, "description": wf["description"], "builtin": True}
    if os.path.isdir(WORKFLOW_DIR):
        for fname in sorted(os.listdir(WORKFLOW_DIR)):
            if not fname.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(WORKFLOW_DIR, fname)
            try:
                with open(path) as f:
                    wf = yaml.safe_load(f)
                if wf and "name" in wf:
                    name = wf["name"]
                    workflows[name] = {
                        "name": name,
                        "description": wf.get("description", ""),
                        "builtin": False,
                        "file": fname,
                    }
            except Exception:
                pass
    return list(workflows.values())


def load_workflow(name: str) -> dict | None:
    if name in BUILTIN_WORKFLOWS:
        return dict(BUILTIN_WORKFLOWS[name])
    _ensure_dir()
    if not os.path.isdir(WORKFLOW_DIR):
        return None
    for fname in os.listdir(WORKFLOW_DIR):
        if not fname.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(WORKFLOW_DIR, fname)
        try:
            with open(path) as f:
                wf = yaml.safe_load(f)
            if wf and wf.get("name") == name:
                return wf
        except Exception:
            pass
    return None


# ─────────────────────────────────────────────
# INTERPOLATION
# ─────────────────────────────────────────────
def _interpolate(text: str, outputs: dict, params: dict) -> str:
    def _replace(m):
        key = m.group(1)
        if key in params:
            return str(params[key])
        if key in outputs:
            val = outputs[key]
            if isinstance(val, str):
                return val
            return str(val)
        # Try dot-path: node_id.output or node_id.prop
        if "." in key:
            parts = key.split(".", 1)
            node_val = outputs.get(parts[0])
            if isinstance(node_val, dict):
                return str(node_val.get(parts[1], m.group(0)))
            if node_val is not None:
                return str(node_val)
        return m.group(0)

    return re.sub(r"\{([\w.]+)\}", _replace, text)


def _resolve_args(args: dict, outputs: dict, params: dict) -> dict:
    resolved = {}
    for k, v in args.items():
        if isinstance(v, str):
            resolved[k] = _interpolate(v, outputs, params)
        elif isinstance(v, dict):
            resolved[k] = _resolve_args(v, outputs, params)
        elif isinstance(v, list):
            resolved[k] = [_resolve_args(i, outputs, params) if isinstance(i, dict) else _interpolate(i, outputs, params) if isinstance(i, str) else i for i in v]
        else:
            resolved[k] = v
    return resolved


# ─────────────────────────────────────────────
# EXECUTOR
# ─────────────────────────────────────────────
def _execute_node(node: dict, outputs: dict, params: dict) -> str:
    ntype = node.get("type", "tool_call")
    if ntype == "tool_call":
        tool_name = _interpolate(node.get("tool", ""), outputs, params)
        raw_args = node.get("args", {})
        args = _resolve_args(raw_args, outputs, params)
        fn = TOOL_REGISTRY.get(tool_name)
        if not fn:
            raise ValueError(f"Unknown tool: {tool_name}")
        result = fn(**args)
        return str(result)

    if ntype == "llm":
        prompt = _interpolate(node.get("prompt", ""), outputs, params)
        from brain import ask_with_tools

        result = ask_with_tools(prompt)
        return str(result)

    raise ValueError(f"Unknown node type: {ntype}")


def run_workflow(name: str, params: dict = None, run_id: int = None) -> dict:
    params = params or {}
    wf = load_workflow(name)
    if not wf:
        return {"ok": False, "error": f"Workflow '{name}' not found"}

    own_run = False
    if run_id is None:
        run_id = _create_run(name, params)
        own_run = True

    nodes = wf.get("nodes", [])
    outputs = {}
    done = _get_latest_checkpoint(run_id) if not own_run else set()

    # Topological sort: nodes without deps first
    remaining = [n for n in nodes if n["id"] not in done]
    completed_this_run = set(done)

    max_iterations = 50
    iteration = 0

    while remaining and iteration < max_iterations:
        iteration += 1
        ready = []
        for n in remaining:
            deps = set(n.get("depends_on", []))
            if deps.issubset(completed_this_run):
                ready.append(n)

        if not ready:
            return {"ok": False, "error": "Circular dependency or unsatisfied deps", "run_id": run_id}

        for node in ready:
            node_id = node["id"]
            try:
                result = _execute_node(node, outputs, params)
                outputs[node_id] = result
                completed_this_run.add(node_id)
                _checkpoint_node(run_id, node_id, output=result)
            except Exception as e:
                outputs[node_id] = f"<error: {e}>"
                _checkpoint_node(run_id, node_id, error=str(e))
                if not node.get("continue_on_error"):
                    _finish_run(run_id, "error", error=f"Node {node_id}: {e}")
                    return {"ok": False, "error": f"Node {node_id} failed: {e}", "run_id": run_id}

        remaining = [n for n in remaining if n["id"] not in completed_this_run]

    final_output = outputs.get(nodes[-1]["id"], "") if nodes else ""
    _finish_run(run_id, "done", result=final_output)
    return {"ok": True, "result": final_output, "run_id": run_id, "outputs": outputs}


def retry_failed_run(run_id: int) -> dict:
    detail = get_run_detail(run_id)
    if not detail:
        return {"ok": False, "error": f"Run {run_id} not found"}
    if detail["status"] != "error":
        return {"ok": False, "error": f"Run {run_id} is not in error state (status={detail['status']})"}
    name = detail["workflow"]
    params = json.loads(detail["params"] or "{}")
    return run_workflow(name, params, run_id=run_id)


init_db()
