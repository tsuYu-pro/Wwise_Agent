#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Wwise Agent — 启动器

用法:
    python launcher.py                         # GUI 模式（默认）
    python launcher.py --headless              # 无头模式（API Server only，供 UE 插件调用）
    python launcher.py --headless --port 8765  # 指定端口
"""

import sys
import argparse
from pathlib import Path

# 确保项目根目录在 sys.path（支持直接 python launcher.py 启动）
_root = Path(__file__).parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def main():
    parser = argparse.ArgumentParser(description="Wwise Agent Launcher")
    parser.add_argument("--headless", action="store_true",
                        help="Run in headless/server mode (no GUI, API server only)")
    parser.add_argument("--port", type=int, default=8765,
                        help="API server port (default: 8765)")
    args = parser.parse_args()

    if args.headless:
        from wwise_agent.api_server import run_headless
        run_headless(port=args.port)
    else:
        from wwise_agent.main import main as _main
        _main()


if __name__ == '__main__':
    main()
