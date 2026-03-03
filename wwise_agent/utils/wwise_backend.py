# -*- coding: utf-8 -*-
"""
Wwise Backend — 工具执行器

将 AI 的 Function Calling tool_call 分派到 wwise_mcp.tools.* 异步函数，
通过 call_sync() 在 Agent 后台线程中同步执行。
"""

import json
import asyncio
import logging
from typing import Any, Dict, Optional, Callable

logger = logging.getLogger("wwise_agent.backend")


class WwiseToolExecutor:
    """Wwise 工具执行器 — 替代 Houdini-Agent 中的 HoudiniMCP 角色。

    所有 wwise_mcp 工具函数都是 async def，本执行器通过
    ``asyncio.run()`` 或已有事件循环的 ``run_until_complete()``
    将其转为同步调用，供 Agent 后台线程使用。
    """

    # ---- 工具名 → 异步函数的映射 ----
    _TOOL_MAP: Dict[str, Callable[..., Any]] = {}

    def __init__(self):
        if not self._TOOL_MAP:
            self._build_tool_map()

    @classmethod
    def _build_tool_map(cls):
        """延迟构建工具映射（避免导入时循环依赖）"""
        from wwise_mcp.tools.query import (
            get_project_hierarchy,
            get_object_properties,
            search_objects,
            get_bus_topology,
            get_event_actions,
            get_soundbank_info,
            get_rtpc_list,
            get_selected_objects,
            get_effect_chain,
        )
        from wwise_mcp.tools.action import (
            create_object,
            set_property,
            create_event,
            assign_bus,
            delete_object,
            move_object,
            preview_event,
            set_rtpc_binding,
            add_effect,
            remove_effect,
        )
        from wwise_mcp.tools.verify import (
            verify_structure,
            verify_event_completeness,
        )
        from wwise_mcp.tools.fallback import execute_waapi

        cls._TOOL_MAP = {
            # Query (9)
            "get_project_hierarchy": get_project_hierarchy,
            "get_object_properties": get_object_properties,
            "search_objects": search_objects,
            "get_bus_topology": get_bus_topology,
            "get_event_actions": get_event_actions,
            "get_soundbank_info": get_soundbank_info,
            "get_rtpc_list": get_rtpc_list,
            "get_selected_objects": get_selected_objects,
            "get_effect_chain": get_effect_chain,
            # Action (10)
            "create_object": create_object,
            "set_property": set_property,
            "create_event": create_event,
            "assign_bus": assign_bus,
            "delete_object": delete_object,
            "move_object": move_object,
            "preview_event": preview_event,
            "set_rtpc_binding": set_rtpc_binding,
            "add_effect": add_effect,
            "remove_effect": remove_effect,
            # Verify (2)
            "verify_structure": verify_structure,
            "verify_event_completeness": verify_event_completeness,
            # Fallback (1)
            "execute_waapi": execute_waapi,
        }

    # ------------------------------------------------------------------ #
    # 同步执行入口（供 AIClient.agent_loop 的 tool_executor 回调使用）
    # ------------------------------------------------------------------ #

    def execute(self, tool_name: str, **kwargs) -> dict:
        """同步执行工具（从后台线程调用）

        返回格式与 Houdini-Agent 兼容::
            {"success": True/False, "result": str, "error": str}
        """
        func = self._TOOL_MAP.get(tool_name)
        if func is None:
            return {"success": False, "error": f"未知工具: {tool_name}"}

        try:
            # 优先使用现有事件循环（Wwise Agent 主线程可能已有）
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # 在已有事件循环中，用 run_coroutine_threadsafe
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(func(**kwargs), loop)
                raw = future.result(timeout=60)
            else:
                raw = asyncio.run(func(**kwargs))

        except Exception as e:
            logger.error("工具 %s 执行异常: %s", tool_name, e, exc_info=True)
            return {"success": False, "error": str(e)}

        # 统一转换返回格式
        return self._normalize(raw, tool_name)

    # ------------------------------------------------------------------ #
    # 格式标准化
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize(raw: dict, tool_name: str) -> dict:
        """将 wwise_mcp 的 {success, data, error} 转为
        AIClient 期望的 {success, result, error} 字符串格式。
        """
        if not isinstance(raw, dict):
            return {"success": False, "error": f"工具 {tool_name} 返回了非 dict 类型: {type(raw)}"}

        success = raw.get("success", False)

        if success:
            data = raw.get("data")
            if data is None:
                result_str = "操作成功"
            elif isinstance(data, str):
                result_str = data
            else:
                try:
                    result_str = json.dumps(data, ensure_ascii=False, indent=2)
                except (TypeError, ValueError):
                    result_str = str(data)
            return {"success": True, "result": result_str}
        else:
            err = raw.get("error")
            if isinstance(err, dict):
                msg = err.get("message", "")
                suggestion = err.get("suggestion", "")
                error_str = msg
                if suggestion:
                    error_str += f"\n建议: {suggestion}"
            elif isinstance(err, str):
                error_str = err
            else:
                error_str = str(err) if err else "未知错误"
            return {"success": False, "error": error_str}

    # ------------------------------------------------------------------ #
    # 便捷：作为可调用对象
    # ------------------------------------------------------------------ #

    def __call__(self, tool_name: str, **kwargs) -> dict:
        return self.execute(tool_name, **kwargs)
