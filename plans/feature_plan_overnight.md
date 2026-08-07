# Overnight Feature Plan: Proactive Context Engine

Based on 2026 research, the most impactful new feature is a **Proactive Context Engine** that shifts Jarvis from reactive to proactive.

## Core Features
1. **Cross-channel memory** — One shared context across CLI, webapp, and future platforms
2. **Proactive morning briefings** — Weather, calendar, top tasks, system health delivered to preferred channel (terminal or webapp)
3. **Energy-aware scheduling** — Suggest tasks based on time of day and user activity patterns
4. **Contextual nudges** — Remind about unfinished tasks or relevant info based on current activity
5. **Tool orchestration** — Chain multiple tools (web search → file write → notification) without user prompting

## Implementation Steps
1. Extend `proactive.py` with context gathering module
2. Add cross-platform memory store (SQLite or JSON)
3. Build briefing generator using existing LLM
4. Add scheduling cron in background thread
5. Test in sandbox
