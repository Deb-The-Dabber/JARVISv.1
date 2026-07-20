# Jarvis on your phone (Tailscale)

Jarvis does **not** run on the phone. The phone is a remote control: talk/type → your **Mac** runs the brain, tools, Safari, Spotify, and TTS.

You already have everything needed in this repo:

- `server.py` — FastAPI on port **8000**
- `static/index.html` — mobile web UI (text + microphone)

Tailscale connects your phone to your Mac over a private VPN, so you do **not** need to be on the same Wi‑Fi.

---

## 1. Install Tailscale (both devices)

### Mac (Mac mini)

1. Install from [https://tailscale.com/download](https://tailscale.com/download) or `brew install --cask tailscale`
2. Open **Tailscale** from the menu bar → **Log in** (Google/GitHub/Microsoft)
3. Leave Tailscale **connected** (green icon)

### iPhone / Android

1. Install **Tailscale** from the App Store / Play Store
2. Log in with the **same account** as the Mac
3. Turn Tailscale **on**

You should see both devices in the [Tailscale admin console](https://login.tailscale.com/admin/machines).

---

## 2. Get your Mac’s Tailscale IP

On the Mac, in Terminal:

```bash
tailscale ip -4
```

Example output: `100.64.12.34` — that is the address your phone will use.

(If `tailscale: command not found`, open the Tailscale app once or install the CLI via the Mac app.)

---

## 3. Start Jarvis server on the Mac

```bash
cd ~/Jarvis
source venv/bin/activate
python server.py
```

You should see:

- `http://localhost:8000` — on the Mac only  
- `http://100.x.x.x:8000` — **use this on your phone** (Tailscale IP)

Keep this terminal open. Jarvis only works while the server is running.

**Optional — prevent Mac sleep while using Jarvis:**

```bash
caffeinate -dims python server.py
```

---

## 4. Open Jarvis on your phone

1. Tailscale **on** on the phone  
2. Safari (or Chrome) → `http://100.x.x.x:8000` (your Mac’s Tailscale IP)  
3. **Add to Home Screen** (Share → Add to Home Screen) for an app-like icon  

Use the mic button for voice (`/ask-voice`) or type in the chat box (`/ask`).

---

## 5. What works from the phone

| Works | Notes |
|--------|--------|
| Chat, voice → STT | Audio is transcribed **on the Mac** |
| Discord, Safari, Spotify tools | Automation runs **on the Mac** |
| “Yes” for permissions | Same as terminal — reply **yes** when asked |
| Groq/Gemini fallbacks | Same as `terminal.py` |

| Limitation | Why |
|------------|-----|
| TTS plays on **Mac speakers**, not the phone | `speak()` uses Mac audio |
| Mac must be **awake** and server **running** | Brain lives on the Mac |
| Accessibility | Still required for Terminal/Python on the Mac |

---

## Troubleshooting

### Phone can’t open the page

- Tailscale on **both** devices?  
- Same Tailscale account?  
- Mac server running? (`python server.py`)  
- Try `http://100.x.x.x:8000/health` — should show JSON `{"status":"online",...}`  

### Works on Wi‑Fi but not on cellular

You need Tailscale (or another VPN). Plain `192.168.x.x` only works on local Wi‑Fi.

### Voice fails on phone

- Allow microphone for Safari in iOS Settings  
- Install **ffmpeg** on the Mac: `brew install ffmpeg` (converts phone audio to WAV)  

### Permission / osascript errors

On the Mac: **System Settings → Privacy & Security → Accessibility** → enable **Terminal** (or whatever runs `python server.py`).

---

## Security

- Tailscale is a **private** network; only your devices see the Mac IP.  
- Do **not** port-forward 8000 to the public internet without adding auth.  
- Optional later: set `JARVIS_API_TOKEN` in `.env` (if you add token checks to `server.py`).

---

## Quick reference

```bash
# Mac — one-time check
tailscale ip -4

# Mac — every session
cd ~/Jarvis && source venv/bin/activate && python server.py

# Phone browser
http://<tailscale-ip>:8000
```
