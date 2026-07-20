import ast
import os
import subprocess
import tempfile


def validate_file_syntax(filename: str, content: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".py":
        return _validate_python(content)
    elif ext in (".c", ".h"):
        return _validate_c(filename, content)
    return ""


def _validate_python(content: str) -> str:
    try:
        ast.parse(content)
        return ""
    except SyntaxError as e:
        return f"Python syntax error: {e}"


def _validate_c(filename: str, content: str) -> str:
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=os.path.splitext(filename)[1], delete=False) as f:
            f.write(content)
            tmp_path = f.name
        result = subprocess.run(
            ["gcc", "-fsyntax-only", "-x", "c", tmp_path],
            capture_output=True,
            text=True,
            timeout=15,
        )
        os.unlink(tmp_path)
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            lines = [l for l in stderr.split("\n") if "error:" in l.lower() or "warning:" in l.lower()]
            msg = "; ".join(lines[:3]) if lines else f"compilation error (code {result.returncode})"
            return f"C syntax error: {msg}"
        return ""
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""
