# Project Yolo

Project Yolo is an elite, highly autonomous AI system controller and expert software engineer agent. It acts as an orchestrator capable of solving complex software engineering, research, and general desktop tasks end-to-end. Built with a decoupled LLM architecture, it primarily operates via a chat gateway (Telegram/Discord) but also supports CLI and standalone server modes.

<center>
<a href="https://deepwiki.com/dharsahan/ProjectYolo"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
</center>
<br>
## Contributing

Contributions are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) before submitting a PR.

## Table of Contents
- [Core Capabilities](#core-capabilities)
- [System Architecture & Flows](#system-architecture--flows)
- [Desktop Interface](#desktop-interface)
- [Tool System](#tool-system)
- [Architecture & Internals](#architecture--internals)
- [Prerequisites & Dependencies](#prerequisites--dependencies)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Usage & Gateways](#usage--gateways)
- [Safety & Sandboxing](#safety--sandboxing)
- [License](#license)

---

## Core Capabilities

- **Autonomous Execution Engine (`agent.py`)**: A deep-reasoning cognitive loop that can think step-by-step, generate plans, and autonomously use tools. Supported execution modes:
  - **YOLO mode**: Full autonomy, zero human intervention.
  - **Safe mode**: Human-in-the-loop (HITL) confirmation required for destructive or sensitive tool actions.
  - **Think mode**: Dynamic cognitive mode (`auto`, `on`, `off`) that forces Yolo to plan multi-step tasks thoroughly before acting.

- **GUI Perception & Interaction (`gui_ops.py`)**: UI-TARS-inspired perception-first GUI interaction. Utilizing `pytesseract`, `opencv`, and `pyautogui`, Yolo perceives the screen state, draws Set-of-Mark (SoM) overlays, and grounds its actions to actual UI elements rather than blindly clicking coordinates.
  - *Abilities*: Analyze screen, find elements, click elements, read text regions, observe transitions before and after clicks.

- **Advanced Stealth Browsing**: Powered by `cloverlabs-camoufox` for fingerprinting resistance and stealthy web interactions, enabling Yolo to crawl, read, and extract intelligence from modern websites effectively without getting blocked.
  - *Abilities*: Pagination handling, deep link extraction, JavaScript execution, scrolling, and DOM interaction.

- **Multimodal Intelligence (`bot.py`)**: 
  - **Text**: Send commands natively in plain text.
  - **Vision**: Upload photos for visual OCR (via OpenAI Vision).
  - **Audio**: Upload audio/voice notes for instant transcription and analysis.

- **LLM Agnostic (`llm_router.py`)**: Intercepts and routes calls seamlessly across LLM providers:
  - OpenAI (`gpt-5-mini`, `gpt-5.5`)
  - Anthropic (`claude-4-6-sonnet`)
  - Google(OPENAI) (`gemini-3.1-pro` , `gemini-3-flash`)
  - OpenRouter
  - Local / OpenAI-compatible endpoints.

- **Continuous Operation & Evolution**: 
  - **Memories**: Long-term persistent user context.
  - **Experiences**: Records of past bug fixes and technical lessons learned (`experience_ops.py`).
  - **Self Upgrade**: Yolo can optimize its own skills and schedule background/cron tasks (`cron_ops.py`).

---

## System Architecture & Flows

This section provides a technical deep-dive into the inner workings of Project Yolo.

### 1. High-Level Architecture
Project Yolo is built on a "Decoupled Agent Core" pattern. The core cognitive logic is independent of the gateway (Telegram, CLI, Desktop, etc.).

```mermaid
graph TD
    User((User))
    
    subgraph Gateways
        TG[Telegram Bot]
        DS[Discord Bot]
        CLI[CLI Tool]
        TUI[Terminal UI]
        DK[Desktop Electron App]
    end
    
    subgraph CoreEngine[Agent Core]
        Router[LLM Router]
        Session[Session Manager]
        Prompt[Prompt Builder]
        AgentLoop[Cognitive Loop]
    end
    
    subgraph ToolSystem[Tool Execution]
        Dispatcher[Tool Dispatcher]
        OS[OS & File Tools]
        GUI[GUI Perception]
        Web[Stealth Browser]
        Mem[Memory & Experiences]
    end
    
    User <--> Gateways
    Gateways <--> AgentLoop
    AgentLoop <--> Router
    AgentLoop <--> Session
    AgentLoop <--> Dispatcher
    Dispatcher <--> OS
    Dispatcher <--> GUI
    Dispatcher <--> Web
    Dispatcher <--> Mem
```

### 2. Agent Cognitive Loop (The "Think-Act-Observe" Cycle)
The agent doesn't just call tools; it reasons, plans, and validates.

```mermaid
sequenceDiagram
    participant U as User
    participant A as Agent Core
    participant L as LLM (OpenAI/Anthropic)
    participant T as Tool Dispatcher
    participant S as Session Memory

    U->>A: Task (e.g., "Fix the bug in main.js")
    A->>S: Fetch Context & Memories
    A->>A: Build Prompt (System + Context + History)
    
    loop Cognitive Cycle
        A->>L: Think & Plan (with Tools)
        L-->>A: Reason + Tool Calls
        A->>T: Execute Tools (Parallel)
        T-->>A: Tool Results
        A->>S: Update History
        Note over A: Evaluate: Is task complete?
    end
    
    A->>U: Final Answer / Confirmation
```

### 3. GUI Perception Pipeline (UI-TARS Inspired)
How the agent "sees" and interacts with your desktop.

```mermaid
flowchart LR
    Start([Action Needed]) --> Snap[Take Screenshot]
    Snap --> OCR[Run Tesseract OCR]
    OCR --> SoM[Set-of-Mark Overlay]
    SoM --> Ground[Grounding: Match Query to Element]
    Ground --> Coord[Extract Coordinates]
    Coord --> Move[Mouse Move & Click]
    Move --> Trans[Observe Transition]
    Trans --> End([Action Verified])
    
    subgraph Grounding Logic
        Ground -- Fuzzy Match --> Match{Match Found?}
        Match -- No --> HallucinationGuard[Return Element List to LLM]
    end
```

### 4. Self-Evolution & Experience Learning
How Yolo gets smarter over time by fixing its own bugs.

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> TaskExecution: User Request
    TaskExecution --> ErrorDetected: Tool Fails / Bug Found
    ErrorDetected --> SelfUpgradeMode: Start Self-Upgrade Cycle
    
    state SelfUpgradeMode {
        [*] --> AnalyzeError
        AnalyzeError --> GenerateFix: Modify Source Code
        GenerateFix --> Validate: Run Pytest/Lint
        Validate --> CommitFix: Git Commit
    }
    
    SelfUpgradeMode --> LearnExperience: Resolution Successful
    LearnExperience --> Idle: Archive Lesson (Mem0)
    
    note right of LearnExperience: "Experienced" agent avoids the same mistake next time.
```

### 5. Stealth Browsing Architecture (Camoufox)
Bypassing anti-bot measures for deep research.

```mermaid
graph TD
    Agent --> Nav[Navigate to URL]
    Nav --> Camou[Camoufox Browser]
    
    subgraph Fingerprint Resistance
        Camou --> UA[Randomize User Agent]
        Camou --> JS[Humanize JS Runtime]
        Camou --> M[Human Mouse Paths]
    end
    
    Camou --> Scrap[Crawl Steps]
    Scrap --> Scroll[Human-like Scroll Bursts]
    Scrap --> Extract[Link & Text Extraction]
    Scrap --> Next[Auto-Next Pagination]
    
    Extract --> Data[Structured Intelligence]
```

### 6. Multi-Tool Execution & HITL Safety
Handling parallel tool calls and Human-In-The-Loop safety.

```mermaid
flowchart TD
    Calls[LLM Requests 3 Tool Calls] --> Check{YOLO Mode?}
    Check -- Yes --> Parallel[Parallel Execution: asyncio.gather]
    Check -- No --> Sensitive{Destructive / Sensitive?}
    
    Sensitive -- No --> Parallel
    Sensitive -- Yes --> HITL[Pending Confirmation]
    
    HITL --> UserApprove{User Approves?}
    UserApprove -- Yes --> Parallel
    UserApprove -- No --> Deny[Return 'Action Denied']
    
    Parallel --> Results[Merge Results]
    Results --> Feedback[Return to LLM]
```

---

## Desktop Interface

The Yolo Desktop app is a premium Electron-based interface for interacting with the Yolo AI agent. It provides a real-time, fluid chat experience with syntax highlighting and markdown support.

### 🏗️ Desktop Architecture

```mermaid
graph LR
    UI[Electron Renderer] <--> Main[Electron Main Process]
    Main <--> Bridge[Python API Bridge]
    Bridge <--> Agent[Yolo Agent Core]
```

- **Renderer**: Built with vanilla HTML/JS and `motion` for smooth animations.
- **Main**: Handles system-level events and bridge communication.
- **API Bridge**: (`api_bridge.py`) Exposes the agent's cognitive loop via an IPC channel or local socket.

---

## Tool System

Project Yolo is equipped with a vast library of 60+ specialized tools that allow it to interact with the OS, web, and its own codebase.

### 🛠️ Core Tool Categories

- **GUI Perception (`gui_ops.py`)**: UI-TARS Grounding, SoM numbered overlays, and state transition validation.
- **Stealth Browsing (`browser_ops.py`)**: Camoufox engine with humanized mouse paths and automated pagination.
- **File & OS Operations (`file_ops.py`, `system_ops.py`)**: Filesystem mastery and bash execution with parallel background support.
- **Memory & Evolution (`memory_ops.py`, `experience_ops.py`)**: Long-term persistence via vector DB and automated technical lesson learning.

### 🏗️ Tool Dispatcher Flow

```mermaid
graph TD
    LLM[LLM Tool Call] --> Reg[Registry Lookup]
    Reg --> Inject[Context Injection: user_id, session, etc.]
    Inject --> Exec[Execution: Sync/Async]
    Exec --> Parallel[Parallel Gather: if multiple]
    Parallel --> Sanitize[History Sanitization]
    Sanitize --> Feedback[Return to LLM]
```

---

## Architecture & Internals

- `agent.py`: The main cognitive engine. Manages prompt formatting, parses LLM responses, manages tool sequences, and enforces safety boundaries.
- `llm_router.py`: LLM provider abstraction and connection routing.
- `session.py`: Message history and execution state management. Handles history compaction to preserve context windows.
- `tools/`: A powerful suite of system, OS, memory, and application operations.
  - `background_ops.py`: Dispatch parallel background agents.
  - `gui_ops.py`: See, find, analyze, and manipulate screen objects.
  - `experience_ops.py` / `memory_ops.py`: Save and recall long-term knowledge.
  - `artifact_ops.py`: Generate structured, persistent deliverables.
  - `mission_ops.py`: Oversee large, serialized research plans.
- `bot.py` / `discord_gateway.py` / `cli.py` / `server.py`: Front-end adapters for messaging, terminal, and API access.

## Prerequisites & Dependencies

- **Python**: 3.9+ 
- **Tesseract OCR**: Required for GUI interactions.
  - Linux: `sudo apt install tesseract-ocr` or `sudo pacman -S tesseract`
  - macOS: `brew install tesseract`
  - Windows: Download and install from [UB Mannheim's Tesseract page](https://github.com/UB-Mannheim/tesseract/wiki). Ensure `tesseract.exe` is added to your System PATH.
- **System Utils**:
  - Linux: `wmctrl` or `xdotool` to manage and read active window statuses.
  - Windows: `pygetwindow` (installed automatically via `requirements.txt`).
- **Node.js**: Expected if running web applications concurrently.

## Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd project-Yolo
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize configurations (Optional):**
   - **Linux:** Run `./install.sh` to symlink config files.
   - **Windows:** Run `powershell -ExecutionPolicy Bypass -File install.ps1` to symlink config files.

## Configuration

Copy the example config and adjust as necessary:
```bash
cp .env.example .env
```
Key Variables:
- `LLM_PROVIDER`: `auto`, `openai`, `anthropic`, `openrouter`, or `compatible`
- `OPENAI_API_KEY`: API Key for the default intelligence engine.
- `TELEGRAM_BOT_TOKEN`: Token from BotFather for the Telegram gateway.
- `TELEGRAM_ALLOWED_USER_IDS`: Comma-separated list of your Telegram Account IDs for authorization.
- `DISCORD_BOT_TOKEN`: Token for the Discord integration.

## Usage & Gateways

Yolo can be run in multiple ways depending on your workflow:

### Telegram Gateway (Primary)

Start the Telegram bot:
```bash
python bot.py
```
From Telegram, you can:
- Message the bot natural language tasks. Example: `"Set up a new React project in the artifacts directory and deploy a simple hello world app."`
- Toggle modes: `/mode yolo` or `/mode safe`.
- Toggle "Think" logic for complex tasks: `/think auto` or `/think on`.
- View experiences, memories, and active schedules via `/experiences`, `/memories`, `/schedules`.
- Upload Images/Audio directly for the agent to analyze.

### CLI Access

You can directly interact with the agent from the terminal for local testing:
```bash
python cli.py
```

### Discord Gateway

To run the agent on Discord:
```bash
python discord_gateway.py
```

### Server Endpoint (Multi-Gateway)

Start Webhooks, Telegram, and Discord concurrently, along with a health monitor:
```bash
python server.py --mode all
```

## Safety and Sandboxing

> [!WARNING]
> Yolo has the capability to write, delete, and modify system files, as well as interact with your active desktop GUI. 

It is highly recommended to run Yolo within an isolated sandbox, virtual machine, or container when utilizing full YOLO mode, or ensure `/mode safe` is active so you can manually approve tool executions in the chat client.

### Core Safeguards
- **Path Sandboxing (`resolve_and_verify_path`)**: Proactively prevents arbitrary access to sensitive OS files (e.g., `/etc`, `/dev`, `C:/Windows`), fully resolving symlinks to thwart evasion.
- **Strict Output Constraints**: Generation tools like `create_artifact` employ rigorous alphanumeric sanitization on filenames and extensions to prevent directory traversal payloads.
- **Robust Execution**: Tool and agent loops natively handle corrupt data and non-UTF8 payloads without crashing, ensuring the core cognitive cycle (`agent.py`) remains stable.
