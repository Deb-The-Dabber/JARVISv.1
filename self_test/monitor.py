"""Optional scheduled self-test monitor.

Disabled by default (JARVIS_SELF_TEST_SCHEDULE=1 to enable). When enabled,
runs a full scan every JARVIS_SELF_TEST_INTERVAL seconds (default 6h) as long
as no scan is already running.
"""

import os
import threading
import time

SCHEDULE_ENABLED_ENV = "JARVIS_SELF_TEST_SCHEDULE"
MIN_INTERVAL_ENV = "JARVIS_SELF_TEST_INTERVAL"
DEFAULT_MIN_INTERVAL = 6 * 3600
_CHECK_INTERVAL = 60

_started = False
_lock = threading.Lock()


def start():
    global _started
    with _lock:
        if _started:
            return
        if os.getenv(SCHEDULE_ENABLED_ENV, "0").lower() not in ("1", "true", "yes", "on"):
            return
        _started = True
    threading.Thread(target=_loop, daemon=True).start()


def _loop():
    try:
        interval = float(os.getenv(MIN_INTERVAL_ENV, str(DEFAULT_MIN_INTERVAL)))
    except ValueError:
        interval = DEFAULT_MIN_INTERVAL
    last = 0.0
    while True:
        time.sleep(_CHECK_INTERVAL)
        if time.time() - last < interval:
            continue
        last = time.time()
        try:
            from .agent import _agent

            _agent.run(hours=24, use_llm=True)
        except Exception:
            pass
