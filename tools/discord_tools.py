"""Discord web automation in Safari/Chrome via keyboard shortcuts (Cmd+K quick switcher)."""

import subprocess
import time

DEFAULT_BROWSER = "Safari"


def _escape_applescript(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _run_applescript(script: str) -> tuple[str, str]:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()


def _activate_browser(browser: str) -> str | None:
    script = f'tell application "{browser}" to activate'
    _, err = _run_applescript(script)
    if err:
        return f"Couldn't activate {browser}. Open it first and allow Accessibility for Terminal/Cursor in System Settings → Privacy."
    time.sleep(0.6)
    return None


def discord_open_channel(channel_name: str, browser: str = DEFAULT_BROWSER):
    """
    Open a Discord channel/DM using the in-app quick switcher (Cmd+K).
    Discord must already be loaded in the browser and you must be logged in.
    """
    err = _activate_browser(browser)
    if err:
        return err

    name = _escape_applescript(channel_name.strip())
    script = f'''
tell application "System Events"
    keystroke "k" using command down
    delay 0.4
    keystroke "{name}"
    delay 0.8
    keystroke return
end tell
'''
    _, run_err = _run_applescript(script)
    if run_err:
        return f"Quick-switch may have failed: {run_err[:200]}. Grant Accessibility permission and ensure Discord is open in the browser."
    time.sleep(0.5)
    return f"Opened Discord channel matching '{channel_name}'."


def discord_send_message(text: str, browser: str = DEFAULT_BROWSER):
    """Type and send a message in the active Discord channel (message box must be focused)."""
    import subprocess

    err = _activate_browser(browser)
    if err:
        return err

    msg = text.strip()
    subprocess.run(["pbcopy"], input=msg.encode("utf-8"), check=True)
    script = """
tell application "System Events"
    keystroke "v" using command down
    delay 0.25
    keystroke return
end tell
"""
    _, run_err = _run_applescript(script)
    if run_err:
        return f"Couldn't send message: {run_err[:200]}"
    return f"Sent: {msg}"


def discord_open_and_send(channel_name: str, message: str, browser: str = DEFAULT_BROWSER):
    """Open a channel via quick switcher, then send a message."""
    open_result = discord_open_channel(channel_name, browser=browser)
    if open_result.startswith("Couldn't") or open_result.startswith("Quick-switch may have failed"):
        return open_result
    time.sleep(1.0)
    return discord_send_message(message, browser=browser)


DISCORD_TOOLS = {
    "discord_open_channel": discord_open_channel,
    "discord_send_message": discord_send_message,
    "discord_open_and_send": discord_open_and_send,
}

DISCORD_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "discord_open_channel",
            "description": "Open a Discord channel or DM in the browser using Cmd+K quick switcher. User must be logged into discord.com.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_name": {"type": "string", "description": "Partial channel name, e.g. Electrolights V2 Official"},
                    "browser": {"type": "string", "description": "Safari or Google Chrome"},
                },
                "required": ["channel_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_send_message",
            "description": "Send a message in the currently open Discord channel in the browser",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "browser": {"type": "string"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discord_open_and_send",
            "description": "Open a Discord channel by name and send a message in one step (Safari/Chrome, discord.com)",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_name": {"type": "string"},
                    "message": {"type": "string"},
                    "browser": {"type": "string"},
                },
                "required": ["channel_name", "message"],
            },
        },
    },
]
