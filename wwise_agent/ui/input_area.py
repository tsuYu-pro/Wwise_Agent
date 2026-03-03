# -*- coding: utf-8 -*-
"""
Input Area UI 构建 — 输入区域和模式切换

从 ai_tab.py 中拆分出的 Mixin，所有方法通过 self 访问 AITab 实例状态。
样式由全局 style_template.qss 通过 objectName 选择器控制。

Wwise 版本：移除了 Houdini 特有的 @ 节点补全和 VEX 预览，
简化为 Agent/Ask 两种模式（无 Plan 模式）。
"""

from wwise_agent.qt_compat import QtWidgets, QtCore
from .i18n import tr
from .cursor_widgets import (
    CursorTheme,
    ChatInput,
    SendButton,
    StopButton,
    UnifiedStatusBar,
)


class InputAreaMixin:
    """输入区域构建、模式切换"""

    def _build_input_area(self) -> QtWidgets.QWidget:
        """输入区域 — 紧凑现代布局：
        
        ┌─ batch bar (hidden) ──────────────────────────────┐
        │ unified status bar (hidden)                        │
        │ image preview (hidden)                             │
        │ [+] Agent  Cfm           1.1M | $16   61% 122K/200K│  ← toolbar
        │ ┌──────────────────────────────────┐ ┌────┐┌────┐ │
        │ │ input text area                  │ │Stop││Send│ │  ← input row
        │ └──────────────────────────────────┘ └────┘└────┘ │
        └───────────────────────────────────────────────────┘
        """
        container = QtWidgets.QFrame()
        container.setObjectName("inputArea")
        
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(8, 3, 8, 5)
        layout.setSpacing(2)
        
        # -------- Undo All / Keep All 批量操作栏（默认隐藏）--------
        self._batch_bar = QtWidgets.QFrame()
        self._batch_bar.setObjectName("batchBar")
        self._batch_bar.setVisible(False)
        batch_layout = QtWidgets.QHBoxLayout(self._batch_bar)
        batch_layout.setContentsMargins(8, 3, 8, 3)
        batch_layout.setSpacing(6)
        
        self._batch_count_label = QtWidgets.QLabel("")
        self._batch_count_label.setObjectName("batchCountLabel")
        batch_layout.addWidget(self._batch_count_label)
        batch_layout.addStretch()
        
        self._btn_undo_all = QtWidgets.QPushButton("Undo All")
        self._btn_undo_all.setObjectName("btnUndoAll")
        self._btn_undo_all.setCursor(QtCore.Qt.PointingHandCursor)
        self._btn_undo_all.clicked.connect(self._undo_all_ops)
        batch_layout.addWidget(self._btn_undo_all)
        
        self._btn_keep_all = QtWidgets.QPushButton("Keep All")
        self._btn_keep_all.setObjectName("btnKeepAll")
        self._btn_keep_all.setCursor(QtCore.Qt.PointingHandCursor)
        self._btn_keep_all.clicked.connect(self._keep_all_ops)
        batch_layout.addWidget(self._btn_keep_all)
        
        layout.addWidget(self._batch_bar)
        
        # -------- 统一状态栏（合并 ThinkingBar + ToolStatusBar）--------
        self.thinking_bar = UnifiedStatusBar()
        self.tool_status_bar = self.thinking_bar  # 兼容别名
        layout.addWidget(self.thinking_bar)
        
        # 图片附件预览区（输入框上方，默认隐藏）
        self._pending_images = []  # List[Tuple[str, str, QPixmap]]
        self.image_preview_container = QtWidgets.QWidget()
        self.image_preview_container.setVisible(False)
        self.image_preview_layout = QtWidgets.QHBoxLayout(self.image_preview_container)
        self.image_preview_layout.setContentsMargins(4, 2, 4, 2)
        self.image_preview_layout.setSpacing(4)
        self.image_preview_layout.addStretch()
        layout.addWidget(self.image_preview_container)
        
        # -------- 工具行：+ | Agent | Cfm | stretch | token | context --------
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(6)
        toolbar.setContentsMargins(0, 0, 0, 0)
        
        self._agent_mode = True
        self._confirm_mode = False
        
        # + 附件弹出菜单
        self.btn_attach_menu = QtWidgets.QPushButton("+")
        self.btn_attach_menu.setObjectName("btnAttach")
        self.btn_attach_menu.setFixedSize(18, 18)
        self.btn_attach_menu.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_attach_menu.setToolTip("Attach / Actions")
        self.btn_attach_menu.clicked.connect(self._show_attach_menu)
        toolbar.addWidget(self.btn_attach_menu)
        
        # Agent/Ask 模式
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.setObjectName("modeCombo")
        self.mode_combo.addItem("Agent")
        self.mode_combo.addItem("Ask")
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setProperty("mode", "agent")
        self.mode_combo.setCursor(QtCore.Qt.PointingHandCursor)
        self.mode_combo.setToolTip(tr('mode.tooltip'))
        self.mode_combo.setFixedWidth(58)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        toolbar.addWidget(self.mode_combo)
        
        # 确认模式开关
        self.chk_confirm_mode = QtWidgets.QCheckBox("Cfm")
        self.chk_confirm_mode.setObjectName("chkConfirm")
        self.chk_confirm_mode.setChecked(False)
        self.chk_confirm_mode.setCursor(QtCore.Qt.PointingHandCursor)
        self.chk_confirm_mode.setToolTip(tr('confirm.tooltip'))
        self.chk_confirm_mode.toggled.connect(self._on_confirm_mode_toggled)
        toolbar.addWidget(self.chk_confirm_mode)
        
        toolbar.addStretch()
        
        # Token 统计
        self.token_stats_btn = QtWidgets.QPushButton("0")
        self.token_stats_btn.setObjectName("tokenStats")
        self.token_stats_btn.setToolTip(tr('header.token_stats.tooltip'))
        self.token_stats_btn.clicked.connect(self._show_token_stats_dialog)
        toolbar.addWidget(self.token_stats_btn)
        
        # 上下文统计
        self.context_label = QtWidgets.QLabel("0K / 64K")
        self.context_label.setObjectName("contextLabel")
        toolbar.addWidget(self.context_label)
        
        layout.addLayout(toolbar)
        
        # -------- 输入行：输入框 + Send/Stop --------
        input_row = QtWidgets.QHBoxLayout()
        input_row.setSpacing(6)
        
        # 输入框（自适应高度）
        self.input_edit = ChatInput()
        self.input_edit.imageDropped.connect(self._on_image_dropped)
        input_row.addWidget(self.input_edit, 1)
        
        # Send / Stop 按钮 — 输入框右侧
        btn_col = QtWidgets.QVBoxLayout()
        btn_col.setSpacing(4)
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.addStretch()
        
        self.btn_stop = StopButton()
        self.btn_stop.setFixedHeight(26)
        self.btn_stop.setVisible(False)
        btn_col.addWidget(self.btn_stop)
        
        self.btn_send = SendButton()
        self.btn_send.setFixedHeight(26)
        btn_col.addWidget(self.btn_send)
        
        input_row.addLayout(btn_col)
        
        layout.addLayout(input_row)
        
        # -------- 隐藏按钮（保持 self.btn_xxx 引用兼容 _wire_events）--------
        self.btn_attach_image = QtWidgets.QPushButton("Img")
        self.btn_attach_image.setVisible(False)
        
        self.btn_export_train = QtWidgets.QPushButton("Train")
        self.btn_export_train.setVisible(False)
        
        return container

    # -------- + 菜单弹出 --------

    def _show_attach_menu(self):
        """弹出附件/低频操作菜单"""
        menu = QtWidgets.QMenu(self)
        menu.addAction("Attach Image", self.btn_attach_image.click)
        menu.addSeparator()
        menu.addAction("Export Train", self.btn_export_train.click)
        menu.exec_(self.btn_attach_menu.mapToGlobal(
            QtCore.QPoint(0, -menu.sizeHint().height())
        ))

    # ---------- 确认模式切换 ----------
    
    def _on_confirm_mode_toggled(self, checked: bool):
        self._confirm_mode = checked

    # ---------- Agent / Ask 模式切换（下拉框）----------

    def _on_mode_changed(self, index: int):
        """模式下拉框切换：0=Agent, 1=Ask"""
        _MODE_MAP = {0: "agent", 1: "ask"}
        mode = _MODE_MAP.get(index, "agent")
        self._agent_mode = (mode == "agent")
        self.mode_combo.setProperty("mode", mode)
        self.mode_combo.style().unpolish(self.mode_combo)
        self.mode_combo.style().polish(self.mode_combo)
        self.btn_send.setProperty("mode", mode)
        self.btn_send.style().unpolish(self.btn_send)
        self.btn_send.style().polish(self.btn_send)

    # ---------- 工具执行状态（兼容旧 API）----------

    def _on_show_tool_status(self, tool_name: str):
        """在输入区域状态栏显示当前正在执行的工具"""
        try:
            self.thinking_bar.show_tool(tool_name)
        except RuntimeError:
            pass

    def _on_hide_tool_status(self):
        """隐藏工具状态"""
        try:
            self.thinking_bar.hide_tool()
        except RuntimeError:
            pass

    def _on_show_generating(self):
        """显示 Generating... 状态（API 请求等待中）"""
        try:
            self.thinking_bar.show_generating()
        except RuntimeError:
            pass

    def _retranslate_input_area(self):
        """语言切换后更新输入区域所有翻译文本"""
        self.mode_combo.setToolTip(tr('mode.tooltip'))
        self.chk_confirm_mode.setToolTip(tr('confirm.tooltip'))
        self.input_edit.setPlaceholderText(tr('placeholder'))
        self.btn_attach_image.setToolTip(tr('attach_image.tooltip'))
        self.btn_export_train.setToolTip(tr('train.tooltip'))
        self.token_stats_btn.setToolTip(tr('header.token_stats.tooltip'))
