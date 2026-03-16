"""
Layer 2 — WwiseRAG：按需收集 Wwise 项目状态
"""

import logging
import sys
import os
from typing import Optional

# 确保 shared 可以被导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from shared.wwise_version import version_manager
from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError

logger = logging.getLogger("wwise_mcp.rag")


class WwiseRAG:
    """按需检索 Wwise 项目状态，根据用户消息关键词决定收集哪些上下文。"""

    _KEYWORD_TRIGGERS = {
        "hierarchy": ["actor_mixer_hierarchy"],
        "sound": ["actor_mixer_hierarchy"],
        "event": ["event_overview"],
        "trigger": ["event_overview"],
        "触发": ["event_overview"],
        "bus": ["bus_topology"],
        "mix": ["bus_topology"],
        "output": ["bus_topology"],
        "rtpc": ["rtpc_list"],
        "game parameter": ["rtpc_list"],
        "parameter": ["rtpc_list"],
        "this": ["selected_objects"],
        "selected": ["selected_objects"],
        "当前": ["selected_objects"],
        "选中": ["selected_objects"],
        "soundbank": ["soundbank_info"],
        "bank": ["soundbank_info"],
    }

    def __init__(self):
        self._cache: dict[str, tuple] = {}

    async def collect(self, user_message: str) -> dict[str, str]:
        """根据用户消息关键词，按需收集相关上下文。"""
        msg_lower = user_message.lower()

        needed: set[str] = set()
        for keyword, context_types in self._KEYWORD_TRIGGERS.items():
            if keyword in msg_lower:
                needed.update(context_types)

        needed.add("project_info")

        results: dict[str, str] = {}
        for context_type in needed:
            try:
                data = await self._collect_context(context_type)
                if data:
                    results[context_type] = data
            except Exception as e:
                logger.warning("收集上下文 '%s' 失败：%s", context_type, e)

        return results

    async def _collect_context(self, context_type: str) -> Optional[str]:
        adapter = WwiseAdapter()

        if context_type == "project_info":
            return await self._collect_project_info(adapter)
        elif context_type == "actor_mixer_hierarchy":
            return await self._collect_actor_mixer(adapter)
        elif context_type == "bus_topology":
            return await self._collect_bus_topology(adapter)
        elif context_type == "selected_objects":
            return await self._collect_selected(adapter)
        elif context_type == "event_overview":
            return await self._collect_events(adapter)
        elif context_type == "rtpc_list":
            return await self._collect_rtpcs(adapter)
        elif context_type == "soundbank_info":
            return await self._collect_soundbanks(adapter)
        return None

    async def _collect_project_info(self, adapter: WwiseAdapter) -> str:
        try:
            info = await adapter.get_info()
            version = info.get("version", {}).get("displayName", "Unknown")
            root = await adapter.get_objects(
                from_spec={"path": ["\\"]},
                return_fields=["name"],
            )
            project = root[0].get("name", "Unknown") if root else "Unknown"
            return f"[项目信息] 名称：{project}，Wwise 版本：{version}"
        except Exception:
            return "[项目信息] 无法获取（Wwise 可能未运行）"

    async def _collect_actor_mixer(self, adapter: WwiseAdapter) -> str:
        try:
            am_path = version_manager.resolve_path("actor_mixer")
            objects = await adapter.get_objects(
                from_spec={"path": [am_path]},
                return_fields=["name", "type", "childrenCount", "path"],
                transform=[{"select": ["children"]}],
            )
            lines = ["[Actor-Mixer 层级概览]"]
            for obj in objects[:30]:
                lines.append(f"  {obj.get('type', '')}：{obj.get('name', '')} "
                             f"（{obj.get('childrenCount', 0)} 个子对象）")
            if len(objects) > 30:
                lines.append(f"  ... 共 {len(objects)} 个对象")
            return "\n".join(lines)
        except Exception as e:
            return f"[Actor-Mixer 层级] 获取失败：{e}"

    async def _collect_bus_topology(self, adapter: WwiseAdapter) -> str:
        try:
            mm_path = version_manager.resolve_path("master_mixer")
            result = await adapter.call(
                "ak.wwise.core.object.get",
                {
                    "from": {"path": [mm_path]},
                    "transform": [{"select": ["descendants"]}],
                },
                {"return": ["name", "type", "path", "childrenCount"]},
            )
            buses = result.get("return", []) if result else []
            lines = [f"[Master-Mixer Bus 拓扑] 共 {len(buses)} 个节点"]
            for bus in buses[:20]:
                depth = bus.get("path", "").count("\\") - 2
                indent = "  " * depth
                lines.append(f"{indent}{bus.get('type', '')}: {bus.get('name', '')}")
            return "\n".join(lines)
        except Exception as e:
            return f"[Bus 拓扑] 获取失败：{e}"

    async def _collect_selected(self, adapter: WwiseAdapter) -> str:
        try:
            objects = await adapter.get_selected_objects()
            if not objects:
                return "[当前选中对象] 无"
            lines = ["[当前选中对象]"]
            for obj in objects:
                lines.append(f"  {obj.get('type')}: {obj.get('name')} — {obj.get('path')}")
            return "\n".join(lines)
        except Exception as e:
            return f"[当前选中对象] 获取失败：{e}"

    async def _collect_events(self, adapter: WwiseAdapter) -> str:
        try:
            result = await adapter.call(
                "ak.wwise.core.object.get",
                {"from": {"ofType": ["Event"]}},
                {"return": ["name", "path", "childrenCount"]},
            )
            events = result.get("return", []) if result else []
            lines = [f"[Event 列表] 共 {len(events)} 个 Event"]
            for ev in events[:30]:
                action_count = ev.get("childrenCount", 0)
                lines.append(f"  {ev.get('name')} （{action_count} 个 Action）")
            if len(events) > 30:
                lines.append(f"  ... 还有 {len(events) - 30} 个")
            return "\n".join(lines)
        except Exception as e:
            return f"[Event 列表] 获取失败：{e}"

    async def _collect_rtpcs(self, adapter: WwiseAdapter) -> str:
        try:
            result = await adapter.call(
                "ak.wwise.core.object.get",
                {"from": {"ofType": ["GameParameter"]}},
                {"return": ["name", "path", "Min", "Max", "InitialValue"]},
            )
            rtpcs = result.get("return", []) if result else []
            lines = [f"[Game Parameter 列表] 共 {len(rtpcs)} 个"]
            for rtpc in rtpcs[:20]:
                lines.append(f"  {rtpc.get('name')} "
                             f"[{rtpc.get('Min', 0)}, {rtpc.get('Max', 100)}] "
                             f"默认={rtpc.get('InitialValue', 0)}")
            return "\n".join(lines)
        except Exception as e:
            return f"[Game Parameter 列表] 获取失败：{e}"

    async def _collect_soundbanks(self, adapter: WwiseAdapter) -> str:
        try:
            result = await adapter.call(
                "ak.wwise.core.object.get",
                {"from": {"path": ["\\SoundBanks"]}, "transform": [{"select": ["children"]}]},
                {"return": ["name", "type", "path"]},
            )
            banks = result.get("return", []) if result else []
            lines = [f"[SoundBank] 共 {len(banks)} 个（Auto-Defined 模式）"]
            for bank in banks[:10]:
                lines.append(f"  {bank.get('name')}")
            return "\n".join(lines)
        except Exception as e:
            return f"[SoundBank] 获取失败：{e}"


async def build_dynamic_context(user_message: str = "") -> str:
    """收集并格式化动态上下文。"""
    try:
        rag = WwiseRAG()
        context_map = await rag.collect(user_message)
        if not context_map:
            return ""
        lines = ["", "--- 当前 Wwise 项目状态（动态） ---"]
        for ctx in context_map.values():
            lines.append(ctx)
        lines.append("---")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("build_dynamic_context 失败：%s", e)
        return ""
