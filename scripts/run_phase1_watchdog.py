#!/usr/bin/env python3
"""Run baseline under watchdog: dump traceback after JARVIS_WATCHDOG seconds, exit."""

import faulthandler
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

watchdog_s = int(os.getenv("JARVIS_WATCHDOG", "90"))
faulthandler.enable()
faulthandler.dump_traceback_later(watchdog_s, exit=False, file=sys.stderr)

from scripts.run_phase1_baseline import print_summary, run_phase1_baseline  # noqa: E402

report = run_phase1_baseline(require_no_api="--no-api" in sys.argv)
print_summary(report)
sys.exit(1 if report.get("failed", 0) > 0 else 0)
