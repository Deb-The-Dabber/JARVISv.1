"""
Automation Mode — JARVIS's proactive coding & task automation engine.

Flow:
1. User triggers automation mode
2. JARVIS asks "What do you want to automate today?"
3. User describes the task
4. JARVIS classifies intent → routes to appropriate handler
5. For coding tasks: detects IDE, asks for folder, then codes like a human
6. For other tasks: delegates to appropriate subsystem
7. If JARVIS can't do it: learns how, fixes own code via DeepSeek, asks user to restart
8. Session state persisted to memory for resume capability
"""

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from agent import score_intent_categories, get_top_intent
from memory import save_memory
from tools import TOOL_REGISTRY


class AutomationState(Enum):
    IDLE = "idle"
    AWAITING_TASK = "awaiting_task"
    DETECTING_IDE = "detecting_ide"
    SELECTING_IDE = "selecting_ide"
    SELECTING_FOLDER = "selecting_folder"
    AWAITING_CODE_TASK = "awaiting_code_task"
    EXECUTING = "executing"
    LEARNING = "learning"
    AWAITING_RESTART = "awaiting_restart"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskType(Enum):
    CODING = "coding"
    RESEARCH = "research"
    BUILDING = "building"
    CAD = "cad"
    AUTOMATION = "automation"
    FILE_OPS = "file_ops"
    UNKNOWN = "unknown"


@dataclass
class AutomationSession:
    session_id: str
    created_at: datetime
    updated_at: datetime
    state: AutomationState = AutomationState.IDLE
    task_description: str = ""
    task_type: TaskType = TaskType.UNKNOWN
    ide: str = ""
    ide_path: str = ""
    project_folder: str = ""
    code_task: str = ""
    ide_detected: list = field(default_factory=list)
    folders_found: list = field(default_factory=list)
    steps_completed: list = field(default_factory=list)
    current_step: str = ""
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "state": self.state.value,
            "task_description": self.task_description,
            "task_type": self.task_type.value,
            "ide": self.ide,
            "ide_path": self.ide_path,
            "project_folder": self.project_folder,
            "code_task": self.code_task,
            "ide_detected": self.ide_detected,
            "folders_found": self.folders_found,
            "steps_completed": self.steps_completed,
            "current_step": self.current_step,
            "error": self.error,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationSession":
        session = cls(
            session_id=data["session_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            state=AutomationState(data["state"]),
            task_description=data["task_description"],
            task_type=TaskType(data["task_type"]),
            ide=data["ide"],
            ide_path=data["ide_path"],
            project_folder=data["project_folder"],
            code_task=data["code_task"],
            ide_detected=data.get("ide_detected", []),
            folders_found=data.get("folders_found", []),
            steps_completed=data.get("steps_completed", []),
            current_step=data.get("current_step", ""),
            error=data.get("error", ""),
            metadata=data.get("metadata", {}),
        )
        return session


class AutomationEngine:
    """Main automation engine — orchestrates the automation workflow."""

    SESSION_FILE = os.path.expanduser("~/.jarvis/automation_sessions.json")
    SESSION_LOCK = threading.Lock()

    def __init__(self):
        self.current_session: Optional[AutomationSession] = None
        self._load_sessions()

    def _load_sessions(self):
        """Load persisted sessions from disk."""
        try:
            if os.path.exists(self.SESSION_FILE):
                with open(self.SESSION_FILE, "r") as f:
                    data = json.load(f)
                    # Could restore last session here if needed
        except Exception:
            pass

    def _save_sessions(self):
        """Persist sessions to disk."""
        try:
            os.makedirs(os.path.dirname(self.SESSION_FILE), exist_ok=True)
            # For now, just save current session
            if self.current_session:
                with open(self.SESSION_FILE, "w") as f:
                    json.dump(self.current_session.to_dict(), f, indent=2)
        except Exception:
            pass

    def start_automation(self, task_description: str) -> str:
        """Start a new automation session."""
        from agent import score_intent_categories, get_top_intent

        session = AutomationSession(
            session_id=datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
            state=AutomationState.AWAITING_TASK,
            task_description=task_description,
        )

        # Classify task type
        scores = score_intent_categories(task_description)
        top_intent, top_score = get_top_intent(task_description, threshold=3)

        intent_to_task_type = {
            "coding": TaskType.CODING,
            "research": TaskType.RESEARCH,
            "file_ops": TaskType.FILE_OPS,
            "automation": TaskType.AUTOMATION,
            "browser": TaskType.FILE_OPS,  # browser tasks often involve file ops
            "agent_signals": TaskType.AUTOMATION,
        }

        task_type = intent_to_task_type.get(top_intent, TaskType.UNKNOWN)
        session.task_type = task_type

        self.current_session = session
        self._save_sessions()

        return self._prompt_next_step(session)

    def _prompt_next_step(self, session: AutomationSession) -> str:
        """Generate the next prompt for the user based on current state."""
        session.updated_at = datetime.now()
        self._save_sessions()

        if session.state == AutomationState.AWAITING_TASK:
            return "What do you want to automate today? Describe the task in your own words."

        elif session.state == AutomationState.DETECTING_IDE:
            return self._detect_ides(session)

        elif session.state == AutomationState.SELECTING_IDE:
            ides = session.ide_detected
            if not ides:
                session.state = AutomationState.FAILED
                session.error = "No IDEs detected. Please install an IDE (VS Code, Cursor, PyCharm, etc.)"
                return f"❌ {session.error}"
            ide_list = "\n".join(f"  {i+1}. {ide['name']} ({ide['path']})" for i, ide in enumerate(ides))
            return f"Detected IDEs:\n{ide_list}\n\nWhich IDE should I use? Reply with the number (1-{len(ides)}) or name."

        elif session.state == AutomationState.SELECTING_FOLDER:
            return self._scan_folders(session)

        elif session.state == AutomationState.AWAITING_CODE_TASK:
            return "What would you like me to code? Describe the feature, bug fix, or implementation."

        elif session.state == AutomationState.EXECUTING:
            return f"🔧 Executing: {session.current_step}..."

        elif session.state == AutomationState.LEARNING:
            return f"📚 Learning how to: {session.current_step}... This may take a moment."

        elif session.state == AutomationState.AWAITING_RESTART:
            return f"⚠️ I've learned how to handle this task. Please restart JARVIS and ask me to '{session.task_description}' again."

        elif session.state == AutomationState.COMPLETED:
            return f"✅ Task completed! {session.current_step}"

        elif session.state == AutomationState.FAILED:
            return f"❌ Task failed: {session.error}"

        return "Unknown state."

    def _detect_ides(self, session: AutomationSession) -> str:
        """Detect installed IDEs on the system."""
        session.state = AutomationState.DETECTING_IDE
        session.updated_at = datetime.now()

        common_ides = {
            "VS Code": {
                "darwin": [
                    "/Applications/Visual Studio Code.app",
                    "~/Applications/Visual Studio Code.app",
                ],
                "linux": [
                    "/usr/bin/code",
                    "/usr/share/code/code",
                    "~/.local/bin/code",
                ],
                "win32": [
                    "C:\\Program Files\\Microsoft VS Code\\Code.exe",
                    "C:\\Program Files (x86)\\Microsoft VS Code\\Code.exe",
                    os.path.expandvars("%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe"),
                ],
            },
            "Cursor": {
                "darwin": [
                    "/Applications/Cursor.app",
                    "~/Applications/Cursor.app",
                ],
                "linux": [
                    "/usr/bin/cursor",
                    "/opt/cursor/cursor",
                    "~/.local/bin/cursor",
                ],
                "win32": [
                    os.path.expandvars("%LOCALAPPDATA%\\Programs\\cursor\\Cursor.exe"),
                ],
            },
            "PyCharm": {
                "darwin": [
                    "/Applications/PyCharm.app",
                    "~/Applications/PyCharm.app",
                ],
                "linux": [
                    "/usr/bin/pycharm",
                    "/opt/pycharm/bin/pycharm.sh",
                ],
                "win32": [
                    "C:\\Program Files\\JetBrains\\PyCharm\\bin\\pycharm64.exe",
                ],
            },
            "IntelliJ IDEA": {
                "darwin": [
                    "/Applications/IntelliJ IDEA.app",
                ],
                "linux": [
                    "/usr/bin/idea",
                    "/opt/idea/bin/idea.sh",
                ],
                "win32": [
                    "C:\\Program Files\\JetBrains\\IntelliJ IDEA\\bin\\idea64.exe",
                ],
            },
            "Zed": {
                "darwin": [
                    "/Applications/Zed.app",
                ],
                "linux": [
                    "/usr/bin/zed",
                    "~/.local/bin/zed",
                ],
            },
            "Neovim": {
                "darwin": [
                    "/usr/local/bin/nvim",
                    "/opt/homebrew/bin/nvim",
                ],
                "linux": [
                    "/usr/bin/nvim",
                    "/usr/local/bin/nvim",
                ],
            },
        }

        import platform
        system = platform.system().lower()
        detected = []

        for ide_name, paths_by_os in common_ides.items():
            paths = paths_by_os.get(system, [])
            for path_template in paths:
                path = os.path.expanduser(os.path.expandvars(path_template))
                if os.path.exists(path):
                    detected.append({"name": ide_name, "path": path})
                    break

        session.ide_detected = detected
        session.updated_at = datetime.now()

        if detected:
            session.state = AutomationState.SELECTING_IDE
            self._save_sessions()
            return self._prompt_next_step(session)
        else:
            session.state = AutomationState.FAILED
            session.error = "No IDEs detected. Please install an IDE (VS Code, Cursor, PyCharm, etc.)"
            return f"❌ {session.error}"

    def _scan_folders(self, session: AutomationSession) -> str:
        """Scan for potential project folders."""
        session.state = AutomationState.SELECTING_FOLDER
        session.updated_at = datetime.now()

        common_paths = [
            os.path.expanduser("~/Projects"),
            os.path.expanduser("~/projects"),
            os.path.expanduser("~/Code"),
            os.path.expanduser("~/code"),
            os.path.expanduser("~/Developer"),
            os.path.expanduser("~/dev"),
            os.path.expanduser("~/workspace"),
            os.path.expanduser("~/Workspace"),
            os.path.expanduser("~/Documents/Projects"),
        ]

        folders = []
        for path in common_paths:
            if os.path.isdir(path):
                try:
                    for item in os.listdir(path):
                        item_path = os.path.join(path, item)
                        if os.path.isdir(item_path):
                            # Check if it looks like a project (has common project files)
                            has_project_file = any(
                                os.path.exists(os.path.join(item_path, f))
                                for f in [".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml", "requirements.txt", "setup.py"]
                            )
                            folders.append({
                                "name": item,
                                "path": item_path,
                                "is_project": has_project_file,
                            })
                except PermissionError:
                    continue

        # Sort: projects first, then by name
        folders.sort(key=lambda x: (not x["is_project"], x["name"].lower()))
        session.folders_found = folders[:20]  # Limit to 20
        session.updated_at = datetime.now()

        if folders:
            session.state = AutomationState.SELECTING_FOLDER
            self._save_sessions()
            folder_list = "\n".join(
                f"  {i+1}. {f['name']} ({'📦 project' if f['is_project'] else '📁 folder'}) — {f['path']}"
                for i, f in enumerate(folders[:15])
            )
            return f"Found project folders:\n{folder_list}\n\nWhich folder should I work in? Reply with the number (1-{min(len(folders), 15)}) or full path."
        else:
            session.state = AutomationState.FAILED
            session.error = "No project folders found. Please create a project folder first."
            return f"❌ {session.error}"

    def handle_user_response(self, response: str) -> str:
        """Process user's response based on current state."""
        if not self.current_session:
            return "No active automation session. Start with 'start automation'."

        session = self.current_session
        response = response.strip()

        if session.state == AutomationState.SELECTING_IDE:
            return self._handle_ide_selection(session, response)

        elif session.state == AutomationState.SELECTING_FOLDER:
            return self._handle_folder_selection(session, response)

        elif session.state == AutomationState.AWAITING_CODE_TASK:
            session.code_task = response
            session.steps_completed.append(f"Code task specified: {response[:50]}...")
            session.state = AutomationState.EXECUTING
            return self._execute_code_task(session)

        elif session.state == AutomationState.AWAITING_TASK:
            session.task_description = response
            session.task_type = self._classify_task(response)
            session.state = AutomationState.DETECTING_IDE
            return self._prompt_next_step(session)

        elif session.state == AutomationState.AWAITING_RESTART:
            if response.lower() in ("yes", "y", "ok", "restart"):
                session.state = AutomationState.DETECTING_IDE
                return self._prompt_next_step(session)
            return "Waiting for restart confirmation..."

        return "I didn't understand. Please try again."

    def _handle_ide_selection(self, session: AutomationSession, response: str) -> str:
        """Handle IDE selection from user."""
        try:
            # Try parsing as number
            idx = int(response.strip()) - 1
            if 0 <= idx < len(session.ide_detected):
                ide = session.ide_detected[idx]
                session.ide = ide["name"]
                session.ide_path = ide["path"]
                session.steps_completed.append(f"Selected IDE: {ide['name']}")
                session.state = AutomationState.SELECTING_FOLDER
                return self._prompt_next_step(session)
        except ValueError:
            # Try matching by name
            for ide in session.ide_detected:
                if ide["name"].lower() == response.strip().lower():
                    session.ide = ide["name"]
                    session.ide_path = ide["path"]
                    session.steps_completed.append(f"Selected IDE: {ide['name']}")
                    session.state = AutomationState.SELECTING_FOLDER
                    return self._prompt_next_step(session)

        return "Invalid selection. Please reply with the number or name of the IDE."

    def _handle_folder_selection(self, session: AutomationSession, response: str) -> str:
        """Handle folder selection from user."""
        try:
            idx = int(response.strip()) - 1
            if 0 <= idx < len(session.folders_found):
                folder = session.folders_found[idx]
                session.project_folder = folder["path"]
                session.steps_completed.append(f"Selected folder: {folder['name']}")
                session.state = AutomationState.AWAITING_CODE_TASK
                return self._prompt_next_step(session)
        except ValueError:
            # Try matching by path
            for folder in session.folders_found:
                if folder["path"] == response.strip() or folder["name"] == response.strip():
                    session.project_folder = folder["path"]
                    session.steps_completed.append(f"Selected folder: {folder['name']}")
                    session.state = AutomationState.AWAITING_CODE_TASK
                    return self._prompt_next_step(session)

        return "Invalid selection. Please reply with the number or full path."

    def _execute_code_task(self, session: AutomationSession) -> str:
        """Execute the coding task using the selected IDE and folder."""
        session.updated_at = datetime.now()
        session.current_step = f"Opening {session.ide} and navigating to project folder"
        self._save_sessions()

        # Step 1: Open IDE
        self._open_ide(session)

        # Step 2: Navigate to project folder
        session.current_step = "Navigating to project folder in IDE"
        self._navigate_to_folder(session)

        # Step 3: Execute coding task
        session.current_step = f"Coding task: {session.code_task}"
        self._save_sessions()

        # Route to appropriate handler based on task type
        if session.task_type == TaskType.CODING:
            return self._execute_coding_task(session)
        else:
            session.state = AutomationState.COMPLETED
            session.current_step = "Task completed"
            return "Task completed."

    def _open_ide(self, session: AutomationSession):
        """Open the selected IDE."""
        # Use the open_app tool
        open_app = TOOL_REGISTRY.get("open_app")
        if open_app:
            open_app(session.ide)

    def _navigate_to_folder(self, session: AutomationSession):
        """Navigate to project folder in IDE."""
        # Use browser_navigate or terminal command depending on IDE
        # For VS Code/Cursor: use terminal command `code .` or similar
        if session.ide in ("VS Code", "Cursor"):
            import subprocess
            cmd = ["code", session.project_folder] if session.ide == "VS Code" else ["cursor", session.project_folder]
            try:
                subprocess.Popen(cmd, start_new_session=True)
            except Exception as e:
                pass

    def _execute_coding_task(self, session: AutomationSession) -> str:
        """Execute the actual coding task."""
        session.current_step = "Analyzing code task and planning implementation"
        session.steps_completed.append("Started coding task execution")

        # Route to DeepSeek for coding tasks
        # This will be handled by the brain's routing logic
        session.state = AutomationState.COMPLETED
        session.current_step = f"Code task '{session.code_task[:50]}...' routed to DeepSeek for implementation"
        self._save_sessions()
        return f"🔧 Coding task sent to DeepSeek: {session.code_task}\n\nI'll implement this in {session.project_folder} using {session.ide}. Check the IDE for progress."

    def _classify_task(self, description: str) -> TaskType:
        """Classify the task type from description."""
        from agent import score_intent_categories, get_top_intent

        scores = score_intent_categories(description)
        top_intent, score = get_top_intent(description, threshold=2)

        intent_map = {
            "coding": TaskType.CODING,
            "research": TaskType.RESEARCH,
            "file_ops": TaskType.FILE_OPS,
            "automation": TaskType.AUTOMATION,
        }
        return intent_map.get(top_intent, TaskType.UNKNOWN)

    def learn_new_automation(self, task_description: str, error_context: str) -> str:
        """Learn how to automate a new task by analyzing the error and generating code."""
        from learner import learn_capability

        session = self.current_session
        if not session:
            return "No active session to learn from."

        session.state = AutomationState.LEARNING
        session.current_step = f"Learning how to: {task_description}"
        self._save_sessions()

        # Use learner to generate new capability
        try:
            result = learn_capability(task_description)
            session.steps_completed.append(f"Learned new automation: {result}")

            # Save learning to memory
            from memory import save_memory
            save_memory(
                f"Automation learned: {task_description}. Solution: {result}",
                "fact"
            )

            # Ask user to restart
            session.state = AutomationState.AWAITING_RESTART
            session.current_step = f"Learned new automation for: {task_description}. Please restart JARVIS."
            self._save_sessions()

            return f"✅ Learned how to automate: {task_description}\n\n{result}\n\nPlease restart JARVIS and ask me to '{task_description}' again."
        except Exception as e:
            session.state = AutomationState.FAILED
            session.error = f"Learning failed: {e}"
            return f"❌ Learning failed: {e}"

    def resume_session(self, session_id: str) -> str:
        """Resume a previous automation session."""
        # TODO: Load session from disk
        return "Session resume not yet implemented. Starting new session."


# Global automation engine instance
_automation_engine: Optional[AutomationEngine] = None


def get_automation_engine() -> AutomationEngine:
    global _automation_engine
    if _automation_engine is None:
        _automation_engine = AutomationEngine()
    return _automation_engine


# Tool definitions for automation mode
def start_automation(task_description: str) -> str:
    """Start a new automation session with the given task description."""
    engine = get_automation_engine()
    return engine.start_automation(task_description)


def automation_response(response: str) -> str:
    """Handle user response in an active automation session."""
    engine = get_automation_engine()
    return engine.handle_user_response(response)


def resume_automation(session_id: str) -> str:
    """Resume a previous automation session."""
    engine = get_automation_engine()
    return engine.resume_session(session_id)


AUTOMATION_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "start_automation",
            "description": "Start a new automation session. JARVIS will guide you through selecting an IDE, project folder, and task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "What do you want to automate? Describe the task in your own words.",
                    }
                },
                "required": ["task_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "automation_response",
            "description": "Provide your response to an active automation session (e.g., select IDE number, folder number, or describe code task).",
            "parameters": {
                "type": "object",
                "properties": {
                    "response": {
                        "type": "string",
                        "description": "Your response to the current automation prompt.",
                    }
                },
                "required": ["response"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resume_automation",
            "description": "Resume a previous automation session by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "The session ID to resume.",
                    }
                },
                "required": ["session_id"],
            },
        },
    },
]

AUTOMATION_TOOLS = {
    "start_automation": start_automation,
    "automation_response": automation_response,
    "resume_automation": resume_automation,
}