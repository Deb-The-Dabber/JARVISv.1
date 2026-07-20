import datetime
import glob
import os
import shutil
import subprocess

HOME = os.path.expanduser("~")

SCREENSHOT_DIRS = [
    os.path.join(HOME, "Desktop"),
    os.path.join(HOME, "Pictures", "Screenshots"),
]

FILE_TYPE_FOLDERS = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg", ".tiff"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv", ".m4v"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".md", ".pages", ".xls", ".xlsx", ".pptx", ".csv"],
    "Archives": [".zip", ".tar", ".gz", ".rar", ".7z", ".dmg", ".pkg"],
    "Audio": [".mp3", ".wav", ".aac", ".flac", ".m4a"],
    "Code": [".py", ".js", ".ts", ".html", ".css", ".json", ".sh"],
}


def find_recent_screenshot():
    files = []
    for d in SCREENSHOT_DIRS:
        if os.path.exists(d):
            for ext in ["*.png", "*.jpg", "*.jpeg"]:
                files.extend(glob.glob(os.path.join(d, ext)))
    if not files:
        return "No screenshots found."
    latest = max(files, key=os.path.getmtime)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(latest))
    subprocess.run(["open", "-R", latest])
    return f"Most recent: '{os.path.basename(latest)}' taken {mtime.strftime('%B %d at %I:%M %p')}. Revealed in Finder."


def get_largest_files(folder: str = "~/Downloads", count: int = 5):
    folder = os.path.expanduser(folder)
    if not os.path.exists(folder):
        return f"{folder} doesn't exist."
    files = [(os.path.join(folder, f), os.path.getsize(os.path.join(folder, f))) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]
    if not files:
        return "No files found."
    files.sort(key=lambda x: x[1], reverse=True)
    parts = [f"{os.path.basename(p)} ({s / (1024**2):.1f} MB)" for p, s in files[:count]]
    return f"Largest files in {os.path.basename(folder)}: {', '.join(parts)}."


def organize_downloads():
    folder = os.path.join(HOME, "Downloads")
    moved = 0
    for filename in os.listdir(folder):
        src = os.path.join(folder, filename)
        if not os.path.isfile(src):
            continue
        ext = os.path.splitext(filename)[1].lower()
        target = "Others"
        for fname, exts in FILE_TYPE_FOLDERS.items():
            if ext in exts:
                target = fname
                break
        dest_dir = os.path.join(folder, target)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        if not os.path.exists(dest):
            shutil.move(src, dest)
            moved += 1
    subprocess.run(["open", folder])
    return f"Organized {moved} files into subfolders."


def open_in_finder(folder: str):
    subprocess.run(["open", os.path.expanduser(folder)])
    return f"Opened {folder} in Finder."


def create_file(filename: str, content: str, path: str = None) -> str:
    folder = os.path.expanduser(path) if path else os.path.join(HOME, "Desktop")
    os.makedirs(folder, exist_ok=True)
    full_path = os.path.join(folder, filename)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    result = f"File created at {full_path}"
    validate_result = _validate_file_syntax(filename, content)
    if validate_result:
        result += f"\nWarning: {validate_result}"
    return result


def _validate_file_syntax(filename: str, content: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".py":
        try:
            import ast

            ast.parse(content)
            return ""
        except SyntaxError as e:
            return f"Python syntax error: {e}"
    elif ext in (".c", ".h"):
        import subprocess
        import tempfile

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False) as f:
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
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
    return ""


FILE_TOOLS = {
    "find_recent_screenshot": find_recent_screenshot,
    "get_largest_files": get_largest_files,
    "organize_downloads": organize_downloads,
    "open_in_finder": open_in_finder,
    "create_file": create_file,
}

FILE_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "find_recent_screenshot",
            "description": "Find the most recent screenshot and reveal in Finder",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_largest_files",
            "description": "Find largest files in a folder (default Downloads). Also shows most recently downloaded files. Use this for 'find my latest download' or 'find large files'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {"type": "string"},
                    "count": {"type": "integer", "description": "Number of largest files to show (default 5)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "organize_downloads",
            "description": "Organize Downloads folder into subfolders by file type",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_in_finder",
            "description": "Open a folder in Finder",
            "parameters": {"type": "object", "properties": {"folder": {"type": "string"}}, "required": ["folder"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a new file with given content, defaults to Desktop",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                    "path": {"type": "string", "description": "Directory to create file in. Defaults to Desktop."},
                },
                "required": ["filename", "content"],
            },
        },
    },
]
