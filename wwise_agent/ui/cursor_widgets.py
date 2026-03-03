# -*- coding: utf-8 -*-
"""
Cursor 风格 UI 组件 — Wwise Agent 版
模仿 Cursor 侧边栏的简洁设计
每次对话形成完整块：思考 → 操作 → 总结
"""

from wwise_agent.qt_compat import QtWidgets, QtCore, QtGui
from datetime import datetime
from typing import Optional, List, Dict
import html
import math
import re
import time

from .i18n import tr


def _fmt_duration(seconds: float) -> str:
    """格式化时长: <60s -> '18s', >=60s -> '1m43s'"""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m{s % 60:02d}s"


# ============================================================
# Wwise 对象路径 → 可点击链接
# ============================================================

# 匹配 Wwise 对象路径: \Actor-Mixer Hierarchy\..., \Events\..., etc.
_WWISE_PATH_RE = re.compile(
    r'(?<!["\w\\])'
    r'(\\(?:Actor-Mixer Hierarchy|Interactive Music Hierarchy|Events|'
    r'Switches|States|Game Parameters|Triggers|Effects|Attenuations|'
    r'Presets|Soundcaster Sessions|Mixing Sessions|SoundBanks|'
    r'Master-Mixer Hierarchy|Virtual Acoustics|Queries)'
    r'(?:\\[^\s"\\]+)+)'
    r'(?!["\w\\])'
)

_WWISE_LINK_STYLE = "color:#10b981;text-decoration:none;font-family:Consolas,Monaco,monospace;"


def _linkify_wwise_paths(text: str) -> str:
    """将文本中的 Wwise 对象路径转换为可点击的 <a> 标签

    使用 wwise:// 协议，点击后由 Qt 的 linkActivated 信号处理跳转。
    """
    return _WWISE_PATH_RE.sub(
        lambda m: f'<a href="wwise://{m.group(1)}" style="{_WWISE_LINK_STYLE}">{m.group(1)}</a>',
        text,
    )


def _linkify_wwise_paths_plain(text: str) -> str:
    """将纯文本中的 Wwise 路径转换为富文本 HTML（含可点击链接）

    先 html.escape 再 linkify，保证安全。
    """
    escaped = html.escape(text)
    return _linkify_wwise_paths(escaped).replace('\n', '<br>')


# ============================================================
# 流光边框 — AI 响应活跃时在左侧显示流动渐变光带
# ============================================================

class AuroraBar(QtWidgets.QWidget):
    """流动渐变光带 — 放在 AIResponse 左侧，AI 回复期间持续流动。"""

    _NUM_STOPS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(3)
        self._phase = 0.0
        self._active = False
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)
        self._key_colors = [
            QtGui.QColor(226, 232, 240, 200),
            QtGui.QColor(100, 116, 139, 100),
            QtGui.QColor(226, 232, 240, 200),
        ]

    def start(self):
        self._active = True
        self._phase = 0.0
        self.setFixedWidth(3)
        self.setVisible(True)
        self._timer.start()
        self.update()

    def stop(self):
        self._active = False
        self._timer.stop()
        self.update()

    def _tick(self):
        self._phase += 0.02
        if self._phase > 1.0:
            self._phase -= 1.0
        self.update()

    def paintEvent(self, event):
        if not self._active and self._phase == 0.0:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        if self._active:
            grad = QtGui.QLinearGradient(0, 0, 0, h)
            n = self._NUM_STOPS
            for i in range(n):
                t = i / max(n - 1, 1)
                raw = (t + self._phase) % 1.0
                c = self._lerp_key(raw)
                grad.setColorAt(t, c)
            p.fillRect(0, 0, w, h, grad)
        else:
            p.fillRect(0, 0, w, h, QtGui.QColor(226, 232, 240, 30))
        p.end()

    def _lerp_key(self, t: float) -> QtGui.QColor:
        keys = self._key_colors
        n = len(keys) - 1
        idx = t * n
        i0 = int(idx)
        i1 = min(i0 + 1, n)
        f = idx - i0
        c0, c1 = keys[i0], keys[i1]
        return QtGui.QColor(
            int(c0.red() + (c1.red() - c0.red()) * f),
            int(c0.green() + (c1.green() - c0.green()) * f),
            int(c0.blue() + (c1.blue() - c0.blue()) * f),
            int(c0.alpha() + (c1.alpha() - c0.alpha()) * f),
        )


# ============================================================
# 主题常量
# ============================================================

class CursorTheme:
    """Glassmorphism 深色主题常量"""
    BG_PRIMARY = "#0d0f1a"
    BG_SECONDARY = "#111420"
    BG_CARD = "rgba(17, 20, 32, 0.85)"
    BG_INPUT = "#1a1d2e"
    BORDER = "rgba(255, 255, 255, 8)"
    BORDER_FOCUS = "rgba(99, 102, 241, 0.4)"
    TEXT_PRIMARY = "#e2e8f0"
    TEXT_SECONDARY = "#94a3b8"
    TEXT_MUTED = "#64748b"
    TEXT_BRIGHT = "#f1f5f9"
    ACCENT_BLUE = "#6366f1"
    ACCENT_GREEN = "#10b981"
    ACCENT_ORANGE = "#f59e0b"
    ACCENT_RED = "#ef4444"
    ACCENT_PURPLE = "#a78bfa"
    ACCENT_YELLOW = "#eab308"
    ACCENT_BEIGE = "#d4c5a9"
    MSG_BORDER = "rgba(255, 255, 255, 6)"
    FONT_BODY = "'Microsoft YaHei', 'SimSun', 'Segoe UI', sans-serif"
    FONT_CODE = "'Consolas', 'Monaco', 'Courier New', monospace"


# ============================================================
# 通用可折叠区块
# ============================================================

class CollapsibleSection(QtWidgets.QWidget):
    """通用可折叠区块"""

    def __init__(self, title: str = "", icon: str = "", collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._collapsed = collapsed
        self._title_text = title

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(0)

        arrow = "▶" if collapsed else "▼"
        display = f"{icon} {arrow} {title}".strip() if icon else f"{arrow} {title}"
        self.header = QtWidgets.QPushButton(display)
        self.header.setFlat(True)
        self.header.setCursor(QtCore.Qt.PointingHandCursor)
        self.header.setObjectName("collapsibleHeader")
        self.header.clicked.connect(self.toggle)
        layout.addWidget(self.header)

        self._content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self._content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self._content_widget.setVisible(not collapsed)
        layout.addWidget(self._content_widget)

    def set_title(self, title: str):
        self._title_text = title
        arrow = "▶" if self._collapsed else "▼"
        self.header.setText(f"{arrow} {title}")

    def toggle(self):
        self._collapsed = not self._collapsed
        self._content_widget.setVisible(not self._collapsed)
        arrow = "▶" if self._collapsed else "▼"
        self.header.setText(f"{arrow} {self._title_text}")

    def expand(self):
        if self._collapsed:
            self.toggle()

    def collapse(self):
        if not self._collapsed:
            self.toggle()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def add_text(self, text: str, style: str = ""):
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        if style == "muted":
            lbl.setObjectName("mutedText")
        self.content_layout.addWidget(lbl)


# ============================================================
# 脉冲圆点
# ============================================================

class PulseIndicator(QtWidgets.QWidget):
    """小型脉冲圆点动画"""

    def __init__(self, color: str = "#d4c5a9", size: int = 6, parent=None):
        super().__init__(parent)
        self._color = QtGui.QColor(color)
        self._size = size
        self.setFixedSize(size + 4, size + 4)
        self._opacity = 1.0
        self._anim = QtCore.QPropertyAnimation(self, b"pulse_opacity")
        self._anim.setDuration(1200)
        self._anim.setStartValue(0.25)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QtCore.QEasingCurve.InOutSine)

    def get_pulse_opacity(self):
        return self._opacity

    def set_pulse_opacity(self, val):
        self._opacity = val
        self.update()

    pulse_opacity = QtCore.Property(float, get_pulse_opacity, set_pulse_opacity)

    def start(self):
        self._anim.start()

    def stop(self):
        self._anim.stop()
        self._opacity = 1.0
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        c = QtGui.QColor(self._color)
        c.setAlphaF(self._opacity)
        p.setBrush(c)
        p.setPen(QtCore.Qt.NoPen)
        cx = self.width() / 2
        cy = self.height() / 2
        p.drawEllipse(QtCore.QPointF(cx, cy), self._size / 2, self._size / 2)
        p.end()


# ============================================================
# 思考过程区块
# ============================================================

class ThinkingSection(CollapsibleSection):
    """展示 AI 思考过程"""

    def __init__(self, parent=None):
        super().__init__(tr('thinking.title'), collapsed=False, parent=parent)
        self.header.setObjectName("thinkingHeader")
        self._finalized = False
        self._start_time = time.time()
        self._paused_elapsed = 0.0

        self._text_edit = QtWidgets.QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._text_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._text_edit.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self._text_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self._text_edit.setObjectName("thinkingText")
        self._text_edit.setMaximumHeight(400)
        self.content_layout.addWidget(self._text_edit)

    def append_thinking(self, text: str):
        self._text_edit.moveCursor(QtGui.QTextCursor.End)
        self._text_edit.insertPlainText(text)
        self._text_edit.moveCursor(QtGui.QTextCursor.End)
        self._auto_height()

    def _auto_height(self):
        doc = self._text_edit.document()
        visual_lines = 0
        block = doc.begin()
        while block.isValid():
            bl = block.layout()
            if bl and bl.lineCount() > 0:
                visual_lines += bl.lineCount()
            else:
                visual_lines += 1
            block = block.next()
        line_h = self._text_edit.fontMetrics().lineSpacing()
        target = max(visual_lines * line_h + 16, 40)
        target = min(target, 400)
        self._text_edit.setFixedHeight(target)

    def update_time(self):
        if self._finalized:
            return
        elapsed = self._total_elapsed()
        self.set_title(f"{tr('thinking.title')} ({_fmt_duration(elapsed)})")

    def _total_elapsed(self) -> float:
        if self._finalized:
            return self._paused_elapsed
        return self._paused_elapsed + (time.time() - self._start_time)

    def resume(self):
        self._start_time = time.time()
        self._finalized = False

    def finalize(self):
        if self._finalized:
            return
        self._paused_elapsed += time.time() - self._start_time
        self._finalized = True
        elapsed = self._paused_elapsed
        self.set_title(f"{tr('thinking.title')} ({_fmt_duration(elapsed)})")
        self.collapse()


# ============================================================
# 思考状态指示条（兼容旧 ThinkingBar）
# ============================================================

class ThinkingBar(QtWidgets.QWidget):
    """输入框上方的思考状态指示条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setVisible(False)
        self._phase = 0.0
        self._elapsed = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._phase = 0.0
        self._elapsed = 0.0
        self.setVisible(True)
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def set_elapsed(self, s: float):
        self._elapsed = s
        self.update()

    def _tick(self):
        self._phase += 0.025
        if self._phase > 1.0:
            self._phase -= 1.0
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        display = f"Thinking {self._elapsed:.1f}s" if self._elapsed > 0 else "Thinking..."
        font = QtGui.QFont(CursorTheme.FONT_BODY, 10)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(display)
        x = (w - tw) // 2
        y = (h + fm.ascent() - fm.descent()) // 2

        for i, ch in enumerate(display):
            char_pos = i / max(len(display), 1)
            dist = abs(char_pos - self._phase)
            dist = min(dist, 1.0 - dist)
            glow = max(0.0, 1.0 - dist * 5.0)

            base = QtGui.QColor(CursorTheme.ACCENT_PURPLE)
            muted = QtGui.QColor(CursorTheme.TEXT_MUTED)
            r = int(muted.red() + (base.red() - muted.red()) * glow)
            g = int(muted.green() + (base.green() - muted.green()) * glow)
            b = int(muted.blue() + (base.blue() - muted.blue()) * glow)
            p.setPen(QtGui.QColor(r, g, b))
            p.drawText(x, y, ch)
            x += fm.horizontalAdvance(ch)
        p.end()


# ============================================================
# 确认模式 — 内联预览确认控件
# ============================================================

class WwisePreviewInline(QtWidgets.QFrame):
    """嵌入对话流中的工具执行预览卡片。"""

    confirmed = QtCore.Signal()
    cancelled = QtCore.Signal()

    def __init__(self, tool_name: str, args: dict, parent=None):
        super().__init__(parent)
        self._decided = False
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Maximum,
        )
        self.setObjectName("wwisePreviewInline")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(3)

        title = QtWidgets.QLabel(tr('confirm.title', tool_name))
        title.setObjectName("wwisePreviewTitle")
        title.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(title)

        summary_lines = []
        for k, v in args.items():
            sv = str(v)
            if len(sv) > 120:
                sv = sv[:117] + "..."
            summary_lines.append(f"  {k}: {sv}")
        if summary_lines:
            summary_text = "\n".join(summary_lines[:6])
            if len(summary_lines) > 6:
                summary_text += f"\n  {tr('confirm.params_more', len(summary_lines))}"
            summary_lbl = QtWidgets.QLabel(summary_text)
            summary_lbl.setWordWrap(True)
            summary_lbl.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            summary_lbl.setObjectName("wwiseInlineSummary")
            summary_lbl.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Maximum,
            )
            layout.addWidget(summary_lbl)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch()

        btn_cancel = QtWidgets.QPushButton(tr('confirm.cancel'))
        btn_cancel.setCursor(QtCore.Qt.PointingHandCursor)
        btn_cancel.setFixedHeight(24)
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(btn_cancel)

        btn_confirm = QtWidgets.QPushButton(tr('confirm.execute'))
        btn_confirm.setCursor(QtCore.Qt.PointingHandCursor)
        btn_confirm.setFixedHeight(24)
        btn_confirm.setObjectName("btnConfirmGreen")
        btn_confirm.clicked.connect(self._on_confirm)
        btn_row.addWidget(btn_confirm)

        layout.addLayout(btn_row)

    def _on_confirm(self):
        if self._decided:
            return
        self._decided = True
        self.setVisible(False)
        self.setFixedHeight(0)
        self.confirmed.emit()

    def _on_cancel(self):
        if self._decided:
            return
        self._decided = True
        self.setVisible(False)
        self.setFixedHeight(0)
        self.cancelled.emit()


# ============================================================
# 工具调用项
# ============================================================

class ToolCallItem(CollapsibleSection):
    """单个工具调用 — CollapsibleSection 风格"""

    wwisePathClicked = QtCore.Signal(str)

    def __init__(self, tool_name: str, parent=None):
        super().__init__(tool_name, icon="", collapsed=True, parent=parent)
        self.tool_name = tool_name
        self._result = None
        self._success = None
        self._start_time = time.time()

        self.header.setObjectName("toolCallHeader")

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setFixedHeight(2)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setObjectName("toolProgress")
        self.content_layout.addWidget(self.progress_bar)

        self._result_label = None

    def set_result(self, result: str, success: bool = True):
        self._result = result
        self._success = success
        elapsed = time.time() - self._start_time

        self.progress_bar.setVisible(False)
        self.set_title(f"{self.tool_name} ({elapsed:.1f}s)")

        if not success:
            self.header.setProperty("state", "failed")
            self.header.style().unpolish(self.header)
            self.header.style().polish(self.header)

        if result.strip():
            rich_html = _linkify_wwise_paths_plain(result)
            self._result_label = QtWidgets.QLabel(rich_html)
            self._result_label.setWordWrap(True)
            self._result_label.setTextFormat(QtCore.Qt.RichText)
            self._result_label.setOpenExternalLinks(False)
            self._result_label.setTextInteractionFlags(
                QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse
            )
            self._result_label.linkActivated.connect(self._on_result_link)
            self._result_label.setObjectName("toolResultLabel")
            if not success:
                self._result_label.setProperty("state", "failed")
            self.content_layout.addWidget(self._result_label)

    def _on_result_link(self, url: str):
        if url.startswith('wwise://'):
            self.wwisePathClicked.emit(url[len('wwise://'):])


# ============================================================
# 执行过程区块
# ============================================================

class ExecutionSection(CollapsibleSection):
    """执行过程 - 卡片式工具调用显示"""

    wwisePathClicked = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(tr('exec.running'), icon="", collapsed=True, parent=parent)
        self._tool_calls: List[ToolCallItem] = []
        self._start_time = time.time()
        self.header.setObjectName("execHeader")

    def add_tool_call(self, tool_name: str) -> ToolCallItem:
        item = ToolCallItem(tool_name, self)
        item.wwisePathClicked.connect(self.wwisePathClicked.emit)
        self._tool_calls.append(item)
        self.content_layout.addWidget(item)
        self._update_title()
        return item

    def set_tool_result(self, tool_name: str, result: str, success: bool = True):
        for item in reversed(self._tool_calls):
            if item.tool_name == tool_name and item._result is None:
                item.set_result(result, success)
                break
        self._update_title()

    def _update_title(self):
        total = len(self._tool_calls)
        done = sum(1 for item in self._tool_calls if item._result is not None)
        if done < total:
            self.set_title(tr('exec.progress', done, total))
        else:
            elapsed = time.time() - self._start_time
            self.set_title(tr('exec.done', total, _fmt_duration(elapsed)))

    def finalize(self):
        elapsed = time.time() - self._start_time
        total = len(self._tool_calls)
        for item in self._tool_calls:
            if item._result is None:
                item.progress_bar.setVisible(False)
                item_elapsed = time.time() - item._start_time
                item.set_title(f"{item.tool_name} ({item_elapsed:.1f}s)")
                item._result = ""
                item._success = True
        success = sum(1 for item in self._tool_calls if item._success)
        failed = total - success
        if failed > 0:
            self.set_title(tr('exec.done_err', success, failed, _fmt_duration(elapsed)))
        else:
            self.set_title(tr('exec.done', total, _fmt_duration(elapsed)))


# ============================================================
# 图片预览
# ============================================================

class ImagePreviewDialog(QtWidgets.QDialog):
    """模态图片预览弹窗"""

    def __init__(self, pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('img.preview'))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowMaximizeButtonHint)
        self._pixmap = pixmap

        screen = QtWidgets.QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            max_w, max_h = int(avail.width() * 0.8), int(avail.height() * 0.8)
        else:
            max_w, max_h = 1200, 800
        init_w = min(pixmap.width() + 40, max_w)
        init_h = min(pixmap.height() + 40, max_h)
        self.resize(init_w, init_h)
        self.setObjectName("imgPreviewDlg")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(QtCore.Qt.AlignCenter)
        scroll.setObjectName("chatScrollArea")

        self._img_label = QtWidgets.QLabel()
        self._img_label.setAlignment(QtCore.Qt.AlignCenter)
        scroll.setWidget(self._img_label)
        layout.addWidget(scroll)

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(12, 4, 12, 8)
        info = QtWidgets.QLabel(f"{pixmap.width()} × {pixmap.height()} px")
        info.setObjectName("imgInfoLabel")
        bar.addWidget(info)
        bar.addStretch()
        close_btn = QtWidgets.QPushButton(tr('btn.close'))
        close_btn.setObjectName("imgCloseBtn")
        close_btn.clicked.connect(self.close)
        bar.addWidget(close_btn)
        layout.addLayout(bar)
        self._update_preview()

    def _update_preview(self):
        viewport_w = self.width() - 20
        viewport_h = self.height() - 50
        if self._pixmap.width() > viewport_w or self._pixmap.height() > viewport_h:
            scaled = self._pixmap.scaled(
                viewport_w, viewport_h,
                QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        else:
            scaled = self._pixmap
        self._img_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_preview()

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self.close()
        super().keyPressEvent(event)


class ClickableImageLabel(QtWidgets.QLabel):
    """可点击的图片缩略图"""

    def __init__(self, thumb_pixmap: QtGui.QPixmap, full_pixmap: QtGui.QPixmap, parent=None):
        super().__init__(parent)
        self._full_pixmap = full_pixmap
        self.setPixmap(thumb_pixmap)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(tr('img.click_zoom'))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            dlg = ImagePreviewDialog(self._full_pixmap, self.window())
            dlg.exec()
        else:
            super().mousePressEvent(event)


# ============================================================
# 用户消息
# ============================================================

class UserMessage(QtWidgets.QWidget):
    """用户消息 - 支持折叠"""

    _COLLAPSED_MAX_LINES = 2

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._full_text = text
        self._collapsed = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 4)
        layout.setSpacing(0)

        self._container = QtWidgets.QWidget()
        self._container.setObjectName("userMsgContainer")
        container_layout = QtWidgets.QVBoxLayout(self._container)
        container_layout.setContentsMargins(12, 8, 12, 4)
        container_layout.setSpacing(2)

        self.content = QtWidgets.QLabel(text)
        self.content.setWordWrap(True)
        self.content.setTextFormat(QtCore.Qt.PlainText)
        self.content.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.content.setObjectName("userMsgText")
        container_layout.addWidget(self.content)

        self._toggle_btn = QtWidgets.QPushButton()
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setObjectName("userMsgToggle")
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        self._toggle_btn.setVisible(False)
        container_layout.addWidget(self._toggle_btn)

        layout.addWidget(self._container)
        QtCore.QTimer.singleShot(0, self._maybe_collapse)

    def _maybe_collapse(self):
        line_count = self._full_text.count('\n') + 1
        if line_count > self._COLLAPSED_MAX_LINES:
            self._collapsed = True
            self._apply_collapsed()
            self._toggle_btn.setVisible(True)
        else:
            self._toggle_btn.setVisible(False)

    def _apply_collapsed(self):
        lines = self._full_text.split('\n')
        preview = '\n'.join(lines[:self._COLLAPSED_MAX_LINES])
        if len(lines) > self._COLLAPSED_MAX_LINES:
            preview += ' …'
        self.content.setText(preview)
        remaining = len(lines) - self._COLLAPSED_MAX_LINES
        self._toggle_btn.setText(tr('msg.expand', remaining))

    def _apply_expanded(self):
        self.content.setText(self._full_text)
        self._toggle_btn.setText(tr('msg.collapse'))

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._apply_collapsed()
        else:
            self._apply_expanded()


# ============================================================
# AI 回复块
# ============================================================

class AIResponse(QtWidgets.QWidget):
    """AI 回复 - Cursor 风格（Wwise 版：无 createWrangleRequested/nodePathClicked）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._start_time = time.time()
        self._content = ""
        self._has_thinking = False
        self._has_execution = False

        # 增量渲染状态
        self._frozen_segments: list = []
        self._pending_text = ""
        self._in_code_fence = False
        self._code_fence_lang = ""
        self._incremental_enabled = True

        # 顶层水平布局
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 8)
        outer.setSpacing(0)

        self.aurora_bar = AuroraBar(self)
        outer.addWidget(self.aurora_bar)

        content_col = QtWidgets.QVBoxLayout()
        content_col.setContentsMargins(0, 0, 0, 0)
        content_col.setSpacing(4)
        outer.addLayout(content_col, 1)
        layout = content_col

        # 思考过程区块
        self.thinking_section = ThinkingSection(self)
        self.thinking_section.setVisible(False)
        layout.addWidget(self.thinking_section)

        # 执行过程区块
        self.execution_section = ExecutionSection(self)
        self.execution_section.setVisible(False)
        layout.addWidget(self.execution_section)

        # 总结/回复区域
        self.summary_frame = QtWidgets.QFrame()
        self.summary_frame.setObjectName("aiSummary")
        self._summary_layout = QtWidgets.QVBoxLayout(self.summary_frame)
        self._summary_layout.setContentsMargins(8, 8, 6, 8)
        self._summary_layout.setSpacing(4)

        status_row = QtWidgets.QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(8)

        self.status_label = QtWidgets.QLabel(tr('thinking.init'))
        self.status_label.setObjectName("aiStatusLabel")
        status_row.addWidget(self.status_label)
        status_row.addStretch()

        self._copy_btn = QtWidgets.QPushButton(tr('btn.copy'))
        self._copy_btn.setVisible(False)
        self._copy_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._copy_btn.setFixedHeight(22)
        self._copy_btn.setObjectName("aiCopyBtn")
        self._copy_btn.clicked.connect(self._copy_content)
        status_row.addWidget(self._copy_btn)

        self._summary_layout.addLayout(status_row)

        # 冻结段落容器
        self._frozen_container = QtWidgets.QWidget()
        self._frozen_layout = QtWidgets.QVBoxLayout(self._frozen_container)
        self._frozen_layout.setContentsMargins(0, 0, 0, 0)
        self._frozen_layout.setSpacing(0)
        self._frozen_container.setVisible(False)
        self._summary_layout.addWidget(self._frozen_container)

        # 流式内容区
        self.content_label = QtWidgets.QPlainTextEdit()
        self.content_label.setReadOnly(True)
        self.content_label.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.content_label.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.content_label.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.content_label.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.content_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum
        )
        self.content_label.setObjectName("aiContentLabel")
        _stream_font = QtGui.QFont()
        _stream_font.setFamilies(['Microsoft YaHei', 'SimSun', 'Segoe UI'])
        _stream_font.setPixelSize(14)
        self.content_label.setFont(_stream_font)
        self.content_label.document().setDefaultFont(_stream_font)
        self.content_label.document().setDocumentMargin(0)
        self._apply_line_spacing(160)
        fm = QtGui.QFontMetrics(_stream_font)
        self._content_line_h = int(fm.height() * 1.6)
        self.content_label.setFixedHeight(self._content_line_h + 4)
        self.content_label.document().contentsChanged.connect(self._auto_resize_content)
        self._summary_layout.addWidget(self.content_label)

        layout.addWidget(self.summary_frame)

        self.details_layout = QtWidgets.QVBoxLayout()
        self.details_layout.setSpacing(2)
        layout.addLayout(self.details_layout)

    def add_thinking(self, text: str):
        if not self._has_thinking:
            self._has_thinking = True
            self.thinking_section.setVisible(True)
            self.thinking_section.expand()
        self.thinking_section.append_thinking(text)

    def update_thinking_time(self):
        if self._has_thinking:
            if self.thinking_section._finalized:
                return
            self.thinking_section.update_time()
            total = self.thinking_section._total_elapsed()
            self.status_label.setText(tr('thinking.progress', _fmt_duration(total)))

    def add_status(self, text: str):
        if text.startswith("[tool]"):
            tool_name = text[6:].strip()
            self._add_tool_call(tool_name)
        else:
            self.status_label.setText(text)

    def _add_tool_call(self, tool_name: str):
        if not self._has_execution:
            self._has_execution = True
            self.execution_section.setVisible(True)
        self.execution_section.add_tool_call(tool_name)
        self.status_label.setText(tr('exec.tool', tool_name))

    def add_tool_result(self, tool_name: str, result: str):
        success = not result.startswith("[err]") and not result.startswith("错误") and not result.startswith("Error")
        clean_result = result.removeprefix("[ok] ").removeprefix("[err] ")
        self.execution_section.set_tool_result(tool_name, clean_result, success)

    def _apply_line_spacing(self, percent: int = 160):
        doc = self.content_label.document()
        cursor = QtGui.QTextCursor(doc)
        cursor.select(QtGui.QTextCursor.Document)
        fmt = QtGui.QTextBlockFormat()
        fmt.setLineHeight(percent, 1)
        cursor.mergeBlockFormat(fmt)

    def _auto_resize_content(self):
        doc = self.content_label.document()
        doc.adjustSize()
        doc_height = int(doc.size().height())
        target = doc_height + 4
        min_h = self._content_line_h + 4
        target = max(target, min_h)
        current_h = self.content_label.height()
        if abs(target - current_h) > 1:
            self.content_label.setFixedHeight(target)

    def append_content(self, text: str):
        if not text.strip() and '\n' not in text:
            return
        if '\ufffd' in text:
            text = text.replace('\ufffd', '')
        self._content += text
        self._pending_text += text

        if self._incremental_enabled:
            self._try_freeze_completed()

        self.content_label.setPlainText(self._pending_text)
        self._apply_line_spacing(160)
        cursor = self.content_label.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.content_label.setTextCursor(cursor)

    def _try_freeze_completed(self):
        text = self._pending_text
        if not text:
            return
        lines = text.split('\n')
        freeze_up_to = -1
        i = 0
        in_fence = self._in_code_fence
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if in_fence:
                if stripped.startswith('```'):
                    in_fence = False
                    freeze_up_to = i + 1
                i += 1
                continue
            if stripped.startswith('```'):
                in_fence = True
                self._code_fence_lang = stripped[3:].strip()
                i += 1
                continue
            if not stripped:
                if i > 0 and freeze_up_to < i:
                    has_content_before = any(
                        lines[j].strip()
                        for j in range(max(0, freeze_up_to + 1 if freeze_up_to >= 0 else 0), i)
                    )
                    if has_content_before:
                        freeze_up_to = i
            i += 1
        self._in_code_fence = in_fence
        if freeze_up_to > 0 and not in_fence:
            frozen_text = '\n'.join(lines[:freeze_up_to])
            remaining_text = '\n'.join(lines[freeze_up_to:])
            if frozen_text.strip():
                self._freeze_text(frozen_text)
            self._pending_text = remaining_text

    def _freeze_text(self, text: str):
        segments = SimpleMarkdown.parse_segments(text)
        for seg in segments:
            if seg[0] == 'text':
                lbl = QtWidgets.QLabel()
                lbl.setWordWrap(True)
                lbl.setTextFormat(QtCore.Qt.RichText)
                lbl.setOpenExternalLinks(False)
                lbl.setTextInteractionFlags(
                    QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse
                )
                lbl.setText(seg[1])
                lbl.setObjectName("richText")
                lbl.linkActivated.connect(self._on_link_activated)
                self._frozen_layout.addWidget(lbl)
            elif seg[0] == 'code':
                cb = CodeBlockWidget(seg[2], seg[1], self)
                cb.setContentsMargins(0, 6, 0, 6)
                self._frozen_layout.addWidget(cb)
            elif seg[0] == 'image':
                img_lbl = QtWidgets.QLabel()
                img_lbl.setObjectName("richImage")
                img_lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
                img_lbl.setText(
                    f'<div style="margin:4px 0;">'
                    f'<img src="{html.escape(seg[1])}" '
                    f'style="max-width:100%;max-height:300px;border-radius:6px;">'
                    f'</div>'
                )
                img_lbl.setTextFormat(QtCore.Qt.RichText)
                self._frozen_layout.addWidget(img_lbl)
        if not self._frozen_container.isVisible():
            self._frozen_container.setVisible(True)
        self._frozen_segments.append(text)

    def set_content(self, text: str):
        self._content = text
        self._pending_text = ""
        self._incremental_enabled = False
        content = self._clean_content(text)
        if not content:
            self.content_label.setPlainText("")
            return
        self.content_label.setVisible(False)
        self._freeze_text(content)

    @staticmethod
    def _clean_content(text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r'\n{3,}', '\n\n', text)
        return cleaned.strip()

    def add_collapsible(self, title: str, content: str) -> CollapsibleSection:
        section = CollapsibleSection(title, collapsed=True, parent=self)
        section.add_text(content, "muted")
        self.details_layout.addWidget(section)
        return section

    def _copy_content(self):
        content = self._clean_content(self._content)
        if content:
            QtWidgets.QApplication.clipboard().setText(content)
            self._copy_btn.setText(tr('btn.copied'))
            self._copy_btn.setProperty("state", "copied")
            self._copy_btn.style().unpolish(self._copy_btn)
            self._copy_btn.style().polish(self._copy_btn)
            QtCore.QTimer.singleShot(1500, self._reset_copy_btn)

    def _reset_copy_btn(self):
        try:
            self._copy_btn.setText(tr('btn.copy'))
            self._copy_btn.setProperty("state", "")
            self._copy_btn.style().unpolish(self._copy_btn)
            self._copy_btn.style().polish(self._copy_btn)
        except RuntimeError:
            pass

    def start_aurora(self):
        self.aurora_bar.start()

    def stop_aurora(self):
        self.aurora_bar.stop()

    def finalize(self):
        self.aurora_bar.stop()
        elapsed = time.time() - self._start_time
        if self._has_thinking:
            self.thinking_section.finalize()
        if self._has_execution:
            self.execution_section.finalize()
        parts = []
        if self._has_thinking:
            parts.append(tr('status.thinking'))
        if self._has_execution:
            tool_count = len(self.execution_section._tool_calls)
            parts.append(tr('status.calls', tool_count))
        status_text = tr('status.done', _fmt_duration(elapsed))
        if parts:
            status_text += f" | {', '.join(parts)}"
        self.status_label.setText(status_text)
        if self._clean_content(self._content):
            self._copy_btn.setVisible(True)
        content = self._clean_content(self._content)
        if not content:
            if self._has_execution:
                self.content_label.setPlainText(tr('status.exec_done_see_above'))
            else:
                self.content_label.setPlainText(tr('status.no_reply'))
            self.content_label.setProperty("state", "empty")
            self.content_label.style().unpolish(self.content_label)
            self.content_label.style().polish(self.content_label)
        elif self._frozen_segments:
            remaining = self._clean_content(self._pending_text)
            if remaining:
                self._freeze_text(remaining)
                self.content_label.setVisible(False)
            else:
                self.content_label.setVisible(False)
        else:
            self.content_label.setVisible(False)
            self._freeze_text(content)

    def _on_link_activated(self, url: str):
        if url.startswith('wwise://'):
            pass  # Wwise 路径点击处理（由外部连接）
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


# ============================================================
# 简洁状态行
# ============================================================

class StatusLine(QtWidgets.QLabel):
    """简洁状态行"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("statusLine")
        self.setWordWrap(True)


# ============================================================
# Markdown 解析器
# ============================================================

class SimpleMarkdown:
    """将 Markdown 转换为 Qt Rich Text HTML"""

    _CODE_BLOCK_RE = re.compile(r'```(\w*)\n(.*?)```', re.DOTALL)
    _TABLE_SEP_RE = re.compile(r'^\|?\s*[-:]+[-| :]*$')
    _AUTO_URL_RE = re.compile(
        r'(?<!["\w/=])(?<!\]\()(?<!\[)'
        r'(https?://[^\s<>\)\]\"\'`]+)'
    )
    _FOOTNOTE_REF_RE = re.compile(r'\[\^(\w+)\](?!:)')
    _FOOTNOTE_DEF_RE = re.compile(r'^\[\^(\w+)\]:\s*(.*)')
    _IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')
    _LIST_ITEM_RE = re.compile(r'^(\s*)([-*]|\d+\.)\s+(.*)')
    _TASK_ITEM_RE = re.compile(r'^(\s*)[-*]\s+\[([ xX])\]\s+(.*)')

    @classmethod
    def parse_segments(cls, text: str) -> list:
        segments: list = []
        last = 0
        for m in cls._CODE_BLOCK_RE.finditer(text):
            before = text[last:m.start()]
            if before.strip():
                cls._parse_text_with_images(before, segments)
            segments.append(('code', m.group(1) or '', m.group(2).rstrip()))
            last = m.end()
        after = text[last:]
        if after.strip():
            cls._parse_text_with_images(after, segments)
        if not segments and text.strip():
            cls._parse_text_with_images(text, segments)
        return segments

    @classmethod
    def _parse_text_with_images(cls, text: str, segments: list):
        lines = text.split('\n')
        buf_lines: list = []

        def _flush_buf():
            if buf_lines:
                joined = '\n'.join(buf_lines)
                if joined.strip():
                    segments.append(('text', cls._text_to_html(joined)))
                buf_lines.clear()

        for line in lines:
            stripped = line.strip()
            img_match = cls._IMAGE_RE.fullmatch(stripped)
            if img_match:
                _flush_buf()
                segments.append(('image', img_match.group(2), img_match.group(1)))
            else:
                buf_lines.append(line)
        _flush_buf()

    @classmethod
    def has_rich_content(cls, text: str) -> bool:
        if '```' in text:
            return True
        if re.search(r'^#{1,4}\s', text, re.MULTILINE):
            return True
        if '**' in text or '`' in text:
            return True
        if re.search(r'^[-*]\s', text, re.MULTILINE):
            return True
        if re.search(r'^\d+\.\s', text, re.MULTILINE):
            return True
        if '|' in text and re.search(r'^\|.+\|', text, re.MULTILINE):
            return True
        if cls._IMAGE_RE.search(text):
            return True
        if cls._FOOTNOTE_REF_RE.search(text):
            return True
        return False

    @classmethod
    def _get_indent(cls, line: str) -> int:
        return len(line) - len(line.lstrip())

    @classmethod
    def _text_to_html(cls, text: str) -> str:
        lines = text.split('\n')
        out: list = []
        i = 0
        n = len(lines)
        list_stack: list = []
        quote_buf: list = []
        footnotes: dict = {}

        remaining_lines: list = []
        for line in lines:
            fn_match = cls._FOOTNOTE_DEF_RE.match(line.strip())
            if fn_match:
                footnotes[fn_match.group(1)] = fn_match.group(2)
            else:
                remaining_lines.append(line)
        lines = remaining_lines
        n = len(lines)

        def _flush_all_lists():
            while list_stack:
                _, ltag = list_stack.pop()
                out.append(f'</{ltag}>')

        def _flush_lists_to_indent(target_indent: int):
            while list_stack and list_stack[-1][0] > target_indent:
                _, ltag = list_stack.pop()
                out.append(f'</{ltag}>')

        def _flush_quote():
            nonlocal quote_buf
            if quote_buf:
                q_html = '<br>'.join(cls._inline(q, footnotes) for q in quote_buf)
                out.append(
                    f'<div style="border-left:2px solid rgba(148,163,184,50);padding:8px 14px;'
                    f'margin:8px 0;background:transparent;'
                    f'color:#cbd5e1;border-radius:0 6px 6px 0;'
                    f'line-height:1.6;">{q_html}</div>'
                )
                quote_buf = []

        while i < n:
            raw_line = lines[i]
            s = raw_line.strip()

            if not s:
                _flush_quote()
                _flush_all_lists()
                out.append('<div style="height:4px;"></div>')
                i += 1
                continue

            if re.match(r'^[-*_]{3,}\s*$', s):
                _flush_quote()
                _flush_all_lists()
                out.append(
                    '<hr style="border:none;border-top:1px solid rgba(255,255,255,8);margin:16px 0;width:100%;">'
                )
                i += 1
                continue

            if '|' in s and i + 1 < n and cls._TABLE_SEP_RE.match(lines[i + 1].strip()):
                _flush_quote()
                _flush_all_lists()
                table_html = cls._parse_table(lines, i)
                if table_html:
                    out.append(table_html[0])
                    i = table_html[1]
                    continue

            header_match = re.match(r'^(#{1,4})\s+(.+)', s)
            if header_match:
                _flush_quote()
                _flush_all_lists()
                lvl = len(header_match.group(1))
                content = header_match.group(2)
                styles = {
                    1: ('1.5em', '#f1f5f9', '700', '18px 0 8px 0',
                        'border-bottom:1px solid rgba(255,255,255,12);padding-bottom:8px;letter-spacing:0.3px;'),
                    2: ('1.3em', '#e2e8f0', '600', '16px 0 6px 0', 'letter-spacing:0.2px;'),
                    3: ('1.1em', '#cbd5e1', '600', '12px 0 4px 0', ''),
                    4: ('1.0em', '#94a3b8', '600', '10px 0 3px 0', ''),
                }
                sz, clr, wt, mg, extra = styles[lvl]
                out.append(
                    f'<p style="font-size:{sz};font-weight:{wt};'
                    f'color:{clr};margin:{mg};{extra}">'
                    f'{cls._inline(content, footnotes)}</p>'
                )
                i += 1
                continue

            if s.startswith('> '):
                _flush_all_lists()
                quote_buf.append(s[2:])
                i += 1
                continue
            elif s.startswith('>'):
                _flush_all_lists()
                quote_buf.append(s[1:].lstrip())
                i += 1
                continue
            else:
                _flush_quote()

            task_match = cls._TASK_ITEM_RE.match(raw_line)
            if task_match:
                indent = len(task_match.group(1))
                _flush_lists_to_indent(indent)
                if not list_stack or list_stack[-1][0] < indent:
                    out.append('<ul style="margin:2px 0;padding-left:4px;list-style:none;">')
                    list_stack.append((indent, 'ul'))
                checked = task_match.group(2) in ('x', 'X')
                box = (
                    '<span style="color:#10b981;font-weight:bold;margin-right:6px;">✓</span>'
                    if checked else
                    '<span style="color:#64748b;margin-right:6px;">○</span>'
                )
                text_style = 'color:#64748b;text-decoration:line-through;' if checked else ''
                out.append(
                    f'<li style="margin:4px 0;line-height:1.6;{text_style}">'
                    f'{box}{cls._inline(task_match.group(3), footnotes)}</li>'
                )
                i += 1
                continue

            list_match = cls._LIST_ITEM_RE.match(raw_line)
            if list_match:
                indent = len(list_match.group(1))
                marker = list_match.group(2)
                item_text = list_match.group(3)
                is_ordered = marker[-1] == '.'
                new_tag = 'ol' if is_ordered else 'ul'
                _flush_lists_to_indent(indent)
                if not list_stack or list_stack[-1][0] < indent:
                    if is_ordered:
                        out.append('<ol style="margin:4px 0;padding-left:22px;color:#94a3b8;">')
                    else:
                        out.append(
                            '<ul style="margin:4px 0;padding-left:22px;'
                            'list-style-type:disc;color:#94a3b8;">'
                        )
                    list_stack.append((indent, new_tag))
                elif list_stack[-1][1] != new_tag:
                    old_indent, old_tag = list_stack.pop()
                    out.append(f'</{old_tag}>')
                    if is_ordered:
                        out.append('<ol style="margin:4px 0;padding-left:22px;color:#94a3b8;">')
                    else:
                        out.append(
                            '<ul style="margin:4px 0;padding-left:22px;'
                            'list-style-type:disc;color:#94a3b8;">'
                        )
                    list_stack.append((indent, new_tag))
                out.append(
                    f'<li style="margin:4px 0;line-height:1.6;color:{CursorTheme.TEXT_PRIMARY};">'
                    f'{cls._inline(item_text, footnotes)}</li>'
                )
                i += 1
                continue

            _flush_all_lists()
            out.append(
                f'<p style="margin:4px 0;line-height:1.6;color:#e2e8f0;">'
                f'{cls._inline(s, footnotes)}</p>'
            )
            i += 1

        _flush_quote()
        _flush_all_lists()

        if footnotes:
            out.append(
                '<hr style="border:none;border-top:1px solid rgba(255,255,255,8);'
                'margin:12px 0 6px 0;width:40%;">'
            )
            for fn_id, fn_text in footnotes.items():
                out.append(
                    f'<p style="margin:2px 0;font-size:0.85em;color:{CursorTheme.TEXT_SECONDARY};'
                    f'line-height:1.4;">'
                    f'<sup style="color:#60a5fa;">[{html.escape(fn_id)}]</sup> '
                    f'{cls._inline(fn_text, footnotes)}</p>'
                )
        return '\n'.join(out)

    @classmethod
    def _parse_table(cls, lines: list, start: int) -> tuple:
        header_line = lines[start].strip()
        if start + 1 >= len(lines):
            return None
        sep_line = lines[start + 1].strip()
        sep_cells = [c.strip() for c in sep_line.strip('|').split('|')]
        aligns = []
        for c in sep_cells:
            c = c.strip()
            if c.startswith(':') and c.endswith(':'):
                aligns.append('center')
            elif c.endswith(':'):
                aligns.append('right')
            else:
                aligns.append('left')

        def _parse_row(line: str) -> list:
            line = line.strip()
            if line.startswith('|'):
                line = line[1:]
            if line.endswith('|'):
                line = line[:-1]
            return [c.strip() for c in line.split('|')]

        headers = _parse_row(header_line)
        rows = []
        j = start + 2
        while j < len(lines):
            row_s = lines[j].strip()
            if not row_s or '|' not in row_s:
                break
            rows.append(_parse_row(row_s))
            j += 1

        tbl = [
            '<table style="border-collapse:collapse;margin:10px 0;width:100%;font-size:0.92em;">'
        ]
        tbl.append('<tr>')
        for ci, h in enumerate(headers):
            align = aligns[ci] if ci < len(aligns) else 'left'
            tbl.append(
                f'<th style="border-bottom:2px solid rgba(255,255,255,12);'
                f'padding:7px 14px;background:transparent;color:#e2e8f0;'
                f'font-weight:600;text-align:{align};font-size:0.95em;">{cls._inline(h)}</th>'
            )
        tbl.append('</tr>')
        for ri, row in enumerate(rows):
            tbl.append('<tr>')
            for ci, cell in enumerate(row):
                align = aligns[ci] if ci < len(aligns) else 'left'
                border_bottom = (
                    'border-bottom:1px solid rgba(255,255,255,5);'
                    if ri < len(rows) - 1 else ''
                )
                tbl.append(
                    f'<td style="{border_bottom}padding:7px 14px;'
                    f'background:transparent;color:{CursorTheme.TEXT_PRIMARY};'
                    f'text-align:{align};line-height:1.5;">{cls._inline(cell)}</td>'
                )
            tbl.append('</tr>')
        tbl.append('</table>')
        return ('\n'.join(tbl), j)

    @classmethod
    def _inline(cls, text: str, footnotes: dict = None) -> str:
        _ESC_MAP = {}
        _esc_counter = [0]

        def _replace_escape(m):
            key = f'\x00ESC{_esc_counter[0]}\x00'
            _ESC_MAP[key] = m.group(1)
            _esc_counter[0] += 1
            return key

        text = re.sub(r'\\([\\`*_~\[\]()#>!|])', _replace_escape, text)
        text = html.escape(text)

        text = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            r'<img src="\2" alt="\1" style="max-width:100%;max-height:200px;'
            r'border-radius:4px;margin:2px 0;vertical-align:middle;">',
            text,
        )
        text = re.sub(
            r'\[([^\]]+?)\]\(([^)]+?)\)',
            r'<a href="\2" style="color:#818cf8;text-decoration:none;'
            r'border-bottom:1px solid rgba(129,140,248,0.3);">\1</a>',
            text,
        )
        if footnotes:
            def _fn_ref(m):
                fid = m.group(1)
                if fid in footnotes:
                    return (
                        f'<sup style="color:#818cf8;cursor:pointer;">'
                        f'<a href="#fn-{html.escape(fid)}" style="color:#818cf8;'
                        f'text-decoration:none;">[{html.escape(fid)}]</a></sup>'
                    )
                return m.group(0)
            text = cls._FOOTNOTE_REF_RE.sub(_fn_ref, text)

        text = re.sub(r'\*\*(.+?)\*\*', r'<b style="color:#f1f5f9;font-weight:600;">\1</b>', text)
        text = re.sub(r'~~(.+?)~~', r'<s style="color:#64748b;">\1</s>', text)
        text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<i style="color:#cbd5e1;">\1</i>', text)
        text = re.sub(
            r'`([^`]+?)`',
            r'<code style="background:rgba(255,255,255,8);padding:2px 7px;border-radius:5px;'
            r'font-family:Consolas,Monaco,monospace;color:#c9d1d9;'
            r'font-size:0.88em;border:1px solid rgba(255,255,255,5);">\1</code>',
            text,
        )
        text = cls._AUTO_URL_RE.sub(
            r'<a href="\1" style="color:#818cf8;text-decoration:none;">\1</a>',
            text,
        )
        # Wwise 对象路径 → 可点击链接
        text = _linkify_wwise_paths(text)

        for key, char in _ESC_MAP.items():
            text = text.replace(key, html.escape(char))
        return text


# ============================================================
# 语法高亮器
# ============================================================

class SyntaxHighlighter:
    """代码语法高亮 — 基于 token 的着色

    支持语言: Python, Lua, JSON, YAML, Bash/Shell, JavaScript/TypeScript, GLSL
    """

    COL = {
        'keyword':  '#569CD6',
        'type':     '#4EC9B0',
        'builtin':  '#DCDCAA',
        'string':   '#CE9178',
        'comment':  '#6A9955',
        'number':   '#B5CEA8',
        'attr':     '#9CDCFE',
        'key':      '#9CDCFE',
        'constant': '#569CD6',
        'operator': '#D4D4D4',
        'directive': '#C586C0',
    }

    # ---- Python ----
    PY_KW = frozenset(
        'import from def class return if else elif for while try except finally '
        'with as in not and or is None True False pass break continue raise '
        'yield lambda global nonlocal del assert'.split()
    )
    PY_BI = frozenset(
        'print len range str int float list dict tuple set type isinstance '
        'enumerate zip map filter sorted reversed open super property '
        'staticmethod classmethod hasattr getattr setattr'.split()
    )

    # ---- Lua (for Wwise scripting) ----
    LUA_KW = frozenset(
        'and break do else elseif end false for function goto if in '
        'local nil not or repeat return then true until while'.split()
    )
    LUA_BI = frozenset(
        'assert collectgarbage dofile error getmetatable ipairs load loadfile '
        'next pairs pcall print rawequal rawget rawlen rawset require select '
        'setmetatable tonumber tostring type unpack xpcall '
        'string table math io os coroutine debug package '
        'ak WwiseModule'.split()
    )

    # ---- JavaScript / TypeScript ----
    JS_KW = frozenset(
        'var let const function return if else for while do switch case default '
        'break continue new this typeof instanceof void delete throw try catch '
        'finally class extends import export from as async await yield of in '
        'static get set super'.split()
    )
    JS_TY = frozenset(
        'string number boolean any void never unknown object symbol bigint '
        'undefined null Array Promise Map Set Record Partial Required Readonly '
        'interface type enum namespace'.split()
    )
    JS_BI = frozenset(
        'console log warn error parseInt parseFloat isNaN isFinite '
        'JSON Math Date RegExp Object Array String Number Boolean '
        'setTimeout setInterval clearTimeout clearInterval '
        'fetch require module exports process'.split()
    )

    # ---- Bash / Shell ----
    BASH_KW = frozenset(
        'if then else elif fi for do done while until case esac in '
        'function return exit break continue select'.split()
    )
    BASH_BI = frozenset(
        'echo printf cd ls cp mv rm mkdir rmdir cat grep sed awk find '
        'chmod chown tar gzip gunzip curl wget git pip python node npm '
        'export source alias unalias set unset read eval exec test '
        'true false shift'.split()
    )

    # ---- GLSL ----
    GLSL_KW = frozenset(
        'if else for while do return break continue discard switch case default '
        'struct void const in out inout uniform varying attribute '
        'layout precision highp mediump lowp flat smooth noperspective '
        'centroid sample'.split()
    )
    GLSL_TY = frozenset(
        'float vec2 vec3 vec4 int ivec2 ivec3 ivec4 uint uvec2 uvec3 uvec4 '
        'bool bvec2 bvec3 bvec4 mat2 mat3 mat4 mat2x2 mat2x3 mat2x4 '
        'mat3x2 mat3x3 mat3x4 mat4x2 mat4x3 mat4x4 '
        'sampler1D sampler2D sampler3D samplerCube sampler2DShadow'.split()
    )
    GLSL_BI = frozenset(
        'texture texture2D textureCube normalize length distance dot cross '
        'reflect refract mix clamp smoothstep step min max abs sign floor '
        'ceil fract mod pow exp log sqrt inversesqrt sin cos tan asin acos atan '
        'radians degrees dFdx dFdy fwidth'.split()
    )

    @classmethod
    def highlight_python(cls, code: str) -> str:
        return cls._tokenize(code, cls.PY_KW, frozenset(), cls.PY_BI,
                              '#', None, None)

    @classmethod
    def highlight_lua(cls, code: str) -> str:
        return cls._tokenize(code, cls.LUA_KW, frozenset(), cls.LUA_BI,
                              '--', ('--[[', ']]'), None)

    @classmethod
    def highlight_javascript(cls, code: str) -> str:
        return cls._tokenize(code, cls.JS_KW, cls.JS_TY, cls.JS_BI,
                              '//', ('/*', '*/'), None)

    @classmethod
    def highlight_bash(cls, code: str) -> str:
        return cls._tokenize(code, cls.BASH_KW, frozenset(), cls.BASH_BI,
                              '#', None, '$')

    @classmethod
    def highlight_glsl(cls, code: str) -> str:
        return cls._tokenize(code, cls.GLSL_KW, cls.GLSL_TY, cls.GLSL_BI,
                              '//', ('/*', '*/'), None)

    @classmethod
    def highlight_json(cls, code: str) -> str:
        parts: list = []
        i, n = 0, len(code)
        expect_key = True
        while i < n:
            c = code[i]
            if c in (' ', '\t', '\n', '\r'):
                parts.append(c)
                if c == '\n':
                    expect_key = True
                i += 1
                continue
            if c == '"':
                j = i + 1
                while j < n and code[j] != '"':
                    if code[j] == '\\':
                        j += 1
                    j += 1
                if j < n:
                    j += 1
                s = code[i:j]
                rest = code[j:].lstrip()
                if expect_key and rest.startswith(':'):
                    parts.append(cls._span('key', s))
                    expect_key = False
                else:
                    parts.append(cls._span('string', s))
                i = j
                continue
            if c == ':':
                parts.append(html.escape(c))
                expect_key = False
                i += 1
                continue
            if c == ',':
                parts.append(html.escape(c))
                expect_key = True
                i += 1
                continue
            if c in ('{', '['):
                parts.append(html.escape(c))
                expect_key = True
                i += 1
                continue
            if c in ('}', ']'):
                parts.append(html.escape(c))
                i += 1
                continue
            if c.isdigit() or (c == '-' and i + 1 < n and code[i + 1].isdigit()):
                j = i + 1 if c == '-' else i
                while j < n and (code[j].isdigit() or code[j] in ('.', 'e', 'E', '+', '-')):
                    j += 1
                parts.append(cls._span('number', code[i:j]))
                i = j
                continue
            for kw in ('true', 'false', 'null'):
                if code[i:i + len(kw)] == kw:
                    parts.append(cls._span('constant', kw))
                    i += len(kw)
                    break
            else:
                parts.append(html.escape(c))
                i += 1
        return ''.join(parts)

    @classmethod
    def highlight_yaml(cls, code: str) -> str:
        parts: list = []
        lines = code.split('\n')
        for li, line in enumerate(lines):
            if li > 0:
                parts.append('\n')
            stripped = line.lstrip()
            if stripped.startswith('#'):
                parts.append(cls._span('comment', line))
                continue
            if stripped in ('---', '...'):
                parts.append(cls._span('directive', line))
                continue
            indent = line[:len(line) - len(stripped)]
            if indent:
                parts.append(html.escape(indent))
            colon_pos = stripped.find(':')
            if colon_pos > 0 and (colon_pos + 1 >= len(stripped) or stripped[colon_pos + 1] == ' '):
                key_part = stripped[:colon_pos]
                if key_part.startswith('- '):
                    parts.append(html.escape('- '))
                    key_part = key_part[2:]
                parts.append(cls._span('key', key_part))
                parts.append(html.escape(':'))
                value_part = stripped[colon_pos + 1:]
                if value_part:
                    comment_pos = value_part.find(' #')
                    if comment_pos >= 0:
                        val = value_part[:comment_pos]
                        comment = value_part[comment_pos:]
                        parts.append(cls._highlight_yaml_value(val))
                        parts.append(cls._span('comment', comment))
                    else:
                        parts.append(cls._highlight_yaml_value(value_part))
            else:
                if stripped.startswith('- '):
                    parts.append(html.escape('- '))
                    parts.append(cls._highlight_yaml_value(stripped[2:]))
                else:
                    parts.append(html.escape(stripped))
        return ''.join(parts)

    @classmethod
    def _highlight_yaml_value(cls, value: str) -> str:
        v = value.strip()
        if not v:
            return html.escape(value)
        leading = value[:len(value) - len(value.lstrip())]
        result = html.escape(leading) if leading else ''
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            return result + cls._span('string', v)
        if v.lower() in ('true', 'false', 'yes', 'no', 'on', 'off', 'null', '~'):
            return result + cls._span('constant', v)
        try:
            float(v)
            return result + cls._span('number', v)
        except ValueError:
            pass
        return result + html.escape(v)

    @classmethod
    def _tokenize(cls, code, keywords, types, builtins,
                   comment_single, comment_multi, attr_prefix):
        parts: list = []
        i, n = 0, len(code)
        while i < n:
            c = code[i]
            if comment_single and code[i:i + len(comment_single)] == comment_single:
                end = code.find('\n', i)
                if end == -1:
                    end = n
                parts.append(cls._span('comment', code[i:end]))
                i = end
                continue
            if comment_multi and code[i:i + len(comment_multi[0])] == comment_multi[0]:
                end = code.find(comment_multi[1], i + len(comment_multi[0]))
                end = n if end == -1 else end + len(comment_multi[1])
                parts.append(cls._span('comment', code[i:end]))
                i = end
                continue
            if c in ('"', "'", '`'):
                if c == '`':
                    j = i + 1
                    while j < n and code[j] != '`':
                        if code[j] == '\\':
                            j += 1
                        j += 1
                    if j < n:
                        j += 1
                    parts.append(cls._span('string', code[i:j]))
                    i = j
                    continue
                triple = code[i:i + 3]
                if triple in ('"""', "'''"):
                    end = code.find(triple, i + 3)
                    end = n if end == -1 else end + 3
                    parts.append(cls._span('string', code[i:end]))
                    i = end
                    continue
                j = i + 1
                while j < n and code[j] != c and code[j] != '\n':
                    if code[j] == '\\':
                        j += 1
                    j += 1
                if j < n and code[j] == c:
                    j += 1
                parts.append(cls._span('string', code[i:j]))
                i = j
                continue
            if (attr_prefix and c == attr_prefix
                    and i + 1 < n and (code[i + 1].isalpha() or code[i + 1] == '_')):
                j = i + 1
                while j < n and (code[j].isalnum() or code[j] in ('_', '.')):
                    j += 1
                parts.append(cls._span('attr', code[i:j]))
                i = j
                continue
            if c == '#' and (not comment_single or comment_single != '#'):
                if i == 0 or code[i - 1] == '\n':
                    end = code.find('\n', i)
                    if end == -1:
                        end = n
                    parts.append(cls._span('directive', code[i:end]))
                    i = end
                    continue
            if c.isalpha() or c == '_':
                j = i
                while j < n and (code[j].isalnum() or code[j] == '_'):
                    j += 1
                word = code[i:j]
                if word in keywords:
                    parts.append(cls._span('keyword', word))
                elif word in types:
                    parts.append(cls._span('type', word))
                elif word in builtins:
                    parts.append(cls._span('builtin', word))
                else:
                    parts.append(html.escape(word))
                i = j
                continue
            if c.isdigit() or (c == '.' and i + 1 < n and code[i + 1].isdigit()):
                j = i
                if c == '0' and j + 1 < n and code[j + 1] in ('x', 'X'):
                    j += 2
                    while j < n and (code[j].isdigit() or code[j] in 'abcdefABCDEF'):
                        j += 1
                else:
                    while j < n and (code[j].isdigit() or code[j] in ('.', 'e', 'E', '+', '-', 'f')):
                        if code[j] in ('+', '-') and j > 0 and code[j - 1] not in ('e', 'E'):
                            break
                        j += 1
                parts.append(cls._span('number', code[i:j]))
                i = j
                continue
            parts.append(html.escape(c))
            i += 1
        return ''.join(parts)

    @classmethod
    def _span(cls, tok_type: str, text: str) -> str:
        color = cls.COL.get(tok_type, '#D4D4D4')
        return f'<span style="color:{color};">{html.escape(text)}</span>'


# ============================================================
# 代码块组件
# ============================================================

class CodeBlockWidget(QtWidgets.QFrame):
    """代码块 — 语法高亮 + 行号 + 复制 + 折叠"""

    _COLLAPSE_THRESHOLD = 15
    _LINE_NUM_THRESHOLD = 5
    _MAX_HEIGHT = 400

    def __init__(self, code: str, language: str = "", parent=None):
        super().__init__(parent)
        self._code = code
        self._lang = language.lower()
        self._line_count = code.count('\n') + 1
        self._collapsed = self._line_count > self._COLLAPSE_THRESHOLD
        self._show_line_numbers = self._line_count > self._LINE_NUM_THRESHOLD
        self.setObjectName("CodeBlockWidget")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QtWidgets.QWidget()
        header.setObjectName("codeBlockHeader")
        hl = QtWidgets.QHBoxLayout(header)
        hl.setContentsMargins(8, 3, 4, 3)
        hl.setSpacing(4)

        lang_text = self._lang.upper() or "CODE"
        lang_info = f"{lang_text}"
        if self._line_count > 1:
            lang_info += f"  ({self._line_count} 行)"
        lang_lbl = QtWidgets.QLabel(lang_info)
        lang_lbl.setObjectName("codeBlockLang")
        hl.addWidget(lang_lbl)
        hl.addStretch()

        self._action_btns: list = []

        if self._line_count > self._COLLAPSE_THRESHOLD:
            self._toggle_btn = QtWidgets.QPushButton(
                f"展开 ({self._line_count} 行)" if self._collapsed else "收起"
            )
            self._toggle_btn.setCursor(QtCore.Qt.PointingHandCursor)
            self._toggle_btn.setObjectName("codeBlockBtn")
            self._toggle_btn.clicked.connect(self._toggle_collapse)
            hl.addWidget(self._toggle_btn)

        copy_btn = QtWidgets.QPushButton("复制")
        copy_btn.setCursor(QtCore.Qt.PointingHandCursor)
        copy_btn.setObjectName("codeBlockBtn")
        copy_btn.clicked.connect(self._on_copy)
        copy_btn.setVisible(False)
        hl.addWidget(copy_btn)
        self._action_btns.append(copy_btn)

        layout.addWidget(header)

        self._code_edit = QtWidgets.QTextEdit()
        self._code_edit.setReadOnly(True)
        self._code_edit.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self._code_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._code_edit.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self._code_edit.setObjectName("codeBlockEdit")

        highlighted = self._highlight()
        code_html = self._add_line_numbers(highlighted) if self._show_line_numbers else highlighted
        self._code_edit.setHtml(
            f'<pre style="margin:0;white-space:pre;">{code_html}</pre>'
        )
        doc = self._code_edit.document()
        doc.setDocumentMargin(4)
        self._full_h = int(doc.size().height()) + 20
        fm = self._code_edit.fontMetrics()
        line_h = fm.lineSpacing() if fm.lineSpacing() > 0 else 17
        self._collapsed_h = self._COLLAPSE_THRESHOLD * line_h + 20
        if self._collapsed:
            self._code_edit.setFixedHeight(min(self._collapsed_h, self._MAX_HEIGHT))
            self._code_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        else:
            self._code_edit.setFixedHeight(min(self._full_h, self._MAX_HEIGHT))
        layout.addWidget(self._code_edit)

    def _add_line_numbers(self, highlighted_code: str) -> str:
        lines = highlighted_code.split('\n')
        width = len(str(len(lines)))
        result: list = []
        num_color = '#4a5568'
        sep_color = 'rgba(255,255,255,6)'
        for i, line in enumerate(lines, 1):
            num = str(i).rjust(width)
            result.append(
                f'<span style="color:{num_color};user-select:none;'
                f'padding-right:12px;border-right:1px solid {sep_color};'
                f'margin-right:12px;">{num}</span>{line}'
            )
        return '\n'.join(result)

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self._code_edit.setFixedHeight(min(self._collapsed_h, self._MAX_HEIGHT))
            self._code_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self._code_edit.verticalScrollBar().setValue(0)
            self._toggle_btn.setText(f"展开 ({self._line_count} 行)")
        else:
            self._code_edit.setFixedHeight(min(self._full_h, self._MAX_HEIGHT))
            if self._full_h > self._MAX_HEIGHT:
                self._code_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            else:
                self._code_edit.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self._toggle_btn.setText("收起")

    def _highlight(self) -> str:
        lang = self._lang
        if lang in ('python', 'py'):
            return SyntaxHighlighter.highlight_python(self._code)
        if lang == 'lua':
            return SyntaxHighlighter.highlight_lua(self._code)
        if lang == 'json':
            return SyntaxHighlighter.highlight_json(self._code)
        if lang in ('yaml', 'yml'):
            return SyntaxHighlighter.highlight_yaml(self._code)
        if lang in ('bash', 'sh', 'shell', 'zsh', 'powershell', 'ps1', 'bat', 'cmd'):
            return SyntaxHighlighter.highlight_bash(self._code)
        if lang in ('javascript', 'js', 'typescript', 'ts', 'jsx', 'tsx'):
            return SyntaxHighlighter.highlight_javascript(self._code)
        if lang in ('glsl', 'hlsl', 'shader', 'frag', 'vert', 'wgsl'):
            return SyntaxHighlighter.highlight_glsl(self._code)
        if lang in ('c', 'cpp', 'c++', 'cxx', 'h', 'hpp', 'cs', 'csharp'):
            return SyntaxHighlighter.highlight_glsl(self._code)
        if lang in ('xml', 'html', 'svg'):
            return html.escape(self._code)
        return html.escape(self._code)

    def enterEvent(self, event):
        for btn in self._action_btns:
            btn.setVisible(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        for btn in self._action_btns:
            btn.setVisible(False)
        super().leaveEvent(event)

    def _on_copy(self):
        QtWidgets.QApplication.clipboard().setText(self._code)
        btn = self.sender()
        if btn:
            btn.setText("已复制")
            QtCore.QTimer.singleShot(1500, lambda: btn.setText("复制"))


# ============================================================
# 富文本内容组件
# ============================================================

class RichContentWidget(QtWidgets.QWidget):
    """渲染 Markdown 文本 + 交互式代码块"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        segments = SimpleMarkdown.parse_segments(text)
        for seg in segments:
            if seg[0] == 'text':
                lbl = QtWidgets.QLabel()
                lbl.setWordWrap(True)
                lbl.setTextFormat(QtCore.Qt.RichText)
                lbl.setOpenExternalLinks(False)
                lbl.setTextInteractionFlags(
                    QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse
                )
                lbl.setText(seg[1])
                lbl.setObjectName("richText")
                lbl.linkActivated.connect(self._on_link)
                layout.addWidget(lbl)
            elif seg[0] == 'code':
                cb = CodeBlockWidget(seg[2], seg[1], self)
                cb.setContentsMargins(0, 6, 0, 6)
                layout.addWidget(cb)
            elif seg[0] == 'image':
                img_url = seg[1]
                img_alt = seg[2] if len(seg) > 2 else ''
                img_lbl = QtWidgets.QLabel()
                img_lbl.setObjectName("richImage")
                img_lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
                img_lbl.setWordWrap(False)
                img_lbl.setText(
                    f'<div style="margin:4px 0;">'
                    f'<img src="{html.escape(img_url)}" '
                    f'alt="{html.escape(img_alt)}" '
                    f'style="max-width:100%;max-height:300px;border-radius:6px;">'
                    f'</div>'
                )
                img_lbl.setTextFormat(QtCore.Qt.RichText)
                layout.addWidget(img_lbl)

    def _on_link(self, url: str):
        if url.startswith('wwise://'):
            pass  # Wwise 路径由外部处理
        else:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


# ============================================================
# 输入区域
# ============================================================

class ChatInput(QtWidgets.QPlainTextEdit):
    """聊天输入框 — 自适应高度，支持图片粘贴/拖拽"""

    sendRequested = QtCore.Signal()
    imageDropped = QtCore.Signal(QtGui.QImage)

    _MIN_H = 44
    _MAX_H = 220

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(tr('placeholder'))
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.setWordWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)
        self.setObjectName("chatInput")
        self.setMinimumHeight(self._MIN_H)
        self.setMaximumHeight(self._MAX_H)
        self.textChanged.connect(self._schedule_adjust)

    def _schedule_adjust(self):
        QtCore.QTimer.singleShot(0, self._adjust_height)

    def _adjust_height(self):
        doc = self.document()
        visual_lines = 0
        block = doc.begin()
        while block.isValid():
            bl = block.layout()
            if bl and bl.lineCount() > 0:
                visual_lines += bl.lineCount()
            else:
                visual_lines += 1
            block = block.next()
        visual_lines = max(1, visual_lines)
        line_h = self.fontMetrics().lineSpacing()
        content_h = visual_lines * line_h
        margins = self.contentsMargins()
        frame_w = self.frameWidth()
        padding = margins.top() + margins.bottom() + frame_w * 2 + 18
        total = content_h + padding
        h = max(self._MIN_H, min(self._MAX_H, total))
        if h != self.height():
            self.setFixedHeight(h)
            self.updateGeometry()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if event.modifiers() & QtCore.Qt.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.sendRequested.emit()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_adjust()

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage() or mime.hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage():
            image = mime.imageData()
            if image and not image.isNull():
                self.imageDropped.emit(image)
                event.acceptProposedAction()
                return
        if mime.hasUrls():
            _IMG_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
            for url in mime.urls():
                if url.isLocalFile():
                    import os
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in _IMG_EXTS:
                        img = QtGui.QImage(url.toLocalFile())
                        if not img.isNull():
                            self.imageDropped.emit(img)
                            event.acceptProposedAction()
                            return
        super().dropEvent(event)

    def insertFromMimeData(self, source):
        if source.hasImage():
            image = source.imageData()
            if image and not image.isNull():
                self.imageDropped.emit(image)
                return
        if source.hasUrls():
            _IMG_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}
            for url in source.urls():
                if url.isLocalFile():
                    import os
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in _IMG_EXTS:
                        img = QtGui.QImage(url.toLocalFile())
                        if not img.isNull():
                            self.imageDropped.emit(img)
                            return
        super().insertFromMimeData(source)


# ============================================================
# 停止/发送按钮
# ============================================================

class StopButton(QtWidgets.QPushButton):
    def __init__(self, parent=None):
        super().__init__("Stop", parent)
        self.setObjectName("btnStop")


class SendButton(QtWidgets.QPushButton):
    def __init__(self, parent=None):
        super().__init__("Send", parent)
        self.setObjectName("btnSend")


# ============================================================
# Todo 系统
# ============================================================

class TodoItem(QtWidgets.QWidget):
    """单个 Todo 项"""

    statusChanged = QtCore.Signal(str, str)

    def __init__(self, todo_id: str, text: str, status: str = "pending", parent=None):
        super().__init__(parent)
        self.todo_id = todo_id
        self.text = text
        self.status = status

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(4)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setFixedWidth(14)
        layout.addWidget(self.status_label)

        self.text_label = QtWidgets.QLabel(text)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, 1)

        self._update_style()

    def _update_style(self):
        icons = {"pending": "○", "in_progress": "◎", "done": "●", "error": "✗"}
        icon = icons.get(self.status, "○")
        self.status_label.setText(icon)
        self.status_label.setObjectName("todoStatusIcon")
        self.status_label.setProperty("state", self.status)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.text_label.setObjectName("todoText")
        self.text_label.setProperty("state", self.status)
        self.text_label.style().unpolish(self.text_label)
        self.text_label.style().polish(self.text_label)

    def set_status(self, status: str):
        self.status = status
        self._update_style()
        self.statusChanged.emit(self.todo_id, status)


class TodoList(QtWidgets.QWidget):
    """Todo 列表 - 显示 AI 的任务计划"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._todos = {}

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(0)

        self._card = QtWidgets.QFrame(self)
        self._card.setObjectName("todoCard")
        card_layout = QtWidgets.QVBoxLayout(self._card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(4)

        header = QtWidgets.QHBoxLayout()
        header.setSpacing(6)
        self.title_label = QtWidgets.QLabel("Todo")
        self.title_label.setObjectName("todoTitle")
        header.addWidget(self.title_label)
        self.count_label = QtWidgets.QLabel("0/0")
        self.count_label.setObjectName("todoCount")
        header.addWidget(self.count_label)
        header.addStretch()
        self.clear_btn = QtWidgets.QPushButton("Clear")
        self.clear_btn.setFixedHeight(20)
        self.clear_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.clear_btn.setObjectName("todoClearBtn")
        self.clear_btn.clicked.connect(self.clear_all)
        header.addWidget(self.clear_btn)
        card_layout.addLayout(header)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setObjectName("todoSeparator")
        card_layout.addWidget(sep)

        self.list_layout = QtWidgets.QVBoxLayout()
        self.list_layout.setSpacing(2)
        self.list_layout.setContentsMargins(0, 2, 0, 0)
        card_layout.addLayout(self.list_layout)

        outer.addWidget(self._card)
        self.setVisible(False)

    def add_todo(self, todo_id: str, text: str, status: str = "pending") -> TodoItem:
        if todo_id in self._todos:
            self._todos[todo_id].text_label.setText(text)
            self._todos[todo_id].set_status(status)
            return self._todos[todo_id]
        item = TodoItem(todo_id, text, status, self)
        self._todos[todo_id] = item
        self.list_layout.addWidget(item)
        self._update_count()
        self.setVisible(True)
        return item

    def update_todo(self, todo_id: str, status: str):
        if todo_id in self._todos:
            self._todos[todo_id].set_status(status)
            self._update_count()

    def remove_todo(self, todo_id: str):
        if todo_id in self._todos:
            item = self._todos.pop(todo_id)
            item.deleteLater()
            self._update_count()
            if not self._todos:
                self.setVisible(False)

    def clear_all(self):
        for item in self._todos.values():
            item.deleteLater()
        self._todos.clear()
        self._update_count()
        self.setVisible(False)

    def _update_count(self):
        total = len(self._todos)
        done = sum(1 for item in self._todos.values() if item.status == "done")
        self.count_label.setText(f"{done}/{total}")

    def get_pending_todos(self) -> list:
        return [
            {"id": todo_id, "text": item.text, "status": item.status}
            for todo_id, item in self._todos.items()
            if item.status not in ("done", "error")
        ]

    def get_all_todos(self) -> list:
        return [
            {"id": todo_id, "text": item.text, "status": item.status}
            for todo_id, item in self._todos.items()
        ]

    def get_todos_data(self) -> list:
        return [
            {"id": todo_id, "text": item.text, "status": item.status}
            for todo_id, item in self._todos.items()
        ]

    def restore_todos(self, todos_data: list):
        if not todos_data:
            return
        for td in todos_data:
            tid = td.get('id', '')
            text = td.get('text', '')
            status = td.get('status', 'pending')
            if tid and text:
                self.add_todo(tid, text, status)

    def get_todos_summary(self) -> str:
        if not self._todos:
            return ""
        lines = ["Current Todo List:"]
        for todo_id, item in self._todos.items():
            status_icons = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]", "error": "[!]"}
            icon = status_icons.get(item.status, "[ ]")
            lines.append(f"  {icon} {item.text}")
        pending = [item for item in self._todos.values() if item.status == "pending"]
        if pending:
            lines.append(f"\nReminder: {len(pending)} tasks pending.")
        return "\n".join(lines)


# ============================================================
# 统一状态指示栏
# ============================================================

class UnifiedStatusBar(QtWidgets.QWidget):
    """统一状态指示栏 — 合并思考状态、生成状态和工具执行状态"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        self.setObjectName("unifiedStatusBar")
        self.setVisible(False)
        self._mode = None
        self._elapsed = 0.0
        self._phase = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def start(self):
        self._mode = 'thinking'
        self._elapsed = 0.0
        self._phase = 0.0
        self.setVisible(True)
        self._timer.start()
        self.update()

    def stop(self):
        self._mode = None
        self._timer.stop()
        self.setVisible(False)

    def set_elapsed(self, seconds: float):
        self._elapsed = seconds
        self.update()

    def show_generating(self):
        self._mode = 'generating'
        self._phase = 0.0
        self.setVisible(True)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def show_tool(self, tool_name: str):
        self._mode = 'tool'
        self._tool_name = tool_name
        self._phase = 0.0
        self.setVisible(True)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def hide_tool(self):
        if self._mode == 'tool':
            self.show_generating()

    def _tick(self):
        self._phase += 0.025
        if self._phase > 1.0:
            self._phase -= 1.0
        self.update()

    def paintEvent(self, event):
        if self._mode == 'thinking':
            self._paint_sweep(event, "Thinking", self._elapsed, (100, 116, 139), (226, 232, 240))
        elif self._mode == 'generating':
            self._paint_sweep(event, "Generating...", 0, (139, 116, 100), (240, 232, 220))
        elif self._mode == 'tool':
            tool_name = getattr(self, '_tool_name', '')
            text = f"Exec: {tool_name}" if tool_name else "Executing..."
            self._paint_sweep(event, text, 0, (170, 145, 100), (230, 210, 170))

    def _paint_sweep(self, event, label: str, elapsed: float,
                     base_rgb: tuple, glow_rgb: tuple):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        text = f"{label} {elapsed:.1f}s" if elapsed > 0 else f"{label}..."
        font = QtGui.QFont(CursorTheme.FONT_BODY, 10)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        x = (w - tw) // 2
        y = (h + fm.ascent() - fm.descent()) // 2
        br, bg_, bb = base_rgb
        p.setPen(QtGui.QColor(br, bg_, bb, 120))
        p.drawText(x, y, text)
        gr, gg, gb = glow_rgb
        grad = QtGui.QLinearGradient(x, 0, x + tw, 0)
        pos = self._phase
        before = max(0.0, pos - 0.15)
        after = min(1.0, pos + 0.15)
        grad.setColorAt(0.0, QtGui.QColor(gr, gg, gb, 0))
        if before > 0:
            grad.setColorAt(before, QtGui.QColor(gr, gg, gb, 0))
        grad.setColorAt(pos, QtGui.QColor(gr, gg, gb, 200))
        if after < 1.0:
            grad.setColorAt(after, QtGui.QColor(gr, gg, gb, 0))
        grad.setColorAt(1.0, QtGui.QColor(gr, gg, gb, 0))
        p.setPen(QtGui.QPen(QtGui.QBrush(grad), 0))
        p.drawText(x, y, text)
        p.end()


# ============================================================
# Token Analytics Panel
# ============================================================

class _BarWidget(QtWidgets.QWidget):
    """水平柱状图条"""

    def __init__(self, segments: list, max_val: float, parent=None):
        super().__init__(parent)
        self._segments = segments
        self._max = max(max_val, 1)
        self.setFixedHeight(14)
        self.setMinimumWidth(60)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w = self.width()
        h = self.height()
        x = 0.0
        for val, color in self._segments:
            seg_w = (val / self._max) * w
            if seg_w < 0.5:
                continue
            painter.setBrush(QtGui.QColor(color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRoundedRect(QtCore.QRectF(x, 1, seg_w, h - 2), 2, 2)
            x += seg_w
        painter.end()


class TokenAnalyticsPanel(QtWidgets.QDialog):
    """Token 使用分析面板"""

    _COL_HEADERS = [
        "#", "时间", "模型", "Input", "Cache↓", "Cache↑",
        "Output", "Think", "Total", "延迟", "费用", "",
    ]

    def __init__(self, call_records: list, token_stats: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Token 使用分析")
        self.setMinimumSize(920, 560)
        self.resize(1020, 640)
        self.setObjectName("tokenPanel")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(12)
        root.addWidget(self._build_summary(call_records, token_stats))
        root.addWidget(self._build_table(call_records), 1)

        self.should_reset_stats = False
        foot = QtWidgets.QHBoxLayout()
        foot.setContentsMargins(0, 0, 0, 0)
        reset_btn = QtWidgets.QPushButton("重置统计")
        reset_btn.setFixedWidth(82)
        reset_btn.setObjectName("tokenResetBtn")
        reset_btn.clicked.connect(self._on_reset)
        foot.addWidget(reset_btn)
        foot.addStretch()
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.setFixedWidth(72)
        close_btn.setObjectName("tokenCloseBtn")
        close_btn.clicked.connect(self.accept)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    def _on_reset(self):
        self.should_reset_stats = True
        self.accept()

    def _build_summary(self, records, stats) -> QtWidgets.QWidget:
        card = QtWidgets.QFrame()
        card.setObjectName("tokenSummaryCard")
        grid = QtWidgets.QGridLayout(card)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)

        total_in = stats.get('input_tokens', 0)
        total_out = stats.get('output_tokens', 0)
        reasoning = stats.get('reasoning_tokens', 0)
        cache_r = stats.get('cache_read', 0)
        cache_w = stats.get('cache_write', 0)
        reqs = stats.get('requests', 0)
        total = stats.get('total_tokens', 0)
        cost = stats.get('estimated_cost', 0.0)
        cache_total = cache_r + cache_w
        hit_rate = (cache_r / cache_total * 100) if cache_total > 0 else 0
        latencies = [r.get('latency', 0) for r in records if r.get('latency', 0) > 0]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        if cost >= 1.0:
            cost_str = f"${cost:.2f}"
        elif cost > 0:
            cost_str = f"${cost:.4f}"
        else:
            cost_str = "$0.00"

        metrics = [
            ("Requests",    f"{reqs}",              CursorTheme.ACCENT_BLUE),
            ("Input",       self._fmt_k(total_in),   CursorTheme.ACCENT_PURPLE),
            ("Output",      self._fmt_k(total_out),  CursorTheme.ACCENT_GREEN),
            ("Reasoning",   self._fmt_k(reasoning),  CursorTheme.ACCENT_YELLOW),
            ("Cache Hit",   self._fmt_k(cache_r),    "#10b981"),
            ("Hit Rate",    f"{hit_rate:.1f}%",      "#10b981"),
            ("Avg Latency", f"{avg_latency:.1f}s",   CursorTheme.TEXT_SECONDARY),
            ("Est. Cost",   cost_str,                CursorTheme.ACCENT_BLUE),
        ]
        for col, (label, value, color) in enumerate(metrics):
            lbl = QtWidgets.QLabel(label)
            lbl.setObjectName("tokenMetricLabel")
            lbl.setAlignment(QtCore.Qt.AlignCenter)
            grid.addWidget(lbl, 0, col)
            val = QtWidgets.QLabel(value)
            val.setObjectName("tokenMetricValue")
            val.setStyleSheet(f"color:{color};")
            val.setAlignment(QtCore.Qt.AlignCenter)
            grid.addWidget(val, 1, col)

        if total > 0:
            bar = _BarWidget([
                (cache_r, "#10b981"),
                (cache_w, CursorTheme.ACCENT_ORANGE),
                (max(total_in - cache_r - cache_w, 0), CursorTheme.ACCENT_PURPLE),
                (reasoning, CursorTheme.ACCENT_YELLOW),
                (max(total_out - reasoning, 0), CursorTheme.ACCENT_GREEN),
            ], total)
            bar.setFixedHeight(8)
            grid.addWidget(bar, 2, 0, 1, len(metrics))
        return card

    def _build_table(self, records) -> QtWidgets.QWidget:
        container = QtWidgets.QFrame()
        container.setObjectName("tokenTableCard")
        vbox = QtWidgets.QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        title_lbl = QtWidgets.QLabel(f"  调用明细 ({len(records)} calls)")
        title_lbl.setObjectName("tokenTableTitle")
        vbox.addWidget(title_lbl)
        if not records:
            empty = QtWidgets.QLabel("  暂无 API 调用记录")
            empty.setObjectName("tokenTableEmpty")
            vbox.addWidget(empty)
            return container
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        scroll.setObjectName("chatScrollArea")
        table_widget = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(table_widget)
        table_layout.setContentsMargins(8, 0, 8, 8)
        table_layout.setSpacing(0)
        hdr = self._make_row_widget(self._COL_HEADERS, is_header=True)
        table_layout.addWidget(hdr)
        max_total = max((r.get('total_tokens', 0) for r in records), default=1)
        for display_idx, (orig_idx, rec) in enumerate(reversed(list(enumerate(records)))):
            row = self._make_record_row(orig_idx, rec, max_total)
            table_layout.addWidget(row)
        table_layout.addStretch()
        scroll.setWidget(table_widget)
        vbox.addWidget(scroll, 1)
        return container

    _COL_WIDTHS = [24, 50, 90, 54, 54, 54, 54, 48, 54, 44, 52, 0]

    def _make_row_widget(self, cells: list, is_header=False) -> QtWidgets.QWidget:
        row_w = QtWidgets.QWidget()
        row_h = QtWidgets.QHBoxLayout(row_w)
        row_h.setContentsMargins(4, 3, 4, 3)
        row_h.setSpacing(2)
        widths = self._COL_WIDTHS
        for i, text in enumerate(cells):
            lbl = QtWidgets.QLabel(str(text))
            lbl.setObjectName("tokenHeaderCell" if is_header else "tokenDataCell")
            if i < len(widths) and widths[i] > 0:
                lbl.setFixedWidth(widths[i])
            lbl.setAlignment(QtCore.Qt.AlignRight if 3 <= i <= 10 else QtCore.Qt.AlignLeft)
            if i < len(widths) and widths[i] == 0:
                row_h.addWidget(lbl, 1)
            else:
                row_h.addWidget(lbl)
        if is_header:
            row_w.setObjectName("tokenHeaderRow")
        return row_w

    def _make_record_row(self, idx: int, rec: dict, max_total: float) -> QtWidgets.QWidget:
        row_w = QtWidgets.QWidget()
        row_w.setObjectName("tokenDataRow")
        row_h = QtWidgets.QHBoxLayout(row_w)
        row_h.setContentsMargins(4, 2, 4, 2)
        row_h.setSpacing(2)

        ts = rec.get('timestamp', '')
        if len(ts) > 10:
            ts = ts[11:19]
        model = rec.get('model', '-')
        if len(model) > 12:
            model = model[:10] + '..'
        inp = rec.get('input_tokens', 0)
        c_hit = rec.get('cache_hit', 0)
        c_miss = rec.get('cache_miss', 0)
        out = rec.get('output_tokens', 0)
        reasoning = rec.get('reasoning_tokens', 0)
        total = rec.get('total_tokens', 0)
        latency = rec.get('latency', 0)
        row_cost = rec.get('estimated_cost', 0.0)
        if not row_cost:
            try:
                from wwise_agent.utils.token_optimizer import calculate_cost
                row_cost = calculate_cost(
                    model=rec.get('model', ''),
                    input_tokens=inp, output_tokens=out,
                    cache_hit=c_hit, cache_miss=c_miss,
                    reasoning_tokens=reasoning,
                )
            except Exception:
                row_cost = 0.0
        cost_str = f"${row_cost:.4f}" if row_cost > 0 else "-"
        latency_str = f"{latency:.1f}s" if latency > 0 else "-"

        cells = [
            str(idx + 1), ts, model,
            self._fmt_k(inp), self._fmt_k(c_hit), self._fmt_k(c_miss),
            self._fmt_k(out),
            self._fmt_k(reasoning) if reasoning > 0 else "-",
            self._fmt_k(total), latency_str, cost_str,
        ]
        widths = self._COL_WIDTHS[:-1]
        colors = [
            CursorTheme.TEXT_MUTED, CursorTheme.TEXT_MUTED, CursorTheme.TEXT_PRIMARY,
            CursorTheme.ACCENT_PURPLE, "#10b981", CursorTheme.ACCENT_ORANGE,
            CursorTheme.ACCENT_GREEN, CursorTheme.ACCENT_YELLOW,
            CursorTheme.TEXT_BRIGHT, CursorTheme.TEXT_SECONDARY, CursorTheme.ACCENT_BLUE,
        ]
        for i, text in enumerate(cells):
            lbl = QtWidgets.QLabel(text)
            lbl.setObjectName("tokenDataCell")
            if i < len(widths):
                lbl.setFixedWidth(widths[i])
            align = QtCore.Qt.AlignRight if i >= 3 else QtCore.Qt.AlignLeft
            lbl.setAlignment(align)
            c = colors[i] if i < len(colors) else CursorTheme.TEXT_PRIMARY
            lbl.setStyleSheet(f"color:{c};")
            row_h.addWidget(lbl)

        bar = _BarWidget([
            (c_hit, "#10b981"),
            (c_miss, CursorTheme.ACCENT_ORANGE),
            (max(inp - c_hit - c_miss, 0), CursorTheme.ACCENT_PURPLE),
            (reasoning, CursorTheme.ACCENT_YELLOW),
            (max(out - reasoning, 0), CursorTheme.ACCENT_GREEN),
        ], max_total)
        row_h.addWidget(bar, 1)
        return row_w

    @staticmethod
    def _fmt_k(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 10_000:
            return f"{n / 1000:.1f}K"
        if n >= 1000:
            return f"{n / 1000:.1f}K"
        return str(n)
