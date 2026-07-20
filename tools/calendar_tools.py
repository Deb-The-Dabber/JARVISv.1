import datetime
import subprocess


def _applescript(script):
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    return result.stdout.strip(), result.stderr.strip()


def get_calendar_events(day: str = "today"):
    offset = 0 if day == "today" else 86400
    script = f"""
    set output to ""
    set theDate to (current date) + {offset}
    set startDate to theDate - (time of theDate)
    set endDate to startDate + 86400
    tell application "Calendar"
        set allCals to every calendar
        repeat with aCal in allCals
            set theEvents to every event of aCal whose start date >= startDate and start date < endDate
            repeat with e in theEvents
                set output to output & summary of e & " at " & (start date of e as string) & ", "
            end repeat
        end repeat
    end tell
    return output
    """
    out, _ = _applescript(script)
    out = out.strip().rstrip(",")
    return f"Events for {day}: {out}" if out else f"No events for {day}."


def add_calendar_event(title: str, date: str, time: str = "12:00"):
    try:
        start_dt = datetime.datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            start_dt = datetime.datetime.strptime(f"{date} {time}", "%B %d %Y %H:%M")
        except ValueError:
            return "Could not parse date/time. Use date like 2026-06-01 and time like 14:30."

    apple_date = start_dt.strftime("%B %d, %Y %I:%M:%S %p")
    safe_title = title.replace('"', '\\"')
    script = f'''tell application "Calendar"
        set theCalendar to first calendar
        set theDate to date "{apple_date}"
        make new event at end of events of theCalendar with properties {{summary:"{safe_title}", start date:theDate, end date:theDate + 3600}}
    end tell'''
    _, err = _applescript(script)
    if err:
        return f"Calendar event failed: {err}"
    return f"Added '{title}' to your calendar on {date} at {time}."


CALENDAR_TOOLS = {
    "get_calendar_events": get_calendar_events,
    "add_calendar_event": add_calendar_event,
}

CALENDAR_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Get calendar events for today or tomorrow",
            "parameters": {"type": "object", "properties": {"day": {"type": "string", "description": "'today' or 'tomorrow'"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_event",
            "description": "Add an event to Apple Calendar on a specific date and time",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string", "description": "Event date, preferably YYYY-MM-DD"},
                    "time": {"type": "string", "description": "Event time in 24-hour HH:MM format, defaults to 12:00"},
                },
                "required": ["title", "date"],
            },
        },
    },
]
