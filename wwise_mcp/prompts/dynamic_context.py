"""
Layer 6 — 动态上下文注入（区块 5）
"""

import logging

from ..rag.context_collector import WwiseRAG

logger = logging.getLogger("wwise_mcp.prompts.dynamic")

_rag = WwiseRAG()


async def build_dynamic_context(user_message: str) -> str:
    """根据用户消息收集相关 Wwise 项目状态。"""
    contexts = await _rag.collect(user_message)
    if not contexts:
        return ""

    order = [
        "project_info",
        "selected_objects",
        "actor_mixer_hierarchy",
        "bus_topology",
        "event_overview",
        "rtpc_list",
        "soundbank_info",
    ]

    lines = []
    for key in order:
        if key in contexts:
            lines.append(contexts[key])

    for key, value in contexts.items():
        if key not in order:
            lines.append(value)

    return "\n\n".join(lines)
