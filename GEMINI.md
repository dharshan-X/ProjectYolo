# ProjectYolo: AI Agentic IDE & Desktop Controller

ProjectYolo is a highly autonomous AI system designed for end-to-end desktop control, software engineering, and deep research. It features a decoupled architecture allowing it to operate across various gateways (Telegram, Discord, CLI, TUI, and Electron).

## 🏗️ Architecture Overview

The system is built on a "Decoupled Agent Core" pattern:

- **Agent Core (`agent.py`)**: The main cognitive engine. Manages the "Think-Act-Observe" cycle, prompt construction, and tool execution.
- **LLM Router (`llm_router.py`)**: A provider-agnostic abstraction layer supporting OpenAI, Anthropic, Google (Gemini), and OpenRouter.
- **Tool System (`tools/`)**: A modular library of 60+ tools. Tools are dispatched via `tool_dispatcher.py` which handles both native Python tools and MCP (Model Context Protocol) servers.
- **Session Manager (`session.py`)**: Handles message history, state persistence, and context window optimization (auto-compaction).
- **Gateways**: 
    - `bot.py`: Telegram bot interface.
    - `discord_gateway.py`: Discord bot interface.
    - `cli.py`: Interactive terminal interface.
    - `tui.py`: Full-featured Terminal UI (Textual-based).
    - `desktop/`: Electron-based desktop application.

## 🛠️ Key Technologies

- **Python 3.9+** (Core)
- **Node.js** (Electron Desktop App)
- **Camoufox**: Stealth browsing for research.
- **UI-TARS / PyAutoGUI / Tesseract**: GUI perception and interaction.
- **Mem0**: Long-term persistent memory and experience learning.
- **Textual**: TUI framework.
- **LiteLLM**: Standardized LLM calling.

## 🚀 Development Conventions

### General Standards
- **Surgical Updates**: Prefer targeted edits using `replace` over complete file rewrites.
- **Audit Logging**: Every tool MUST call `audit_log` from `tools.base` on both success and failure.
- **Path Safety**: Use `resolve_and_verify_path` from `tools.base` for ALL file system operations to ensure sandboxing.
- **Return Types**: Tools should return plain strings or JSON-serializable strings.
- **Naming**: Use `snake_case` for functions and variables; `PascalCase` for classes.

### Adding a New Tool
1.  **Define Function**: Create a plain Python function in a module under `tools/`.
2.  **Audit Log**: Include `audit_log("tool_name", args, "success/error", detail)`.
3.  **Register**: Import and add the function to `tools/__init__.py`.
4.  **Schema**: Add the function's JSON schema to `TOOLS_SCHEMAS` in `tools/__init__.py`.
5.  **Dispatch**: The `tool_dispatcher.py` handles most tools automatically via `TOOL_REGISTRY`.

### Testing
- **Framework**: `pytest`
- **Location**: `tests/`
- **Execution**: Run `pytest tests/` to verify core logic.
- **Requirement**: New features or bug fixes must include corresponding tests.

## 📋 Common Commands

- **Run CLI**: `python cli.py`
- **Run TUI**: `python tui.py`
- **Run Telegram Bot**: `python bot.py`
- **Run All Gateways**: `python server.py --mode all`
- **Run Tests**: `pytest`
- **Install Dependencies**: `pip install -r requirements.txt`

## 🛡️ Safety Modes
- **YOLO Mode**: Full autonomy.
- **Safe Mode**: Requires Human-In-The-Loop (HITL) confirmation for destructive or out-of-scope actions.
- **Path Sandbox**: Restricts file operations to the current workspace unless explicitly approved.

## 🧠 Memory & Evolution
- **Experiences**: Records of past bug fixes and lessons learned are stored in `yolo_memory.db` and leveraged in future tasks.
- **Identity**: `configs/identity.md` defines the agent's core personality and engineering style.
