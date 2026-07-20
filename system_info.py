import os
import platform
import subprocess

HOME = os.path.expanduser("~")

def fetch_system_info():
    info = {}
    try:
        result = subprocess.run(["system_profiler", "SPHardwareDataType"],
                                capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            if "Model Name" in line:
                info["model"] = line.split(":")[-1].strip()
            if "Chip" in line or "Processor Name" in line:
                info["chip"] = line.split(":")[-1].strip()
            if "Memory:" in line:
                info["ram"] = line.split(":")[-1].strip()
    except Exception:
        info["model"] = platform.machine()
    try:
        result = subprocess.run(["sw_vers"], capture_output=True, text=True, timeout=5)
        v = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                k, val = line.split(":", 1)
                v[k.strip()] = val.strip()
        info["os"] = f"macOS {v.get('ProductVersion','?')} ({v.get('ProductName','')})"
    except Exception:
        info["os"] = platform.platform()
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        parts = result.stdout.strip().splitlines()[1].split()
        info["disk_total"] = parts[1]
        info["disk_free"] = parts[3]
    except Exception:
        pass
    info["username"] = os.environ.get("USER", "unknown")
    return info
