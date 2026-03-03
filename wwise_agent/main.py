# -*- coding: utf-8 -*-
"""
Wwise Agent — 主入口模块
从 launcher.py 调用，或直接 python -m wwise_agent.main 启动
"""

import sys
from pathlib import Path


def main():
    """启动 Wwise Agent 主窗口"""
    # 确保项目根目录在 sys.path
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    from wwise_agent.qt_compat import QtWidgets, QtCore
    
    app = QtWidgets.QApplication.instance()
    standalone = app is None
    if standalone:
        app = QtWidgets.QApplication(sys.argv)
        app.setApplicationName("Wwise Agent")
        app.setOrganizationName("WwiseAI")
    
    # 设置高 DPI 缩放（Qt5 兼容）
    try:
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass  # Qt6 默认启用
    
    from wwise_agent.core.main_window import MainWindow
    
    window = MainWindow()
    window.show()
    
    if standalone:
        sys.exit(app.exec_() if hasattr(app, 'exec_') else app.exec())


if __name__ == '__main__':
    main()
