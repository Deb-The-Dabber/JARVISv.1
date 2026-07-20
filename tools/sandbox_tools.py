from sandbox import run_sandboxed_command, run_sandboxed_python


def run_python_sandboxed(code: str, timeout: int = 30, memory_mb: int = 256, cpu_seconds: int = 30) -> str:
    """Run Python code in an isolated sandbox with resource limits."""
    result = run_sandboxed_python(code, timeout=timeout, memory_mb=memory_mb, cpu_seconds=cpu_seconds)
    parts = [f"Exit code: {result['exit_code']}"]
    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()
    if stdout:
        parts.append(f"STDOUT:\n{stdout}")
    if stderr:
        parts.append(f"STDERR:\n{stderr}")
    if result.get("error"):
        parts.append(f"Error: {result['error']}")
    sandboxed = result.get("sandboxed", False)
    if sandboxed:
        parts.append(f"[Sandboxed] CPU: {cpu_seconds}s, Mem: {memory_mb}MB, No network")
    return "\n\n".join(parts)


def run_command_sandboxed(command: str, timeout: int = 30, memory_mb: int = 256, cpu_seconds: int = 30, allow_network: bool = False) -> str:
    """Run a shell command in an isolated sandbox with resource limits."""
    result = run_sandboxed_command(command, timeout=timeout, memory_mb=memory_mb, cpu_seconds=cpu_seconds, allow_network=allow_network)
    output = result.get("stdout", "").strip() or result.get("stderr", "").strip()
    sandboxed = result.get("sandboxed", False)
    sandbox_note = ""
    if sandboxed:
        net = "Network allowed" if allow_network else "No network"
        sandbox_note = f" [Sandboxed] CPU: {cpu_seconds}s, Mem: {memory_mb}MB, {net}"
    if result.get("error"):
        error = result["error"]
        if "timed out" in error.lower():
            return f"Command timed out.{sandbox_note}"
        return f"Command failed: {error}{sandbox_note}"
    if output:
        return output[:1000] + sandbox_note
    return f"Command ran with no output.{sandbox_note}"


SANDBOX_TOOLS = {
    "run_python_sandboxed": run_python_sandboxed,
    "run_command_sandboxed": run_command_sandboxed,
}

SANDBOX_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "run_python_sandboxed",
            "description": ("Run Python code in an isolated sandbox with CPU/memory limits (256MB, 30s), no network. Safer than run_python."),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {"type": "integer", "description": "Max execution time in seconds (default 30)"},
                    "memory_mb": {"type": "integer", "description": "Memory limit in MB (default 256)"},
                    "cpu_seconds": {"type": "integer", "description": "CPU time limit in seconds (default 30)"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command_sandboxed",
            "description": ("Run a shell command in an isolated sandbox with CPU/memory limits. No network by default. Safer than run_terminal_command."),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Max execution time in seconds (default 30)"},
                    "memory_mb": {"type": "integer", "description": "Memory limit in MB (default 256)"},
                    "cpu_seconds": {"type": "integer", "description": "CPU time limit in seconds (default 30)"},
                    "allow_network": {"type": "boolean", "description": "Allow network access (default false)"},
                },
                "required": ["command"],
            },
        },
    },
]
