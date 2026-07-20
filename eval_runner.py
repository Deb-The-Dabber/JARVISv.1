import datetime
import json
import os
import sqlite3
import sys
import time

from config import EVAL_DB_PATH

EVAL_RUNS_DIR = os.path.expanduser("~/.jarvis/eval_runs")
GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "tests", "eval", "golden_set.jsonl")


def load_golden_set(path: str = None) -> list[dict]:
    path = path or GOLDEN_SET_PATH
    if not os.path.exists(path):
        return []
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def score_tool_accuracy(called_tools: list[str], expected_tools: list[str]) -> float:
    if not expected_tools:
        return 1.0
    if not called_tools:
        return 0.0
    called_set = set(t.lower() for t in called_tools)
    expected_set = set(t.lower() for t in expected_tools)
    hits = called_set & expected_set
    return len(hits) / len(expected_set)


def score_keyword_recall(text: str, expected_keywords: list[str]) -> float:
    if not expected_keywords:
        return 1.0
    if not text:
        return 0.0
    t = text.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in t)
    return hits / len(expected_keywords)


def score_intent_accuracy(actual_intent: str, expected_intent: str) -> float:
    if not expected_intent:
        return 1.0
    return 1.0 if actual_intent == expected_intent else 0.0


def run_eval_case(case: dict, require_no_api: bool = False) -> dict:
    from brain import classify_intent, process

    prompt = case.get("prompt", "")
    requires_api = case.get("requires_api", False)

    if require_no_api and requires_api:
        return {
            "prompt": prompt,
            "skipped": True,
            "reason": "requires API",
        }

    start = time.time()
    try:
        os.environ["JARVIS_EVAL_MODE"] = "1"
        intent = classify_intent(prompt)
        reply = process(prompt)
    except Exception as e:
        return {
            "prompt": prompt,
            "error": str(e),
            "latency": time.time() - start,
        }

    elapsed = time.time() - start
    called_tools = []
    try:
        from brain import get_last_tool_calls

        called_tools = get_last_tool_calls()
    except Exception:
        pass

    expected_tools = case.get("expected_tools", [])
    expected_keywords = case.get("expected_keywords", [])
    expected_intent = case.get("expected_intent", "")

    tool_acc = score_tool_accuracy(called_tools, expected_tools)
    kw_recall = score_keyword_recall(reply, expected_keywords)
    intent_acc = score_intent_accuracy(intent, expected_intent)
    latency_ok = elapsed <= case.get("max_latency", 30)
    passed = tool_acc >= 0.5 and kw_recall >= 0.5 and intent_acc >= 0.5 and latency_ok

    return {
        "prompt": prompt,
        "intent": intent,
        "expected_intent": expected_intent,
        "intent_accuracy": intent_acc,
        "tools_called": called_tools,
        "expected_tools": expected_tools,
        "tool_accuracy": tool_acc,
        "keywords_found": [kw for kw in expected_keywords if kw.lower() in (reply or "").lower()],
        "keyword_recall": kw_recall,
        "latency": round(elapsed, 3),
        "max_latency": case.get("max_latency", 30),
        "latency_ok": latency_ok,
        "passed": passed,
        "reply_preview": (reply or "")[:200],
    }


def run_eval_suite(path: str = None, require_no_api: bool = False) -> dict:
    cases = load_golden_set(path)
    if not cases:
        return {"error": "No golden set cases found", "results": [], "passed": 0, "failed": 0, "skipped": 0}

    results = []
    for case in cases:
        result = run_eval_case(case, require_no_api=require_no_api)
        results.append(result)

    passed = sum(1 for r in results if r.get("passed") and not r.get("skipped"))
    failed = sum(1 for r in results if not r.get("passed") and not r.get("skipped"))
    skipped = sum(1 for r in results if r.get("skipped"))

    avg_tool_acc = 0.0
    avg_kw_recall = 0.0
    avg_intent_acc = 0.0
    avg_latency = 0.0
    non_skipped = [r for r in results if not r.get("skipped")]
    if non_skipped:
        avg_tool_acc = sum(r.get("tool_accuracy", 0) for r in non_skipped) / len(non_skipped)
        avg_kw_recall = sum(r.get("keyword_recall", 0) for r in non_skipped) / len(non_skipped)
        avg_intent_acc = sum(r.get("intent_accuracy", 0) for r in non_skipped) / len(non_skipped)
        avg_latency = sum(r.get("latency", 0) for r in non_skipped) / len(non_skipped)

    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "total": len(cases),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "avg_tool_accuracy": round(avg_tool_acc, 3),
        "avg_keyword_recall": round(avg_kw_recall, 3),
        "avg_intent_accuracy": round(avg_intent_acc, 3),
        "avg_latency_seconds": round(avg_latency, 3),
        "pass_rate": round(passed / max(len(non_skipped), 1), 3) if non_skipped else 0,
        "results": results,
    }

    _save_report(report)
    return report


def _save_report(report: dict):
    os.makedirs(EVAL_RUNS_DIR, exist_ok=True)
    ts = report.get("timestamp", datetime.datetime.now().isoformat())
    safe_ts = ts.replace(":", "-").replace(".", "-")
    path = os.path.join(EVAL_RUNS_DIR, f"eval_{safe_ts}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    latest_path = os.path.join(EVAL_RUNS_DIR, "latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, indent=2, default=str)


def load_latest_report() -> dict | None:
    latest_path = os.path.join(EVAL_RUNS_DIR, "latest.json")
    if os.path.exists(latest_path):
        try:
            with open(latest_path) as f:
                return json.load(f)
        except Exception:
            pass
    return None


def load_eval_history(limit: int = 10) -> list[dict]:
    os.makedirs(EVAL_RUNS_DIR, exist_ok=True)
    files = sorted(
        [f for f in os.listdir(EVAL_RUNS_DIR) if f.startswith("eval_") and f.endswith(".json")],
        reverse=True,
    )[:limit]
    history = []
    for fname in files:
        try:
            with open(os.path.join(EVAL_RUNS_DIR, fname)) as f:
                report = json.load(f)
                history.append(
                    {
                        "timestamp": report.get("timestamp"),
                        "passed": report.get("passed"),
                        "failed": report.get("failed"),
                        "skipped": report.get("skipped"),
                        "pass_rate": report.get("pass_rate"),
                        "avg_tool_accuracy": report.get("avg_tool_accuracy"),
                        "avg_keyword_recall": report.get("avg_keyword_recall"),
                        "avg_latency_seconds": report.get("avg_latency_seconds"),
                        "total": report.get("total"),
                    }
                )
        except Exception:
            pass
    return history


def is_regression(thresholds: dict = None) -> bool:
    thresholds = thresholds or {
        "pass_rate": 0.7,
        "avg_tool_accuracy": 0.5,
        "avg_keyword_recall": 0.5,
    }
    latest = load_latest_report()
    if not latest:
        return False
    if latest.get("passed", 0) == 0 and latest.get("total", 0) > 0:
        return True
    if latest.get("pass_rate", 1) < thresholds.get("pass_rate", 0.7):
        return True
    if latest.get("avg_tool_accuracy", 1) < thresholds.get("avg_tool_accuracy", 0.5):
        return True
    if latest.get("avg_keyword_recall", 1) < thresholds.get("avg_keyword_recall", 0.5):
        return True
    return False


if __name__ == "__main__":
    require_no_api = "--no-api" in sys.argv
    report = run_eval_suite(require_no_api=require_no_api)
    print(f"Passed: {report['passed']}/{report['total']} (skipped: {report['skipped']})")
    print(f"Intent accuracy: {report['avg_intent_accuracy']}")
    print(f"Tool accuracy: {report['avg_tool_accuracy']}")
    print(f"Keyword recall: {report['avg_keyword_recall']}")
    print(f"Avg latency: {report['avg_latency_seconds']}s")
    if report.get("error"):
        print(f"Error: {report['error']}")
        sys.exit(1)
    if report.get("failed", 0) > 0:
        for r in report.get("results", []):
            if not r.get("passed") and not r.get("skipped"):
                ta = r.get("tool_accuracy")
                kr = r.get("keyword_recall")
                print(f"  FAIL: {r['prompt'][:60]} — tool_acc={ta}, kw_recall={kr}")
        sys.exit(1)


# ── SQLite Storage ──


def _eval_db() -> sqlite3.Connection:
    conn = sqlite3.connect(EVAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_eval_db():
    with _eval_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                total INTEGER NOT NULL,
                passed INTEGER NOT NULL,
                failed INTEGER NOT NULL,
                skipped INTEGER DEFAULT 0,
                pass_rate REAL NOT NULL,
                avg_tool_accuracy REAL,
                avg_keyword_recall REAL,
                avg_intent_accuracy REAL,
                avg_latency_seconds REAL,
                llm_score REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eval_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                intent TEXT,
                expected_intent TEXT,
                intent_accuracy REAL,
                tools_called TEXT,
                expected_tools TEXT,
                tool_accuracy REAL,
                keyword_recall REAL,
                latency REAL,
                passed INTEGER,
                llm_score REAL,
                error TEXT,
                FOREIGN KEY (run_id) REFERENCES eval_runs(id)
            )
        """)
        conn.commit()


def _save_to_sqlite(report: dict):
    _init_eval_db()
    with _eval_db() as conn:
        cur = conn.execute(
            """INSERT INTO eval_runs
               (timestamp, total, passed, failed, skipped, pass_rate,
                avg_tool_accuracy, avg_keyword_recall, avg_intent_accuracy,
                avg_latency_seconds, llm_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                report["timestamp"],
                report["total"],
                report["passed"],
                report["failed"],
                report["skipped"],
                report["pass_rate"],
                report.get("avg_tool_accuracy"),
                report.get("avg_keyword_recall"),
                report.get("avg_intent_accuracy"),
                report.get("avg_latency_seconds"),
                report.get("llm_score"),
            ),
        )
        run_id = cur.lastrowid
        for r in report.get("results", []):
            conn.execute(
                """INSERT INTO eval_results
                   (run_id, prompt, intent, expected_intent, intent_accuracy,
                    tools_called, expected_tools, tool_accuracy, keyword_recall,
                    latency, passed, llm_score, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    r.get("prompt"),
                    r.get("intent"),
                    r.get("expected_intent"),
                    r.get("intent_accuracy"),
                    json.dumps(r.get("tools_called") or []),
                    json.dumps(r.get("expected_tools") or []),
                    r.get("tool_accuracy"),
                    r.get("keyword_recall"),
                    r.get("latency"),
                    int(r.get("passed", False)),
                    r.get("llm_score"),
                    r.get("error"),
                ),
            )
        conn.commit()


# ── LLM-as-Judge ──

_RELEVANCE_SCORE_PROMPT = """You are evaluating Jarvis's response quality. Rate how well the response addresses the user's prompt on a scale of 0.0 to 1.0.

User prompt: {prompt}
Jarvis response: {response}

Criteria:
- 1.0: Perfect response — fully addresses the query with correct, relevant, and complete information
- 0.7: Good response — addresses the query but could be more specific or complete
- 0.4: Partial response — somewhat relevant but missing key information
- 0.0: Irrelevant or wrong — does not address the query at all

Reply with ONLY a number between 0.0 and 1.0."""


def llm_judge_score(prompt: str, response: str) -> float:
    """Score a response on relevance/quality using an LLM judge (0.0-1.0)."""
    try:
        from google.genai import types

        from brain import _get_client

        client = _get_client()
        if not client:
            return 0.5
        text = _RELEVANCE_SCORE_PROMPT.format(prompt=prompt[:500], response=(response or "")[:1000])
        result = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[types.Part(text=text)])],
            config=types.GenerateContentConfig(max_output_tokens=10),
        )
        candidate = result.candidates[0]
        parts = [p.text for p in (candidate.content.parts or []) if hasattr(p, "text") and p.text]
        raw = " ".join(parts).strip()
        score = float(raw)
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.5


# Replace _save_report to also use SQLite
_orig_save = _save_report


def _save_report(report: dict):
    _orig_save(report)
    try:
        _save_to_sqlite(report)
    except Exception:
        pass


# Override run_eval_case to add LLM judge scoring
_orig_run_case = run_eval_case


def run_eval_case(case: dict, require_no_api: bool = False) -> dict:
    result = _orig_run_case(case, require_no_api=require_no_api)
    if not result.get("skipped") and not result.get("error"):
        reply = result.get("reply_preview", "")
        prompt = case.get("prompt", "")
        if reply and prompt:
            result["llm_score"] = llm_judge_score(prompt, reply)
    return result
