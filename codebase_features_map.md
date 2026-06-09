# Project Yolo: Codebase & Feature Map

This document provides a comprehensive mapping of the Project Yolo codebase, detailing all major features and the files where their implementations reside.

## 🧠 1. Autonomous Cognitive Loop (Core Agent)
The "brain" of Yolo, responsible for planning, reasoning, and multi-step execution.

| Feature | Primary File(s) | Description |
| :--- | :--- | :--- |
| **Main Execution Loop** | `agent.py` | Orchestrates the `run_agent_turn` cycle: thinking, tool selection, and execution. |
| **LLM Routing & Config** | `llm_router.py` | Handles LLM provider abstraction (OpenAI, Anthropic, Gemini, etc.) and model selection. |
| **Prompt Engineering** | `prompt_builder.py` | Constructs dynamic system prompts, including identity, tools, and context injection. |
| **Session Management** | `session.py` | Manages conversation history, metadata, and user-specific state persistence. |
| **History Compaction** | `agent.py`, `prompt_builder.py` | Automatically summarizes long conversations to stay within LLM context limits. |

---

## 🛠️ 2. Extensible Tool Engine
The "hands" of Yolo, allowing it to interact with the OS, web, and external services.

| Category | Primary File(s) | Description |
| :--- | :--- | :--- |
| **Tool Dispatcher** | `tool_dispatcher.py` | Dispatches tool calls from the LLM to specific Python functions. |
| **File Operations** | `tools/file_ops.py` | Read, write, move, delete, and search files. |
| **Codebase Analysis** | `tools/codebase_ops.py` | Deep search and structural analysis of local code repositories. |
| **Browser Interaction** | `tools/browser_ops.py` | Stealth browsing using Camoufox (Playwright) for data extraction and automation. |
| **Git Management** | `tools/git_ops.py` | Perform commits, branching, pushing, and history inspection. |
| **System Interaction** | `tools/system_ops.py` | Execute shell commands, manage processes, and monitor system health. |
| **MCP Integration** | `tools/mcp_ops.py` | Support for Model Context Protocol (MCP) servers and tools. |
| **Database Ops** | `tools/database_ops.py` | Direct interaction with SQL databases. |

---

## 🖥️ 3. Cross-Platform Desktop Interface
A premium Electron-based GUI for real-time interaction and status monitoring.

| Feature | Primary File(s) | Description |
| :--- | :--- | :--- |
| **App Entry Point** | `desktop/main.js` | Electron main process: window management, IPC registration, and lifecycle. |
| **Backend Bridge** | `desktop/api_bridge.py` | Aiohttp server bridging the Electron frontend to the Python agent. |
| **Frontend Core** | `desktop/renderer/app.js` | UI logic: SSE message streaming, tool status handling, and worker monitoring. |
| **UI Structure** | `desktop/renderer/index.html` | The main layout, modals, and component containers. |
| **Styling & Theme** | `desktop/renderer/styles.css` | Modern, premium styling (Glassmorphism, dark mode, animations). |
| **Secure Preload** | `desktop/preload.js` | Exposes specific IPC methods to the renderer process. |

---

## 👁️ 4. Multimodal Perception (GUI/Vision)
Enables Yolo to "see" and interact with graphical user interfaces.

| Feature | Primary File(s) | Description |
| :--- | :--- | :--- |
| **GUI Interaction** | `tools/gui_ops.py` | Click, type, and navigate desktop GUIs via coordinate-based control. |
| **OCR & Vision** | `bot.py`, `whisper_local.py` | Extract text from images/screenshots and transcribe audio messages. |
| **Vision Analysis** | `playground/test_vision.py` | Specialized logic for analyzing visual input from screenshots. |

---

## 📡 5. Multi-Gateway Communication
Ways to interact with Yolo outside of the desktop application.

| Gateway | Primary File(s) | Description |
| :--- | :--- | :--- |
| **Telegram Bot** | `bot.py` | Full-featured bot with file upload support, OCR, and rich messaging. |
| **Discord Gateway** | `discord_gateway.py` | Integration for Discord servers with interactive confirmation buttons. |
| **CLI REPL** | `cli.py` | Interactive command-line interface with watchdog support. |
| **TUI (Terminal UI)** | `tui.py`, `tui_widgets.py` | A feature-rich Textual interface for terminal power users. |

---

## 💾 6. Persistent Memory & Context
How Yolo remembers users, facts, and previous technical challenges.

| Feature | Primary File(s) | Description |
| :--- | :--- | :--- |
| **Long-term Memory** | `tools/yolo_memory.py` | RAG-based memory system using SQLite/Qdrant for persistent context. |
| **Experience Ops** | `tools/experience_ops.py` | Records technical "lessons learned" to prevent repeating mistakes. |
| **Identity Management** | `tools/identity_ops.py` | Manages the agent's persona and system-level identity. |
| **Fact Management** | `tools/memory_ops.py` | Specific operations for storing and retrieving facts about the user. |

---

## 🚀 7. Background Mission System
Enables Yolo to work on long-running tasks autonomously in the background.

| Feature | Primary File(s) | Description |
| :--- | :--- | :--- |
| **Mission Control** | `tools/mission_ops.py` | Define, start, and monitor autonomous background "missions". |
| **Background Tasks** | `tools/background_ops.py` | Manage parallel execution of tool tasks without blocking the main chat. |
| **Worker Logic** | `worker.py` | The execution loop for individual background workers. |

---

## 🛠️ 8. Self-Evolution & Health
Monitoring and self-improvement capabilities.

| Feature | Primary File(s) | Description |
| :--- | :--- | :--- |
| **Evolution Engine** | `tools/evolution_ops.py` | Logic for the agent to modify its own code or tools. |
| **Health Monitoring** | `health_server.py` | Provides a health check endpoint for deployment monitoring. |
| **System Monitoring** | `monitoring.py` | Tracks system resource usage and agent performance metrics. |
