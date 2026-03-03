# -*- coding: utf-8 -*-
"""
Wwise Agent - 主窗口
支持工作区保存/恢复（窗口状态 + 上下文缓存）
"""

import os
import json
import atexit
from pathlib import Path
from wwise_agent.qt_compat import QtWidgets, QtGui, QtCore
from wwise_agent.ui.ai_tab import AITab


class MainWindow(QtWidgets.QMainWindow):
    """Wwise Agent 主窗口"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Wwise Agent")
        self.setMinimumSize(420, 600)
        
        # 工作区配置目录
        self._workspace_dir = Path(__file__).parent.parent.parent / "cache" / "workspace"
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        self._workspace_file = self._workspace_dir / "workspace.json"
        
        self.setWindowFlags(QtCore.Qt.Window)
        
        # 深邃蓝黑背景（与 aiTab glassmorphism 主题匹配）
        self.setStyleSheet("QMainWindow { background-color: #0a0a12; }")
        
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        
        self.force_quit = False
        self._already_saved = False
        
        self.init_ui(central_widget)
        
        # 加载工作区（窗口状态 + 上下文）
        self._load_workspace()
        
        # 注册退出保存钩子
        app = QtWidgets.QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._on_app_about_to_quit)
        atexit.register(self._atexit_save)

    def init_ui(self, central_widget):
        """初始化UI"""
        layout = QtWidgets.QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.ai_tab = AITab(workspace_dir=self._workspace_dir)
        layout.addWidget(self.ai_tab)

    def force_quit_application(self):
        """强制退出应用程序"""
        self.force_quit = True
        self.close()

    def _save_workspace(self):
        """保存工作区（窗口状态 + 所有会话缓存）"""
        try:
            geometry = self.geometry()
            window_state = {
                'x': geometry.x(),
                'y': geometry.y(),
                'width': geometry.width(),
                'height': geometry.height(),
                'is_maximized': self.isMaximized()
            }
            
            has_sessions = False
            tab_count = 0
            if hasattr(self, 'ai_tab') and self.ai_tab:
                has_sessions = self.ai_tab._save_all_sessions()
                tab_count = self.ai_tab.session_tabs.count()
            
            workspace_data = {
                'version': '1.1',
                'window_state': window_state,
                'cache_info': {
                    'has_conversation': has_sessions,
                    'tab_count': tab_count,
                    'use_manifest': True,
                }
            }
            
            with open(self._workspace_file, 'w', encoding='utf-8') as f:
                json.dump(workspace_data, f, ensure_ascii=False, indent=2)
            
            print(f"[Workspace] Saved: window({window_state['width']}x{window_state['height']}), {tab_count} session tabs")
            
        except Exception as e:
            print(f"[Workspace] Save failed: {str(e)}")
    
    def _load_workspace(self):
        """加载工作区（窗口状态 + 上下文缓存）"""
        try:
            if not self._workspace_file.exists():
                self.resize(450, 700)
                return
            
            with open(self._workspace_file, 'r', encoding='utf-8') as f:
                workspace_data = json.load(f)
            
            window_state = workspace_data.get('window_state', {})
            if window_state:
                x = window_state.get('x', 100)
                y = window_state.get('y', 100)
                width = window_state.get('width', 450)
                height = window_state.get('height', 700)
                is_maximized = window_state.get('is_maximized', False)
                
                self.setGeometry(x, y, width, height)
                if is_maximized:
                    self.setWindowState(QtCore.Qt.WindowMaximized)
            
            if hasattr(self, 'ai_tab'):
                QtCore.QTimer.singleShot(200, self._load_workspace_cache)
            
            print(f"[Workspace] Loaded: {self._workspace_file}")
            
        except Exception as e:
            print(f"[Workspace] Load failed: {str(e)}")
            self.resize(450, 700)
    
    def _load_workspace_cache(self):
        """延迟加载工作区缓存"""
        try:
            if not hasattr(self, 'ai_tab'):
                return
            
            if self.ai_tab._restore_all_sessions():
                return
            
            cache_dir = self.ai_tab._cache_dir
            latest_cache = cache_dir / "cache_latest.json"
            if latest_cache.exists():
                self.ai_tab._load_cache_silent(latest_cache)
        except Exception as e:
            print(f"[Workspace] Cache load failed: {str(e)}")
    
    def _on_app_about_to_quit(self):
        self._save_workspace_once()
    
    def _atexit_save(self):
        self._save_workspace_once()
    
    def _save_workspace_once(self):
        """确保退出时只保存一次"""
        if self._already_saved:
            return
        self._already_saved = True
        try:
            self._save_workspace()
        except Exception as e:
            print(f"[Workspace] Exit save failed: {e}")
    
    def closeEvent(self, event):
        self._save_workspace()
        event.accept()
        super().closeEvent(event)
