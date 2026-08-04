# IDE Core Engine

<p align="center">
  <a href="https://github.com/your-org/ide-core/actions/workflows/ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/your-org/ide-core/ci.yml?branch=main&label=tests" alt="CI">
  </a>
  <img src="https://img.shields.io/badge/python-3.10%20|%203.11-blue" alt="Python">
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/your-org/ide-core" alt="License">
  </a>
  <a href="https://github.com/your-org/ide-core/releases">
    <img src="https://img.shields.io/github/v/release/your-org/ide-core" alt="Release">
  </a>
</p>

The **IDE Core Engine v2.0.0** is a modular, open-source AI IDE backend written in Python. It now unifies a piece-table text buffer, LSP client, multi-tenant middleware, multimodal input processing, creative media generation, smart decision ranking, a friend personality layer, and an autonomous ReAct agent into a single WebSocket gateway that powers a Monaco + xterm.js frontend with a built-in chat interface.

## Features

- **Piece Table Text Buffer** — immutable `original` and append-only `add` buffers make edits non-destructive and support undo/snapshot workflows.
- **LSP Client** — async JSON-RPC client for language servers (Python, TypeScript, etc.) with `textDocument/didOpen`, `didChange`, `completion`, and diagnostic publishing.
- **Autonomous ReAct Agent** — `AgentOrchestrator` drives an iterative tool loop with file, search, command, and diagnostic tools.
- **Multi-Tenant Middleware** — `TenantManager` isolates workspaces, auth, and chat data per tenant.
- **Multimodal Input Engine** — voice, image OCR, PDF, and document text extraction.
- **Creative Agent** — generates images, logos, sound, music, voiceovers, and video previews.
- **Smart Decision System** — `SmartAssistant` scores and ranks creative or code candidates with explanations.
- **Friend Personality** — `FriendPersonality` provides greetings, celebrations, encouragement, and memory.
- **Unified Chat Gateway** — `ChatWebSocketServer` routes text, voice, image, PDF, and creative requests through all subsystems.
- **Monaco Editor UI + Chat** — `frontend/index.html` loads Monaco Editor and the new chat panel over WebSocket.
- **xterm.js PTY** — `TerminalManager` spawns a persistent shell and streams output to the UI.
- **Git Diffing** — `GitManager` provides status, staging, commit, and per-file diff support.
- **Pydantic Settings** — configuration loaded from `.env` or environment variables.
- **181 passing pytest suite** covering buffer, document, LSP, agent, server, tenant, multimodal, creative, smart decision, personality, and chat tests.

## Architecture

```mermaid
graph TB
  A[Monaco + xterm.js Frontend] -->|WebSocket /ws/editor| B[ide_core.server.EditorServer]
  A -->|WebSocket /ws/chat| C[ide_core.chat.ChatWebSocketServer]
  B --> D[DocumentManager]
  D --> E[TextBuffer Piece Table]
  B --> F[LSPClient JSON-RPC]
  B --> G[TerminalManager PTY]
  B --> H[ProjectManager]
  B --> I[GitManager]
  C --> J[MessageHandler]
  J --> K[UnifiedChatIntegration]
  K --> L[MultimodalInputEngine]
  K --> M[CreativeAgent]
  K --> N[SmartAssistant]
  K --> O[FriendPersonality]
  K --> P[AgentOrchestrator]
  C --> Q[RoomManager]
  C --> R[PresenceManager]
  Q --> S[TenantManager + Auth]
  P --> T[ToolRegistry]
  T --> D
  T --> G
  T --> H
  T --> I

  subgraph Core Engine
    D
    E
    F
  end

  subgraph Multi-Tenant Middleware
    S
  end

  subgraph Multimodal Processing
    L --> L1[Voice]
    L --> L2[Image OCR]
    L --> L3[PDF]
    L --> L4[Document]
  end

  subgraph Creative Agent
    M --> M1[Image / Logo / UI Mockup]
    M --> M2[Sound / Music / Voiceover]
    M --> M3[Video / Tutorial]
    M --> M4[ToolInstaller]
  end

  subgraph Smart Decision
    N --> N1[Scorer]
    N --> N2[Chooser]
    N --> N3[Learner]
  end

  subgraph Friend Personality
    O --> O1[Greeter]
    O --> O2[Celebrator]
    O --> O3[ProactiveHelper]
    O --> O4[FriendMemory]
  end

  subgraph Unified Chat
    C
    J
    K
    Q
    R
  end
```

## Quickstart

1. Clone the repository and create a virtual environment:

```bash
git clone https://github.com/your-org/ide-core.git
cd ide-core
python -m venv .venv
.venv\Scripts\activate  # Windows
# or: source .venv/bin/activate  # Linux/macOS
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. (Optional) Install a Python language server:

```bash
pip install python-lsp-server
```

4. Create a `.env` file with at least a JWT secret:

```bash
JWT_SECRET=change-me-in-production
```

5. Start the WebSocket server:

```bash
python -m ide_core.server
```

6. Open `frontend/index.html` in a browser (or serve it with any static file server).

## Configuration

`ide_core.config.settings.IDESettings` loads values from a `.env` file or environment variables. Common settings:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | `""` | OpenAI API key for the agent. |
| `ANTHROPIC_API_KEY` | `""` | Anthropic API key for the agent. |
| `DEFAULT_MODEL` | `gpt-4o` | Default LLM model. |
| `DEFAULT_TEMPERATURE` | `0.2` | Sampling temperature. |
| `EDITOR_THEME` | `vs-dark` | Monaco editor theme. |
| `LSP_PYTHON_COMMAND` | `pylsp` | Command to start the Python language server. |
| `LSP_TYPESCRIPT_COMMAND` | `typescript-language-server --stdio` | TypeScript language server command. |
| `DIRECTORY_EXCLUSIONS` | `__pycache__,node_modules,.git,.venv,venv` | Directory exclude list (parsed as JSON list in `.env`). |
| `JWT_SECRET` | `dev-secret-change-in-production` | Secret for JWT token signing. |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm. |
| `JWT_EXPIRY_MINUTES` | `60` | JWT expiry. |
| `LOG_LEVEL` | `INFO` | Log level. |
| `LOG_PATH` | `ide_engine.log` | Log file path. |
| `IDE_HOST` | `localhost` | Editor WebSocket host. |
| `IDE_PORT` | `8765` | Editor WebSocket port. |
| `ENABLE_MULTI_TENANT` | `False` | Enable multi-tenant workspaces. |
| `ENABLE_MULTIMODAL` | `True` | Enable voice, image, PDF, and document processing. |
| `ENABLE_VOICE_INPUT` | `True` | Enable voice transcription. |
| `ENABLE_IMAGE_OCR` | `True` | Enable image text extraction. |
| `ENABLE_PDF_PARSING` | `True` | Enable PDF text extraction. |
| `ENABLE_CREATIVE_AGENT` | `True` | Enable image, sound, and video generation. |
| `CREATIVE_TOOLS_PATH` | `.creative_tools` | Directory for generated creative assets. |
| `ENABLE_SMART_DECISIONS` | `True` | Enable candidate scoring and ranking. |
| `ENABLE_FRIEND_PERSONALITY` | `True` | Enable friendly greeting, celebration, and help. |
| `ENABLE_CHAT` | `True` | Enable the unified chat WebSocket gateway. |
| `CHAT_WEBSOCKET_PATH` | `/ws/chat` | Chat WebSocket path. |
| `CHAT_MESSAGE_HISTORY_LIMIT` | `100` | Max messages persisted per room. |
| `CHAT_PRESENCE_TIMEOUT` | `60` | Presence timeout in seconds. |
| `CHAT_ENABLE_FRIENDS` | `True` | Decorate chat responses with FriendPersonality. |

## Development

Run the full test suite:

```bash
pytest
```

Build and run with Docker:

```bash
docker compose up --build
```

## Project Layout

```
ide_core/
  agent/           # ReAct agent and tools
  auth/            # JWT and tenant-aware auth
  buffer.py        # Piece-table text buffer
  chat/            # Unified chat subsystem
  config/          # Pydantic settings
  creative/        # Image, sound, video generation
  diagnostics.py   # Diagnostic manager
  document_manager.py
  git/             # Git integration
  lsp/             # LSP client and protocol
  multimodal/      # Voice, OCR, PDF, document input
  personality/     # Friend personality (greet, celebrate, memory)
  project/         # Workspace scanning
  server.py        # Editor WebSocket gateway
  smart_decision/  # Scorer, chooser, learner
  terminal.py      # PTY manager
  tenant/          # Multi-tenant middleware
frontend/
  index.html       # Monaco + xterm.js + Chat UI
  editor.js        # Editor WebSocket client
  chat_ui.js       # Chat client
  chat_ui.css      # Chat styles
tests/             # pytest suite (181 tests)
scripts/
  release.py       # Automated release script
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE).
