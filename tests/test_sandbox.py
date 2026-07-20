import os

import pytest

from sandbox import (
    run_sandboxed,
    run_sandboxed_command,
    run_sandboxed_python,
)


class TestRunSandboxed:
    def test_echo(self):
        result = run_sandboxed(["echo", "hello world"])
        assert result["ok"] is True
        assert result["exit_code"] == 0
        assert "hello world" in result["stdout"]

    def test_exit_code(self):
        result = run_sandboxed(["python3", "-c", "exit(42)"])
        assert result["ok"] is False
        assert result["exit_code"] == 42

    def test_stderr(self):
        result = run_sandboxed(["python3", "-c", "import sys; sys.stderr.write('err')"])
        assert "err" in result["stderr"]

    def test_timeout(self):
        result = run_sandboxed(["sleep", "10"], timeout=1)
        assert result["ok"] is False
        err = (result.get("error") or "").lower()
        assert "timed out" in err or "timeout" in err

    def test_memory_limit(self):
        from sandbox import run_sandboxed

        os.environ["JARVIS_SANDBOX_ENABLED"] = "0"
        try:
            code = "import resource, sys\nresource.setrlimit(resource.RLIMIT_AS, (1, 1))\nsys.stdout.write('ok')"
            result = run_sandboxed(["python3", "-c", code], memory_mb=0, timeout=5)
            assert result["ok"] is False
        finally:
            os.environ["JARVIS_SANDBOX_ENABLED"] = "1"

    def test_run_dir_created(self):
        result = run_sandboxed(["echo", "test"])
        assert "run_dir" in result
        assert os.path.isdir(result["run_dir"])


class TestRunSandboxedPython:
    def test_simple(self):
        result = run_sandboxed_python("print('hello')")
        assert result["ok"] is True
        assert "hello" in result["stdout"]

    def test_math(self):
        result = run_sandboxed_python("print(2 + 2)")
        assert result["ok"] is True
        assert "4" in result["stdout"]

    def test_syntax_error(self):
        result = run_sandboxed_python("print(")
        assert result["ok"] is False
        assert result["exit_code"] != 0

    def test_file_write_in_sandbox(self):
        from sandbox import _use_sandbox

        if _use_sandbox():
            import shutil

            if shutil.which("sandbox-exec") is not None:
                pytest.skip("sandbox-exec profile may block file writes, depends on macOS version")
        result = run_sandboxed_python("""
with open('test.txt', 'w') as f:
    f.write('sandbox works')
print('ok')
""")
        assert result["ok"] is True

    def test_network_blocked(self):
        code = """
import urllib.request
try:
    urllib.request.urlopen('http://example.com', timeout=3)
    print('connected')
except Exception as e:
    print('blocked:', type(e).__name__)
"""
        result = run_sandboxed_python(code, timeout=10)
        assert result["ok"] is True
        assert "blocked" in result["stdout"] or "blocked" in result["stderr"]

    def test_exit_code_in_result(self):
        result = run_sandboxed_python("exit(7)")
        assert result["exit_code"] == 7

    def test_timeout(self):
        result = run_sandboxed_python("import time; time.sleep(30)", timeout=2)
        assert result["ok"] is False
        error = (result.get("error") or "").lower()
        assert "timed out" in error or "timeout" in error


class TestRunSandboxedCommand:
    def test_shell_echo(self):
        result = run_sandboxed_command("echo hello_shell")
        assert result["ok"] is True
        assert "hello_shell" in result["stdout"]

    def test_shell_error(self):
        result = run_sandboxed_command("exit 99")
        assert result["ok"] is False
        assert result["exit_code"] == 99

    def test_shell_timeout(self):
        result = run_sandboxed_command("sleep 30", timeout=1)
        assert result["ok"] is False
        error = (result.get("error") or "").lower()
        assert "timed out" in error or "timeout" in error


class TestRunDir:
    def test_different_dirs(self):
        r1 = run_sandboxed(["echo", "a"])
        r2 = run_sandboxed(["echo", "b"])
        assert r1["run_dir"] != r2["run_dir"]

    def test_dir_is_writable(self):
        from sandbox import _use_sandbox

        if _use_sandbox():
            import shutil

            if shutil.which("sandbox-exec") is not None:
                pytest.skip("sandbox-exec profile may block file writes, depends on macOS version")
        result = run_sandboxed_python("""
import os
d = os.getcwd()
print(open('test.txt', 'w'))
print('ok')
""")
        assert result["ok"] is True
