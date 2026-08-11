#!/usr/bin/env python3
"""Watch a baseline run and report when a resource_tracker child spawns."""

import os
import subprocess
import time

log = open("/tmp/baseline_B_watch.log", "w")
p = subprocess.Popen(
    [
        "venv/bin/python",
        "-u",
        "-X",
        "faulthandler",
        "scripts/run_phase1_watchdog.py",
    ],
    env={**os.environ, "JARVIS_INSTRUMENTATION": "0", "JARVIS_WATCHDOG": "300"},
    stdout=log,
    stderr=subprocess.STDOUT,
)

t0 = time.time()
last_task = ""
last_rt = None
while p.poll() is None:
    time.sleep(2)
    task_line = subprocess.run(
        ["grep", "\\[[0-9]/10\\]", "/tmp/baseline_B_watch.log"],
        capture_output=True,
        text=True,
    )
    tasks = [ln for ln in task_line.stdout.splitlines() if ln]
    cur_task = tasks[-1][:60] if tasks else ""
    if cur_task != last_task:
        print(f"[{time.time() - t0:5.0f}s] task: {cur_task}", flush=True)
        last_task = cur_task
    rt = subprocess.run(["pgrep", "-f", "resource_tracker"], capture_output=True, text=True)
    cur_rt = len([pid for pid in rt.stdout.split() if pid])
    if cur_rt != last_rt:
        print(f"[{time.time() - t0:5.0f}s] resource_tracker children: {cur_rt}", flush=True)
        last_rt = cur_rt

print(f"[{time.time() - t0:5.0f}s] process exited rc={p.returncode}", flush=True)
