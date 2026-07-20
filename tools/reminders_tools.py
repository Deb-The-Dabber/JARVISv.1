import subprocess
from functools import lru_cache
from typing import List, Optional


def _applescript(script: str) -> tuple[str, str]:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()


def _parse_reminders_output(output: str) -> List[dict]:
    reminders = []
    if not output:
        return reminders
    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ||| ")
        if len(parts) >= 4:
            reminders.append(
                {
                    "id": parts[0],
                    "name": parts[1],
                    "body": parts[2] if parts[2] != "(no body)" else "",
                    "due_date": parts[3] if parts[3] != "(no due date)" else None,
                    "completed": parts[4] == "true" if len(parts) > 4 else False,
                    "list": parts[5] if len(parts) > 5 else "Reminders",
                }
            )
    return reminders


def reminders_get_lists() -> str:
    script = """
    tell application "Reminders"
        set listNames to name of every list
        return listNames
    end tell
    """
    out, err = _applescript(script)
    if err:
        return f"Error: {err}"
    if not out:
        return "No reminder lists found."
    return "Reminder lists:\n" + "\n".join(f"  - {name.strip()}" for name in out.split(","))


@lru_cache(maxsize=1)
def _get_default_list() -> str:
    return "Reminders"


def reminders_list(list_name: Optional[str] = None, completed: bool = False) -> str:
    target_list = list_name or _get_default_list()
    completed_str = "true" if completed else "false"

    script = f'''
    tell application "Reminders"
        set targetList to list "{target_list}"
        set rems to reminders of targetList whose completed is {completed_str}
        set output to ""
        repeat with r in rems
            set rId to id of r
            set rName to name of r
            set rBody to body of r
            if rBody is missing value then set rBody to "(no body)"
            set rDue to due date of r
            if rDue is missing value then set rDue to "(no due date)"
            set rCompleted to completed of r
            set rList to name of container of r
            set output to output & rId & " ||| " & rName & " ||| " & rBody & " ||| " & rDue & " ||| " & rCompleted & " ||| " & rList & linefeed
        end repeat
        return output
    end tell
    '''
    out, err = _applescript(script)
    if err:
        return f"Error: {err}"

    reminders = _parse_reminders_output(out)
    if not reminders:
        status = "completed" if completed else "active"
        return f"No {status} reminders in '{target_list}'."

    lines = [f"Reminders in '{target_list}' ({'completed' if completed else 'active'}):"]
    for r in reminders:
        due = f" 📅 {r['due_date']}" if r["due_date"] else ""
        body = f"\n    {r['body'][:100]}" if r["body"] else ""
        lines.append(f"  [{r['id']}] {r['name']}{due}{body}")
    return "\n".join(lines)


def reminders_create(title: str, notes: str = "", due_date: Optional[str] = None, list_name: Optional[str] = None) -> str:
    target_list = list_name or _get_default_list()

    safe_title = title.replace('"', '\\"')
    safe_notes = notes.replace('"', '\\"')

    due_script = ""
    if due_date:
        due_script = f'set due date of newReminder to date "{due_date}"'

    script = f'''
    tell application "Reminders"
        set targetList to list "{target_list}"
        set newReminder to make new reminder at targetList with properties {{name:"{safe_title}", body:"{safe_notes}"}}
        {due_script}
        return id of newReminder
    end tell
    '''
    out, err = _applescript(script)
    if err:
        return f"Error creating reminder: {err}"
    return f"Reminder created in '{target_list}' (ID: {out})."


def reminders_complete(reminder_id: str) -> str:
    script = f'''
    tell application "Reminders"
        set targetReminder to first reminder whose id is "{reminder_id}"
        set completed of targetReminder to true
        return "Completed."
    end tell
    '''
    out, err = _applescript(script)
    if err:
        return f"Error: {err}"
    return f"Reminder {reminder_id} marked complete."


def reminders_delete(reminder_id: str) -> str:
    script = f'''
    tell application "Reminders"
        set targetReminder to first reminder whose id is "{reminder_id}"
        delete targetReminder
        return "Deleted."
    end tell
    '''
    out, err = _applescript(script)
    if err:
        return f"Error: {err}"
    return f"Reminder {reminder_id} deleted."


def reminders_search(query: str) -> str:
    script = f'''
    tell application "Reminders"
        set output to ""
        set allLists to every list
        repeat with aList in allLists
            set listName to name of aList
            set listReminders to reminders of aList
            repeat with r in listReminders
                set rName to name of r
                set rBody to body of r
                if rBody is missing value then set rBody to ""
                if rName contains "{query}" or rBody contains "{query}" then
                    set rId to id of r
                    set rDue to due date of r
                    if rDue is missing value then set rDue to "(no due date)"
                    set rCompleted to completed of r
                    set output to output & rId & " ||| " & rName & " ||| " & rBody & " ||| " & rDue & " ||| " & rCompleted & " ||| " & listName & linefeed
                end if
            end repeat
        end repeat
        return output
    end tell
    '''
    out, err = _applescript(script)
    if err:
        return f"Error: {err}"

    reminders = _parse_reminders_output(out)
    if not reminders:
        return f"No reminders matching '{query}'."

    lines = [f"Search results for '{query}':"]
    for r in reminders:
        due = f" 📅 {r['due_date']}" if r["due_date"] else ""
        status = " ✓" if r["completed"] else ""
        body = f"\n    {r['body'][:100]}" if r["body"] else ""
        lines.append(f"  [{r['id']}] {r['name']}{due}{status}{body}  (in {r['list']})")
    return "\n".join(lines)


REMINDERS_TOOLS = {
    "reminders_get_lists": reminders_get_lists,
    "reminders_list": reminders_list,
    "reminders_create": reminders_create,
    "reminders_complete": reminders_complete,
    "reminders_delete": reminders_delete,
    "reminders_search": reminders_search,
}

REMINDERS_DEFINITIONS = [
    {"type": "function", "function": {"name": "reminders_get_lists", "description": "List all reminder lists in macOS Reminders app.", "parameters": {"type": "object", "properties": {}}}},
    {
        "type": "function",
        "function": {
            "name": "reminders_list",
            "description": "List reminders in a list. Defaults to 'Reminders' list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "list_name": {"type": "string", "description": "Name of the reminder list (default: Reminders)"},
                    "completed": {"type": "boolean", "default": False, "description": "Show completed reminders"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_create",
            "description": "Create a new reminder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "notes": {"type": "string", "default": ""},
                    "due_date": {"type": "string", "description": "Due date (e.g., '2024-12-25 10:00' or 'tomorrow 9am')"},
                    "list_name": {"type": "string", "description": "Reminder list name (default: Reminders)"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_complete",
            "description": "Mark a reminder as completed.",
            "parameters": {"type": "object", "properties": {"reminder_id": {"type": "string"}}, "required": ["reminder_id"]},
        },
    },
    {
        "type": "function",
        "function": {"name": "reminders_delete", "description": "Delete a reminder.", "parameters": {"type": "object", "properties": {"reminder_id": {"type": "string"}}, "required": ["reminder_id"]}},
    },
    {
        "type": "function",
        "function": {
            "name": "reminders_search",
            "description": "Search reminders by name or body text.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
]
