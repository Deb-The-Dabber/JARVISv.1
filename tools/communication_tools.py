import subprocess


def _applescript(script):
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()


def list_contacts(query: str = "") -> str:
    """Search macOS Contacts and return matching names."""
    script = '''
    tell application "Contacts"
        set contactNames to name of every person
        set contactEmails to value of every email of every person
        set contactPhones to value of every phone of every person
        return contactNames
    end tell
    '''
    out, _ = _applescript(script)
    if not out:
        return "No contacts found."
    names = [n.strip() for n in out.split(",") if n.strip()]
    if query:
        q = query.lower()
        names = [n for n in names if q in n.lower()]
    if not names:
        return f"No contacts matching '{query}'. Available contacts: {', '.join(names[:20])}" if not query else f"No contacts matching '{query}'."
    return f"Contacts ({len(names)}): " + ", ".join(names[:30])


def send_imessage(contact: str, message: str):
    safe = message.replace('"', '\\"')
    script = f'''tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        set targetBuddy to buddy "{contact}" of targetService
        send "{safe}" to targetBuddy
    end tell'''
    _, err = _applescript(script)
    if err and "execution error" in err.lower():
        # Try to suggest contacts
        try:
            suggestions = list_contacts(contact)
            if suggestions:
                return f"Couldn't send to '{contact}'. {suggestions}"
        except Exception:
            pass
        return f"Couldn't send to '{contact}'. Make sure they're in your contacts and try the exact name."
    return f"Message sent to {contact}."


COMMUNICATION_TOOLS = {
    "send_imessage": send_imessage,
    "list_contacts": list_contacts,
}

COMMUNICATION_DEFINITIONS = [
    {"type":"function","function":{"name":"send_imessage","description":"Send an iMessage to a contact — always confirm before sending","parameters":{"type":"object","properties":{"contact":{"type":"string"},"message":{"type":"string"}},"required":["contact","message"]}}},
    {"type":"function","function":{"name":"list_contacts","description":"Search macOS Contacts by name. Returns matching contact names to help find the right person. Use this before send_imessage if unsure of exact name.","parameters":{"type":"object","properties":{"query":{"type":"string","description":"Optional name to search for (case-insensitive partial match)"}},"required":[]}}},
]
