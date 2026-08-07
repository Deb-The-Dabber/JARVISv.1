J.A.R.V.I.S.

A modular, autonomous AI desktop assistant built in Python.
JARVIS combines multiple LLM providers, long-term memory, voice interaction, tool execution, workflow automation, and autonomous agents into a single desktop AI platform.

Features

🧠 Multi-provider AI routing
🎤 Voice recognition + TTS
🔧 Dynamic tool calling
🖥️ Desktop automation
🌐 Browser automation
📁 File creation & editing
📚 Long-term vector memory
⚡ Semantic cache
🔌 Plugin system
🤖 Autonomous coding agent
📊 Workflow engine
📅 Scheduler
🔍 Self-evaluation framework
User │ ▼ Intent Router │ ├── Chat ├── Coding ├── Tool Use └── Reasoning │ ▼ LLM Router │ ├── Nemotron ├── DeepSeek ├── Gemini ├── Groq └── Others │ ▼ Tool Engine │ ├── Weather ├── Browser ├── Files ├── Apps ├── Workflows └── Plugins │ ▼ Memory

Why JARVIS?

Doesn't rely on one LLM.
Automatically chooses the best model.
Supports autonomous workflows.
Modular plugin architecture.
Designed as an operating system for AI, not just a chatbot.
AI Providers Nemotron Ultra --> Main reasoning DeepSeek V4 --> Coding Gemini --> Tool calling fallback Groq --> Fast fallback OpenRouter --> Additional reasoning Pollinations --> Emergency fallback
