import os
import threading
import time
import urllib.request

import uvicorn
import webview

from server import app


PORT = int(os.getenv("JARVIS_PORT", "8002"))


# ─────────────────────────────────────────────
# Start FastAPI in background thread
# ─────────────────────────────────────────────
def start_server():
    # We keep log_level="info" so you can see and COPY incoming requests!
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info", use_colors=True)


print("  Starting backend server thread...")
server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

# Wait for server to be ready before calling webview
print("  Waiting for Jarvis backend to respond...")
for i in range(20):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
        print("  Backend is ONLINE!")
        break
    except Exception:
        if i == 19:
            print("  Backend failed to start. Check your server.py file for errors.")
        time.sleep(0.5)

# ─────────────────────────────────────────────
# Open desktop window (Safe PyWebView setup)
# ─────────────────────────────────────────────
window = webview.create_window(
    title="Jarvis",
    url=f"http://127.0.0.1:{PORT}",
    width=420,
    height=740,
    resizable=True,
    frameless=False,
    on_top=True,
    background_color="#070b0f",
)

# This will launch the GUI window but keep your terminal stream unlocked and readable
print("  Launching GUI shell...")
webview.start()
