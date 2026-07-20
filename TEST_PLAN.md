# JARVIS Test Plan (Mac mini M1, 8GB)

Use this as a repeatable regression checklist after code changes.

## 0) Preconditions

- [ ] In project root: `/Users/debasishbeura/Jarvis`
- [ ] Virtualenv active:
  - `source venv/bin/activate`
- [ ] Ollama running with model available:
  - `ollama list`
- [ ] Microphone permission granted (Terminal / Python)
- [ ] Accessibility permissions granted (for pyautogui/browser control)
- [ ] Calendar / Messages / Spotify available (for related tests)

---

## 1) Startup Modes

### 1.1 Terminal Mode

Run:
```bash
cd /Users/debasishbeura/Jarvis
source venv/bin/activate
JARVIS_DEBUG=1 ./run_jarvis.sh
```

Checks:
- [ ] Banner appears: `J.A.R.V.I.S. — Terminal Mode`
- [ ] `Brain initialized.`
- [ ] `Proactive engine started.`
- [ ] `Ollama ready.` (or prewarm fallback noted)
- [ ] Mic selection line prints without crash

### 1.2 API Mode

Run in another terminal:
```bash
cd /Users/debasishbeura/Jarvis
source venv/bin/activate
python server.py
```

Checks:
- [ ] `http://localhost:8000/health` returns online
- [ ] Server boots without import/runtime exceptions

---

## 2) Core Chat + TTS

In terminal mode (`m`):

Prompts:
1. `hello`
2. `what can you do?`
3. `could you tell me the weather today?`

Checks:
- [ ] First reply speaks audibly (no first-response silence)
- [ ] No clipped “last few words only” playback
- [ ] Responses print and speak consistently

---

## 3) Mic / STT Paths

### 3.1 Manual Record Path

In `m` mode, press Enter on empty prompt to record.

Checks:
- [ ] `Listening for ... seconds` appears
- [ ] STT result is processed into a reply
- [ ] No `Error querying device -1`

### 3.2 Wake Word Path

In terminal mode, switch to wake: `wake` or start in `w` mode.

Checks:
- [ ] Wake engine starts
- [ ] Saying `Hey Jarvis` triggers callback
- [ ] Jarvis says `Yes?` and records follow-up command
- [ ] No mic device errors in OWW/fallback loop

---

## 4) Memory Features

Prompts:
1. `remember that I like black coffee`
2. `what do you remember about me`
3. `forget black coffee`
4. `what do you remember about me`
5. `search memory for coffee preferences`

Checks:
- [ ] Memory saves
- [ ] Memory retrieval includes saved item
- [ ] Forget removes relevant item
- [ ] Semantic memory search returns sensible results

API check:
- [ ] `GET /memories` matches expected state

---

## 5) Tool Coverage by Module

## 5.1 System Tools

Prompts:
- `what is my current system usage`
- `get open apps`
- `set a timer called tea for 20 seconds`
- `cancel timer`

Checks:
- [ ] CPU/RAM/disk values returned
- [ ] Open apps returned
- [ ] Timer triggers or cancels properly

## 5.2 Weather + Web

Prompts:
- `what’s the detailed weather`
- `search web for latest python 3.12 features`

Checks:
- [ ] Weather details returned (temp/humidity/wind/rain)
- [ ] Web search result returned (no tool crash)

## 5.3 Spotify

Prompts:
- `what’s playing on spotify`
- `play song bohemian rhapsody on spotify`
- `pause spotify`
- `next track`

Checks:
- [ ] AppleScript commands control Spotify

## 5.4 Calendar

Prompts:
- `what’s on my calendar today`
- `add calendar event test jarvis event`

Checks:
- [ ] Events list returned
- [ ] Event added

## 5.5 File Tools

Prompts:
- `find my latest screenshot`
- `show largest files in downloads`
- `open downloads in finder`
- `organize downloads`

Checks:
- [ ] Finder opens/reveals expected path
- [ ] Largest files list returned
- [ ] Organize runs without crashing

## 5.6 Browser Tools

Prompts:
- `open example.com in browser`
- `open new tab`
- `go back`
- `reload page`
- `what page am i on`

Checks:
- [ ] Browser actions execute as expected

## 5.7 Communication Tool

Prompt:
- `send an imessage to <contact> saying test from jarvis`

Checks:
- [ ] Confirmation requested before sending
- [ ] On confirm, message is sent (or clear contact error)

## 5.8 Vision Tools

Prompts:
- `read my screen`
- `summarize screen`
- `find the search bar on screen`

Checks:
- [ ] Screen description returned
- [ ] No screenshot/moondream crash

## 5.9 Computer Tools

Prompts:
- `take screenshot`
- `move mouse to x 500 y 400 and click`
- `type text hello from jarvis`
- `press key enter`

Checks:
- [ ] Warning confirmation behavior works where expected
- [ ] Actions execute on desktop

## 5.10 Terminal Command Tool

Prompts:
- `run terminal command pwd`
- `run terminal command ls`
- `run terminal command rm -rf /`

Checks:
- [ ] Dangerous command asks confirmation
- [ ] Blocked command is denied

---

## 6) Safety and Audit

Prompts:
- `quit app Safari` (warning)
- `send imessage ...` (dangerous)
- `run terminal command sudo reboot` (dangerous/blocked)

Checks:
- [ ] Warning tools request confirmation (session behavior applies)
- [ ] Dangerous tools always require confirmation
- [ ] Blocked commands are denied
- [ ] `GET /audit` shows expected decisions (`ALLOWED`, `EXECUTED`, `DENIED`, `BLOCKED`)

---

## 7) Priority Engine + Proactive

Let Jarvis run 10-20 minutes idle/normal usage.

Checks:
- [ ] Alerts are serialized (not overlapping spam)
- [ ] Reasonable spacing between proactive alerts
- [ ] Critical alerts still fire
- [ ] `GET /priorities` returns learned stats

Adaptive learning checks:
- [ ] Ignore a repeated alert type (e.g., CPU) and observe lower priority over time
- [ ] Respond after an alert and observe acknowledged count increases

Forced scenario checks:
- [ ] Create calendar event 6 minutes ahead → 5-minute warning fires
- [ ] Briefly disconnect internet → internet_down alert behavior

---

## 8) API Endpoint Smoke Test (copy/paste)

```bash
curl http://localhost:8000/health
curl http://localhost:8000/system
curl http://localhost:8000/weather
curl http://localhost:8000/recap
curl http://localhost:8000/memories
curl http://localhost:8000/priorities
curl http://localhost:8000/audit
```

Checks:
- [ ] All endpoints return valid JSON (except `/` HTML)

---

## 9) Function-Calling Regression Focus

Use prompts that previously failed:
- `could you tell me the weather today?`
- `skibs`
- `its a short form of a word`

Checks:
- [ ] No unexpected kwargs crash on no-arg tools
- [ ] `semantic_search_memory` is not wrongly safety-blocked
- [ ] Tool parsing fallback works when model emits text JSON tool calls

---

## 10) Debug Toggle

Run with debug OFF:
```bash
JARVIS_DEBUG=0 ./run_jarvis.sh
```

Checks:
- [ ] No `[DEBUG]` brain logs
- [ ] Core behavior unchanged

Run with debug ON:
```bash
JARVIS_DEBUG=1 ./run_jarvis.sh
```

Checks:
- [ ] `[DEBUG]` logs appear for tool rounds/calls/results

---

## 11) Pass Criteria

Release-ready for your current setup when:
- [ ] No crashes across startup + core chat + wake path
- [ ] No `device -1` mic errors in normal use
- [ ] Tool calls execute with correct arg sanitization
- [ ] Safety confirmation/blocking behaves as designed
- [ ] Proactive alerts are useful and not noisy
- [ ] API endpoints return valid responses

