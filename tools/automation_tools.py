"""
Automation Mode tools — exposed to the LLM for the automation workflow.
"""

import os
import json
from pathlib import Path
from typing import Any


def start_automation(task_description: str) -> str:
    """
    Start a new automation session.

    Args:
        task_description: What you want to automate (e.g., "build a REST API in VS Code",
                          "research Python async patterns", "organize my downloads folder")
    """
    from automation import AutomationEngine

    engine = AutomationEngine()
    return engine.start_automation(task_description)


def automation_respond(response: str) -> str:
    """
    Respond to an automation prompt (IDE selection, folder selection, code task, etc.).

    Args:
        response: Your response to the current automation prompt
    """
    from automation import AutomationEngine

    engine = AutomationEngine()
    return engine.handle_user_response(response)


def get_automation_status() -> str:
    """Get the current automation session status."""
    from automation import AutomationEngine

    engine = AutomationEngine()
    session = engine.current_session
    if not session:
        return "No active automation session."
    return f"Session: {session.session_id}\nState: {session.state.value}\nTask: {session.task_description}\nType: {session.task_type.value}\nIDE: {session.ide or 'Not selected'}\nFolder: {session.project_folder or 'Not selected'}"


def cancel_automation() -> str:
    """Cancel the current automation session."""
    from automation import AutomationEngine

    engine = AutomationEngine()
    if engine.current_session:
        session_id = engine.current_session.session_id
        engine.current_session = None
        return f"Automation session {session_id} cancelled."
    return "No active automation session to cancel."


# Tool definitions
AUTOMATION_TOOLS = {
    "start_automation": start_automation,
    "automation_respond": automation_respond,
    "get_automation_status": get_automation_status,
    "cancel_automation": cancel_automation,
}

AUTOMATION_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "start_automation",
            "description": "Start a new automation session. Tell JARVIS what you want to automate (coding, research, file ops, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "What you want to automate (e.g., 'build a REST API in VS Code', 'research Python async patterns', 'organize my downloads folder')"
                    }
                },
                "required": ["task_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automation_respond",
            "description": "Respond to an automation prompt (IDE selection, folder selection, code task, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "Your response to the current automation prompt"
                    }
                },
                "required": ["response"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_automation_status",
            "description": "Get the current automation session status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_automation",
            "description": "Cancel the current automation session.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

__all__ = [
    "start_automation",
    "automation_respond",
    "get_automation_status",
    "cancel_automation",
    "AUTOMATION_TOOLS",
    "AUTOMATION_DEFINITIONS",
]