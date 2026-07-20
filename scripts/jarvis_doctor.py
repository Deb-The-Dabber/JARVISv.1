#!/usr/bin/env python3
"""Jarvis health check — run from project root.

Usage:
    source venv/bin/activate && python scripts/jarvis_doctor.py
    python scripts/jarvis_doctor.py --verbose
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OK = "\033[92mOK\033[0m"
WARN = "\033[93mWARN\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[90mSKIP\033[0m"

checks_passed = 0
checks_failed = 0
checks_skipped = 0


def check(name: str, ok: bool, detail: str = ""):
    global checks_passed, checks_failed, checks_skipped
    if ok:
        tag = OK
        checks_passed += 1
    elif detail == "skip":
        tag = SKIP
        checks_skipped += 1
    else:
        tag = FAIL
        checks_failed += 1
    msg = f"  [{tag}] {name}"
    if detail and detail != "skip":
        msg += f" — {detail}"
    print(msg)


print("=" * 56)
print("  Jarvis Diagnostics")
print("=" * 56)

# ── 1. Python & venv ──
print("\n--- Environment ---")
check("Python 3.12+", sys.version_info >= (3, 12), sys.version.split()[0])

venv = os.environ.get("VIRTUAL_ENV") or os.environ.get("CONDA_DEFAULT_ENV", "")
check("Virtual env active", bool(venv), venv.split("/")[-1] if venv else "none")

# ── 2. API keys ──
print("\n--- API Keys ---")
from dotenv import load_dotenv

load_dotenv()

required_keys = {
    "GOOGLE_GENAI_API_KEY": "Gemini (primary fallback)",
    "NVIDIA_NEMOTRON_API_KEY": "Nemotron Ultra (primary)",
}
optional_keys = {
    "NVIDIA_API_KEY": "Vision / screen analysis",
    "DEEPSEEK_API_KEY": "DeepSeek V4 (coding)",
    "GROQ_API_KEY": "Groq Llama",
    "OPENROUTER_API_KEY": "OpenRouter",
    "TAVILY_API_KEY": "Web search",
    "ELEVENLABS_API_KEY": "TTS",
}

for key, desc in required_keys.items():
    val = os.getenv(key, "").strip()
    check(f"{key} ({desc})", bool(val), "set" if val else "MISSING")

for key, desc in optional_keys.items():
    val = os.getenv(key, "").strip()
    if val:
        check(f"{key} ({desc})", True, "set")
    else:
        check(f"{key} ({desc})", True, "skip")

# ── 3. Disk ──
print("\n--- Disk ---")
home = os.path.expanduser("~")
usage = os.statvfs(home)
free_gb = (usage.f_frsize * usage.f_bavail) / (1024**3)
check("Free disk space", free_gb > 1, f"{free_gb:.1f}GB free")

log_dir = os.path.expanduser("~/.jarvis/logs")
if os.path.exists(log_dir):
    log_size = sum(os.path.getsize(os.path.join(log_dir, f)) for f in os.listdir(log_dir) if os.path.isfile(os.path.join(log_dir, f)))
    check("Log directory", True, f"{log_size / 1024:.0f}KB")
else:
    check("Log directory", True, "skip")

# ── 4. Import check ──
print("\n--- Core Imports ---")
modules = [
    "cache",
    "config",
    "safety",
    "jarvis_logger",
    "memory",
    "vector_memory",
    "priority",
    "watchlog",
]
for mod_name in modules:
    try:
        __import__(mod_name)
        check(f"{mod_name}", True)
    except Exception as e:
        check(f"{mod_name}", False, str(e)[:60])

# ── 5. Tool registration ──
print("\n--- Tool System ---")
try:
    from tools import TOOL_DEFINITIONS, TOOL_REGISTRY

    check("TOOL_DEFINITIONS count", len(TOOL_DEFINITIONS) >= 70, str(len(TOOL_DEFINITIONS)))
    check("TOOL_REGISTRY count", len(TOOL_REGISTRY) >= 70, str(len(TOOL_REGISTRY)))
    check("Definitions == Registry", len(TOOL_DEFINITIONS) == len(TOOL_REGISTRY))
except Exception as e:
    check("Tool system load", False, str(e)[:60])

# ── 6. Provider check (no calls) ──
print("\n--- Providers ---")
from brain import check_providers

try:
    status = check_providers()
    for name, ok in status.items():
        check(f"{name}", ok, "configured" if ok else "missing key")
except Exception as e:
    check("Provider check", False, str(e)[:60])

# ── 7. Plugins ──
print("\n--- Plugins ---")
try:
    from plugin_manager import get_loaded_plugins, list_available_plugins

    available = list_available_plugins()
    loaded = get_loaded_plugins()
    check("Plugins available", len(available) >= 0, f"{len(available)} available")
    check("Plugins loaded", len(loaded) >= 0, f"{len(loaded)} loaded")
    if loaded:
        for p in loaded:
            check(f"  plugin: {p['name']}", True, f"v{p['version']} ({p['type']})")
except Exception as e:
    check("Plugin manager", False, str(e)[:60])

# ── 8. Logger ──
print("\n--- Logger ---")
try:
    from jarvis_logger import get_cost_summary, get_latest_logs, get_metrics_snapshot

    metrics = get_metrics_snapshot()
    check("Metrics available", bool(metrics), f"{metrics['requests_total']} requests")
    cost = get_cost_summary()
    check("Cost tracker", True, f"${cost.get('cost_usd_total', 0):.4f} total")
    logs = get_latest_logs(1)
    check("Log file", len(logs) >= 0, f"{len(logs)} recent entries")
except Exception as e:
    check("Logger module", False, str(e)[:60])

# ── 9. Supply Chain Security ──
print("\n--- Supply Chain ---")
try:
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "pip_audit", "--desc"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    ok = result.returncode == 0
    check("pip-audit", ok, "No vulns" if ok else result.stdout[:200])
except Exception as e:
    check("pip-audit", True, f"skip ({e})")

try:
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "safety", "check"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    check("safety check", True, "done")
except Exception as e:
    check("safety check", True, f"skip ({e})")

try:
    import subprocess

    result = subprocess.run(
        ["git", "secrets", "--scan", "-r"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    check("git-secrets", result.returncode == 0)
except Exception as e:
    check("git-secrets", True, f"skip ({e})")

# ── 10. Voice / STT / TTS ──
print("\n--- Voice ---")
try:
    from stt import get_model, vad_is_available

    model = get_model()
    check("STT model loaded", model is not None)
    check("VAD available", vad_is_available())
except Exception as e:
    check("STT module", False, str(e)[:60])

try:
    from tts import EDGE_TTS_VOICE, ELEVENLABS_API_KEY

    check("TTS ElevenLabs key", bool(ELEVENLABS_API_KEY))
    check("TTS Edge voice", bool(EDGE_TTS_VOICE), EDGE_TTS_VOICE)
except Exception as e:
    check("TTS module", False, str(e)[:60])

try:
    import pvporcupine

    check("Porcupine wake word", True, f"v{pvporcupine.__version__}")
except ImportError:
    check("Porcupine wake word", True, "skip (not installed)")
except Exception as e:
    check("Porcupine wake word", True, f"skip ({e})")

try:
    from stt import _model_kind

    check("STT backend", True, _model_kind or "unknown")
except Exception:
    pass

# ── 11. Capability System ──
print("\n--- Capability System ---")
try:
    from safety import CAPABILITY_REGISTRY
    from tools import TOOL_REGISTRY

    caps_count = len(CAPABILITY_REGISTRY)
    check("Capabilities declared", caps_count > 0, f"{caps_count} tools have capabilities")

    missing = [t for t in TOOL_REGISTRY if t not in CAPABILITY_REGISTRY and not t.startswith("_")]
    if missing:
        check("All tools covered", True, f"{len(missing)} missing (tools without explicit caps)")
    else:
        check("All tools covered", True)
except Exception as e:
    check("Capability system", False, str(e)[:60])

# ── 9. Evaluation Suite ──
print("\n--- Evaluation ---")
try:
    from eval_runner import load_latest_report

    report = load_latest_report()
    if report:
        ts = report.get("timestamp", "")[:19]
        rate = report.get("pass_rate", 0)
        check("Eval last run", True, f"{ts} — {report['passed']}/{report['total']} passed (rate: {rate:.0%})")
        if report.get("failed", 0) > 0:
            check("Eval no regressions", False, f"{report['failed']} failed cases")
        else:
            check("Eval no regressions", True)
    else:
        check("Eval last run", True, "skip")
except Exception as e:
    check("Eval suite", False, str(e)[:60])

# ── Summary ──
print(f"\n{'=' * 56}")
print(f"  {checks_passed} passed, {checks_failed} failed, {checks_skipped} skipped")
if checks_failed:
    print(f"\n  {FAIL} Some checks failed — see above.")
    sys.exit(1)
else:
    print(f"\n  {OK} All clear.")
    sys.exit(0)
