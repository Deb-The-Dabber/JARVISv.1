import base64
import datetime
import os
import re
import subprocess
import tempfile
import time

import pyautogui
import requests
from dotenv import load_dotenv

load_dotenv()

DEBUG = os.getenv("JARVIS_DEBUG", "0").lower() in ("1", "true", "yes", "on")
HOME = os.path.expanduser("~")


def _debug(message: str):
    if DEBUG:
        print(f"  [DEBUG] {message}")


def _describe_element(what: str) -> tuple[int, int] | None:
    """Use NVIDIA vision to find coordinates of an element on screen."""
    api_key = (os.getenv("NVIDIA_API_KEY") or "").strip()
    if not api_key:
        return None

    screenshot = pyautogui.screenshot()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        screenshot.save(f.name)
        path = f.name

    try:
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        resp = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            json={
                "model": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
                "max_tokens": 256,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                            {
                                "type": "text",
                                "text": (
                                    f"Find '{what}' on the screen. "
                                    "Return ONLY coordinates in JSON format: "
                                    '{"x": number, "y": number}. '
                                    "The coordinates should be the center of the element. "
                                    'If not found, return {"x": 0, "y": 0}.'
                                ),
                            },
                        ],
                    }
                ],
            },
            timeout=30,
        )
        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        match = re.search(r'"x"\s*:\s*(\d+).*?"y"\s*:\s*(\d+)', text)
        if match:
            x, y = int(match.group(1)), int(match.group(2))
            if x > 0 and y > 0:
                return (x, y)
        return None
    except Exception:
        return None
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def click_on_screen(what: str, max_retries: int = 3):
    """Find an element on screen by description and click it.
    Retries with scroll if not found. Returns structured result."""
    for attempt in range(1, max_retries + 1):
        coords = _describe_element(what)
        if coords is not None:
            x, y = coords
            pyautogui.moveTo(x, y, duration=0.4)
            pyautogui.click()
            return f"Clicked '{what}' at ({x}, {y}) (attempt {attempt})."
        if attempt < max_retries:
            pyautogui.scroll(-3)
            time.sleep(0.5)
    return f"Could not find '{what}' on screen after {max_retries} attempts with scroll."


def move_and_click(x: int, y: int):
    pyautogui.moveTo(x, y, duration=0.4)
    pyautogui.click()
    return f"Clicked at ({x}, {y})."


def type_text(text: str, submit: bool = False):
    """Paste text via clipboard (handles spaces and most characters on macOS)."""
    subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    pyautogui.hotkey("command", "v")
    time.sleep(0.15)
    if submit:
        pyautogui.press("return")
        return f"Typed and sent: {text}"
    return f"Typed: {text}"


def press_key(key: str):
    pyautogui.press(key)
    return f"Pressed {key}."


def take_screenshot():
    path = os.path.join(HOME, "Desktop", f"jarvis_screenshot_{int(datetime.datetime.now().timestamp())}.png")
    screenshot = pyautogui.screenshot()
    screenshot.save(path)
    return f"Screenshot saved to {path}"


def run_terminal_command(command: str):
    from sandbox import run_sandboxed_command

    original_command = command
    # Robust macOS rewrite: case-insensitive regex for Linux ps patterns
    ps_rewrites = [
        (r"ps\s+aux\s+--sort=-%mem", "ps axm -o pid,%mem,%cpu,comm | sort -nrk2 | head -20"),
        (r"ps\s+-ef", "ps -ax"),
        (r"ps\s+aux", "ps ax"),
        (r"ps\s+--sort", "ps axm | sort -nrk2"),
    ]
    for pattern, replacement in ps_rewrites:
        if re.search(pattern, command, re.IGNORECASE):
            command = re.sub(pattern, replacement, command, flags=re.IGNORECASE)
            _debug(f"[Rewrite] Linux ps -> macOS: {original_command[:60]}...")
            break
    result = run_sandboxed_command(command, timeout=30)
    output = result.get("stdout", "").strip() or result.get("stderr", "").strip()
    sandbox_note = " [Sandboxed]" if result.get("sandboxed") else ""
    rewrite_note = " [Rewrote Linux ps syntax for macOS]" if command != original_command else ""
    if result.get("error"):
        error = result["error"]
        if "timed out" in error.lower():
            return f"Command timed out.{sandbox_note}{rewrite_note}"
        return f"Command failed: {error}{sandbox_note}{rewrite_note}"
    if output:
        return output[:1000] + sandbox_note + rewrite_note
    return f"Command ran with no output.{sandbox_note}{rewrite_note}"


COMPUTER_TOOLS = {
    "move_and_click": move_and_click,
    "type_text": type_text,
    "press_key": press_key,
    "take_screenshot": take_screenshot,
    "run_terminal_command": run_terminal_command,
    "click_on_screen": click_on_screen,
}

COMPUTER_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "move_and_click",
            "description": "Move mouse and click at screen coordinates",
            "parameters": {
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the focused field (paste). Set submit=true to press Enter after typing.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "submit": {"type": "boolean"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a keyboard key (e.g. enter, escape)",
            "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot and save to Desktop",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Run a shell command — dangerous, always confirm first. ONLY use when no specific tool exists for the task. Prefer dedicated tools like get_system_info, get_largest_files, search_in_files for file/system operations.",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_on_screen",
            "description": "Find an element on screen by description and click it. Uses vision AI with retry+scroll.",
            "parameters": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "description": "What to click, e.g. 'submit button' or 'Discord #general'",
                    },
                    "max_retries": {
                        "type": "integer",
                        "description": "Max retry attempts with scroll between tries (default 3)",
                    },
                },
                "required": ["what"],
            },
        },
    },
]
