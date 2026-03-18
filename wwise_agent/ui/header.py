# -*- coding: utf-8 -*-
"""
Header UI 构建 — 顶部设置栏（模型选择、Provider、Web/Think 开关等）

从 ai_tab.py 中拆分出的 Mixin，所有方法通过 self 访问 AITab 实例状态。
样式由全局 style_template.qss 通过 objectName 选择器控制。
"""

from wwise_agent.qt_compat import QtWidgets, QtCore
from .i18n import tr, get_language, set_language, language_changed


class HeaderMixin:
    """顶部设置栏构建与交互逻辑"""

    def _build_header(self) -> QtWidgets.QWidget:
        """顶部设置栏 — 单行：Provider + Model + keyStatus + Web + Think + ⋯ 溢出菜单"""
        header = QtWidgets.QFrame()
        header.setObjectName("headerFrame")
        
        outer = QtWidgets.QVBoxLayout(header)
        outer.setContentsMargins(8, 2, 8, 2)
        outer.setSpacing(0)
        
        # -------- 单行：Provider + Model + keyStatus + Web + Think + ⋯ --------
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(4)
        
        # 提供商
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.setObjectName("providerCombo")
        self.provider_combo.addItem("Ollama", 'ollama')
        self.provider_combo.addItem("DeepSeek", 'deepseek')
        self.provider_combo.addItem("GLM", 'glm')
        self.provider_combo.addItem("OpenAI", 'openai')
        self.provider_combo.addItem("CodeBuddy", 'codebuddy_cli')
        self.provider_combo.addItem("Duojie", 'duojie')
        self.provider_combo.addItem("WLAI", 'wlai')
        self.provider_combo.setMinimumWidth(70)
        self.provider_combo.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        row.addWidget(self.provider_combo)
        
        # 模型
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.setObjectName("modelCombo")
        self._model_map = {
            'ollama': ['qwen2.5:14b', 'qwen2.5:7b', 'llama3:8b', 'mistral:7b'],
            'deepseek': ['deepseek-chat', 'deepseek-reasoner'],
            'glm': ['glm-4.7'],
            'openai': ['gpt-5.2', 'gpt-5.3-codex'],
            'codebuddy_cli': ['claude-sonnet-4.6 (Default)', 'claude-opus-4.6 (Opus)', 'glm-4.7 (Haiku)'],
            'duojie': [
                'claude-sonnet-4-5',
                'claude-opus-4-5-kiro',
                'claude-opus-4-5-max',
                'claude-opus-4-6-normal',
                'claude-opus-4-6-kiro',
                'claude-haiku-4-5',
                'gemini-3-pro-image-preview',
                'gpt-5.3-codex',
                'glm-4.7',
                'glm-5',
                'kimi-k2.5',
                'MiniMax-M2.5',
                'qwen3.5-plus',
            ],
            'wlai': [
                'gpt-4o',
                'gpt-4o-mini',
                'gpt-4-turbo',
                'claude-sonnet-4-20250514',
                'claude-sonnet-4-6',
                'claude-opus-4-6',
                'claude-3-5-sonnet-20241022',
                'claude-3-haiku-20240307',
                'deepseek-chat',
                'deepseek-reasoner',
                'gemini-2.0-flash',
                'gemini-1.5-pro',
            ],
        }
        self._model_context_limits = {
            'qwen2.5:14b': 32000, 'qwen2.5:7b': 32000, 'llama3:8b': 8000, 'mistral:7b': 32000,
            'deepseek-chat': 128000, 'deepseek-reasoner': 128000,
            'glm-4.7': 200000,
            'gpt-5.2': 128000,
            'gpt-5.3-codex': 200000,
            # CodeBuddy (通过 claude-internal CLI 调用)
            'claude-sonnet-4.6 (Default)': 200000,
            'claude-opus-4.6 (Opus)': 200000,
            'glm-4.7 (Haiku)': 128000,
            # Duojie 模型
            'claude-sonnet-4-5': 200000,
            'claude-opus-4-5-kiro': 200000,
            'claude-opus-4-5-max': 200000,
            'claude-opus-4-6-normal': 200000,
            'claude-opus-4-6-kiro': 200000,
            'claude-haiku-4-5': 200000,
            'gemini-3-pro-image-preview': 128000,
            'glm-5': 200000,
            'kimi-k2.5': 128000,
            'MiniMax-M2.5': 128000,
            'qwen3.5-plus': 128000,
            # WLAI 模型
            'gpt-4o': 128000,
            'gpt-4o-mini': 128000,
            'gpt-4-turbo': 128000,
            'claude-sonnet-4-20250514': 200000,
            'claude-sonnet-4-6': 200000,
            'claude-opus-4-6': 200000,
            'claude-3-5-sonnet-20241022': 200000,
            'claude-3-haiku-20240307': 200000,
            'gemini-2.0-flash': 128000,
            'gemini-1.5-pro': 128000,
        }
        # 模型特性配置
        self._model_features = {
            'qwen2.5:14b':               {'supports_prompt_caching': True, 'supports_vision': False},
            'qwen2.5:7b':                {'supports_prompt_caching': True, 'supports_vision': False},
            'llama3:8b':                  {'supports_prompt_caching': True, 'supports_vision': False},
            'mistral:7b':                 {'supports_prompt_caching': True, 'supports_vision': False},
            'deepseek-chat':              {'supports_prompt_caching': True, 'supports_vision': False},
            'deepseek-reasoner':          {'supports_prompt_caching': True, 'supports_vision': False},
            'glm-4.7':                    {'supports_prompt_caching': True, 'supports_vision': False},
            'gpt-5.2':                    {'supports_prompt_caching': True, 'supports_vision': True},
            'gpt-5.3-codex':              {'supports_prompt_caching': True, 'supports_vision': True},
            # CodeBuddy (claude-internal CLI)
            'claude-sonnet-4.6 (Default)': {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-opus-4.6 (Opus)':      {'supports_prompt_caching': True, 'supports_vision': True},
            'glm-4.7 (Haiku)':            {'supports_prompt_caching': True, 'supports_vision': False},
            'claude-sonnet-4-5':          {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-opus-4-5-kiro':       {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-opus-4-5-max':        {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-opus-4-6-normal':     {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-opus-4-6-kiro':       {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-haiku-4-5':           {'supports_prompt_caching': True, 'supports_vision': True},
            'gemini-3-pro-image-preview': {'supports_prompt_caching': True, 'supports_vision': True},
            'glm-5':                      {'supports_prompt_caching': True, 'supports_vision': False},
            'kimi-k2.5':                  {'supports_prompt_caching': True, 'supports_vision': False},
            'MiniMax-M2.5':               {'supports_prompt_caching': True, 'supports_vision': False},
            'qwen3.5-plus':               {'supports_prompt_caching': True, 'supports_vision': False},
            # WLAI 模型
            'gpt-4o':                     {'supports_prompt_caching': True, 'supports_vision': True},
            'gpt-4o-mini':                {'supports_prompt_caching': True, 'supports_vision': True},
            'gpt-4-turbo':                {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-sonnet-4-20250514':   {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-sonnet-4-6':          {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-opus-4-6':            {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-3-5-sonnet-20241022': {'supports_prompt_caching': True, 'supports_vision': True},
            'claude-3-haiku-20240307':    {'supports_prompt_caching': True, 'supports_vision': True},
            'gemini-2.0-flash':           {'supports_prompt_caching': True, 'supports_vision': True},
            'gemini-1.5-pro':             {'supports_prompt_caching': True, 'supports_vision': True},
        }
        self._refresh_models('ollama')
        self.model_combo.setMinimumWidth(100)
        self.model_combo.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        row.addWidget(self.model_combo, 1)
        
        # API Key 状态 — 紧凑指示
        self.key_status = QtWidgets.QLabel()
        self.key_status.setObjectName("keyStatus")
        self.key_status.setMaximumWidth(90)
        self.key_status.setMinimumWidth(0)
        self.key_status.setTextInteractionFlags(QtCore.Qt.NoTextInteraction)
        row.addWidget(self.key_status)
        
        # Web / Think 开关
        self.web_check = QtWidgets.QCheckBox("Web")
        self.web_check.setObjectName("chkWeb")
        self.web_check.setChecked(True)
        row.addWidget(self.web_check)
        
        self.think_check = QtWidgets.QCheckBox("Think")
        self.think_check.setObjectName("chkThink")
        self.think_check.setChecked(True)
        self.think_check.setToolTip(tr('header.think.tooltip'))
        row.addWidget(self.think_check)
        
        # ⋯ 溢出菜单按钮
        self.btn_overflow = QtWidgets.QPushButton("···")
        self.btn_overflow.setObjectName("btnOverflow")
        self.btn_overflow.setFixedSize(24, 22)
        self.btn_overflow.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_overflow.clicked.connect(self._show_overflow_menu)
        row.addWidget(self.btn_overflow)
        
        outer.addLayout(row)
        
        # -------- 隐藏按钮（保持 self.btn_xxx 引用兼容 _wire_events）--------
        self.btn_key = QtWidgets.QPushButton("Key")
        self.btn_key.setObjectName("btnSmall")
        self.btn_key.setVisible(False)
        
        self.btn_clear = QtWidgets.QPushButton("Clear")
        self.btn_clear.setObjectName("btnSmall")
        self.btn_clear.setVisible(False)
        
        self.btn_cache = QtWidgets.QPushButton("Cache")
        self.btn_cache.setObjectName("btnSmall")
        self.btn_cache.setVisible(False)
        
        self.btn_optimize = QtWidgets.QPushButton("Opt")
        self.btn_optimize.setObjectName("btnOptimize")
        self.btn_optimize.setVisible(False)
        
        self.btn_update = QtWidgets.QPushButton("Update")
        self.btn_update.setObjectName("btnUpdate")
        self.btn_update.setVisible(False)
        
        self.btn_font_scale = QtWidgets.QPushButton("Aa")
        self.btn_font_scale.setObjectName("btnFontScale")
        self.btn_font_scale.setVisible(False)
        
        # 语言下拉框（隐藏，仅用于引用 + 信号）
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.setObjectName("langCombo")
        self.lang_combo.addItem("中文", "zh")
        self.lang_combo.addItem("EN", "en")
        self.lang_combo.setCurrentIndex(0 if get_language() == 'zh' else 1)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        self.lang_combo.setVisible(False)
        
        return header

    def _show_overflow_menu(self):
        """显示溢出菜单：低频功能集中在此"""
        menu = QtWidgets.QMenu(self)
        
        menu.addAction("API Key", self.btn_key.click)
        menu.addAction("Clear Chat", self.btn_clear.click)
        menu.addAction("Cache", self.btn_cache.click)
        menu.addAction("Optimize", self.btn_optimize.click)
        menu.addSeparator()
        menu.addAction("Update", self.btn_update.click)
        menu.addAction("Font (Aa)", self.btn_font_scale.click)
        menu.addSeparator()
        
        # 语言子菜单
        lang_menu = menu.addMenu("Language")
        act_zh = lang_menu.addAction("中文")
        act_en = lang_menu.addAction("EN")
        current_lang = get_language()
        act_zh.setCheckable(True)
        act_en.setCheckable(True)
        act_zh.setChecked(current_lang == 'zh')
        act_en.setChecked(current_lang == 'en')
        act_zh.triggered.connect(lambda: self._set_lang_from_menu('zh'))
        act_en.triggered.connect(lambda: self._set_lang_from_menu('en'))
        
        menu.exec_(self.btn_overflow.mapToGlobal(
            QtCore.QPoint(0, self.btn_overflow.height())
        ))

    def _set_lang_from_menu(self, lang: str):
        """从溢出菜单切换语言"""
        if lang != get_language():
            set_language(lang)
            expected_idx = 0 if lang == 'zh' else 1
            if self.lang_combo.currentIndex() != expected_idx:
                self.lang_combo.blockSignals(True)
                self.lang_combo.setCurrentIndex(expected_idx)
                self.lang_combo.blockSignals(False)

    def _on_language_changed(self, index: int):
        """语言下拉框切换"""
        lang = self.lang_combo.itemData(index)
        if lang and lang != get_language():
            set_language(lang)

    def _retranslate_header(self):
        """语言切换后更新 Header 区域所有翻译文本"""
        self.think_check.setToolTip(tr('header.think.tooltip'))
        self.btn_cache.setToolTip(tr('header.cache.tooltip'))
        self.btn_optimize.setToolTip(tr('header.optimize.tooltip'))
        self.btn_update.setToolTip(tr('header.update.tooltip'))
        self.btn_font_scale.setToolTip(tr('header.font.tooltip'))
        lang = get_language()
        expected_idx = 0 if lang == 'zh' else 1
        if self.lang_combo.currentIndex() != expected_idx:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(expected_idx)
            self.lang_combo.blockSignals(False)
