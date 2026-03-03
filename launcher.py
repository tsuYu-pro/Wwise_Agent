#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wwise Agent — 启动器
用法: python launcher.py
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path（支持直接 python launcher.py 启动）
_root = Path(__file__).parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def main():
    from wwise_agent.main import main as _main
    _main()


if __name__ == '__main__':
    main()
