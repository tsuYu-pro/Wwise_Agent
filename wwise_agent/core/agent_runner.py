# -*- coding: utf-8 -*-
"""
Agent Runner — Agent 循环辅助：标题生成、确认模式、工具调度常量

从 ai_tab.py 中拆分出的 Mixin，负责：
- 自动 AI 标题生成
- 确认模式拦截
- 工具分类常量（Ask 模式白名单、后台安全工具、静默工具）
"""

import threading
import queue
from wwise_agent.qt_compat import QtWidgets, QtCore
from ..ui.i18n import tr, get_language
from ..ui.cursor_widgets import WwisePreviewInline


class AgentRunnerMixin:
    """Agent 循环辅助、工具调度常量"""

    # 需要用户确认的工具（确认模式下）
    _CONFIRM_TOOLS = frozenset({
        # 创建
        'create_object',
        'create_event',
        # 删除 / 修改
        'delete_object',
        'set_property',
        'assign_bus',
        'move_object',
        # RTPC / Effect
        'set_rtpc_binding',
        'add_effect',
        'remove_effect',
        # 原始 WAAPI（兜底）
        'execute_waapi',
    })

    # 不需要 Wwise 主线程的工具集合
    # 注意: Wwise 通过 WAAPI WebSocket 通信，所有工具均可在后台线程直接执行
    _BG_SAFE_TOOLS = frozenset({
        # 所有 Wwise 工具（WAAPI 是 WebSocket，无主线程约束）
        'get_project_hierarchy',
        'get_object_properties',
        'search_objects',
        'get_bus_topology',
        'get_event_actions',
        'get_soundbank_info',
        'get_rtpc_list',
        'get_selected_objects',
        'get_effect_chain',
        'create_object',
        'set_property',
        'create_event',
        'assign_bus',
        'delete_object',
        'move_object',
        'preview_event',
        'set_rtpc_binding',
        'add_effect',
        'remove_effect',
        'verify_structure',
        'verify_event_completeness',
        'execute_waapi',
        # 系统工具
        'web_search',
        'fetch_webpage',
    })

    # 静默工具：不在执行列表 UI 中显示（AI 自行调用，用户无需感知）
    _SILENT_TOOLS = frozenset({
        'add_todo',
        'update_todo',
    })

    # ★ Ask 模式白名单：只读 / 查询 / 分析工具（不包含任何修改项目的操作）
    _ASK_MODE_TOOLS = frozenset({
        # 查询 (9)
        'get_project_hierarchy',
        'get_object_properties',
        'search_objects',
        'get_bus_topology',
        'get_event_actions',
        'get_soundbank_info',
        'get_rtpc_list',
        'get_selected_objects',
        'get_effect_chain',
        # 验证 (2)
        'verify_structure',
        'verify_event_completeness',
        # 联网搜索
        'web_search',
        'fetch_webpage',
        # 任务管理
        'add_todo',
        'update_todo',
    })

    # ---------- 自动 AI 标题生成 ----------

    def _maybe_generate_title(self, session_id: str, history: list):
        """在 agent 完成后异步生成会话标题（仅首次）"""
        if not session_id:
            return
        sdata = self._sessions.get(session_id)
        if not sdata:
            return
        if sdata.get('_ai_title_generated'):
            return

        user_msgs = [m for m in history if m.get('role') == 'user']
        if not user_msgs:
            return

        first_user = ''
        first_assistant = ''
        for m in history:
            if m.get('role') == 'user' and not first_user:
                c = m.get('content', '')
                first_user = c if isinstance(c, str) else str(c)
            elif m.get('role') == 'assistant' and not first_assistant:
                c = m.get('content', '')
                first_assistant = c if isinstance(c, str) else str(c)
            if first_user and first_assistant:
                break

        sdata['_ai_title_generated'] = True

        def _gen():
            try:
                title = self._generate_short_title(first_user, first_assistant)
                if title:
                    self._autoTitleDone.emit(session_id, title)
            except Exception:
                pass

        t = threading.Thread(target=_gen, daemon=True)
        t.start()

    def _generate_short_title(self, user_msg: str, assistant_msg: str) -> str:
        """调用 LLM 生成 ≤10 字的对话标题"""
        ctx = tr('title_gen.ctx', user_msg[:200], assistant_msg[:200])
        sys_key = 'title_gen.system_zh' if get_language() == 'zh' else 'title_gen.system_en'
        messages = [
            {'role': 'system', 'content': tr(sys_key)},
            {'role': 'user', 'content': ctx}
        ]
        try:
            result = ''
            for chunk in self.client.chat_stream(messages):
                delta = chunk.get('content', '')
                if delta:
                    result += delta
            title = result.strip().strip('"\'""''。，.').strip()
            if title and len(title) <= 20:
                return title
            return title[:10] if title else ''
        except Exception:
            return ''

    @QtCore.Slot(str, str)
    def _on_auto_title_done(self, session_id: str, title: str):
        """AI 标题生成完成 — 更新 tab 标签"""
        if not title:
            return
        for i in range(self.session_tabs.count()):
            if self.session_tabs.tabData(i) == session_id:
                self.session_tabs.setTabText(i, title)
                break

    # ---------- 确认模式 — 内联预览确认 ----------

    @QtCore.Slot()
    def _on_confirm_tool_request(self):
        """主线程：在对话流中插入内联预览卡片，用户确认/取消后写入 _confirm_result_queue。"""
        q = getattr(self, '_confirm_result_queue', None)
        tool_name = getattr(self, '_pending_confirm_tool', 'unknown')
        args = getattr(self, '_pending_confirm_args', {})

        if not q:
            print(f"[ConfirmMode] ⚠ _confirm_result_queue 不存在")
            return

        if not isinstance(args, dict):
            args = {"raw": str(args)}

        try:
            preview = WwisePreviewInline(tool_name, args, parent=self)
        except Exception as e:
            print(f"[ConfirmMode] ✖ WwisePreviewInline 创建失败: {e}")
            q.put(False)
            return

        def _accept():
            q.put(True)

        def _reject():
            q.put(False)

        preview.confirmed.connect(_accept)
        preview.cancelled.connect(_reject)

        # 插入到对话流
        resp = getattr(self, '_agent_response', None) or getattr(self, '_current_response', None)
        inserted = False
        if resp and hasattr(resp, 'details_layout'):
            try:
                resp.details_layout.addWidget(preview)
                inserted = True
            except Exception as e:
                print(f"[ConfirmMode] ⚠ details_layout 插入失败: {e}")

        if not inserted:
            try:
                self.chat_layout.insertWidget(self.chat_layout.count() - 1, preview)
                inserted = True
            except Exception as e:
                print(f"[ConfirmMode] ⚠ chat_layout 插入失败: {e}")

        if not inserted:
            print("[ConfirmMode] ⚠ 所有布局插入失败，使用独立弹窗")
            preview.setParent(None)
            preview.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)
            preview.resize(400, 120)
            preview.show()

        preview.setVisible(True)
        try:
            self._scroll_to_bottom(force=True)
        except Exception:
            pass

    def _request_tool_confirmation(self, tool_name: str, kwargs: dict) -> bool:
        """在确认模式下，在对话中插入内联预览让用户确认或取消。"""
        self._confirm_result_queue = queue.Queue()
        self._pending_confirm_tool = tool_name
        self._pending_confirm_args = dict(kwargs) if kwargs else {}
        self._confirmToolRequest.emit()
        try:
            return self._confirm_result_queue.get(timeout=120.0)
        except queue.Empty:
            return False
