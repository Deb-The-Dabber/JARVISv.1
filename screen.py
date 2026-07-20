import datetime
import os
import subprocess
import tempfile

import requests

HOME = os.path.expanduser("~")
OLLAMA_URL = "http://localhost:11434/api/chat"


def get_frontmost_app() -> str:
    """Get the name of the currently focused app."""
    script = 'tell application "System Events" to get name of first process whose frontmost is true'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.stdout.strip()


def capture_screenshot() -> str:
    """Take a screenshot and return the file path."""
    path = os.path.join(tempfile.gettempdir(), f"jarvis_screen_{int(datetime.datetime.now().timestamp())}.png")
    subprocess.run(["screencapture", "-x", path], check=True)
    return path


def describe_screen_with_moondream(screenshot_path: str, question: str = "What is on this screen? Be concise.") -> str:
    """Use Moondream via Ollama to describe the screen."""
    try:
        import base64

        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        response = requests.post(OLLAMA_URL, json={"model": "moondream", "messages": [{"role": "user", "content": question, "images": [img_b64]}], "stream": False}, timeout=60)

        return response.json()["message"]["content"].strip()
    except Exception as e:
        return f"Couldn't analyze screen: {e}"
    finally:
        # Clean up temp screenshot
        try:
            os.remove(screenshot_path)
        except Exception:
            pass


def read_screen(question: str = "What is on this screen?") -> str:
    """Take a screenshot and describe it using Moondream."""
    app = get_frontmost_app()
    path = capture_screenshot()
    description = describe_screen_with_moondream(path, question)
    return f"Frontmost app: {app}. {description}"


def find_on_screen(what: str) -> str:
    """Ask Moondream to find something specific on screen."""
    path = capture_screenshot()
    question = f"Where is the {what} on this screen? Describe its location precisely."
    result = describe_screen_with_moondream(path, question)
    return result


def summarize_current_screen() -> str:
    """Get a brief summary of what's on screen."""
    path = capture_screenshot()
    question = "Briefly describe what's on this screen in 1-2 sentences. Focus on the main content."
    app = get_frontmost_app()
    description = describe_screen_with_moondream(path, question)
    return f"{app}: {description}"


def check_screen_for_alerts() -> str:
    """Check if there's anything urgent on screen."""
    path = capture_screenshot()
    question = (
        "Is there anything urgent, important, or requiring attention on this screen? "
        "Look for: error messages, notifications, alerts, unread messages, warnings. "
        "If nothing urgent, just say 'Nothing urgent.' Be very brief."
    )
    return describe_screen_with_moondream(path, question)
