import datetime
import glob
import os
import platform
import queue
import shutil
import subprocess
import tempfile
import threading

import requests
import scipy.io.wavfile as wav
import sounddevice as sd
import whisper

from config import (
    DEFAULT_BROWSER,
    HOME,
    RECORD_SECONDS,
    SAMPLE_RATE,
    USER_CITY,
    USER_NAME,
    WAKE_WORD,
    WHISPER_MODEL,
)
from tools.browser_tools import (
    browser_back,
    browser_close_tab,
    browser_current_url,
    browser_forward,
    browser_navigate,
    browser_new_tab,
    browser_reload,
    browser_scroll,
)
from tools.system_tools import APP_ALIASES, get_weather_detailed, open_app, web_search
from tts import speak, stop_speaking, wait_for_speech

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1"


# ─────────────────────────────────────────────
# AUTO-FETCH SYSTEM INFO
# ─────────────────────────────────────────────
def fetch_system_info():
    info = {}
    try:
        result = subprocess.run(["system_profiler", "SPHardwareDataType"],
                                capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            if "Model Name" in line:
                info["model"] = line.split(":")[-1].strip()
            if "Chip" in line or "Processor Name" in line:
                info["chip"] = line.split(":")[-1].strip()
            if "Memory:" in line:
                info["ram"] = line.split(":")[-1].strip()
    except Exception:
        info["model"] = platform.machine()
    try:
        result = subprocess.run(["sw_vers"], capture_output=True, text=True, timeout=5)
        v = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                k, val = line.split(":", 1)
                v[k.strip()] = val.strip()
        info["os"] = f"macOS {v.get('ProductVersion','?')} ({v.get('ProductName','')})"
    except Exception:
        info["os"] = platform.platform()
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        parts = result.stdout.strip().splitlines()[1].split()
        info["disk_total"] = parts[1]
        info["disk_free"] = parts[3]
    except Exception:
        pass
    info["username"] = os.environ.get("USER", "unknown")
    return info

print("Fetching system info...")
SYSTEM_INFO = fetch_system_info()
print(f"  Device : {SYSTEM_INFO.get('model','?')}")
print(f"  Chip   : {SYSTEM_INFO.get('chip','?')}")
print(f"  RAM    : {SYSTEM_INFO.get('ram','?')}")
print(f"  OS     : {SYSTEM_INFO.get('os','?')}")
if "disk_free" in SYSTEM_INFO:
    print(f"  Disk   : {SYSTEM_INFO['disk_free']} free of {SYSTEM_INFO['disk_total']}")
print()


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────
def build_system_prompt():
    now = datetime.datetime.now().strftime("%A, %B %d %Y, %I:%M %p")
    device_block = f"""
- Model: {SYSTEM_INFO.get('model','Unknown Mac')}
- Chip: {SYSTEM_INFO.get('chip','Unknown')}
- RAM: {SYSTEM_INFO.get('ram','Unknown')}
- OS: {SYSTEM_INFO.get('os','Unknown')}"""
    if "disk_free" in SYSTEM_INFO:
        device_block += f"\n- Disk: {SYSTEM_INFO['disk_free']} free of {SYSTEM_INFO['disk_total']}"
    return f"""You are Jarvis, a smart, concise voice assistant running locally on {USER_NAME}'s Mac.
Keep responses short and conversational — spoken aloud via TTS. 1-3 sentences max.
No markdown, bullet points, or lists. Talk naturally.

Facts:
- User: {USER_NAME}, Location: {USER_CITY} Illinois
- Date/Time: {now}
- System:{device_block}
- Default browser: {DEFAULT_BROWSER}

Rules:
- NEVER guess or make up info you don't have
- Tools handle weather, search, browser, files — respond naturally to results given
- Don't say "As an AI..." — just be helpful and direct
- For destructive actions (delete, move, organize) always confirm with the user first"""


# ─────────────────────────────────────────────
# WHISPER
# ─────────────────────────────────────────────
print("Loading Whisper model...")
stt_model = whisper.load_model(WHISPER_MODEL)
print("Whisper ready.\n")
conversation = []


# (TTS, weather, open_app, web_search imported from shared modules above)


def handle_browser(text, text_lower):
    browser = "Safari" if "safari" in text_lower else DEFAULT_BROWSER
    nav_triggers = ["go to", "navigate to", "open", "visit", "take me to", "search for"]
    for trigger in nav_triggers:
        if trigger in text_lower:
            after = text_lower.split(trigger, 1)[-1].strip()
            if after and ("." in after or any(s in after for s in ["youtube", "google"])):
                if " " in after and "." not in after.split()[0]:
                    url = f"https://www.google.com/search?q={requests.utils.quote(after)}"
                else:
                    url = after.strip()
                return browser_navigate(url, browser)
    if "new tab" in text_lower:
        return browser_new_tab(browser)
    if "close tab" in text_lower or "close this tab" in text_lower:
        return browser_close_tab(browser)
    if "go back" in text_lower or "back" in text_lower:
        return browser_back(browser)
    if "go forward" in text_lower or "forward" in text_lower:
        return browser_forward(browser)
    if "scroll down" in text_lower:
        return browser_scroll("down", browser)
    if "scroll up" in text_lower:
        return browser_scroll("up", browser)
    if "reload" in text_lower or "refresh" in text_lower:
        return browser_reload(browser)
    if "what page" in text_lower or "current url" in text_lower or "what site" in text_lower:
        return browser_current_url(browser)
    return "I'm not sure what browser action you want."


# ─────────────────────────────────────────────
# TOOL: FILE & SYSTEM TASKS
# ─────────────────────────────────────────────
SCREENSHOT_DIRS = [
    os.path.join(HOME, "Desktop"),
    os.path.join(HOME, "Pictures", "Screenshots"),
]

FILE_TYPE_FOLDERS = {
    "Images":     [".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg", ".tiff"],
    "Videos":     [".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv"],
    "Documents":  [".pdf", ".doc", ".docx", ".txt", ".md", ".pages", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"],
    "Archives":   [".zip", ".tar", ".gz", ".rar", ".7z", ".dmg", ".pkg"],
    "Audio":      [".mp3", ".wav", ".aac", ".flac", ".m4a"],
    "Code":       [".py", ".js", ".ts", ".html", ".css", ".json", ".sh", ".rb", ".java", ".c", ".cpp"],
}

def find_recent_screenshot():
    files = []
    for d in SCREENSHOT_DIRS:
        if os.path.exists(d):
            for ext in ["*.png", "*.jpg", "*.jpeg"]:
                files.extend(glob.glob(os.path.join(d, ext)))
    if not files:
        return "I couldn't find any screenshots on your Desktop or Screenshots folder."
    latest = max(files, key=os.path.getmtime)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(latest))
    name = os.path.basename(latest)
    # Reveal in Finder
    subprocess.run(["open", "-R", latest])
    return f"Your most recent screenshot is '{name}', taken {mtime.strftime('%B %d at %I:%M %p')}. I've revealed it in Finder."

def find_files_by_type(folder, extension):
    folder = os.path.expanduser(folder)
    matches = glob.glob(os.path.join(folder, f"**/*{extension}"), recursive=True)
    if not matches:
        return f"No {extension} files found in {folder}."
    names = [os.path.basename(f) for f in matches[:5]]
    more = len(matches) - 5
    result = f"Found {len(matches)} {extension} files. First few: {', '.join(names)}"
    if more > 0:
        result += f", and {more} more."
    return result

def get_largest_files(folder="~/Downloads", count=5):
    folder = os.path.expanduser(folder)
    if not os.path.exists(folder):
        return f"Folder {folder} doesn't exist."
    files = []
    for f in os.listdir(folder):
        path = os.path.join(folder, f)
        if os.path.isfile(path):
            files.append((path, os.path.getsize(path)))
    if not files:
        return f"No files found in {folder}."
    files.sort(key=lambda x: x[1], reverse=True)
    top = files[:count]
    result = f"Largest files in {os.path.basename(folder)}: "
    parts = []
    for path, size in top:
        mb = size / (1024 * 1024)
        parts.append(f"{os.path.basename(path)} ({mb:.1f} MB)")
    return result + ", ".join(parts) + "."

def move_to_trash(path):
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return f"Couldn't find '{path}'."
    script = f'tell application "Finder" to delete POSIX file "{path}"'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.stderr.strip():
        return f"Couldn't move to trash: {result.stderr.strip()}"
    return f"Moved '{os.path.basename(path)}' to trash."

def organize_downloads():
    folder = os.path.join(HOME, "Downloads")
    if not os.path.exists(folder):
        return "Downloads folder not found."

    moved = 0
    for filename in os.listdir(folder):
        src = os.path.join(folder, filename)
        if not os.path.isfile(src):
            continue
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        target_folder = "Others"
        for folder_name, extensions in FILE_TYPE_FOLDERS.items():
            if ext in extensions:
                target_folder = folder_name
                break
        dest_dir = os.path.join(folder, target_folder)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        if not os.path.exists(dest):
            shutil.move(src, dest)
            moved += 1

    subprocess.run(["open", folder])
    return f"Done! Organized {moved} files in your Downloads into folders by type. Opening Downloads in Finder."

def open_in_finder(folder):
    folder = os.path.expanduser(folder)
    subprocess.run(["open", folder])
    return f"Opened {folder} in Finder."

def disk_usage_summary():
    total, used, free = shutil.disk_usage(HOME)
    gb = lambda b: b / (1024**3)
    return (f"Your disk has {gb(total):.0f} GB total, "
            f"{gb(used):.0f} GB used, and {gb(free):.0f} GB free.")


# ─────────────────────────────────────────────
# PENDING CONFIRMATION (for destructive actions)
# ─────────────────────────────────────────────
pending_action = {"fn": None, "description": None}

def set_pending(fn, description):
    pending_action["fn"] = fn
    pending_action["description"] = description

def clear_pending():
    pending_action["fn"] = None
    pending_action["description"] = None

def check_confirmation(text_lower):
    """If there's a pending action and user says yes, execute it."""
    if pending_action["fn"] is None:
        return None
    yes_words = ["yes", "yeah", "yep", "do it", "go ahead", "confirm", "sure", "ok", "okay"]
    no_words = ["no", "nope", "cancel", "stop", "don't", "nevermind"]
    if any(w in text_lower for w in yes_words):
        fn = pending_action["fn"]
        clear_pending()
        return fn()
    if any(w in text_lower for w in no_words):
        clear_pending()
        return "Okay, cancelled."
    return None


# ─────────────────────────────────────────────
# INTENT DETECTION
# ─────────────────────────────────────────────
def detect_intent(text):
    t = text.lower()

    # Check pending confirmation first
    if pending_action["fn"]:
        return "confirm", None

    # Weather
    if any(w in t for w in ["weather", "temperature", "forecast", "raining", "sunny", "humid", "wind"]):
        return "weather", None

    # Browser — detect browser-related commands
    browser_triggers = [
        "scroll down", "scroll up", "new tab", "close tab", "go back", "go forward",
        "reload", "refresh", "what page", "current url", "what site",
    ]
    # Navigate triggers that imply browser
    nav_with_site = any(
        trigger in t and any(site in t for site in ["youtube", "google", "twitter", "reddit",
        "github", ".com", ".org", ".net", ".io", "instagram", "netflix", "spotify"])
        for trigger in ["go to", "open", "navigate", "visit", "take me to"]
    )
    if any(bt in t for bt in browser_triggers) or nav_with_site:
        return "browser", None

    # File/system tasks
    if "screenshot" in t:
        return "file_screenshot", None
    if ("organize" in t and "download" in t) or ("sort" in t and "download" in t):
        return "file_organize", None
    if "largest" in t or ("big" in t and "file" in t):
        folder = "Downloads" if "download" in t else "Desktop" if "desktop" in t else "Downloads"
        return "file_largest", folder
    if "disk" in t and ("space" in t or "usage" in t or "storage" in t):
        return "file_disk", None
    if "trash" in t or "delete" in t:
        return "file_trash", t
    if ("open" in t or "show" in t) and ("finder" in t or "folder" in t or "download" in t or "desktop" in t or "documents" in t):
        if "download" in t:
            return "file_open_finder", "~/Downloads"
        if "desktop" in t:
            return "file_open_finder", "~/Desktop"
        if "document" in t:
            return "file_open_finder", "~/Documents"
        return "file_open_finder", "~/Downloads"
    if "pdf" in t:
        folder = "~/Desktop" if "desktop" in t else "~/Downloads"
        return "file_find_type", (folder, ".pdf")

    # App open (non-browser)
    open_words = ["open", "launch", "start"]
    if any(w in t for w in open_words):
        for alias in APP_ALIASES:
            if alias in t and alias not in ["safari", "chrome", "firefox", "dia"]:
                return "open_app", alias
        for word in open_words:
            if word in t:
                parts = t.split(word, 1)
                if len(parts) > 1:
                    app_guess = parts[1].strip().split()[0] if parts[1].strip() else None
                    if app_guess:
                        return "open_app", app_guess

    # Web search
    search_words = ["search", "look up", "google", "find", "what is", "who is", "who are", "tell me about"]
    if any(w in t for w in search_words):
        for word in search_words:
            if word in t:
                query = t.split(word, 1)[-1].strip()
                return "search", query if query else text

    return "chat", None


# ─────────────────────────────────────────────
# OLLAMA
# ─────────────────────────────────────────────
def ask_ollama(user_message, tool_context=None):
    full_message = f"[Tool result: {tool_context}]\nUser said: {user_message}" if tool_context else user_message
    conversation.append({"role": "user", "content": full_message})
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": build_system_prompt()}] + conversation,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        reply = response.json()["message"]["content"].strip()
        conversation.append({"role": "assistant", "content": reply})
        return reply
    except requests.exceptions.ConnectionError:
        return "I can't reach Ollama. Make sure it's running."
    except Exception as e:
        return f"Something went wrong: {e}"


# ─────────────────────────────────────────────
# PROCESS
# ─────────────────────────────────────────────
def process(text):
    t = text.lower()
    intent, param = detect_intent(text)

    # Confirmation check
    if intent == "confirm":
        result = check_confirmation(t)
        if result:
            return result
        return ask_ollama(text)

    if intent == "weather":
        print("🌤  Fetching weather...")
        return ask_ollama(text, tool_context=get_weather_detailed())

    elif intent == "browser":
        print("🌐  Browser action...")
        result = handle_browser(text, t)
        return ask_ollama(text, tool_context=result)

    elif intent == "file_screenshot":
        print("📸  Finding screenshot...")
        result = find_recent_screenshot()
        return ask_ollama(text, tool_context=result)

    elif intent == "file_organize":
        # Confirm before doing it
        set_pending(organize_downloads, "organize Downloads folder")
        return ask_ollama(text, tool_context=(
            "I found files in the Downloads folder. "
            "Ask the user: shall I go ahead and organize them into subfolders by type? Say yes to confirm."
        ))

    elif intent == "file_largest":
        folder = f"~/{param}"
        print(f"📁  Finding largest files in {param}...")
        result = get_largest_files(folder)
        return ask_ollama(text, tool_context=result)

    elif intent == "file_disk":
        result = disk_usage_summary()
        return ask_ollama(text, tool_context=result)

    elif intent == "file_trash":
        # Try to extract a filename — for now ask user to be more specific
        return ask_ollama(text, tool_context=(
            "The user wants to delete something but didn't specify a file path. "
            "Ask them to say the exact file name or location."
        ))

    elif intent == "file_open_finder":
        result = open_in_finder(param)
        speak(result)
        return result

    elif intent == "file_find_type":
        folder, ext = param
        result = find_files_by_type(folder, ext)
        return ask_ollama(text, tool_context=result)

    elif intent == "open_app":
        print(f"📂  Opening: {param}")
        result = open_app(param)
        speak(result)
        return result

    elif intent == "search":
        print(f"🔍  Searching: {param}")
        return ask_ollama(text, tool_context=web_search(param))

    else:
        return ask_ollama(text)


# ─────────────────────────────────────────────
# RECORD + TRANSCRIBE
# ─────────────────────────────────────────────
def record_audio(seconds=RECORD_SECONDS):
    print(f"🎙  Listening for {seconds}s...")
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return audio

def transcribe(audio):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav.write(f.name, SAMPLE_RATE, audio)
        tmp = f.name
    result = stt_model.transcribe(tmp)
    os.remove(tmp)
    return result["text"].strip()


# ─────────────────────────────────────────────
# WAKE WORD
# ─────────────────────────────────────────────
wake_detected = threading.Event()
import wakeword


def listen_for_wake_word():
    def _on_wake():
        wake_detected.set()
    wakeword.start(_on_wake)
    print(f"👂  Say '{WAKE_WORD}' to activate.\n")
    while True:
        wake_detected.wait()
        wake_detected.clear()
        stop_speaking()
        speak("Yes?")
        print("\n✨ Activated!")
        audio = record_audio(seconds=6)
        text = transcribe(audio)
        if not text:
            continue
        print(f"\n🗣  You: {text}")
        _dispatch_request(text)


def _dispatch_request(text: str):
    """Dispatch a user request to a background thread to keep the UI responsive."""
    def _worker(t: str):
        try:
            print(f"\n🗣  You: {t}")
            print("Thinking...")
            reply = process(t)
            print(f"🤖 Jarvis: {reply}\n")
            speak(reply, interrupt=True)
        except Exception as e:
            print(f"Error in dispatched request: {e}")

    threading.Thread(target=_worker, args=(text,), daemon=True).start()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("=" * 50)
    print("  J.A.R.V.I.S. — Local AI Assistant")
    print(f"  Browser: {DEFAULT_BROWSER} | Brain: Ollama | STT: Whisper")
    print("=" * 50)
    print("\nModes:")
    print("  [w] Wake word — say 'Hey Jarvis'")
    print("  [m] Manual    — press Enter to speak")
    print("  [q] Quit\n")

    mode = input("Choose mode (w/m): ").strip().lower()

    if mode == "w":
        listen_for_wake_word()
        return

    else:
        print("\nPress Enter to speak, type a message, or 'quit' to exit.")
        print("Type anything while Jarvis speaks to interrupt.\n")

        q = queue.Queue()

        def listener():
            while True:
                val = input()
                stop_speaking()
                q.put(val)

        threading.Thread(target=listener, daemon=True).start()
        print("[ Press Enter to speak / or type ] → ", end="", flush=True)

        while True:
            user_input = q.get().strip()
            if user_input.lower() in ("quit", "exit", "q"):
                speak("Goodbye.")
                wait_for_speech()
                break

            text = user_input if user_input else None
            if not text:
                audio = record_audio()
                text = transcribe(audio)
                if not text:
                    print("Didn't catch that.")
                    print("[ Press Enter to speak / or type ] → ", end="", flush=True)
                    continue

            # Dispatch the processing to a background thread.
            _dispatch_request(text)
            print("[ Press Enter to speak / or type ] → ", end="", flush=True)

if __name__ == "__main__":
    main()
