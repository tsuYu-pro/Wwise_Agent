# -*- coding: utf-8 -*-
"""
Wwise Backend — 工具执行器

基于 skills/ 目录的自动发现机制执行工具。
不再依赖 wwise_mcp 模块，所有 Wwise 操作通过本地 skills 完成。
"""

import json
import logging
from typing import Any, Dict

from ..skills import list_skills, run_skill

logger = logging.getLogger("wwise_agent.backend")

# 文档检索模块（延迟加载）
HAS_DOC_RAG = False
get_doc_rag = None

try:
    from .doc_rag import get_doc_index as get_doc_rag
    HAS_DOC_RAG = True
except ImportError:
    pass


class WwiseToolExecutor:
    """Wwise 工具执行器 — 基于 Skills 系统。

    所有 Wwise 工具都是 skills/ 目录下的独立模块，
    通过 run_skill() 同步调用，供 Agent 后台线程使用。
    """

    # ------------------------------------------------------------------ #
    # 同步执行入口（供 AIClient.agent_loop 的 tool_executor 回调使用）
    # ------------------------------------------------------------------ #

    def execute(self, tool_name: str, **kwargs) -> dict:
        """同步执行工具（从后台线程调用）

        返回格式::
            {"success": True/False, "result": str, "error": str}
        """
        try:
            raw = run_skill(tool_name, kwargs)
        except Exception as e:
            logger.error("工具 %s 执行异常: %s", tool_name, e, exc_info=True)
            return {"success": False, "error": str(e)}

        # 统一转换返回格式
        return self._normalize(raw, tool_name)

    def execute_tool(self, tool_name: str, kwargs: dict) -> dict:
        """兼容接口 — ai_tab.py 中使用 mcp.execute_tool(name, kwargs)"""
        return self.execute(tool_name, **kwargs)

    # ------------------------------------------------------------------ #
    # 元工具：list_skills / run_skill
    # ------------------------------------------------------------------ #

    def handle_list_skills(self) -> dict:
        """返回所有可用 skill 的元数据"""
        skills = list_skills()
        return {"success": True, "result": json.dumps(skills, ensure_ascii=False, indent=2)}

    def handle_run_skill(self, skill_name: str, params: dict = None) -> dict:
        """执行指定 skill"""
        if params is None:
            params = {}
        try:
            raw = run_skill(skill_name, params)
        except Exception as e:
            return {"success": False, "error": str(e)}
        return self._normalize(raw, skill_name)

    def handle_search_local_doc(self, query: str, top_k: int = 5) -> dict:
        """搜索本地 Wwise 文档索引"""
        if not HAS_DOC_RAG or get_doc_rag is None:
            return {"success": False, "error": "DocIndex 模块未加载"}
        if not query:
            return {"success": False, "error": "缺少 query 参数"}
        try:
            index = get_doc_rag()
            results = index.search(query, top_k=min(top_k, 10))
            if not results:
                return {"success": True, "result": f"未找到与 '{query}' 相关的文档"}
            parts = [f"找到 {len(results)} 个相关条目:\n"]
            for idx, r in enumerate(results, 1):
                parts.append(f"{idx}. [{r['type'].upper()}] {r['name']} (score={r['score']:.1f})")
                parts.append(f"   {r['snippet']}\n")
            return {"success": True, "result": "\n".join(parts)}
        except Exception as e:
            return {"success": False, "error": f"文档搜索异常: {e}"}

    # ------------------------------------------------------------------ #
    # 格式标准化
    # ------------------------------------------------------------------ #

    @staticmethod
    def _normalize(raw: dict, tool_name: str) -> dict:
        """将 skill 返回的 {success, data, error} 转为
        AIClient 期望的 {success, result, error} 字符串格式。
        """
        if not isinstance(raw, dict):
            return {"success": False, "error": f"工具 {tool_name} 返回了非 dict 类型: {type(raw)}"}

        # skill 返回 {"error": "..."} 的简单错误格式
        if "error" in raw and "success" not in raw:
            return {"success": False, "error": raw["error"]}

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
