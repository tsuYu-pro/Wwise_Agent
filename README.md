# Wwise Agent

**Wwise AI Agent** — 嵌入式智能助手，通过 WAAPI 操控 Wwise Authoring Tool。

一个基于 Qt GUI 的 AI Agent 客户端，能够自主理解用户意图，通过 22 个 Wwise 工具函数对 Wwise 项目进行查询、创建、修改、验证等操作。支持多轮 Function Calling、三层记忆系统、自我反思与成长追踪。

## 功能特性

- **Agent 模式**：AI 自主操作 Wwise 对象（全部 22 个工具）
- **Ask 模式**：只读查询分析（仅查询 + 验证 + Web 搜索）
- **Plan 模式**：先规划后执行（规划阶段调研 → 生成结构化计划 → 用户确认 → 逐步执行）
- **MCP Server**：标准 [Model Context Protocol](https://modelcontextprotocol.io) 服务器，支持 Claude Desktop / Cursor 等外部 AI 客户端直接调用 Wwise 工具
- **多 Provider 支持**：Ollama（本地）、DeepSeek、GLM（智谱）、OpenAI、Duojie、WLAI
- **联网搜索**：内置 Web 搜索与网页抓取，可查询 Wwise 文档、WAAPI 参考等
- **三层记忆系统**：Episodic / Semantic / Procedural 记忆，SQLite + 本地 Embedding 向量检索
- **自我反思**：规则反思 + LLM 深度反思，自动提炼经验规则
- **成长追踪**：技能置信度追踪 + 个性特征演化
- **Token 优化**：精准计数 + 三级压缩策略 + 上下文溢出自动裁剪
- **确认模式**：修改操作前内联预览确认，安全可控
- **国际化**：中英双语 UI

## 环境要求

- Python >= 3.10
- PySide6 或 PySide2（Qt GUI）
- Wwise Authoring Tool（需开启 WAAPI，默认端口 8080）

## 快速开始

### 1. 安装依赖

```bash
pip install waapi-client requests
# 可选：精准 token 计数
pip install tiktoken
# Qt（二选一）
pip install PySide6
# 或
pip install PySide2
```

### 2. 配置 API Key

在 `config/wwise_ai.ini` 中填写你的 AI 服务 API Key：

```ini
ollama_api_key:your_key_here
deepseek_api_key:your_key_here
glm_api_key:your_key_here
openai_api_key:your_key_here
duojie_api_key:your_key_here
wlai_api_key:your_key_here
```

### 3. 启动 Wwise

确保 Wwise Authoring Tool 已打开项目，且 WAAPI 已启用（默认 `ws://127.0.0.1:8080/waapi`）。

### 4. 启动 Agent

```bash
python launcher.py
```

### 5. 使用 MCP Server（可选）

Wwise Agent 同时提供标准 MCP Server，可被 Claude Desktop、Cursor 等外部 AI 客户端调用。

#### 配置 Claude Desktop

在 Claude Desktop 配置文件（`claude_desktop_config.json`）中添加：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "你的项目路径/Wwise_Agent"
    }
  }
}
```

#### 配置 Cursor

在 Cursor 的 MCP 设置中添加：

```json
{
  "mcpServers": {
    "wwise": {
      "command": "python",
      "args": ["-m", "wwise_mcp.server"],
      "cwd": "你的项目路径/Wwise_Agent"
    }
  }
}
```

启动后，外部 AI 客户端即可使用全部 22 个 Wwise 工具。

## 项目结构

```
Wwise_Agent/
├── launcher.py                 # 启动入口
├── pyproject.toml              # 项目配置
├── VERSION                     # 版本号
│
├── config/                     # 配置文件（API Key 等）
├── lib/                        # 第三方 vendored 依赖
├── shared/                     # 跨模块共享工具
│
├── wwise_agent/                # GUI 客户端 + AI Agent 逻辑
│   ├── main.py                 #   主入口
│   ├── core/                   #   核心业务（主窗口、Agent 循环、会话管理）
│   ├── ui/                     #   UI 组件（Mixin 架构）
│   └── utils/                  #   工具层（AI Client、记忆、反思、Token 优化等）
│
└── wwise_mcp/                  # WAAPI 通信层 + MCP Server
    ├── server.py               #   MCP Server 入口（stdio 传输）
    ├── config/                 #   WAAPI 连接配置
    ├── core/                   #   连接管理 + WAAPI 封装 + 异常体系
    ├── prompts/                #   System Prompt + 动态上下文
    ├── rag/                    #   RAG 上下文收集 + WAAPI Schema 索引
    └── tools/                  #   22 个工具函数
        ├── query.py            #     9 个查询工具
        ├── action.py           #     10 个操作工具
        ├── verify.py           #     2 个验证工具
        └── fallback.py         #     1 个兜底工具
```

## 工具一览

### 查询工具（9 个）

| 工具 | 说明 |
|------|------|
| `get_project_hierarchy` | 获取项目顶层结构概览 |
| `get_object_properties` | 获取对象属性详情（支持分页） |
| `search_objects` | 按关键词模糊搜索对象 |
| `get_bus_topology` | 获取 Bus 拓扑结构 |
| `get_event_actions` | 获取 Event 下的 Action 详情 |
| `get_soundbank_info` | 获取 SoundBank 信息 |
| `get_rtpc_list` | 获取 Game Parameter（RTPC）列表 |
| `get_selected_objects` | 获取当前选中的对象 |
| `get_effect_chain` | 获取 Effect 插件链 |

### 操作工具（10 个）

| 工具 | 说明 |
|------|------|
| `create_object` | 创建 Wwise 对象 |
| `set_property` | 设置对象属性 |
| `create_event` | 创建 Event + Action |
| `assign_bus` | 路由到指定 Bus |
| `delete_object` | 删除对象（带引用检查） |
| `move_object` | 移动对象到新父节点 |
| `preview_event` | 试听 Event |
| `set_rtpc_binding` | RTPC 绑定 |
| `add_effect` | 添加 Effect 插件 |
| `remove_effect` | 移除 Effect |

### 验证工具（2 个）

| 工具 | 说明 |
|------|------|
| `verify_structure` | 结构完整性验证 |
| `verify_event_completeness` | Event 完整性验证 |

### 兜底工具（1 个）

| 工具 | 说明 |
|------|------|
| `execute_waapi` | 直接执行原始 WAAPI 调用（受黑名单保护） |

## 许可证

MIT
