# -*- coding: utf-8 -*-
"""
Wwise Agent - AI Tab
Agent loop, multi-turn tool calling, streaming UI

模块拆分结构:
  ui/header.py          — HeaderMixin: 顶部设置栏构建
  ui/input_area.py      — InputAreaMixin: 输入区域和模式切换
  ui/chat_view.py       — ChatViewMixin: 对话显示和滚动逻辑
  core/agent_runner.py  — AgentRunnerMixin: Agent 循环和工具调度
  core/session_manager.py — SessionManagerMixin: 多会话管理和缓存
"""

import json
import math
import os
import threading
import time
import uuid
import queue
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from wwise_agent.qt_compat import QtWidgets, QtCore, QtGui, QSettings, invoke_on_main

from .i18n import tr, get_language
from ..utils.ai_client import AIClient, WWISE_TOOLS
from ..utils.wwise_backend import WwiseToolExecutor
from ..utils.token_optimizer import TokenOptimizer, TokenBudget, CompressionStrategy
from ..utils.memory_store import get_memory_store
from ..utils.reward_engine import get_reward_engine
from ..utils.reflection import get_reflection_module
from ..utils.growth_tracker import get_growth_tracker, TaskMetric
from .theme_engine import ThemeEngine
from .cursor_widgets import (
    CursorTheme,
    UserMessage,
    AIResponse,
    StatusLine,
    ChatInput,
    SendButton,
    StopButton,
    TodoList,
    ClickableImageLabel,
    TokenAnalyticsPanel,
    UnifiedStatusBar,
)
import re

# Mixin 模块
from .header import HeaderMixin
from .input_area import InputAreaMixin
from .chat_view import ChatViewMixin
from ..core.agent_runner import AgentRunnerMixin
from ..core.session_manager import SessionManagerMixin


class AITab(
    HeaderMixin,
    InputAreaMixin,
    ChatViewMixin,
    AgentRunnerMixin,
    SessionManagerMixin,
    QtWidgets.QWidget,
):
    """Wwise AI 助手 — 极简侧边栏风格（Mixin 架构）"""
    
    # 信号（用于线程安全的 UI 更新）
    _appendContent = QtCore.Signal(str)
    _addStatus = QtCore.Signal(str)
    _updateThinkingTime = QtCore.Signal()
    _agentDone = QtCore.Signal(dict)
    _agentError = QtCore.Signal(str)
    _agentStopped = QtCore.Signal()
    _updateTodo = QtCore.Signal(str, str, str)          # (todo_id, text, status)
    _addSystemShell = QtCore.Signal(str, str)            # (command, result_json)
    _executeToolRequest = QtCore.Signal(str, dict)       # 工具执行请求信号（线程安全）
    _addThinking = QtCore.Signal(str)                    # 思考内容更新
    _finalizeThinkingSignal = QtCore.Signal()            # 结束思考区块
    _resumeThinkingSignal = QtCore.Signal()              # 恢复思考区块
    _showToolStatus = QtCore.Signal(str)                 # 显示工具执行状态
    _hideToolStatus = QtCore.Signal()                    # 隐藏工具执行状态
    _showGenerating = QtCore.Signal()                    # 显示 "Generating..." 状态
    _autoTitleDone = QtCore.Signal(str, str)             # 自动标题完成: (session_id, title)
    _confirmToolRequest = QtCore.Signal()                # 确认模式：请求确认
    _confirmToolResult = QtCore.Signal(bool)             # 确认模式：结果
    
    def __init__(self, parent=None, workspace_dir: Optional[Path] = None):
        super().__init__(parent)
        
        self.client = AIClient()
        self.mcp = WwiseToolExecutor()
        self.client.set_tool_executor(self._execute_tool_with_todo)
        
        # 状态
        self._conversation_history: List[Dict[str, Any]] = []
        self._pending_ops: list = []
        self._current_response: Optional[AIResponse] = None
        self._is_running = False
        self._thinking_timer: Optional[QtCore.QTimer] = None
        
        # Agent 运行锚点
        self._agent_session_id: Optional[str] = None
        self._agent_response: Optional[AIResponse] = None
        self._agent_scroll_area = None
        self._agent_history: Optional[List[Dict[str, Any]]] = None
        self._agent_token_stats: Optional[Dict] = None
        self._agent_todo_list = None
        self._agent_chat_layout = None
        
        # 上下文管理
        self._max_context_messages = 20
        self._context_summary = ""
        
        # 缓存管理
        self._session_id = str(uuid.uuid4())[:8]
        self._cache_dir = Path(__file__).parent.parent.parent / "cache" / "conversations"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._auto_save_cache = True
        self._workspace_dir = workspace_dir
        
        # 多会话管理
        self._sessions: Dict[str, dict] = {}
        self._session_counter = 0
        self._tabs_backup: list = []
        
        # 静态内容缓存
        self._cached_optimized_system_prompt: Optional[str] = None
        self._cached_optimized_tools: Optional[List[dict]] = None
        self._cached_optimized_tools_no_web: Optional[List[dict]] = None
        
        # Token 优化器
        self.token_optimizer = TokenOptimizer()
        self._auto_optimize = True
        self._optimization_strategy = CompressionStrategy.BALANCED
        
        # 类脑三层记忆系统（延迟初始化，避免阻塞 UI）
        self._memory_store = None
        self._reward_engine = None
        self._reflection_module = None
        self._growth_tracker = None
        self._memory_initialized = False
        self._init_memory_system()
        
        # 思考/输出 Token 限制（不限制）
        self._max_thinking_length = float('inf')
        self._thinking_length_warning = float('inf')
        self._max_output_tokens = float('inf')
        self._output_token_warning = float('inf')
        self._current_output_tokens = 0
        
        # <think> 标签流式解析状态
        self._in_think_block = False
        self._tag_parse_buf = ""
        self._thinking_needs_finalize = False
        self._think_enabled = True
        
        # Token 使用统计
        self._token_stats = {
            'input_tokens': 0,
            'output_tokens': 0,
            'reasoning_tokens': 0,
            'cache_read': 0,
            'cache_write': 0,
            'total_tokens': 0,
            'requests': 0,
            'estimated_cost': 0.0,
        }
        self._call_records: list = []
        
        # 工具执行线程安全机制
        self._tool_result_queue: queue.Queue = queue.Queue()
        self._tool_lock = threading.Lock()
        
        # 连接信号
        self._appendContent.connect(self._on_append_content)
        self._addStatus.connect(self._on_add_status)
        self._updateThinkingTime.connect(self._on_update_thinking)
        self._agentDone.connect(self._on_agent_done)
        self._agentError.connect(self._on_agent_error)
        self._agentStopped.connect(self._on_agent_stopped)
        self._updateTodo.connect(self._on_update_todo)
        self._addSystemShell.connect(self._on_add_system_shell)
        self._executeToolRequest.connect(self._on_execute_tool_main_thread, QtCore.Qt.BlockingQueuedConnection)
        self._addThinking.connect(self._on_add_thinking)
        self._finalizeThinkingSignal.connect(self._finalize_thinking_main_thread)
        self._resumeThinkingSignal.connect(self._resume_thinking_main_thread)
        self._showToolStatus.connect(self._on_show_tool_status)
        self._hideToolStatus.connect(self._on_hide_tool_status)
        self._showGenerating.connect(self._on_show_generating)
        self._autoTitleDone.connect(self._on_auto_title_done)
        self._confirmToolRequest.connect(self._on_confirm_tool_request, QtCore.Qt.QueuedConnection)
        
        # 构建并缓存系统提示词
        self._system_prompt_think = self._build_system_prompt(with_thinking=True)
        self._system_prompt_no_think = self._build_system_prompt(with_thinking=False)
        self._cached_prompt_think = self.token_optimizer.optimize_system_prompt(
            self._system_prompt_think, max_length=1800
        )
        self._cached_prompt_no_think = self.token_optimizer.optimize_system_prompt(
            self._system_prompt_no_think, max_length=1500
        )
        self._system_prompt = self._system_prompt_think
        self._cached_optimized_system_prompt = self._cached_prompt_think
        
        self._build_ui()
        self._wire_events()
        self._load_model_preference(restore_provider=True)
        self._update_key_status()
        self._update_context_stats()
        
        # 启动时自动恢复会话
        self._restore_all_sessions()
        
        # 定期自动保存（每 60 秒）
        self._auto_save_timer = QtCore.QTimer(self)
        self._auto_save_timer.timeout.connect(self._periodic_save_all)
        self._auto_save_timer.start(60_000)
        
        import atexit
        atexit.register(self._atexit_save)
        app = QtWidgets.QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._periodic_save_all)
        
        # 启动时静默检查更新（延迟 5 秒）
        QtCore.QTimer.singleShot(5000, self._silent_update_check)
        
        # 语言切换时重建系统提示词 + 重新翻译 UI
        from .i18n import language_changed
        language_changed.changed.connect(self._rebuild_system_prompts)
        language_changed.changed.connect(self._retranslateUi)

    def _rebuild_system_prompts(self, _lang: str = ''):
        """语言切换后重建系统提示词"""
        self._system_prompt_think = self._build_system_prompt(with_thinking=True)
        self._system_prompt_no_think = self._build_system_prompt(with_thinking=False)
        self._cached_prompt_think = self.token_optimizer.optimize_system_prompt(
            self._system_prompt_think, max_length=1800
        )
        self._cached_prompt_no_think = self.token_optimizer.optimize_system_prompt(
            self._system_prompt_no_think, max_length=1800
        )
        self._system_prompt = self._system_prompt_think
        self._cached_optimized_system_prompt = self._cached_prompt_think
        print(f"[i18n] System prompts rebuilt for language: {_lang or get_language()}")

    def _retranslateUi(self, _lang: str = ''):
        """语言切换后重新翻译所有静态 UI 文本"""
        self._retranslate_header()
        self._retranslate_input_area()
        self._retranslate_session_tabs()
        print(f"[i18n] UI retranslated for language: {_lang or get_language()}")

    # ==========================================================
    # 类脑三层记忆系统
    # ==========================================================

    def _init_memory_system(self):
        """初始化长期记忆系统（后台线程，不阻塞 UI）"""
        def _init():
            try:
                self._memory_store = get_memory_store()
                self._reward_engine = get_reward_engine()
                self._reflection_module = get_reflection_module()
                self._growth_tracker = get_growth_tracker()
                self._memory_initialized = True
                print(f"[Memory] Brain-inspired memory system initialized: {self._memory_store.get_stats()}")
            except Exception as e:
                print(f"[Memory] Init failed (non-fatal): {e}")
                self._memory_initialized = False

        thread = threading.Thread(target=_init, daemon=True)
        thread.start()

    def _activate_long_term_memory(self, user_message: str, scene_context: dict = None) -> str:
        """动态记忆激活 — "我想起来了"

        核心机制:
        1. 当前问题 embedding
        2. 检索相关 episodic (具体经历)
        3. 检索相关 semantic (抽象知识)
        4. 检索适用的 strategies (策略)
        5. 按 importance * relevance 排序，压缩注入

        Context = WorkingMemory + TopK(RelevanceMemory)
        """
        if not self._memory_initialized or not self._memory_store:
            return ""

        try:
            store = self._memory_store

            # 构建查询（用户消息 + Wwise 场景关键词）
            query = user_message
            if scene_context:
                selected_types = scene_context.get('selected_types', [])
                if selected_types:
                    query += ' ' + ' '.join(selected_types)

            parts = []

            # 1. 检索相关 episodic (具体经历) — TopK=3
            episodes = store.search_episodic(query, top_k=3, min_importance=0.2)
            for ep, score in episodes:
                if score > 0.3:
                    status = "SUCCESS" if ep.success else "FAILED"
                    parts.append(
                        f"[Past Experience] {status} {ep.task_description[:80]} "
                        f"-> {ep.result_summary[:60]}"
                    )

            # 2. 检索相关 semantic (抽象知识) — TopK=5
            rules = store.search_semantic(query, top_k=5, min_confidence=0.3)
            for rule, score in rules:
                if score > 0.25:
                    parts.append(f"[Learned Rule] {rule.rule[:100]}")
                    store.increment_semantic_activation(rule.id)

            # 3. 检索适用的 strategies — TopK=3
            strategies = store.search_procedural(query, top_k=3)
            for strat, score in strategies:
                if score > 0.2:
                    parts.append(f"[Strategy] {strat.description[:80]}")

            if not parts:
                return ""

            # 限制注入量（最多 500 字符，避免浪费 token）
            result = "[Long-Term Memory]\n" + "\n".join(parts)
            if len(result) > 500:
                result = result[:500] + "..."
            return result

        except Exception as e:
            print(f"[Memory] Activation failed: {e}")
            return ""

    def _reflect_after_task(self, result: dict, agent_params: dict):
        """任务完成后的反思钩子 — 在后台线程执行"""
        if not self._memory_initialized or not self._reflection_module:
            return

        try:
            tool_calls_history = result.get('tool_calls_history', [])
            final_content = result.get('final_content', '') or result.get('content', '')

            tool_calls = []
            error_count = 0
            retry_count = 0
            for tc in tool_calls_history:
                tc_result = tc.get('result', {})
                success = bool(tc_result.get('success', True))
                has_error = bool(tc_result.get('error', ''))
                tool_calls.append({
                    "name": tc.get('tool_name', ''),
                    "success": success and not has_error,
                    "error": tc_result.get('error', ''),
                })
                if has_error or not success:
                    error_count += 1

            for i in range(1, len(tool_calls)):
                if (tool_calls[i]["name"] == tool_calls[i-1]["name"]
                        and not tool_calls[i-1]["success"]):
                    retry_count += 1

            history = self._agent_history if self._agent_history is not None else self._conversation_history
            task_description = ""
            for msg in reversed(history):
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        task_description = ' '.join(
                            p.get('text', '') for p in content if p.get('type') == 'text'
                        )
                    else:
                        task_description = content
                    task_description = task_description[:200]
                    break

            success = result.get('ok', True) and error_count < len(tool_calls) * 0.5

            result_summary = ""
            if final_content:
                import re as _re
                clean = _re.sub(r'<think>[\s\S]*?</think>', '', final_content).strip()
                result_summary = clean[:150]

            session_id = self._agent_session_id or self._session_id

            reflect_result = self._reflection_module.reflect_on_task(
                session_id=session_id,
                task_description=task_description,
                result_summary=result_summary,
                success=success,
                error_count=error_count,
                retry_count=retry_count,
                tool_calls=tool_calls,
                ai_client=self.client,
                model=agent_params.get('model', 'deepseek-chat'),
                provider=agent_params.get('provider', 'deepseek'),
            )

            if self._growth_tracker:
                metric = TaskMetric(
                    success=success,
                    error_count=error_count,
                    retry_count=retry_count,
                    tool_call_count=len(tool_calls),
                    reward=reflect_result.get('reward', 0.0),
                    tags=reflect_result.get('tags', []),
                )
                self._growth_tracker.record_task(metric)

                if reflect_result.get('deep_reflected') and 'skill_confidence' in reflect_result:
                    self._growth_tracker.update_skill_confidence_batch(
                        reflect_result.get('skill_confidence', {})
                    )

            if reflect_result.get('reward', 0) > 0:
                print(f"[Memory] Reflection done: reward={reflect_result['reward']:.2f}, "
                      f"tags={reflect_result.get('tags', [])}, "
                      f"deep_reflected={reflect_result.get('deep_reflected', False)}")

        except Exception as e:
            import traceback
            print(f"[Memory] Reflection hook error: {e}")
            traceback.print_exc()

    def _get_personality_injection(self) -> str:
        """获取个性注入文本（附加到 system prompt 末尾）"""
        if not self._memory_initialized or not self._growth_tracker:
            return ""
        try:
            return self._growth_tracker.get_personality_description()
        except Exception:
            return ""

    def _collect_scene_context(self) -> dict:
        """[主线程] 收集 Wwise 场景上下文用于记忆检索增强

        通过 WAAPI 获取当前 Wwise 编辑器中选中的对象信息，
        包含：选中对象的类型和名称。

        返回场景上下文 dict，传给后台线程的 _activate_long_term_memory 使用。
        注意：WAAPI 调用是异步的，这里通过 WwiseToolExecutor 同步化。
        """
        ctx = {'selected_types': [], 'selected_names': []}
        try:
            result = self.mcp.execute_tool('get_selected_objects', {})
            if result.get('success'):
                objects = result.get('result', {})
                if isinstance(objects, dict):
                    objects = objects.get('objects', [])
                elif isinstance(objects, str):
                    objects = []
                for obj in objects[:5]:  # 最多 5 个，避免过多
                    obj_type = obj.get('type', '')
                    obj_name = obj.get('name', '')
                    if obj_type:
                        ctx['selected_types'].append(obj_type)
                    if obj_name:
                        ctx['selected_names'].append(obj_name)
        except Exception:
            pass
        return ctx

    # ==========================================================
    # 系统提示词
    # ==========================================================

    def _build_system_prompt(self, with_thinking: bool = True) -> str:
        """构建系统提示词 — Wwise 版本"""
        if get_language() == 'en':
            lang_rule = "CRITICAL: You MUST reply in English for ALL user-facing text."
        else:
            lang_rule = "CRITICAL: You MUST reply in the SAME language the user uses."
        
        base_prompt = f"""You are a Wwise assistant, expert at audio middleware design, interactive audio, and sound design using Audiokinetic Wwise.
{lang_rule}
Never use emoji or icon symbols in replies unless the user explicitly requests them.
"""
        if with_thinking:
            base_prompt += f"""
Output Format (highest priority rule):
Every reply MUST begin with a <think>...</think> block. No exceptions.

Deep Thinking Framework (inside <think> tags):
1.[Understand] What does the user truly want?
2.[Status] Current Wwise project state? Last tool result?
3.[Options] List at least 2 approaches, compare pros/cons.
4.[Decision] Choose optimal approach with reasoning.
5.[Plan] Concrete steps and tools to call.
6.[Risk] What could go wrong?

Thinking Principles:
-Do NOT rush. First understand the existing Wwise object hierarchy before modifying.
-If unsure about object properties or hierarchy, query with tools first. Never guess.
-After each tool result, evaluate: Did it succeed? Is the result reasonable?

Content outside think tags is the formal reply — keep it concise and action-oriented. {lang_rule}
"""
        else:
            base_prompt += """
Output format: Concise, direct, action-oriented. MUST reply in the same language the user uses.
"""

        base_prompt += """
Wwise Object Path Rules:
-When mentioning Wwise objects, use the full hierarchy path: \\Actor-Mixer Hierarchy\\Default Work Unit\\MySound
-Paths start with a top-level category: \\Actor-Mixer Hierarchy\\..., \\Events\\..., \\Switches\\..., etc.
-Object paths are automatically converted to clickable links for navigation.

Fake Tool Call Prevention:
-NEVER write text that looks like tool execution results in your reply.
-If you need information, MUST actually call a tool via function calling.

Tool Call Parameter Rules:
-Before calling a tool, verify all required parameters are filled.
-Don't guess parameter names or values. Use query tools to confirm first.
-If a tool call returns an error, analyze the error and fix parameters before retrying.

Safe Operation Rules:
-Before modifying objects, query their current state with get_object_properties.
-Use search_objects to find objects by name/type before operating on them.
-After creating objects, verify with get_project_hierarchy.

Wwise Concepts:
-Actor-Mixer Hierarchy: Contains sound objects (Sound, Random Container, Blend Container, etc.)
-Events: Actions that trigger sounds (Play, Stop, Pause, etc.)
-Game Syncs: Switches, States, Game Parameters (RTPC), Triggers
-SoundBanks: Packaged audio data for runtime
-Busses: Audio mixing topology (Master-Mixer Hierarchy)
-Effects: ShareSets for audio processing (reverb, delay, etc.)

Web Search Strategy:
-For Wwise-related questions, prefer "Audiokinetic Wwise" prefix.
-When using search results, cite source: [Source: Title](URL).

Todo Management Rules:
-For complex tasks, use add_todo to create a step-by-step checklist.
-After each step, call update_todo to mark it done.

Memory System:
-You have a brain-inspired three-layer memory: episodic (past experiences), semantic (learned rules), procedural (strategies).
-Relevant memories are automatically injected as [Long-Term Memory] context before your response.
-After each task, the system reflects on your performance, calculates rewards, and strengthens/weakens memories.
-When you see [Past Experience], [Learned Rule], or [Strategy], leverage that knowledge.
-When you see [Self-Awareness], it reflects your accumulated behavioral tendencies — adapt accordingly.
"""
        # 个性注入
        personality_text = self._get_personality_injection()
        if personality_text:
            base_prompt = base_prompt + "\n" + personality_text
        return base_prompt

    # ==========================================================
    # UI 构建
    # ==========================================================

    def _build_ui(self):
        self.setObjectName("aiTab")
        self._theme = ThemeEngine()
        self._theme.load_template(Path(__file__).parent / "style_template.qss")
        self._theme.load_preference()
        self.setStyleSheet(self._theme.render())
        
        self.setMinimumWidth(320)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部设置栏
        header = self._build_header()
        layout.addWidget(header)
        
        # 会话标签栏
        session_tabs_bar = self._build_session_tabs()
        layout.addWidget(session_tabs_bar)
        
        # 对话区域（多会话 QStackedWidget）
        self.session_stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.session_stack, 1)
        
        # 创建第一个会话
        self._create_initial_session()

        # 输入区域
        input_area = self._build_input_area()
        layout.addWidget(input_area)

    def _wire_events(self):
        self.btn_send.clicked.connect(self._on_send)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_key.clicked.connect(self._on_set_key)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_cache.clicked.connect(self._on_cache_menu)
        self.btn_optimize.clicked.connect(self._on_optimize_menu)
        self.btn_export_train.clicked.connect(self._on_export_training_data)
        self.btn_attach_image.clicked.connect(self._on_attach_image)
        self.btn_update.clicked.connect(self._on_check_update)
        self.btn_font_scale.clicked.connect(self._on_font_settings)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self.model_combo.currentIndexChanged.connect(self._update_context_stats)
        
        # 字号缩放快捷键
        _QShortcut = getattr(QtWidgets, 'QShortcut', None) or QtGui.QShortcut
        _QShortcut(QtGui.QKeySequence("Ctrl+="), self, self._zoom_in)
        _QShortcut(QtGui.QKeySequence("Ctrl++"), self, self._zoom_in)
        _QShortcut(QtGui.QKeySequence("Ctrl+-"), self, self._zoom_out)
        _QShortcut(QtGui.QKeySequence("Ctrl+0"), self, self._zoom_reset)
        
        self.provider_combo.currentIndexChanged.connect(self._save_model_preference)
        self.model_combo.currentIndexChanged.connect(self._save_model_preference)
        self.think_check.stateChanged.connect(self._save_model_preference)
        self.input_edit.sendRequested.connect(self._on_send)
        
        # 多会话标签
        self.session_tabs.currentChanged.connect(self._switch_session)
        self.btn_new_session.clicked.connect(self._new_session)

    # ===== 字号缩放 =====

    def _apply_font_scale(self):
        self.setStyleSheet(self._theme.render())
        self._theme.save_preference()

    def _zoom_in(self):
        self._theme.zoom_in()
        self._apply_font_scale()

    def _zoom_out(self):
        self._theme.zoom_out()
        self._apply_font_scale()

    def _zoom_reset(self):
        self._theme.zoom_reset()
        self._apply_font_scale()

    def _on_font_settings(self):
        """打开字号设置面板"""
        from .font_settings_dialog import FontSettingsDialog
        dlg = FontSettingsDialog(current_scale=self._theme.scale, parent=self)
        dlg.scaleChanged.connect(self._on_font_scale_preview)
        dlg.exec_()
        self._theme.set_scale(dlg.scale)
        self._apply_font_scale()

    def _on_font_scale_preview(self, scale: float):
        self._theme.set_scale(scale)
        self.setStyleSheet(self._theme.render())

    # ===== 上下文统计 =====
    
    def _estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        tokens = chinese_chars / 1.5 + other_chars / 4
        return int(tokens)
    
    def _calculate_context_tokens(self) -> int:
        if not hasattr(self, '_tools_token_cache'):
            import json as _json
            tools_json = _json.dumps(WWISE_TOOLS, ensure_ascii=False)
            self._tools_token_cache = self.token_optimizer.estimate_tokens(tools_json)
        
        total = self._tools_token_cache
        total += self.token_optimizer.estimate_tokens(self._system_prompt)
        if self._context_summary:
            total += self.token_optimizer.estimate_tokens(self._context_summary)
        total += self.token_optimizer.calculate_message_tokens(self._conversation_history)
        return total
    
    def _save_model_preference(self):
        settings = QSettings("WwiseAI", "Assistant")
        provider = self._current_provider()
        model = self.model_combo.currentText()
        settings.setValue("last_provider", provider)
        settings.setValue("last_model", model)
        settings.setValue("use_think", self.think_check.isChecked())
    
    def _load_model_preference(self, restore_provider: bool = False):
        settings = QSettings("WwiseAI", "Assistant")
        last_provider = settings.value("last_provider", "")
        last_model = settings.value("last_model", "")
        
        use_think = settings.value("use_think", True)
        if isinstance(use_think, str):
            use_think = use_think.lower() == 'true'
        self.think_check.setChecked(bool(use_think))
        
        if not last_provider:
            return
        
        if restore_provider and last_provider != self._current_provider():
            for i in range(self.provider_combo.count()):
                if self.provider_combo.itemData(i) == last_provider:
                    self.provider_combo.blockSignals(True)
                    self.provider_combo.setCurrentIndex(i)
                    self.provider_combo.blockSignals(False)
                    self._refresh_models(last_provider)
                    self._update_key_status()
                    break
        
        current_provider = self._current_provider()
        if last_provider == current_provider and last_model:
            available_models = [self.model_combo.itemText(i) for i in range(self.model_combo.count())]
            if last_model in available_models:
                index = self.model_combo.findText(last_model)
                if index >= 0:
                    self.model_combo.setCurrentIndex(index)
    
    def _get_current_context_limit(self) -> int:
        model = self.model_combo.currentText()
        return self._model_context_limits.get(model, 64000)
    
    def _update_context_stats(self):
        used = self._calculate_context_tokens()
        limit = self._get_current_context_limit()
        
        if used >= 1000:
            used_str = f"{used / 1000:.1f}K"
        else:
            used_str = str(used)
        
        limit_str = f"{limit // 1000}K"
        percent = (used / limit) * 100 if limit > 0 else 0
        
        optimize_indicator = ""
        if self._auto_optimize:
            should_compress, _ = self.token_optimizer.should_compress(used, limit)
            if should_compress:
                optimize_indicator = " *"
        
        self.context_label.setText(f"{percent:.1f}% {used_str}/{limit_str}{optimize_indicator}")
        if percent < 50:
            ctx_state = ""
        elif percent < 80:
            ctx_state = "warning"
        else:
            ctx_state = "critical"
        self.context_label.setProperty("state", ctx_state)
        self.context_label.style().unpolish(self.context_label)
        self.context_label.style().polish(self.context_label)
        
        opt_state = "warning" if percent >= 80 else ""
        self.btn_optimize.setProperty("state", opt_state)
        self.btn_optimize.style().unpolish(self.btn_optimize)
        self.btn_optimize.style().polish(self.btn_optimize)

    def _update_token_stats_display(self):
        total = self._token_stats['total_tokens']
        cost = self._token_stats.get('estimated_cost', 0.0)
        
        if total >= 1000000:
            tok_display = f"{total / 1000000:.1f}M"
        elif total >= 1000:
            tok_display = f"{total / 1000:.1f}K"
        else:
            tok_display = str(total)
        
        if cost >= 0.01:
            cost_display = f"${cost:.2f}"
        elif cost > 0:
            cost_display = f"${cost:.4f}"
        else:
            cost_display = ""
        
        if cost_display:
            self.token_stats_btn.setText(f"{tok_display} | {cost_display}")
        else:
            self.token_stats_btn.setText(tok_display)
        
        cache_read = self._token_stats['cache_read']
        cache_write = self._token_stats['cache_write']
        cache_total = cache_read + cache_write
        hit_rate_display = f"{(cache_read / cache_total * 100):.1f}%" if cache_total > 0 else "N/A"
        
        reasoning = self._token_stats.get('reasoning_tokens', 0)
        reasoning_line = tr('token.reasoning_line', reasoning) if reasoning > 0 else ""
        
        self.token_stats_btn.setToolTip(
            tr('token.summary',
               self._token_stats['requests'],
               self._token_stats['input_tokens'],
               self._token_stats['output_tokens'],
               reasoning_line,
               cache_read, cache_write, hit_rate_display,
               total, cost_display or '$0.00')
        )
    
    def _show_token_stats_dialog(self):
        records = getattr(self, '_call_records', []) or []
        dialog = TokenAnalyticsPanel(records, self._token_stats, parent=self)
        dialog.exec_()
        if dialog.should_reset_stats:
            self._reset_token_stats()
    
    def _reset_token_stats(self):
        self._token_stats = {
            'input_tokens': 0, 'output_tokens': 0, 'reasoning_tokens': 0,
            'cache_read': 0, 'cache_write': 0, 'total_tokens': 0,
            'requests': 0, 'estimated_cost': 0.0,
        }
        self._call_records = []
        self._update_token_stats_display()
        if self._current_response:
            self._current_response.add_status(tr('status.stats_reset'))

    # ===== UI 辅助 =====
    
    def _current_provider(self) -> str:
        return self.provider_combo.currentData() or 'deepseek'

    def _refresh_models(self, provider: str):
        self.model_combo.clear()
        if provider == 'ollama':
            try:
                models = self.client.get_ollama_models()
                if models:
                    self.model_combo.addItems(models)
                    return
            except Exception:
                pass
        self.model_combo.addItems(self._model_map.get(provider, []))

    def _update_key_status(self):
        provider = self._current_provider()
        if provider == 'ollama':
            result = self.client.test_connection('ollama')
            if result.get('ok'):
                self.key_status.setText("Local")
                self.key_status.setProperty("state", "ok")
            else:
                self.key_status.setText("Offline")
                self.key_status.setProperty("state", "error")
        elif self.client.has_api_key(provider):
            masked = self.client.get_masked_key(provider)
            self.key_status.setText(masked)
            self.key_status.setProperty("state", "ok")
        else:
            self.key_status.setText("No Key")
            self.key_status.setProperty("state", "warning")
        self.key_status.style().unpolish(self.key_status)
        self.key_status.style().polish(self.key_status)

    def _on_provider_changed(self):
        provider = self._current_provider()
        self._refresh_models(provider)
        self._load_model_preference()
        self._update_key_status()

    def _set_running(self, running: bool):
        self._is_running = running
        
        if running:
            self._agent_session_id = self._session_id
            self._agent_response = self._current_response
            self._agent_scroll_area = self.scroll_area
            self._agent_history = self._conversation_history
            self._agent_token_stats = self._token_stats
            self._agent_todo_list = self.todo_list
            self._agent_chat_layout = self.chat_layout
            
            self._thinking_buffer = ""
            self._content_buffer = ""
            self._current_output_tokens = 0
            self._in_think_block = False
            self._tag_parse_buf = ""
            self._fake_warned = False
            self._output_buffer = ""
            self._last_flush_time = time.time()
            self._adaptive_buf_size = 80
            self._adaptive_interval = 0.15
            self._last_render_duration = 0.0
            self._flush_count = 0
            self._is_first_content_chunk = True
            
            self.client.reset_stop()
            self._thinking_timer = QtCore.QTimer(self)
            self._thinking_timer.timeout.connect(lambda: self._updateThinkingTime.emit())
            self._thinking_timer.start(1000)
            self._start_input_glow()
        else:
            if self._agent_session_id and self._agent_session_id in self._sessions:
                s = self._sessions[self._agent_session_id]
                s['current_response'] = self._agent_response
                if self._agent_history is not None:
                    s['conversation_history'] = self._agent_history
                if self._agent_token_stats is not None:
                    s['token_stats'] = self._agent_token_stats
                if self._agent_todo_list is not None:
                    s['todo_list'] = self._agent_todo_list
            
            self._agent_session_id = None
            self._agent_response = None
            self._agent_scroll_area = None
            self._agent_history = None
            self._agent_token_stats = None
            self._agent_todo_list = None
            self._agent_chat_layout = None
            
            if self._thinking_timer:
                self._thinking_timer.stop()
                self._thinking_timer = None
            
            self._stop_input_glow()
            self._stop_active_aurora()
        
        self._update_run_buttons()
    
    # ===== 动效：输入框呼吸光晕 + AIResponse 流光边框 =====

    def _start_input_glow(self):
        self._glow_phase = 0.0
        if not hasattr(self, '_glow_timer') or self._glow_timer is None:
            self._glow_timer = QtCore.QTimer(self)
            self._glow_timer.setInterval(50)
            self._glow_timer.timeout.connect(self._update_input_glow)
        self._glow_timer.start()

    def _stop_input_glow(self):
        if hasattr(self, '_glow_timer') and self._glow_timer is not None:
            self._glow_timer.stop()
        try:
            self.input_edit.setStyleSheet("")
        except RuntimeError:
            pass

    def _update_input_glow(self):
        self._glow_phase += 0.04
        t = (math.sin(self._glow_phase) + 1.0) / 2.0
        r = int(100 + (200 - 100) * t)
        g = int(116 + (210 - 116) * t)
        b = int(139 + (220 - 139) * t)
        a = int(60 + 70 * t)
        try:
            self.input_edit.setStyleSheet(
                f"QPlainTextEdit#chatInput {{ border: 1.5px solid rgba({r},{g},{b},{a}); }}"
            )
        except RuntimeError:
            pass

    def _start_active_aurora(self):
        try:
            resp = self._agent_response or self._current_response
            if resp and hasattr(resp, 'aurora_bar'):
                resp.start_aurora()
        except RuntimeError:
            pass

    def _stop_active_aurora(self):
        try:
            resp = self._agent_response or self._current_response
            if resp and hasattr(resp, 'aurora_bar'):
                resp.stop_aurora()
        except RuntimeError:
            pass

    _TAB_RUNNING_PREFIX = "\u25cf "
    
    def _update_run_buttons(self):
        current_is_running = (self._agent_session_id is not None
                              and self._agent_session_id == self._session_id)
        any_running = self._agent_session_id is not None
        self.btn_stop.setVisible(current_is_running)
        self.btn_send.setVisible(not current_is_running)
        self.btn_send.setEnabled(not any_running)
        
        for i in range(self.session_tabs.count()):
            sid = self.session_tabs.tabData(i)
            label = self.session_tabs.tabText(i)
            is_agent_tab = (sid == self._agent_session_id and self._agent_session_id is not None)
            has_prefix = label.startswith(self._TAB_RUNNING_PREFIX)
            if is_agent_tab and not has_prefix:
                self.session_tabs.setTabText(i, self._TAB_RUNNING_PREFIX + label)
            elif not is_agent_tab and has_prefix:
                self.session_tabs.setTabText(i, label[len(self._TAB_RUNNING_PREFIX):])

    # ===== 信号处理 =====
    
    def _on_append_content(self, text: str):
        resp = self._agent_response or self._current_response
        if not text or not resp:
            return
        if not text.strip() and '\n' not in text:
            return
        try:
            if hasattr(self, 'thinking_bar') and getattr(self.thinking_bar, '_mode', None) == 'generating':
                self.thinking_bar.stop()
            resp.append_content(text)
            self._scroll_agent_to_bottom(force=False)
        except RuntimeError:
            pass

    def _on_content_with_limit(self, text: str):
        if not text:
            return
        if not hasattr(self, '_output_buffer'):
            self._output_buffer = ""
            self._last_flush_time = time.time()
            self._adaptive_buf_size = 80
            self._adaptive_interval = 0.15
            self._last_render_duration = 0.0
            self._flush_count = 0
            self._is_first_content_chunk = True
        self._tag_parse_buf += text
        self._drain_tag_buffer()

    # ------------------------------------------------------------------
    # <think> 标签流式解析
    # ------------------------------------------------------------------

    @staticmethod
    def _partial_tag_at_end(text: str, tag: str) -> int:
        for i in range(min(len(tag) - 1, len(text)), 0, -1):
            if tag[:i] == text[-i:]:
                return i
        return 0

    def _drain_tag_buffer(self):
        buf = self._tag_parse_buf
        while buf:
            if not self._in_think_block:
                pos = buf.find('<think>')
                if pos >= 0:
                    if pos > 0:
                        self._emit_normal_content(buf[:pos])
                    buf = buf[pos + 7:]
                    self._in_think_block = True
                    if self._think_enabled:
                        self._thinking_needs_finalize = True
                        self._resume_thinking()
                    continue
                hold = self._partial_tag_at_end(buf, '<think>')
                if hold:
                    self._emit_normal_content(buf[:-hold])
                    self._tag_parse_buf = buf[-hold:]
                    return
                self._emit_normal_content(buf)
                self._tag_parse_buf = ""
                return
            else:
                pos = buf.find('</think>')
                if pos >= 0:
                    if self._think_enabled and pos > 0:
                        self._addThinking.emit(buf[:pos])
                    buf = buf[pos + 8:]
                    self._in_think_block = False
                    if self._think_enabled:
                        self._finalize_thinking()
                    continue
                hold = self._partial_tag_at_end(buf, '</think>')
                if hold:
                    if self._think_enabled:
                        safe = buf[:-hold]
                        if safe:
                            self._addThinking.emit(safe)
                    self._tag_parse_buf = buf[-hold:]
                    return
                if self._think_enabled:
                    self._addThinking.emit(buf)
                self._tag_parse_buf = ""
                return
        self._tag_parse_buf = ""

    def _finalize_thinking(self):
        self._finalizeThinkingSignal.emit()

    def _resume_thinking(self):
        self._resumeThinkingSignal.emit()

    @QtCore.Slot()
    def _finalize_thinking_main_thread(self):
        try:
            resp = self._agent_response or self._current_response
            if resp and resp._has_thinking:
                if not resp.thinking_section._finalized:
                    resp.thinking_section.finalize()
        except RuntimeError:
            pass
        if self._thinking_timer:
            self._thinking_timer.stop()
            self._thinking_timer = None
        try:
            self.thinking_bar.stop()
        except (RuntimeError, AttributeError):
            pass
    
    @QtCore.Slot()
    def _resume_thinking_main_thread(self):
        try:
            resp = self._agent_response or self._current_response
            if resp and resp._has_thinking:
                ts = resp.thinking_section
                if ts._finalized:
                    ts.resume()
        except RuntimeError:
            pass
        if not self._thinking_timer:
            self._thinking_timer = QtCore.QTimer(self)
            self._thinking_timer.timeout.connect(lambda: self._updateThinkingTime.emit())
            self._thinking_timer.start(1000)
        try:
            self.thinking_bar.start()
        except (RuntimeError, AttributeError):
            pass

    def _emit_normal_content(self, text: str):
        if not text:
            return
        if self._in_think_block is False and getattr(self, '_thinking_needs_finalize', True):
            self._finalize_thinking()
            self._thinking_needs_finalize = False

        if not self._check_output_token_limit(text):
            if self._output_buffer:
                self._appendContent.emit(self._output_buffer)
                self._output_buffer = ""
            self._appendContent.emit(tr('ai.token_limit'))
            self._addStatus.emit(tr('ai.token_limit_status'))
            self.client.request_stop()
            return

        self._output_buffer += text

        should_flush = False
        current_time = time.time()

        if not hasattr(self, '_adaptive_buf_size'):
            self._adaptive_buf_size = 80
            self._adaptive_interval = 0.15
            self._last_render_duration = 0.0
            self._flush_count = 0
            self._is_first_content_chunk = True

        if self._is_first_content_chunk:
            should_flush = True
            self._is_first_content_chunk = False
        elif len(self._output_buffer) >= self._adaptive_buf_size:
            should_flush = True
        elif '\n' in text:
            should_flush = True
        elif current_time - self._last_flush_time > self._adaptive_interval:
            should_flush = True

        if should_flush and self._output_buffer:
            flush_start = time.time()
            buf = self._output_buffer

            if '[ok]' in buf or '[err]' in buf or '[工具执行结果]' in buf or '[Tool Result]' in buf:
                lines = buf.split('\n')
                filtered = []
                has_fake = False
                for ln in lines:
                    s = ln.strip()
                    if s in ('[工具执行结果]', '[Tool Result]') or self._FAKE_TOOL_PATTERNS.match(s):
                        has_fake = True
                        continue
                    filtered.append(ln)
                buf = '\n'.join(filtered)
                if has_fake and not getattr(self, '_fake_warned', False):
                    self._addStatus.emit(tr('ai.fake_tool'))
                    self._fake_warned = True
            if buf.strip():
                self._appendContent.emit(buf)
            self._output_buffer = ""
            self._last_flush_time = current_time
            self._flush_count += 1

            render_dur = time.time() - flush_start
            self._last_render_duration = render_dur
            if render_dur < 0.004:
                self._adaptive_buf_size = max(40, self._adaptive_buf_size - 20)
                self._adaptive_interval = max(0.08, self._adaptive_interval - 0.02)
            elif render_dur > 0.012:
                self._adaptive_buf_size = min(500, self._adaptive_buf_size + 40)
                self._adaptive_interval = min(0.40, self._adaptive_interval + 0.05)

    def _check_output_token_limit(self, text: str) -> bool:
        if not text:
            return True
        new_tokens = self.token_optimizer.estimate_tokens(text)
        self._current_output_tokens += new_tokens
        if self._current_output_tokens >= self._max_output_tokens:
            return False
        if (self._current_output_tokens >= self._output_token_warning
                and self._current_output_tokens < self._max_output_tokens):
            remaining = self._max_output_tokens - self._current_output_tokens
            if remaining < 400:
                self._addStatus.emit(
                    tr('ai.approaching_limit', self._current_output_tokens, self._max_output_tokens))
        return True

    def _on_thinking_chunk(self, text: str):
        if text and self._think_enabled:
            self._addThinking.emit(text)
    
    @QtCore.Slot(str)
    def _on_add_thinking(self, text: str):
        try:
            resp = self._agent_response or self._current_response
            if resp:
                resp.add_thinking(text)
                if hasattr(self, 'thinking_bar') and not self.thinking_bar.isVisible():
                    self.thinking_bar.start()
            self._scroll_agent_to_bottom(force=False)
        except RuntimeError:
            pass

    def _on_add_status(self, text: str):
        try:
            resp = self._agent_response or self._current_response
            if resp:
                resp.add_status(text)
                self._scroll_agent_to_bottom(force=False)
        except RuntimeError:
            pass

    def _on_update_thinking(self):
        try:
            resp = self._agent_response or self._current_response
            if resp:
                resp.update_thinking_time()
                if hasattr(self, 'thinking_bar') and self.thinking_bar.isVisible():
                    if resp._has_thinking:
                        self.thinking_bar.set_elapsed(resp.thinking_section._total_elapsed())
        except RuntimeError:
            pass

    def _on_agent_done(self, result: dict):
        try:
            self.thinking_bar.stop()
        except (RuntimeError, AttributeError):
            pass

        resp = self._agent_response or self._current_response
        history = self._agent_history if self._agent_history is not None else self._conversation_history
        stats = self._agent_token_stats or self._token_stats
        
        # 刷新缓冲区
        if self._tag_parse_buf:
            if self._in_think_block:
                if self._think_enabled:
                    self._addThinking.emit(self._tag_parse_buf)
            else:
                self._emit_normal_content(self._tag_parse_buf)
            self._tag_parse_buf = ""
            self._in_think_block = False

        if hasattr(self, '_output_buffer') and self._output_buffer:
            self._on_append_content(self._output_buffer)
            self._output_buffer = ""
        
        try:
            if resp:
                resp.finalize()
        except RuntimeError:
            resp = None
        
        # 保存消息到历史
        tool_calls_history = result.get('tool_calls_history', [])
        new_messages = result.get('new_messages', [])
        
        if new_messages:
            for nm in new_messages:
                clean = nm.copy()
                clean.pop('reasoning_content', None)
                if nm is new_messages[-1] and nm.get('role') == 'assistant' and not nm.get('tool_calls'):
                    continue
                history.append(clean)
        
        final_content = result.get('final_content', '')
        if not final_content or not final_content.strip():
            for nm in reversed(new_messages):
                if nm.get('role') == 'assistant' and nm.get('content'):
                    c = nm['content']
                    stripped = re.sub(r'<think>[\s\S]*?</think>', '', c).strip()
                    if stripped:
                        final_content = c
                        break
            if not final_content or not final_content.strip():
                final_content = result.get('content', '')
        
        thinking_text = ""
        clean_content = ""
        if final_content:
            thinking_parts = re.findall(r'<think>([\s\S]*?)</think>', final_content)
            thinking_text = '\n'.join(thinking_parts).strip() if thinking_parts else ''
            clean_content = re.sub(r'<think>[\s\S]*?</think>', '', final_content).strip()
            clean_content = self._strip_fake_tool_results(clean_content)
        
        need_final = bool(clean_content) or bool(new_messages) or not history or history[-1].get('role') != 'assistant'
        if need_final:
            final_msg = {'role': 'assistant', 'content': clean_content or tr('ai.no_content')}
            if thinking_text:
                final_msg['thinking'] = thinking_text
            # Shell 执行记录
            sys_shells = []
            for tc in tool_calls_history:
                tn = tc.get('tool_name', '')
                ta = tc.get('arguments', {})
                tc_result = tc.get('result', {})
                if tn == 'execute_shell' and ta.get('command'):
                    sys_shells.append({
                        'command': ta['command'],
                        'output': tc_result.get('result', ''),
                        'error': tc_result.get('error', ''),
                        'success': bool(tc_result.get('success')),
                        'cwd': ta.get('cwd', ''),
                    })
            if sys_shells:
                final_msg['system_shells'] = sys_shells
            history.append(final_msg)
        
        self._manage_context()
        
        # 反思钩子：任务完成后触发长期记忆反思（后台线程，不阻塞 UI）
        if self._memory_initialized and tool_calls_history:
            _reflect_params = getattr(self, '_last_agent_params', {})
            def _do_reflect():
                self._reflect_after_task(result, _reflect_params)
            reflect_thread = threading.Thread(target=_do_reflect, daemon=True)
            reflect_thread.start()
        
        # 更新 Token 统计
        usage = result.get('usage', {})
        new_call_records = result.get('call_records', [])
        if usage:
            stats['input_tokens'] += usage.get('prompt_tokens', 0)
            stats['output_tokens'] += usage.get('completion_tokens', 0)
            stats['reasoning_tokens'] = stats.get('reasoning_tokens', 0) + usage.get('reasoning_tokens', 0)
            stats['cache_read'] += usage.get('cache_hit_tokens', 0)
            stats['cache_write'] += usage.get('cache_miss_tokens', 0)
            stats['total_tokens'] += usage.get('total_tokens', 0)
            stats['requests'] += 1
            
            from wwise_agent.utils.token_optimizer import calculate_cost
            model_name = self.model_combo.currentText()
            this_cost = calculate_cost(
                model=model_name,
                input_tokens=usage.get('prompt_tokens', 0),
                output_tokens=usage.get('completion_tokens', 0),
                cache_hit=usage.get('cache_hit_tokens', 0),
                cache_miss=usage.get('cache_miss_tokens', 0),
                reasoning_tokens=usage.get('reasoning_tokens', 0),
            )
            stats['estimated_cost'] = stats.get('estimated_cost', 0.0) + this_cost
        
        if new_call_records:
            if not hasattr(self, '_call_records'):
                self._call_records = []
            self._call_records.extend(new_call_records)
        
        if usage:
            if not self._agent_session_id or self._agent_session_id == self._session_id:
                self._update_token_stats_display()
            
            cache_hit = usage.get('cache_hit_tokens', 0)
            cache_miss = usage.get('cache_miss_tokens', 0)
            cache_rate = usage.get('cache_hit_rate', 0)
            if cache_hit > 0 or cache_miss > 0:
                rate_percent = cache_rate * 100
                self._addStatus.emit(f"Cache: {cache_hit}/{cache_hit+cache_miss} ({rate_percent:.0f}%)")
        
        # 自动保存
        agent_sid = self._agent_session_id
        if self._auto_save_cache and len(history) > 0 and agent_sid:
            if agent_sid in self._sessions:
                self._sessions[agent_sid]['conversation_history'] = history
                self._sessions[agent_sid]['token_stats'] = stats
            if agent_sid == self._session_id:
                self._save_cache()
        
        self._set_running(False)
        self._hideToolStatus.emit()
        self._update_context_stats()
        self._maybe_generate_title(agent_sid, history)

    def _on_agent_error(self, error: str):
        try:
            self.thinking_bar.stop()
        except (RuntimeError, AttributeError):
            pass
        if hasattr(self, '_output_buffer') and self._output_buffer:
            self._on_append_content(self._output_buffer)
            self._output_buffer = ""
        
        resp = self._agent_response or self._current_response
        try:
            if resp:
                resp.finalize()
                resp.add_status(f"Error: {error}")
        except RuntimeError:
            pass
        
        self._ensure_history_ends_with_assistant(f"[Error] {error}")
        self._set_running(False)

    def _on_agent_stopped(self):
        try:
            self.thinking_bar.stop()
        except (RuntimeError, AttributeError):
            pass
        if hasattr(self, '_output_buffer') and self._output_buffer:
            self._on_append_content(self._output_buffer)
            self._output_buffer = ""
        
        resp = self._agent_response or self._current_response
        try:
            if resp:
                resp.finalize()
                resp.add_status("Stopped")
        except RuntimeError:
            pass
        
        self._ensure_history_ends_with_assistant("[Stopped by user]")
        self._set_running(False)
        self._hideToolStatus.emit()
    
    def _ensure_history_ends_with_assistant(self, fallback_content: str):
        history = self._agent_history if self._agent_history is not None else self._conversation_history
        if history and history[-1].get('role') == 'user':
            history.append({'role': 'assistant', 'content': fallback_content})

    # ---------- 工具执行 ----------

    def _on_update_todo(self, todo_id: str, text: str, status: str):
        try:
            todo = self._agent_todo_list or self.todo_list
            layout = self._agent_chat_layout or self.chat_layout
            if not todo:
                return
            self._ensure_todo_in_chat(todo, layout)
        except RuntimeError:
            return
        if text:
            todo.add_todo(todo_id, text, status)
        else:
            todo.update_todo(todo_id, status)

    def _execute_tool_with_todo(self, tool_name: str, **kwargs) -> dict:
        """执行工具，包含 Todo 相关的工具
        WAAPI 全部通过 WebSocket 通信，不需要主线程约束。
        """
        # Ask 模式安全守卫
        if not self._agent_mode and tool_name not in self._ASK_MODE_TOOLS:
            return {"success": False, "error": tr('ask.restricted', tool_name)}
        
        # 确认模式
        if self._confirm_mode and tool_name in self._CONFIRM_TOOLS:
            confirmed = self._request_tool_confirmation(tool_name, kwargs)
            if not confirmed:
                return {"success": False, "error": tr('ask.user_cancel', tool_name)}
        
        self._showToolStatus.emit(tool_name)
        
        try:
            # Todo 工具
            if tool_name == "add_todo":
                todo_id = kwargs.get("todo_id", "")
                text = kwargs.get("text", "")
                status = kwargs.get("status", "pending")
                self._updateTodo.emit(todo_id, text, status)
                return {"success": True, "result": f"Added todo: {text}"}
            elif tool_name == "update_todo":
                todo_id = kwargs.get("todo_id", "")
                status = kwargs.get("status", "done")
                self._updateTodo.emit(todo_id, "", status)
                return {"success": True, "result": f"Updated todo {todo_id} to {status}"}
            
            # WAAPI 工具 — 全部可以在后台线程执行
            if tool_name in self._BG_SAFE_TOOLS:
                return self._execute_tool_in_bg(tool_name, kwargs)
            
            # 其他工具也在后台执行（Wwise 无主线程约束）
            return self._execute_tool_in_bg(tool_name, kwargs)
        finally:
            self._hideToolStatus.emit()
    
    def _execute_tool_in_bg(self, tool_name: str, kwargs: dict) -> dict:
        try:
            return self.mcp.execute_tool(tool_name, kwargs)
        except Exception as e:
            import traceback
            return {"success": False, "error": tr('ai.bg_exec_err', f"{e}\n{traceback.format_exc()[:300]}")}
    
    @QtCore.Slot(str, dict)
    def _on_execute_tool_main_thread(self, tool_name: str, kwargs: dict):
        """主线程工具执行（Wwise 一般不需要，保留兼容性）"""
        result = {"success": False, "error": tr('ai.unknown_err')}
        try:
            result = self.mcp.execute_tool(tool_name, kwargs)
        except Exception as e:
            result = {"success": False, "error": tr('ai.tool_exec_err', str(e))}
        finally:
            try:
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass
            self._tool_result_queue.put(result)

    # ------------------------------------------------------------------
    # 伪造工具调用检测
    # ------------------------------------------------------------------
    _ALL_TOOL_NAMES = (
        'get_project_hierarchy|get_object_properties|search_objects'
        '|get_bus_topology|get_event_actions|get_soundbank_info'
        '|get_rtpc_list|get_selected_objects|get_effect_chain'
        '|create_object|set_property|create_event|assign_bus'
        '|delete_object|move_object|preview_event'
        '|set_rtpc_binding|add_effect|remove_effect'
        '|verify_structure|verify_event_completeness|execute_waapi'
        '|web_search|fetch_webpage|add_todo|update_todo'
    )
    _FAKE_TOOL_PATTERNS = re.compile(
        r'^\[(?:ok|err)\]\s*(?:' + _ALL_TOOL_NAMES + r')\s*[:\uff1a]',
        re.MULTILINE | re.IGNORECASE,
    )

    @staticmethod
    def _split_and_compress_assistant(content: str, max_reply: int = 1500) -> str:
        if '[工具执行结果]' not in content and '[Tool Result]' not in content:
            return content[:max_reply] + ('...' if len(content) > max_reply else '')
        last_tool_line = max(content.rfind('\n[ok]'), content.rfind('\n[err]'))
        if last_tool_line <= 0:
            return content[:max_reply] + ('...' if len(content) > max_reply else '')
        next_nl = content.find('\n', last_tool_line + 1)
        if next_nl <= 0 or next_nl >= len(content) - 5:
            return content[:max_reply] + ('...' if len(content) > max_reply else '')
        tool_text = content[:next_nl]
        reply_text = content[next_nl:].strip()
        tool_lines = tool_text.strip().split('\n')
        if len(tool_lines) > 6:
            tool_text = '\n'.join(tool_lines[:1] + tool_lines[-4:]) + f'\n... {len(tool_lines)-1} calls'
        elif len(tool_text) > 500:
            tool_text = tool_text[:500] + '...'
        if reply_text:
            reply_text = reply_text[:max_reply] + ('...' if len(reply_text) > max_reply else '')
        return tool_text + '\n\n' + reply_text if reply_text else tool_text

    @staticmethod
    def _fix_message_alternation(messages: list) -> list:
        if not messages:
            return messages
        fixed = [messages[0]]
        for msg in messages[1:]:
            role = msg.get('role', '')
            prev_role = fixed[-1].get('role', '')
            if role == 'tool' or prev_role == 'tool':
                fixed.append(msg)
                continue
            if role == 'assistant' and msg.get('tool_calls'):
                fixed.append(msg)
                continue
            if prev_role == 'assistant' and fixed[-1].get('tool_calls'):
                fixed.append(msg)
                continue
            if role == prev_role and role in ('user', 'assistant'):
                prev_content = fixed[-1].get('content')
                curr_content = msg.get('content')
                prev_text = prev_content
                curr_text = curr_content
                if isinstance(prev_content, list):
                    prev_text = '\n'.join(
                        p.get('text', '') for p in prev_content if isinstance(p, dict) and p.get('type') == 'text'
                    ) or ''
                if isinstance(curr_content, list):
                    curr_text = '\n'.join(
                        p.get('text', '') for p in curr_content if isinstance(p, dict) and p.get('type') == 'text'
                    ) or ''
                prev_text = prev_text or ''
                curr_text = curr_text or ''
                fixed[-1] = fixed[-1].copy()
                if isinstance(prev_content, list) or isinstance(curr_content, list):
                    merged_parts = []
                    combined_text = (prev_text + '\n\n' + curr_text).strip()
                    if combined_text:
                        merged_parts.append({'type': 'text', 'text': combined_text})
                    for src in (prev_content, curr_content):
                        if isinstance(src, list):
                            for part in src:
                                if isinstance(part, dict) and part.get('type') == 'image_url':
                                    merged_parts.append(part)
                    fixed[-1]['content'] = merged_parts if merged_parts else combined_text
                else:
                    fixed[-1]['content'] = prev_text + '\n\n' + curr_text
                if 'thinking' in msg and msg['thinking']:
                    prev_thinking = fixed[-1].get('thinking', '')
                    fixed[-1]['thinking'] = (prev_thinking + '\n' + msg['thinking']).strip()
            else:
                fixed.append(msg)
        return fixed

    def _strip_fake_tool_results(self, text: str) -> str:
        if not text:
            return text
        if text.lstrip().startswith('[工具执行结果]') or text.lstrip().startswith('[Tool Result]'):
            lines = text.split('\n')
            real_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped in ('[工具执行结果]', '[Tool Result]'):
                    continue
                if self._FAKE_TOOL_PATTERNS.match(stripped):
                    continue
                real_lines.append(line)
            text = '\n'.join(real_lines).strip()
        lines = text.split('\n')
        cleaned = []
        for line in lines:
            if self._FAKE_TOOL_PATTERNS.match(line.strip()):
                continue
            cleaned.append(line)
        return '\n'.join(cleaned).strip()

    def _manage_context(self):
        history = self._agent_history if self._agent_history is not None else self._conversation_history
        if len(history) < 6:
            return
        current_tokens = self.token_optimizer.calculate_message_tokens(history)
        context_limit = self._get_current_context_limit()
        self.token_optimizer.budget.max_tokens = context_limit
        should_compress, reason = self.token_optimizer.should_compress(current_tokens, context_limit)
        if not (should_compress and self._auto_optimize):
            if reason and ('警告' in reason or 'warning' in reason.lower()):
                self._addStatus.emit(f"Note: {reason}")
            return
        old_tokens = current_tokens
        rounds = []
        current_round = []
        for m in history:
            if m.get('role') == 'user' and current_round:
                rounds.append(current_round)
                current_round = []
            current_round.append(m)
        if current_round:
            rounds.append(current_round)
        if len(rounds) <= 2:
            return
        n_rounds = len(rounds)
        protect_n = max(2, int(n_rounds * 0.6))
        for r_idx in range(n_rounds - protect_n):
            for m in rounds[r_idx]:
                if m.get('role') == 'tool':
                    c = m.get('content') or ''
                    if len(c) > 200:
                        m['content'] = self.client._summarize_tool_content(c, 200) if hasattr(self.client, '_summarize_tool_content') else c[:200] + '...[summary]'
        compressed = [m for rnd in rounds for m in rnd]
        new_tokens = self.token_optimizer.calculate_message_tokens(compressed)
        if new_tokens < context_limit * self.token_optimizer.budget.compression_threshold:
            history.clear()
            history.extend(compressed)
            saved = old_tokens - new_tokens
            if saved > 0:
                self._addStatus.emit(tr('opt.auto_status', saved))
            return
        target = int(context_limit * 0.65)
        while len(rounds) > 2:
            rounds.pop(0)
            compressed = [m for rnd in rounds for m in rnd]
            new_tokens = self.token_optimizer.calculate_message_tokens(compressed)
            if new_tokens <= target:
                break
        summary_note = {'role': 'system', 'content': tr('ai.old_rounds', n_rounds - len(rounds))}
        history.clear()
        history.append(summary_note)
        history.extend([m for rnd in rounds for m in rnd])
        saved = old_tokens - self.token_optimizer.calculate_message_tokens(history)
        if saved > 0:
            self._addStatus.emit(tr('opt.auto_status', saved))

    def _get_context_reminder(self) -> str:
        parts = []
        if self._context_summary:
            parts.append(f"[Context Cache] {self._context_summary}")
        todo_summary = self._get_todo_summary_safe()
        if todo_summary:
            if "0/" in todo_summary or "pending" in todo_summary.lower():
                parts.append(f"[TODO] {todo_summary.split(':', 1)[-1] if ':' in todo_summary else todo_summary}")
        if len(self._conversation_history) > 2:
            parts.append(f"[{len(self._conversation_history)} messages in context, reuse prior info]")
        return " | ".join(parts) if parts else ""

    def _get_todo_summary_safe(self) -> str:
        todo = self._agent_todo_list or self.todo_list
        try:
            return todo.get_todos_summary() if todo else ""
        except Exception:
            return ""

    # ===== URL 识别 =====
    
    def _extract_urls(self, text: str) -> list:
        url_pattern = r'https?://[^\s<>"\'`\]\)]+[^\s<>"\'`\]\)\.,;:!?]'
        return re.findall(url_pattern, text)
    
    def _process_urls_in_text(self, text: str) -> str:
        urls = self._extract_urls(text)
        if not urls:
            return text
        url_list = "\n".join(f"  - {url}" for url in urls)
        hint = tr('ai.detected_url', url_list)
        return text + hint

    # ===== 事件处理 =====
    
    def _on_send(self):
        text = self.input_edit.toPlainText().strip()
        if not text or self._agent_session_id is not None:
            return

        provider = self._current_provider()
        if not self.client.has_api_key(provider):
            self._on_set_key()
            return

        has_images = bool(self._pending_images) and self._current_model_supports_vision()
        pending_imgs = [img for img in self._pending_images if img is not None] if has_images else []

        self._add_user_message(text, images=pending_imgs)
        self.input_edit.clear()
        self._clear_pending_images()
        self._auto_rename_tab(text)
        
        processed_text = self._process_urls_in_text(text)
        
        if pending_imgs:
            msg_content = self._build_multimodal_content(processed_text, pending_imgs)
            self._conversation_history.append({'role': 'user', 'content': msg_content})
        else:
            self._conversation_history.append({'role': 'user', 'content': processed_text})
        
        self._update_context_stats()
        self._set_running(True)
        self._add_ai_response()
        self._agent_response = self._current_response
        self._start_active_aurora()
        
        agent_params = {
            'provider': self._current_provider(),
            'model': self.model_combo.currentText(),
            'use_web': self.web_check.isChecked(),
            'use_agent': self._agent_mode,
            'use_think': self.think_check.isChecked(),
            'context_limit': self._get_current_context_limit(),
            'supports_vision': self._current_model_supports_vision(),
            'scene_context': self._collect_scene_context(),  # ★ 主线程收集 Wwise 场景上下文
        }
        
        self._save_model_preference()
        
        thread = threading.Thread(target=self._run_agent, args=(agent_params,), daemon=True)
        thread.start()

    def _run_agent(self, agent_params: dict):
        provider = agent_params['provider']
        model = agent_params['model']
        use_web = agent_params['use_web']
        use_agent = agent_params['use_agent']
        use_think = agent_params.get('use_think', True)
        context_limit = agent_params['context_limit']
        supports_vision = agent_params.get('supports_vision', True)
        scene_context = agent_params.get('scene_context', {})
        
        self._last_agent_params = agent_params
        self._think_enabled = use_think
        
        try:
            sys_prompt = self._cached_prompt_think if use_think else self._cached_prompt_no_think
            
            if not use_agent:
                sys_prompt = sys_prompt + tr('ai.ask_mode_prompt')
            
            messages = [{'role': 'system', 'content': sys_prompt}]
            
            _INTERNAL_FIELDS = frozenset({
                '_reply_content', '_tool_summary', 'thinking', 'system_shells',
            })
            
            _last_user_idx = None
            for _i in range(len(self._conversation_history) - 1, -1, -1):
                if self._conversation_history[_i].get('role') == 'user':
                    _last_user_idx = _i
                    break
            
            history_to_send = []
            for msg_idx, msg in enumerate(self._conversation_history):
                role = msg.get('role', '')
                
                if role == 'tool':
                    if msg.get('tool_call_id'):
                        clean = {k: v for k, v in msg.items() if k not in _INTERNAL_FIELDS}
                        history_to_send.append(clean)
                    else:
                        tool_name = msg.get('name', 'unknown')
                        content = msg.get('content', '')
                        history_to_send.append({
                            'role': 'assistant',
                            'content': tr('ai.tool_result', tool_name, content[:500])
                        })
                elif role == 'assistant':
                    clean = {k: v for k, v in msg.items() if k not in _INTERNAL_FIELDS}
                    history_to_send.append(clean)
                elif role == 'user':
                    content = msg.get('content')
                    is_current_round = (msg_idx == _last_user_idx)
                    if isinstance(content, list):
                        if is_current_round and supports_vision:
                            history_to_send.append(msg)
                        else:
                            text_parts = []
                            for part in content:
                                if isinstance(part, dict) and part.get('type') == 'text':
                                    text_parts.append(part.get('text', ''))
                            text_only = '\n'.join(t for t in text_parts if t)
                            history_to_send.append({'role': 'user', 'content': text_only or tr('ai.image_msg')})
                    else:
                        history_to_send.append(msg)
                elif role == 'system':
                    history_to_send.append(msg)
            
            history_to_send = self._fix_message_alternation(history_to_send)
            messages.extend(history_to_send)
            
            # 上下文提醒
            context_reminder = self._get_context_reminder()
            if context_reminder:
                messages.append({'role': 'system', 'content': f"[Context] {context_reminder}"})
            
            # 长期记忆激活
            try:
                user_query = ''
                for m in reversed(self._conversation_history):
                    if m.get('role') == 'user':
                        c = m.get('content', '')
                        user_query = c if isinstance(c, str) else ' '.join(
                            p.get('text', '') for p in c if isinstance(p, dict) and p.get('type') == 'text'
                        ) if isinstance(c, list) else ''
                        break
                if user_query:
                    memory_context = self._activate_long_term_memory(
                        user_query, scene_context=scene_context
                    )
                    if memory_context:
                        messages.append({'role': 'system', 'content': memory_context})
            except Exception as e:
                print(f"[Memory] Context injection failed: {e}")
            
            # 预发送压缩
            if self._auto_optimize:
                current_tokens = self.token_optimizer.calculate_message_tokens(messages)
                should_compress, _ = self.token_optimizer.should_compress(current_tokens, context_limit)
                if should_compress:
                    old_tokens = current_tokens
                    first_system = messages[0] if messages and messages[0].get('role') == 'system' else None
                    last_context = messages[-1] if messages and ('[Context]' in messages[-1].get('content', '')) else None
                    start_idx = 1 if first_system else 0
                    end_idx = -1 if last_context else len(messages)
                    body = messages[start_idx:end_idx] if end_idx != len(messages) else messages[start_idx:]
                    
                    rounds = []
                    cur_rnd = []
                    for m in body:
                        if m.get('role') == 'user' and cur_rnd:
                            rounds.append(cur_rnd)
                            cur_rnd = []
                        cur_rnd.append(m)
                    if cur_rnd:
                        rounds.append(cur_rnd)
                    
                    n_rounds = len(rounds)
                    protect_n = max(2, int(n_rounds * 0.6))
                    for r_idx in range(n_rounds - protect_n):
                        for m in rounds[r_idx]:
                            if m.get('role') == 'tool':
                                c = m.get('content') or ''
                                if len(c) > 200:
                                    m['content'] = c[:200] + '...[summary]'
                    
                    target = int(context_limit * 0.7)
                    while len(rounds) > 2:
                        test_body = [m for rnd in rounds for m in rnd]
                        test_msgs = ([first_system] if first_system else []) + test_body + ([last_context] if last_context else [])
                        if self.token_optimizer.calculate_message_tokens(test_msgs) <= target:
                            break
                        rounds.pop(0)
                    
                    compressed_body = [m for rnd in rounds for m in rnd]
                    messages = []
                    if first_system:
                        messages.append(first_system)
                    if n_rounds - len(rounds) > 0:
                        messages.append({'role': 'system', 'content': tr('ai.old_rounds', n_rounds - len(rounds))})
                    messages.extend(compressed_body)
                    if last_context:
                        messages.append(last_context)
                    
                    new_tokens = self.token_optimizer.calculate_message_tokens(messages)
                    saved = old_tokens - new_tokens
                    if saved > 0:
                        self._addStatus.emit(tr('opt.auto_status', saved))
            
            self._addStatus.emit(f"Requesting {provider}/{model}...")
            
            # 推理模型兼容
            is_reasoning_model = AIClient.is_reasoning_model(model)
            cleaned_messages = []
            for msg in messages:
                role = msg.get('role', 'user')
                content = msg.get('content')
                has_tool_calls = 'tool_calls' in msg
                clean_msg = {'role': role}
                if role == 'assistant' and has_tool_calls:
                    clean_msg['content'] = content
                else:
                    clean_msg['content'] = content if content is not None else ''
                if is_reasoning_model and role == 'assistant':
                    clean_msg['reasoning_content'] = msg.get('reasoning_content', '')
                if has_tool_calls:
                    clean_msg['tool_calls'] = msg['tool_calls']
                if 'tool_call_id' in msg:
                    clean_msg['tool_call_id'] = msg['tool_call_id']
                if 'name' in msg:
                    clean_msg['name'] = msg['name']
                if role == 'assistant' and clean_msg.get('content'):
                    c = clean_msg['content']
                    if '<think>' in c:
                        c = re.sub(r'<think>[\s\S]*?</think>', '', c).strip()
                        clean_msg['content'] = c or None
                cleaned_messages.append(clean_msg)
            messages = cleaned_messages
            
            # 工具定义
            if not use_agent:
                ask_filtered = [t for t in WWISE_TOOLS
                                if t['function']['name'] in self._ASK_MODE_TOOLS]
                if not use_web:
                    ask_filtered = [t for t in ask_filtered
                                    if t['function']['name'] not in ('web_search', 'fetch_webpage')]
                tools = ask_filtered
            elif use_web:
                if self._cached_optimized_tools is None:
                    self._cached_optimized_tools = WWISE_TOOLS
                tools = self._cached_optimized_tools
            else:
                if self._cached_optimized_tools_no_web is None:
                    self._cached_optimized_tools_no_web = [
                        t for t in WWISE_TOOLS if t['function']['name'] not in ('web_search', 'fetch_webpage')
                    ]
                tools = self._cached_optimized_tools_no_web
            
            _on_iter = lambda i: self._showGenerating.emit()
            
            # 保存 agent 参数供反思钩子使用
            self._last_agent_params = agent_params
            
            if use_agent:
                result = self.client.agent_loop_auto(
                    messages=messages,
                    model=model,
                    provider=provider,
                    max_iterations=999,
                    max_tokens=None,
                    enable_thinking=use_think,
                    supports_vision=supports_vision,
                    tools_override=tools,
                    on_content=lambda c: self._on_content_with_limit(c),
                    on_thinking=lambda t: self._on_thinking_chunk(t),
                    on_tool_call=lambda n, a: (
                        (self._addStatus.emit(f"[tool]{n}"), self._showToolStatus.emit(n))
                        if n not in self._SILENT_TOOLS else None
                    ),
                    on_tool_result=lambda n, a, r: (
                        (self._add_tool_result(n, r, a), self._hideToolStatus.emit())
                        if n not in self._SILENT_TOOLS else None
                    ),
                    on_iteration_start=_on_iter,
                )
            elif tools:
                result = self.client.agent_loop_auto(
                    messages=messages,
                    model=model,
                    provider=provider,
                    max_iterations=15,
                    max_tokens=None,
                    enable_thinking=use_think,
                    supports_vision=supports_vision,
                    tools_override=tools,
                    on_content=lambda c: self._on_content_with_limit(c),
                    on_thinking=lambda t: self._on_thinking_chunk(t),
                    on_tool_call=lambda n, a: (
                        (self._addStatus.emit(f"[tool]{n}"), self._showToolStatus.emit(n))
                        if n not in self._SILENT_TOOLS else None
                    ),
                    on_tool_result=lambda n, a, r: (
                        (self._add_tool_result(n, r, a), self._hideToolStatus.emit())
                        if n not in self._SILENT_TOOLS else None
                    ),
                    on_iteration_start=_on_iter,
                )
            else:
                self._showGenerating.emit()
                result = {'ok': True, 'content': '', 'tool_calls_history': [], 'iterations': 1, 'usage': {}}
                for chunk in self.client.chat_stream(
                    messages=messages, model=model, provider=provider, tools=None, max_tokens=None,
                ):
                    if self.client.is_stop_requested():
                        self._agentStopped.emit()
                        return
                    ctype = chunk.get('type')
                    if ctype == 'content':
                        content = chunk.get('content', '')
                        result['content'] += content
                        self._on_content_with_limit(content)
                    elif ctype == 'thinking':
                        self._on_thinking_chunk(chunk.get('content', ''))
                    elif ctype == 'done':
                        usage = chunk.get('usage', {})
                        if usage:
                            result['usage'] = usage
                    elif ctype == 'stopped':
                        self._agentStopped.emit()
                        return
                    elif ctype == 'error':
                        result = {'ok': False, 'error': chunk.get('error')}
                        break
            
            if self.client.is_stop_requested():
                self._agentStopped.emit()
                return
            
            if result.get('ok'):
                self._agentDone.emit(result)
            else:
                self._agentError.emit(f"API Error: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            import traceback
            if self.client.is_stop_requested():
                self._agentStopped.emit()
            else:
                error_detail = f"{type(e).__name__}: {str(e)}"
                print(f"[AI Tab Error] {traceback.format_exc()}")
                self._agentError.emit(error_detail)

    def _add_tool_result(self, name: str, result: dict, arguments: dict = None):
        """添加工具结果到执行流程"""
        result_text = str(result.get('result', result.get('error', '')))
        success = result.get('success', True)
        
        # execute_shell 专用展示
        if name == 'execute_shell' and arguments:
            command = arguments.get('command', '')
            if command:
                shell_data = {
                    'command': command,
                    'output': result.get('result', ''),
                    'error': result.get('error', ''),
                    'success': success,
                    'cwd': arguments.get('cwd', ''),
                }
                self._addSystemShell.emit(command, json.dumps(shell_data))
                short = f"[ok] $ {command[:40]}" if success else f"[err] {result_text[:50]}"
                invoke_on_main(self, "_add_tool_result_ui", name, short)
                return
        
        if self._agent_response or self._current_response:
            prefix = "[err]" if not success else "[ok]"
            invoke_on_main(self, "_add_tool_result_ui", name, f"{prefix} {result_text}")
    
    @QtCore.Slot(str, str)
    def _add_tool_result_ui(self, name: str, result: str):
        try:
            resp = self._agent_response or self._current_response
            if resp:
                resp.add_tool_result(name, result)
        except RuntimeError:
            pass

    @QtCore.Slot(str, str)
    def _on_add_system_shell(self, command: str, result_json: str):
        """处理系统 Shell 执行结果显示"""
        try:
            resp = self._agent_response or self._current_response
            if not resp:
                return
            data = json.loads(result_json) if result_json else {}
            output = data.get('output', '')
            error = data.get('error', '')
            success = data.get('success', True)
            prefix = "[ok]" if success else "[err]"
            display = f"{prefix} $ {command[:60]}"
            if output:
                display += f"\n{output[:200]}"
            if error:
                display += f"\n⚠ {error[:100]}"
            resp.add_tool_result('execute_shell', display)
        except RuntimeError:
            pass

    # ===== Wwise 事件处理 =====
    
    def _on_show_tool_status(self, tool_name: str):
        try:
            if hasattr(self, 'thinking_bar'):
                self.thinking_bar.show_tool(tool_name)
        except (RuntimeError, AttributeError):
            pass

    def _on_hide_tool_status(self):
        try:
            if hasattr(self, 'thinking_bar'):
                self.thinking_bar.stop()
        except (RuntimeError, AttributeError):
            pass

    def _on_show_generating(self):
        try:
            if hasattr(self, 'thinking_bar'):
                self.thinking_bar.show_generating()
        except (RuntimeError, AttributeError):
            pass

    # ===== 更新检查（占位） =====
    def _silent_update_check(self):
        pass

    # ===== 缓存菜单 =====
    def _on_cache_menu(self):
        pass

    # ===== 优化菜单 =====
    def _on_optimize_menu(self):
        pass

    # ===== 导出训练数据 =====
    def _on_export_training_data(self):
        pass

    # ===== 检查更新 =====
    def _on_check_update(self):
        pass

    # ==========================================================
    # 核心交互方法
    # ==========================================================

    def _on_stop(self):
        """停止当前 Agent 运行"""
        self.client.request_stop()

    def _on_set_key(self):
        """弹出 API Key 设置对话框"""
        provider = self._current_provider()
        names = {'openai': 'OpenAI', 'deepseek': 'DeepSeek', 'glm': 'GLM', 'ollama': 'Ollama'}

        key, ok = QtWidgets.QInputDialog.getText(
            self, f"Set {names.get(provider, provider)} API Key",
            "Enter API Key:",
            QtWidgets.QLineEdit.Password
        )

        if ok and key.strip():
            self.client.set_api_key(key.strip(), persist=True, provider=provider)
            self._update_key_status()

    def _on_clear(self):
        """清空当前会话"""
        # 如果当前 session 正在运行 agent，先停止
        if self._agent_session_id == self._session_id and self._agent_session_id is not None:
            self.client.request_stop()
            self._agent_response = None
            self._agent_todo_list = None
            self._agent_chat_layout = None
            self._agent_scroll_area = None
            self._set_running(False)

        self._conversation_history.clear()
        self._context_summary = ""
        self._current_response = None
        self._token_stats = {
            'input_tokens': 0, 'output_tokens': 0,
            'reasoning_tokens': 0,
            'cache_read': 0, 'cache_write': 0,
            'total_tokens': 0, 'requests': 0,
            'estimated_cost': 0.0,
        }
        self._call_records = []

        # 清理待确认操作列表和批量操作栏
        self._pending_ops.clear()
        self._batch_bar.setVisible(False)

        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 重建 todo_list
        self.todo_list = self._create_todo_list(self.chat_container)
        if self._session_id in self._sessions:
            self._sessions[self._session_id]['todo_list'] = self.todo_list

        self._save_current_session_state()

        # 删除磁盘上的旧 session 文件
        try:
            old_session_file = self._cache_dir / f"session_{self._session_id}.json"
            if old_session_file.exists():
                old_session_file.unlink()
        except Exception:
            pass
        try:
            self._update_manifest()
        except Exception:
            pass

        # 重置标签名
        for i in range(self.session_tabs.count()):
            if self.session_tabs.tabData(i) == self._session_id:
                self.session_tabs.setTabText(i, f"Chat {self._session_counter}")
                break

        self._update_token_stats_display()
        self._update_context_stats()

    # ==========================================================
    # 批量操作方法
    # ==========================================================

    def _update_batch_bar(self):
        """根据未决操作数量显示/隐藏批量操作栏"""
        self._pending_ops = [
            entry for entry in self._pending_ops
            if entry[0] and not getattr(entry[0], '_decided', True)
        ]
        count = len(self._pending_ops)
        if count > 0:
            self._batch_count_label.setText(f"{count} pending")
            self._batch_bar.setVisible(True)
        else:
            self._batch_bar.setVisible(False)

    def _undo_all_ops(self):
        """撤销所有未决操作"""
        self._pending_ops = [
            entry for entry in self._pending_ops
            if entry[0] and not getattr(entry[0], '_decided', True)
        ]
        if not self._pending_ops:
            self._batch_bar.setVisible(False)
            return

        count = 0
        for label, op_type, paths, snapshot in reversed(self._pending_ops):
            if getattr(label, '_decided', True):
                continue
            try:
                label._on_undo()
            except Exception:
                pass
            count += 1

        self._pending_ops.clear()
        self._batch_bar.setVisible(False)
        if count:
            self._show_toast(f"Undone {count} operations")

    def _keep_all_ops(self):
        """保留所有未决操作"""
        self._pending_ops = [
            entry for entry in self._pending_ops
            if entry[0] and not getattr(entry[0], '_decided', True)
        ]
        if not self._pending_ops:
            self._batch_bar.setVisible(False)
            return

        count = 0
        for label, op_type, paths, snapshot in self._pending_ops:
            if getattr(label, '_decided', True):
                continue
            try:
                label._on_keep()
                if hasattr(label, 'collapse_diff'):
                    label.collapse_diff()
            except Exception:
                pass
            count += 1

        self._pending_ops.clear()
        self._batch_bar.setVisible(False)
        if count:
            self._show_toast(f"Kept {count} operations")

    # ==========================================================
    # 图片功能
    # ==========================================================

    _MAX_IMAGE_DIMENSION = 2048
    _MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB

    def _current_model_supports_vision(self) -> bool:
        """检查当前选中的模型是否支持图片输入"""
        model = self.model_combo.currentText()
        features = self._model_features.get(model, {})
        return features.get('supports_vision', False)

    def _on_attach_image(self):
        """打开文件对话框选择图片"""
        if not self._current_model_supports_vision():
            model = self.model_combo.currentText()
            QtWidgets.QMessageBox.information(
                self, "Not Supported",
                f"Model {model} does not support image input.\nPlease switch to a vision model (e.g. Claude, GPT-5.2)."
            )
            return

        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Images", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All Files (*)"
        )
        for fp in file_paths:
            self._add_image_from_path(fp)

    def _on_image_dropped(self, image: 'QtGui.QImage'):
        """ChatInput 拖拽或粘贴图片的回调"""
        if not self._current_model_supports_vision():
            return
        import base64
        image = self._resize_image_if_needed(image, self._MAX_IMAGE_DIMENSION)
        buf = QtCore.QBuffer()
        buf.open(QtCore.QIODevice.WriteOnly)
        image.save(buf, "PNG")
        raw_bytes = buf.data().data()
        buf.close()
        if len(raw_bytes) > self._MAX_IMAGE_BYTES:
            buf2 = QtCore.QBuffer()
            buf2.open(QtCore.QIODevice.WriteOnly)
            image.save(buf2, "JPEG", 85)
            raw_bytes = buf2.data().data()
            buf2.close()
            media_type = 'image/jpeg'
        else:
            media_type = 'image/png'
        b64 = base64.b64encode(raw_bytes).decode('utf-8')
        self._add_pending_image(b64, media_type)

    def _add_image_from_path(self, file_path: str):
        """从文件路径加载图片并添加到待发送列表"""
        import base64
        try:
            image = QtGui.QImage(file_path)
            if image.isNull():
                return
            image = self._resize_image_if_needed(image, self._MAX_IMAGE_DIMENSION)
            buf = QtCore.QBuffer()
            buf.open(QtCore.QIODevice.WriteOnly)
            ext = Path(file_path).suffix.lower()
            if ext in ('.jpg', '.jpeg'):
                image.save(buf, "JPEG", 90)
                media_type = 'image/jpeg'
            else:
                image.save(buf, "PNG")
                media_type = 'image/png'
            raw_bytes = buf.data().data()
            buf.close()
            if len(raw_bytes) > self._MAX_IMAGE_BYTES:
                buf2 = QtCore.QBuffer()
                buf2.open(QtCore.QIODevice.WriteOnly)
                image.save(buf2, "JPEG", 80)
                raw_bytes = buf2.data().data()
                buf2.close()
                media_type = 'image/jpeg'
            b64 = base64.b64encode(raw_bytes).decode('utf-8')
            self._add_pending_image(b64, media_type)
        except Exception as e:
            print(f"[AI Tab] Failed to load image: {e}")

    def _add_pending_image(self, b64_data: str, media_type: str):
        """将 base64 图片数据添加到待发送列表并显示预览"""
        import base64
        try:
            raw = base64.b64decode(b64_data)
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(raw)
            thumbnail = pixmap.scaled(48, 48, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        except Exception:
            thumbnail = QtGui.QPixmap(48, 48)
            thumbnail.fill(QtGui.QColor(60, 60, 60))

        self._pending_images.append((b64_data, media_type, thumbnail))

        # 在预览区添加缩略图
        thumb_label = ClickableImageLabel(thumbnail, len(self._pending_images) - 1)
        thumb_label.clicked.connect(self._on_remove_pending_image)
        # 插入到 stretch 之前
        self.image_preview_layout.insertWidget(
            self.image_preview_layout.count() - 1, thumb_label
        )
        self.image_preview_container.setVisible(True)

    def _on_remove_pending_image(self, index: int):
        """移除指定索引的待发送图片"""
        if 0 <= index < len(self._pending_images):
            self._pending_images.pop(index)
            # 重建预览区
            while self.image_preview_layout.count() > 1:
                item = self.image_preview_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for i, (b64, mt, thumb) in enumerate(self._pending_images):
                lbl = ClickableImageLabel(thumb, i)
                lbl.clicked.connect(self._on_remove_pending_image)
                self.image_preview_layout.insertWidget(i, lbl)
            if not self._pending_images:
                self.image_preview_container.setVisible(False)

    def _clear_pending_images(self):
        """清空所有待发送图片"""
        self._pending_images.clear()
        while self.image_preview_layout.count() > 1:
            item = self.image_preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.image_preview_container.setVisible(False)

    def _build_multimodal_content(self, text: str, images: list) -> list:
        """构建包含文字和图片的多模态消息内容（OpenAI Vision API 格式）"""
        _SUPPORTED_MEDIA = {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}
        content_parts = []
        content_parts.append({"type": "text", "text": text or " "})
        for b64_data, media_type, _thumb in images:
            if not b64_data:
                continue
            if media_type not in _SUPPORTED_MEDIA:
                media_type = 'image/png'
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{media_type};base64,{b64_data}"
                }
            })
        return content_parts

    @staticmethod
    def _resize_image_if_needed(image: 'QtGui.QImage', max_dim: int) -> 'QtGui.QImage':
        """如果图片超过最大尺寸则按比例缩放"""
        w, h = image.width(), image.height()
        if w <= max_dim and h <= max_dim:
            return image
        if w > h:
            new_w = max_dim
            new_h = int(h * max_dim / w)
        else:
            new_h = max_dim
            new_w = int(w * max_dim / h)
        return image.scaled(new_w, new_h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

    # ==========================================================
    # 会话持久化
    # ==========================================================

    def _save_cache(self) -> bool:
        """自动保存：覆写同 session 文件 + manifest"""
        if not self._conversation_history:
            return False
        try:
            self._save_current_session_state()
            self._sync_tabs_backup()

            cache_data = self._build_cache_data()
            cache_data['conversation_history'] = self._strip_images_for_cache(
                cache_data.get('conversation_history', [])
            )

            session_file = self._cache_dir / f"session_{self._session_id}.json"
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            self._update_manifest()

            if self._workspace_dir:
                self._update_workspace_cache_info()
            return True
        except Exception as e:
            print(f"[Cache] Auto save failed: {e}")
            return False

    def _build_cache_data(self) -> dict:
        """构建当前会话的缓存数据"""
        todo_data = []
        try:
            if hasattr(self, 'todo_list') and self.todo_list:
                todo_data = self.todo_list.get_todos_data()
        except (RuntimeError, AttributeError):
            pass

        return {
            'version': '1.0',
            'session_id': self._session_id,
            'created_at': datetime.now().isoformat(),
            'message_count': len(self._conversation_history),
            'conversation_history': list(self._conversation_history),
            'context_summary': self._context_summary,
            'todo_data': todo_data,
            'token_stats': dict(self._token_stats),
        }

    def _update_manifest(self):
        """更新 sessions_manifest.json"""
        try:
            manifest_tabs = []
            for i in range(self.session_tabs.count()):
                sid = self.session_tabs.tabData(i)
                tab_label = self.session_tabs.tabText(i)
                if not sid or sid not in self._sessions:
                    continue
                sdata = self._sessions[sid]
                if not sdata.get('conversation_history'):
                    continue
                session_file = self._cache_dir / f"session_{sid}.json"
                if not session_file.exists():
                    continue
                manifest_tabs.append({
                    'session_id': sid,
                    'tab_label': tab_label,
                    'file': f"session_{sid}.json",
                })
            if manifest_tabs:
                manifest = {
                    'version': '1.0',
                    'active_session_id': self._session_id,
                    'tabs': manifest_tabs,
                }
                manifest_file = self._cache_dir / "sessions_manifest.json"
                with open(manifest_file, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Cache] Update manifest failed: {e}")

    def _update_workspace_cache_info(self):
        """更新工作区缓存信息"""
        try:
            if not self._workspace_dir:
                return
            workspace_file = self._workspace_dir / "workspace.json"
            if workspace_file.exists():
                with open(workspace_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data.setdefault('cache_info', {})
                data['cache_info']['has_conversation'] = True
                data['cache_info']['tab_count'] = self.session_tabs.count()
                with open(workspace_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _strip_images_for_cache(history: list) -> list:
        """剥离对话历史中的 base64 图片数据以减小缓存大小"""
        stripped = []
        for msg in history:
            content = msg.get('content')
            if isinstance(content, list):
                new_parts = []
                for part in content:
                    if part.get('type') == 'image_url':
                        new_parts.append({
                            'type': 'text',
                            'text': '[image removed for cache]'
                        })
                    else:
                        new_parts.append(part)
                stripped.append({**msg, 'content': new_parts})
            else:
                stripped.append(msg)
        return stripped

    def _save_all_sessions(self) -> bool:
        """保存所有打开的会话到磁盘"""
        try:
            self._save_current_session_state()
            self._sync_tabs_backup()

            manifest_tabs = []
            active_session_id = self._session_id

            for i in range(self.session_tabs.count()):
                sid = self.session_tabs.tabData(i)
                tab_label = self.session_tabs.tabText(i)
                if not sid or sid not in self._sessions:
                    continue

                sdata = self._sessions[sid]
                history = sdata.get('conversation_history', [])
                if not history:
                    try:
                        old_file = self._cache_dir / f"session_{sid}.json"
                        if old_file.exists():
                            old_file.unlink()
                    except Exception:
                        pass
                    continue

                todo_data = []
                try:
                    todo_list_obj = sdata.get('todo_list')
                    todo_data = todo_list_obj.get_todos_data() if todo_list_obj else []
                except (RuntimeError, AttributeError):
                    pass

                cache_data = {
                    'version': '1.0',
                    'session_id': sid,
                    'created_at': datetime.now().isoformat(),
                    'message_count': len(history),
                    'conversation_history': self._strip_images_for_cache(history),
                    'context_summary': sdata.get('context_summary', ''),
                    'todo_data': todo_data,
                    'token_stats': sdata.get('token_stats', {}),
                }
                session_file = self._cache_dir / f"session_{sid}.json"
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, ensure_ascii=False, indent=2)

                manifest_tabs.append({
                    'session_id': sid,
                    'tab_label': tab_label,
                    'file': f"session_{sid}.json",
                })

            if not manifest_tabs:
                return False

            manifest = {
                'version': '1.0',
                'active_session_id': active_session_id,
                'tabs': manifest_tabs,
            }
            manifest_file = self._cache_dir / "sessions_manifest.json"
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[Cache] Save all sessions failed: {e}")
            return False

    def _restore_all_sessions(self) -> bool:
        """从 sessions_manifest.json 恢复所有会话标签（启动时调用，幂等）"""
        if getattr(self, '_sessions_restored', False):
            return True
        try:
            manifest_file = self._cache_dir / "sessions_manifest.json"
            if not manifest_file.exists():
                return False

            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest = json.load(f)

            tabs_info = manifest.get('tabs', [])
            if not tabs_info:
                return False

            active_sid = manifest.get('active_session_id', '')
            active_tab_index = 0
            first_tab = True

            for tab_info in tabs_info:
                sid = tab_info.get('session_id', '')
                tab_label = tab_info.get('tab_label', 'Chat')
                session_file = self._cache_dir / tab_info.get('file', '')

                if not session_file.exists():
                    continue

                with open(session_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                history = cache_data.get('conversation_history', [])
                if not history:
                    continue

                context_summary = cache_data.get('context_summary', '')
                todo_data = cache_data.get('todo_data', [])
                saved_token_stats = cache_data.get('token_stats', {
                    'input_tokens': 0, 'output_tokens': 0,
                    'reasoning_tokens': 0,
                    'cache_read': 0, 'cache_write': 0,
                    'total_tokens': 0, 'requests': 0,
                    'estimated_cost': 0.0,
                })

                if first_tab:
                    first_tab = False
                    old_id = self._session_id

                    self._session_id = sid
                    self._conversation_history = history
                    self._context_summary = context_summary
                    self._token_stats = saved_token_stats

                    if old_id in self._sessions:
                        sdata = self._sessions.pop(old_id)
                        sdata['conversation_history'] = history
                        sdata['context_summary'] = context_summary
                        sdata['token_stats'] = saved_token_stats
                        self._sessions[sid] = sdata
                    elif sid not in self._sessions:
                        self._sessions[sid] = {
                            'scroll_area': self.scroll_area,
                            'chat_container': self.chat_container,
                            'chat_layout': self.chat_layout,
                            'todo_list': self.todo_list,
                            'conversation_history': history,
                            'context_summary': context_summary,
                            'current_response': None,
                            'token_stats': saved_token_stats,
                        }

                    if todo_data and hasattr(self, 'todo_list') and self.todo_list:
                        self.todo_list.restore_todos(todo_data)
                        self._ensure_todo_in_chat(self.todo_list, self.chat_layout)

                    for i in range(self.session_tabs.count()):
                        if self.session_tabs.tabData(i) == old_id:
                            self.session_tabs.setTabData(i, sid)
                            self.session_tabs.setTabText(i, tab_label)
                            if sid == active_sid:
                                active_tab_index = i
                            break

                    self._render_conversation_history()
                else:
                    self._save_current_session_state()
                    self._session_counter += 1

                    scroll_area, chat_container, chat_layout = self._create_session_widgets()
                    self.session_stack.addWidget(scroll_area)

                    tab_index = self.session_tabs.addTab(tab_label)
                    self.session_tabs.setTabData(tab_index, sid)

                    todo = self._create_todo_list(chat_container)
                    if todo_data:
                        todo.restore_todos(todo_data)
                        self._ensure_todo_in_chat(todo, chat_layout)

                    self._sessions[sid] = {
                        'scroll_area': scroll_area,
                        'chat_container': chat_container,
                        'chat_layout': chat_layout,
                        'todo_list': todo,
                        'conversation_history': history,
                        'context_summary': context_summary,
                        'current_response': None,
                        'token_stats': saved_token_stats,
                    }

                    # 临时切换到该标签以渲染历史
                    old_scroll = self.scroll_area
                    old_chat_container = self.chat_container
                    old_chat_layout = self.chat_layout
                    old_todo = self.todo_list
                    old_history = self._conversation_history
                    old_summary = self._context_summary
                    old_stats = self._token_stats
                    old_sid = self._session_id

                    self._session_id = sid
                    self._conversation_history = history
                    self._context_summary = context_summary
                    self._token_stats = saved_token_stats
                    self.scroll_area = scroll_area
                    self.chat_container = chat_container
                    self.chat_layout = chat_layout
                    self.todo_list = todo

                    self._render_conversation_history()

                    # 恢复
                    self._session_id = old_sid
                    self._conversation_history = old_history
                    self._context_summary = old_summary
                    self._token_stats = old_stats
                    self.scroll_area = old_scroll
                    self.chat_container = old_chat_container
                    self.chat_layout = old_chat_layout
                    self.todo_list = old_todo

                    if sid == active_sid:
                        active_tab_index = tab_index

            if self.session_tabs.count() > 0:
                self.session_tabs.blockSignals(True)
                self.session_tabs.setCurrentIndex(active_tab_index)
                self.session_tabs.blockSignals(False)

                target_sid = self.session_tabs.tabData(active_tab_index)
                if target_sid and target_sid in self._sessions:
                    self._load_session_state(target_sid)
                    self.session_stack.setCurrentWidget(
                        self._sessions[target_sid]['scroll_area']
                    )

            self._sync_tabs_backup()
            self._update_token_stats_display()
            self._update_context_stats()
            self._sessions_restored = True
            print(f"[Cache] Restored {self.session_tabs.count()} session tabs")
            return True

        except Exception as e:
            print(f"[Cache] Restore sessions failed: {e}")
            import traceback; traceback.print_exc()
            return False

    def _render_conversation_history(self):
        """从对话历史重建 chat UI（用于恢复会话）"""
        for msg in self._conversation_history:
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role == 'user':
                text = content if isinstance(content, str) else ''
                if isinstance(content, list):
                    text = ' '.join(
                        p.get('text', '') for p in content if p.get('type') == 'text'
                    )
                self._add_user_message(text)
            elif role == 'assistant':
                text = content if isinstance(content, str) else str(content)
                resp = self._add_ai_response()
                if resp:
                    resp.append_markdown(text)
                    resp.finalize()

    def _periodic_save_all(self):
        """定期保存所有会话"""
        try:
            if not self._sessions:
                return
            has_any = any(
                sdata.get('conversation_history')
                for sdata in self._sessions.values()
            )
            if not has_any:
                return
            self._save_all_sessions()
        except Exception as e:
            print(f"[Cache] Periodic save failed: {e}")

    def _atexit_save(self):
        """Python 退出时的最后保存机会（atexit 回调）"""
        try:
            if not hasattr(self, '_sessions') or not self._sessions:
                return
            try:
                self._save_current_session_state()
            except (RuntimeError, AttributeError):
                pass

            tabs_info = getattr(self, '_tabs_backup', [])
            if not tabs_info:
                tabs_info = [(sid, "Chat") for sid in self._sessions]

            manifest_tabs = []
            for sid, tab_label in tabs_info:
                if not sid or sid not in self._sessions:
                    continue
                sdata = self._sessions[sid]
                history = sdata.get('conversation_history', [])
                if not history:
                    continue
                todo_data = []
                try:
                    todo_list_obj = sdata.get('todo_list')
                    todo_data = todo_list_obj.get_todos_data() if todo_list_obj else []
                except (RuntimeError, AttributeError, Exception):
                    pass
                cache_data = {
                    'version': '1.0',
                    'session_id': sid,
                    'message_count': len(history),
                    'conversation_history': self._strip_images_for_cache(history),
                    'context_summary': sdata.get('context_summary', ''),
                    'todo_data': todo_data,
                    'token_stats': sdata.get('token_stats', {}),
                }
                session_file = self._cache_dir / f"session_{sid}.json"
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, ensure_ascii=False)
                manifest_tabs.append({
                    'session_id': sid,
                    'tab_label': tab_label,
                    'file': f"session_{sid}.json",
                })
            if manifest_tabs:
                manifest = {
                    'version': '1.0',
                    'active_session_id': self._session_id,
                    'tabs': manifest_tabs,
                }
                manifest_file = self._cache_dir / "sessions_manifest.json"
                with open(manifest_file, 'w', encoding='utf-8') as f:
                    json.dump(manifest, f, ensure_ascii=False)
        except Exception:
            pass
        
        # 退出时关闭记忆存储
        try:
            if hasattr(self, '_memory_store') and self._memory_store:
                self._memory_store.close()
        except Exception:
            pass

    def _load_cache_silent(self, cache_file: Path) -> bool:
        """静默加载缓存（用于工作区自动恢复）"""
        return self._load_cache(cache_file, silent=True)

    def _load_cache(self, cache_file: Path, silent: bool = False) -> bool:
        """从缓存文件加载对话历史"""
        try:
            if not cache_file.exists():
                return False
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            history = cache_data.get('conversation_history', [])
            if not history:
                return False

            self._conversation_history = history
            self._context_summary = cache_data.get('context_summary', '')
            self._token_stats = cache_data.get('token_stats', self._token_stats)

            todo_data = cache_data.get('todo_data', [])
            if todo_data and hasattr(self, 'todo_list') and self.todo_list:
                self.todo_list.restore_todos(todo_data)

            self._render_conversation_history()
            self._save_current_session_state()
            self._update_token_stats_display()
            self._update_context_stats()

            if not silent:
                self._show_toast(f"Loaded {len(history)} messages")
            return True
        except Exception as e:
            print(f"[Cache] Load failed: {e}")
            return False
