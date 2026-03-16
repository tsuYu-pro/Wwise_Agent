# Wwise Agent

An AI-powered intelligent assistant for Audiokinetic Wwise, featuring autonomous multi-turn tool calling, web search, WAAPI batch operations, Plan mode for complex task orchestration, a brain-inspired long-term memory system, a modern dark UI with bilingual support. Also ships a standard MCP Server for external AI clients like Claude Desktop / Cursor to call Wwise tools directly.

Built on **OpenAI Function Calling**, the Agent can query project structure, search objects, create/modify/move/delete Wwise objects, batch operations, Event management, RTPC binding, Effect management, Bus routing, web search, local document retrieval, structured execution plans, and continuous learning from interaction history — all completed iteratively in an autonomous loop.

## Core Features

### Agent Loop

The AI runs in an autonomous **Agent Loop**: receive user request → plan steps → call tools → inspect results → call more tools → until the task is complete. Three modes are available:

- **Agent Mode** — Full permissions. The AI can use all 30 tools to create, modify, move, delete objects, set properties, batch operations, and manage Events/Bus/RTPC/Effects.
- **Ask Mode** — Read-only. The AI can only query project structure, inspect properties, search objects, and provide analysis. All modification tools are blocked by mode guards.
- **Plan Mode** — The AI enters a planning phase: read-only investigation of the current project, clarify requirements via `ask_question`, then generate a structured execution plan with a DAG flowchart. Execution proceeds only after user approval.

```
User Request → AI Plans → Call Tools → Inspect Results → Call More Tools → … → Final Response
```

- **Multi-turn Tool Calling** — AI autonomously decides which tools to call and in what order
- **Todo Task System** — Complex tasks auto-split into subtasks with real-time status tracking
- **Streaming Output** — Real-time display of thinking process and responses
- **Deep Thinking** — Native support for reasoning models (DeepSeek-R1, GLM-4.7, Claude `<think>` tags)
- **Interrupt Anytime** — Stop the running Agent loop at any moment
- **Smart Context Management** — Trim conversations by turn, never truncate user/assistant messages, only compress tool results
- **Long-term Memory** — Brain-inspired three-layer memory system (episodic memory, abstract knowledge, strategic memory) with reward-driven learning and automatic reflection
- **Confirmation Mode** — Inline preview confirmation cards before modification operations, safe and controllable
- **Clickable Wwise Paths** — Paths like `\Actor-Mixer Hierarchy\...\MySound` in AI responses automatically become links; click to locate the object in Wwise

### Supported AI Providers

| Provider | Models | Notes |
|----------|--------|-------|
| **DeepSeek** | `deepseek-chat`, `deepseek-reasoner` (R1) | Cost-effective, fast response, supports Function Calling and reasoning |
| **GLM (Zhipu)** | `glm-4.7` | Stable access in China, native reasoning and tool calling |
| **OpenAI** | `gpt-5.2`, `gpt-5.3-codex` | Powerful capabilities, full Function Calling and Vision support |
| **Ollama** (Local) | `qwen2.5:14b`, any local model | Privacy-first, auto-detects available models |
| **Duojie** (Proxy) | `claude-sonnet-4-5`, `claude-opus-4-5-kiro`, `claude-opus-4-6-normal`, `claude-opus-4-6-kiro`, `claude-haiku-4-5`, `gemini-3-pro-image-preview`, `glm-4.7`, `glm-5`, `kimi-k2.5`, `MiniMax-M2.5`, `qwen3.5-plus`, `gpt-5.3-codex` | Access Claude, Gemini, GLM, Kimi, MiniMax, Qwen models via proxy |
| **WLAI** | `gpt-4o`, `claude-sonnet-4-6`, `claude-opus-4-6`, `deepseek-chat`, `gemini-2.0-flash`, etc. | Multi-model proxy |

### Image / Multimodal Input

- **Multimodal Messages** — Attach images (PNG/JPG/GIF/WebP) for vision-capable models
- **Paste & Drag** — `Ctrl+V` to paste from clipboard, or drag-and-drop image files into the input box
- **File Picker** — Click "+" → Attach Image to select from disk
- **Image Preview** — Thumbnails shown above input before sending, removable individually; click to enlarge

### Dark UI

- Deep blue-black theme (`#0a0a12` tone), modern dark style
- Thinking process, tool calls, and execution results are all collapsible/expandable
- **Clickable Wwise Paths** — Paths like `\Events\Default Work Unit\Play_BGM` in responses auto-become green links; click to locate in Wwise
- **AuroraBar** — Silver-white flowing gradient light strip on the left side during AI generation
- **Token Analytics** — Real-time token usage, reasoning tokens, cache hit rate, and per-model cost estimation (click for detailed analysis panel)
- Multi-session tabs — Run multiple independent conversations simultaneously
- One-click copy of AI responses
- `Enter` to send, `Shift+Enter` for new line
- **Font Scaling** — Overflow menu → Font slider, 70%–150%
- **Bilingual UI** — Switch Chinese/English via overflow menu; all UI elements and system prompts dynamically re-translated
- **WwisePreviewInline** — Inline operation preview cards in confirmation mode (shows tool name and parameters, Accept/Cancel)
- **Batch Action Bar** — Undo All / Keep All buttons

## Available Tools (30)

### Query Tools (9)

| Tool | Description |
|------|-------------|
| `get_project_hierarchy` | Get Wwise project top-level structure overview (child counts per hierarchy, Wwise version) |
| `get_object_properties` | Get detailed object properties (paginated; must call before setting properties to confirm property names) |
| `search_objects` | Fuzzy search Wwise objects by keyword (filterable by type) |
| `get_bus_topology` | Get the topology of all Buses in the Master-Mixer Hierarchy |
| `get_event_actions` | Get details of all Actions under an Event (type, target reference) |
| `get_soundbank_info` | Get SoundBank info (list or specific bank details) |
| `get_rtpc_list` | Get all Game Parameters (RTPCs) list |
| `get_selected_objects` | Get currently selected objects in Wwise Authoring (no path needed) |
| `get_effect_chain` | Get the Effect plugin chain of an object or Bus (up to 4 slots) |

### Action Tools (10)

| Tool | Description |
|------|-------------|
| `create_object` | Create Wwise objects (Sound, ActorMixer, BlendContainer, RandomSequenceContainer, SwitchContainer, Folder, etc.) |
| `set_property` | Set one or more object properties (Volume, Pitch, LPF, HPF, Positioning, Streaming, etc.) |
| `create_event` | Create Event + Action with target reference (Play/Stop/Pause/Resume/Break/Mute/UnMute) |
| `assign_bus` | Route an object to a specified Bus (sets OverrideOutput + OutputBus reference) |
| `delete_object` | Delete an object (checks Action references by default; force mode skips check) |
| `move_object` | Move an object to a new parent |
| `preview_event` | Preview an Event via Wwise Transport API (play/stop/pause/resume) |
| `set_rtpc_binding` | Bind a Game Parameter to an object property with driver curve control points |
| `add_effect` | Add an Effect plugin to an object or Bus (RoomVerb, Delay, Compressor, PeakLimiter, ParametricEQ, and 16 others) |
| `remove_effect` | Clear all Effect slots on an object |

### Batch Tools (4)

| Tool | Description |
|------|-------------|
| `batch_create` | Batch create objects — flat mode (siblings under one parent) / tree mode (nested hierarchy in one call); all operations wrapped in an Undo Group for one-click undo |
| `batch_set_property` | Batch set properties — uniform (targets + properties) / individual (items array) / auto-set by type filter (type_filter); supports Streaming, Volume, Positioning, and all properties |
| `batch_delete` | Batch delete objects — by path list or type+name filter; dry_run preview; reference protection (auto-skips objects referenced by Events) |
| `batch_move` | Batch move objects — uniform target mode (all to one parent) / individual mapping mode (items array) |

### Verification Tools (2)

| Tool | Description |
|------|-------------|
| `verify_structure` | Structural integrity check — orphan Events, Actions without targets, Sounds without Bus, Volume/Pitch range anomalies |
| `verify_event_completeness` | Event completeness check — Action targets, audio file existence, SoundBank inclusion status |

### Fallback Tool (1)

| Tool | Description |
|------|-------------|
| `execute_waapi` | Execute raw WAAPI calls directly (protected by blocklist; dangerous operations like project.open/close/save are intercepted) |

### Skill Meta-Tools (2)

| Tool | Description |
|------|-------------|
| `list_skills` | List all available Wwise Skill metadata |
| `run_skill` | Execute a specified Wwise Skill |

### Web & Documentation (2)

| Tool | Description |
|------|-------------|
| `web_search` | Web search (Brave/DuckDuckGo auto-fallback, with caching) |
| `fetch_webpage` | Fetch webpage body content (paginated, encoding-adaptive) |

### Document Retrieval (Built-in)

| Tool | Description |
|------|-------------|
| `search_local_doc` | Search local Wwise document index (WAAPI function signatures, object type properties, knowledge base articles) |

### Task Management (2)

| Tool | Description |
|------|-------------|
| `add_todo` | Add a task to the Todo list |
| `update_todo` | Update task status (pending / in_progress / done / error) |

## Skill System

Skills are predefined Wwise tool functions that interact with Wwise Authoring via WAAPI. Each Skill file resides in the `skills/` directory, containing `SKILL_INFO` metadata and a `run()` entry function, auto-scanned and registered at startup.

| Skill | Description |
|-------|-------------|
| `get_project_hierarchy` | Project top-level structure overview |
| `get_object_properties` | Object property details (paginated) |
| `search_objects` | Fuzzy search objects |
| `get_bus_topology` | Bus topology |
| `get_event_actions` | Event Action details |
| `get_soundbank_info` | SoundBank info |
| `get_rtpc_list` | RTPC list |
| `get_selected_objects` | Currently selected objects |
| `get_effect_chain` | Effect plugin chain |
| `create_object` | Create objects |
| `create_event` | Create Event + Action |
| `set_property` | Set properties |
| `assign_bus` | Bus routing |
| `delete_object` | Delete objects (reference check) |
| `move_object` | Move objects |
| `preview_event` | Preview Event |
| `set_rtpc_binding` | RTPC binding |
| `add_effect` | Add Effect |
| `remove_effect` | Remove Effect |
| `execute_waapi` | Raw WAAPI call |
| `verify_structure` | Structural integrity check |
| `verify_event_completeness` | Event completeness check |
| `batch_create` | Batch create objects |
| `batch_set_property` | Batch set properties |
| `batch_delete` | Batch delete objects |
| `batch_move` | Batch move objects |

## Project Structure

```
Wwise_Agent/
├── launcher.py                      # Entry point
├── pyproject.toml                   # Project configuration
├── VERSION                          # Semantic version file (0.1.0)
├── README.md                        # English documentation
├── README_ZH.md                     # Chinese documentation
├── lib/                             # Built-in dependencies
├── config/                          # Runtime configuration
│   └── wwise_ai.ini                # API keys & settings
├── cache/                           # Runtime cache
│   ├── conversations/              # Conversation history
│   ├── memory/                     # Memory database (agent_memory.db, growth_profile.json)
│   ├── plans/                      # Plan mode data files (plan_{session_id}.json)
│   ├── doc_index/                  # Document index cache
│   └── workspace/                  # Workspace state (workspace.json)
├── shared/                          # Shared utilities
│   └── common_utils.py             # Path & config utilities
├── trainData/                       # Exported training data (JSONL)
│
├── wwise_agent/                     # GUI Client + AI Agent Logic
│   ├── main.py                     # Module entry & window management
│   ├── core/
│   │   ├── main_window.py          # Main window (workspace save/restore)
│   │   ├── agent_runner.py         # AgentRunnerMixin — Agent loop helpers, confirmation mode, tool dispatch
│   │   └── session_manager.py      # SessionManagerMixin — Multi-session create/switch/close
│   ├── ui/
│   │   ├── ai_tab.py              # AI Agent tab (Mixin host, Agent loop, context management, streaming UI)
│   │   ├── cursor_widgets.py      # UI components (theme, chat blocks, Todo, Token analytics, Plan viewer)
│   │   ├── header.py              # HeaderMixin — Top settings bar (provider, model, feature toggles)
│   │   ├── input_area.py          # InputAreaMixin — Input area, mode switching, confirmation mode UI
│   │   ├── chat_view.py           # ChatViewMixin — Chat display, scroll control, Toast messages
│   │   ├── i18n.py                # Internationalization — Chinese/English bilingual support (800+ translations)
│   │   ├── theme_engine.py        # QSS template rendering & font scaling engine
│   │   ├── font_settings_dialog.py # Font scaling slider dialog
│   │   └── style_template.qss    # Centralized QSS theme stylesheet
│   ├── skills/                     # Wwise tool functions (26 Skills + helpers)
│   │   ├── __init__.py            # Skill registry & dynamic loader
│   │   ├── _waapi_helpers.py      # WAAPI connection & common utilities (internal module)
│   │   ├── get_project_hierarchy.py
│   │   ├── get_object_properties.py
│   │   ├── search_objects.py
│   │   ├── get_bus_topology.py
│   │   ├── get_event_actions.py
│   │   ├── get_soundbank_info.py
│   │   ├── get_rtpc_list.py
│   │   ├── get_selected_objects.py
│   │   ├── get_effect_chain.py
│   │   ├── create_object.py
│   │   ├── create_event.py
│   │   ├── set_property.py
│   │   ├── assign_bus.py
│   │   ├── delete_object.py
│   │   ├── move_object.py
│   │   ├── preview_event.py
│   │   ├── set_rtpc_binding.py
│   │   ├── add_effect.py
│   │   ├── remove_effect.py
│   │   ├── execute_waapi.py
│   │   ├── verify_structure.py
│   │   ├── verify_event_completeness.py
│   │   ├── batch_create.py
│   │   ├── batch_set_property.py
│   │   ├── batch_delete.py
│   │   └── batch_move.py
│   └── utils/
│       ├── ai_client.py           # AI API client (streaming, Function Calling, web search, 30 tool definitions)
│       ├── wwise_backend.py       # Wwise tool executor (dispatch layer based on Skills system)
│       ├── doc_rag.py             # Local document index (WAAPI functions, object types, knowledge base O(1) lookup)
│       ├── token_optimizer.py     # Token budget & compression strategy (tiktoken precise counting)
│       ├── ultra_optimizer.py     # System prompt & tool definition optimizer
│       ├── training_data_exporter.py # Export conversations to training data JSONL
│       ├── updater.py             # Auto-updater (GitHub Releases, ETag caching)
│       ├── plan_manager.py        # Plan mode data model & persistence
│       ├── memory_store.py        # Three-layer memory store (episodic/abstract/strategic) SQLite + numpy embedding
│       ├── embedding.py           # Local text embedding (sentence-transformers / fallback)
│       ├── reward_engine.py       # Reward scoring & memory importance updates
│       ├── reflection.py          # Rule reflection + LLM deep reflection module
│       └── growth_tracker.py      # Growth tracking & personality trait formation
│
└── wwise_mcp/                      # WAAPI Communication Layer + MCP Server
    ├── __init__.py
    ├── server.py                   # MCP Server entry (stdio transport)
    ├── config/
    │   └── settings.py            # WAAPI connection config
    ├── core/
    │   ├── adapter.py             # WAAPI wrapper (WwiseAdapter)
    │   ├── connection.py          # WebSocket connection management
    │   └── exceptions.py          # Exception hierarchy (6 categorized exceptions)
    ├── prompts/
    │   └── system_prompt.py       # System Prompt + dynamic context
    ├── rag/
    │   └── context.py             # RAG context collection
    └── tools/                      # 22 MCP tool functions
        ├── __init__.py            # Tool registration center
        ├── query.py               # 9 query tools
        ├── action.py              # 10 action tools
        ├── verify.py              # 2 verification tools
        └── fallback.py            # 1 fallback tool
```

## Quick Start

### Requirements

- **Python >= 3.10**
- **PySide6 or PySide2** (Qt GUI)
- **Wwise Authoring Tool** (WAAPI enabled, default port 8080)
- **Windows / macOS**

### Install Dependencies

```bash
pip install waapi-client requests
# Optional: precise token counting
pip install tiktoken
# Qt (choose one)
pip install PySide6
# or
pip install PySide2
```

### Configure API Key

**Option 1: Config File**

Fill in your AI service API key in `config/wwise_ai.ini`:

```ini
ollama_api_key:your_key_here
deepseek_api_key:your_key_here
glm_api_key:your_key_here
openai_api_key:your_key_here
duojie_api_key:your_key_here
wlai_api_key:your_key_here
```

**Option 2: In-App Settings**

Click `···` in the top-right corner → API Key, then enter in the dialog.

### Launch Wwise

Ensure Wwise Authoring Tool has a project open with WAAPI enabled (User Preferences → General → Enable WAAPI, default `ws://127.0.0.1:8080/waapi`).

### Launch the Agent

```bash
python launcher.py
```

### Using MCP Server (Optional)

Wwise Agent also provides a standard MCP Server that can be called by external AI clients like Claude Desktop and Cursor.

#### Configure Claude Desktop

Add the following to your Claude Desktop config file (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "your_project_path/Wwise_Agent"
    }
  }
}
```

#### Configure Cursor

Add the same configuration in Cursor's MCP settings. Once started, external AI clients can use all 22 Wwise MCP tools.

## Architecture

### Agent Loop Flow

```
┌───────────────────────────────────────────────────────┐
│  User sends message                                    │
│  ↓                                                     │
│  System prompt + conversation history + RAG docs       │
│  + long-term memory                                    │
│  ↓                                                     │
│  AI model (streaming) → thinking process + tool_calls  │
│  ↓                                                     │
│  Tool executor (WwiseToolExecutor) dispatches each     │
│  tool call:                                            │
│    - Wwise Skill → background thread WAAPI call        │
│    - Web / Docs → background thread (non-blocking)     │
│  ↓                                                     │
│  Tool results → fed back to AI as tool messages        │
│  ↓                                                     │
│  AI continues (may call more tools or generate final   │
│  response)                                             │
│  ↓                                                     │
│  Loop until AI completes or max iterations reached     │
└───────────────────────────────────────────────────────┘
```

### Mixin Architecture

`AITab` is the core component, composed of five focused Mixins:

| Mixin | Module | Responsibility |
|-------|--------|----------------|
| `HeaderMixin` | `ui/header.py` | Top settings bar — provider/model selectors, Web/Think toggles, Key status |
| `InputAreaMixin` | `ui/input_area.py` | Input area, send/stop buttons, mode switching (Agent/Ask/Plan), confirmation mode |
| `ChatViewMixin` | `ui/chat_view.py` | Chat display, message insertion, scroll control, Toast notifications |
| `AgentRunnerMixin` | `core/agent_runner.py` | Agent loop helpers, auto title generation, confirmation mode interception, tool classification |
| `SessionManagerMixin` | `core/session_manager.py` | Multi-session create/switch/close, session tab bar, state save/restore |

### Plan Mode

Plan mode enables the AI to handle complex tasks through a structured three-phase workflow:

1. **Deep Investigation** — Use read-only query tools to investigate the current Wwise project
2. **Requirement Clarification** — Interact with the user via `ask_question` when ambiguities are found
3. **Structured Planning** — Generate an engineering-grade execution plan with phases, steps, dependencies, and risk assessment

Plans are displayed as interactive `PlanViewer` cards with a DAG flowchart. Users can view details of each step, approve/reject the plan, and monitor execution progress. Plan data is persisted to `cache/plans/plan_{session_id}.json`.

### Brain-Inspired Long-term Memory System

A five-module system that enables the Agent to continuously learn and improve:

| Module | Description |
|--------|-------------|
| `memory_store.py` | Three-layer SQLite storage — **Episodic memory** (specific task experiences), **Abstract knowledge** (experience rules from reflection), **Strategic memory** (problem-solving patterns with priorities) |
| `embedding.py` | Local text vectorization using `sentence-transformers/all-MiniLM-L6-v2` (384-dim), fallback to character n-gram + numpy cosine similarity |
| `reward_engine.py` | Dopamine-like reward scoring — success (0.4), efficiency (0.25), novelty (0.15), error penalty (0.2); drives reinforcement/decay of memory importance |
| `reflection.py` | Hybrid reflection — zero-cost rule extraction after each task + LLM deep reflection every 5 tasks to generate abstract rules and strategy updates |
| `growth_tracker.py` | Rolling window metrics (error rate, success rate trends) + personality trait formation (efficiency preference, risk tolerance, response verbosity, proactiveness) |

Memory is automatically activated during queries: related episodic memories, abstract rules, and strategic memories are retrieved via cosine similarity and compressed into the system prompt (max 500 characters).

### WAAPI Connection

- **WebSocket Communication** — Based on the official `waapi-client` library, connecting to `ws://127.0.0.1:8080/waapi`
- **Global Connection Pool** — Singleton pattern reuses connections, avoiding frequent handshakes
- **Safety Blocklist** — The `execute_waapi` fallback tool is protected by a blocklist (project.open/close/save, remote.connect/disconnect)
- **Undo Group** — Batch operation tools automatically wrap `beginGroup/endGroup` for one-click undo
- **Exception Hierarchy** — 6 categorized exceptions (ConnectionError, APIError, NotFound, InvalidProperty, Forbidden, Timeout), each with suggestions

### Context Management

- **Native tool message chains**: `assistant(tool_calls)` → `tool(result)` messages passed directly to the model
- **Strict user/assistant alternation**: Ensures cross-provider API compatibility
- **Turn-based trimming**: Conversations split into turns by user messages; when exceeding token budget, first compress tool results from old turns, then remove entire turns
- **Never truncate user/assistant**: Only compress or remove `tool` result content
- **Auto RAG injection**: Automatically retrieves relevant WAAPI function signatures and object type docs based on user queries

### Token Counting & Cost Estimation

- **tiktoken Integration** — Uses tiktoken for precise counting when available, otherwise heuristic estimation
- **Multimodal Token Estimation** — Images estimated at ~765 tokens
- **Per-model Pricing** — Cost estimation based on each provider's pricing
- **Reasoning Token Tracking** — Separate statistics for reasoning/thinking tokens
- **Token Analysis Panel** — Detailed breakdown per request: input, output, reasoning, cache, latency, and cost

### Local Document Index

The `doc_rag.py` module provides lightweight dict indexing:

- **WAAPI Function Index** — URI → signature + description
- **Wwise Object Type Index** — type → properties + description
- **Knowledge Base Segment Retrieval** — `Doc/*.txt` knowledge base articles

Relevant documents are automatically injected into the system prompt based on user queries.

## Usage Examples

**Query project structure:**
```
User: Show me what's in the project
Agent: [get_project_hierarchy]
The project contains Actor-Mixer Hierarchy (15 objects), Events (8), Master-Mixer Hierarchy (3 Buses)...
```

**Create a complete sound system:**
```
User: Create a footstep system: RandomContainer with 3 Sounds, then create a play Event.
Agent: [add_todo: plan 3 steps]
       [batch_create: tree mode — RandomContainer + 3 child Sounds]
       [create_event: Play_Footsteps → RandomContainer]
       [verify_event_completeness: verify integrity]
Done. Created Footsteps (RandomSequenceContainer) + 3 child Sounds + Play_Footsteps Event.
```

**Batch property setting:**
```
User: Enable Streaming for all Sounds in the project.
Agent: [batch_set_property: type_filter="Sound", properties={"IsStreamingEnabled": true}]
Enabled Streaming for 23 Sound objects. Ctrl+Z to undo all at once.
```

**Web search for documentation:**
```
User: What new APIs does Wwise 2024 have for Blend Container?
Agent: [web_search: "Wwise 2024 Blend Container WAAPI new API"]
       [fetch_webpage: https://www.audiokinetic.com/...]
According to the official docs, Wwise 2024.1 added new Blend Track management APIs...
```

**Plan mode — reorganize project:**
```
User: Reorganize the entire project's Bus structure.
Agent: [Plan Mode]
       [get_bus_topology: investigate current structure]
       [get_project_hierarchy: understand object distribution]
       [create_plan: generate 3-phase reorganization plan]
       → Display PlanViewer card, wait for user confirmation
User: Approve execution
Agent: [Execute Bus creation, routing adjustments, verification step by step]
```

## FAQ

### WAAPI Connection Issues
- Confirm Wwise Authoring Tool is open with a project loaded
- Confirm WAAPI is enabled: User Preferences → General → Enable Wwise Authoring API
- Default port is 8080; modify `WAAPI_URL` in `_waapi_helpers.py` if there's a conflict

### Agent Not Calling Tools
- Confirm the selected provider supports Function Calling
- DeepSeek, GLM-4.7, OpenAI, and Duojie (Claude) all support tool calling
- Ollama requires a model that supports tool calling (e.g., `qwen2.5`); auto-falls back to JSON Mode otherwise

### Batch Operation Failures
- Confirm target paths exist (use `search_objects` or `get_project_hierarchy` to query first)
- `batch_delete` checks references by default; pass `force=true` for forced deletion
- All batch operations support Undo Group; press Ctrl+Z in Wwise for one-click undo

### UI Lag
- Wwise tools run in background threads and should not block the UI
- If lag occurs, check whether the WAAPI connection is healthy

### Updates
- Click the **Update** button in the overflow menu to check for new versions
- Silently checks GitHub Releases at startup; highlights the Update button when a new version is available
- Updates preserve `config/`, `cache/`, and `trainData/` directories

## Authors

tsuyu & KazamaSuichiku (翠竹, meshy)

## License

MIT
