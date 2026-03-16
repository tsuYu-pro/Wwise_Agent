# -*- coding: utf-8 -*-
"""
Wwise MCP Server — 标准 Model Context Protocol 服务器

通过 stdio 传输向外部 AI 客户端（Claude Desktop / Cursor 等）
暴露 22 个 Wwise 工具 + System Prompt + 动态上下文。

用法:
    python -m wwise_mcp.server
"""

import json
import logging
from typing import Any, Optional, Union

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("wwise_mcp.server")

# ============================================================
# 创建 MCP Server 实例
# ============================================================

mcp = FastMCP(
    "Wwise MCP Server",
    instructions=(
        "Wwise AI 助手 — 通过 WAAPI 操控 Wwise Authoring Tool。"
        "提供查询、创建、修改、验证等 22 个工具，覆盖 Wwise 项目的完整操作流程。"
    ),
)


# ============================================================
# 辅助：将 wwise_mcp 工具的 {success, data, error} 转为纯文本
# ============================================================

def _format_result(raw: dict) -> str:
    """将内部工具返回的 dict 转为 MCP 文本结果。"""
    if not isinstance(raw, dict):
        return str(raw)

    if raw.get("success"):
        data = raw.get("data")
        if data is None:
            return "操作成功"
        if isinstance(data, str):
            return data
        try:
            return json.dumps(data, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(data)
    else:
        err = raw.get("error")
        if isinstance(err, dict):
            msg = err.get("message", "")
            suggestion = err.get("suggestion", "")
            return f"错误: {msg}" + (f"\n建议: {suggestion}" if suggestion else "")
        return f"错误: {err}" if err else "未知错误"


# ============================================================
# Query 工具 (9)
# ============================================================

@mcp.tool()
async def get_project_hierarchy() -> str:
    """获取 Wwise 项目顶层结构概览，包括各 Hierarchy 的子节点数量、Wwise 版本等。首次了解项目时调用。"""
    from .tools.query import get_project_hierarchy as _fn
    return _format_result(await _fn())


@mcp.tool()
async def get_object_properties(
    object_path: str,
    page: int = 1,
    page_size: int = 30,
) -> str:
    """获取指定 Wwise 对象的属性详情（支持分页）。设置属性前必须先调用此工具确认正确的属性名和类型。

    Args:
        object_path: 对象路径，如 '\\Actor-Mixer Hierarchy\\Default Work Unit\\MySound'
        page: 页码（从1开始），属性较多时翻页查看
        page_size: 每页属性数量，默认 30
    """
    from .tools.query import get_object_properties as _fn
    return _format_result(await _fn(object_path, page, page_size))


@mcp.tool()
async def search_objects(
    query: str,
    type_filter: Optional[str] = None,
    max_results: int = 20,
) -> str:
    """按关键词模糊搜索 Wwise 对象。返回匹配的对象列表（名称、类型、路径）。

    Args:
        query: 搜索关键词
        type_filter: 按类型过滤，如 'Sound', 'Event', 'Bus', 'ActorMixer' 等（可选）
        max_results: 最大结果数，默认 20
    """
    from .tools.query import search_objects as _fn
    return _format_result(await _fn(query, type_filter, max_results))


@mcp.tool()
async def get_bus_topology() -> str:
    """获取 Master-Mixer Hierarchy 中所有 Bus 的拓扑结构。用于了解音频路由。"""
    from .tools.query import get_bus_topology as _fn
    return _format_result(await _fn())


@mcp.tool()
async def get_event_actions(event_path: str) -> str:
    """获取指定 Event 下所有 Action 的详情（类型、Target 引用等）。

    Args:
        event_path: Event 路径，如 '\\Events\\Default Work Unit\\Play_Footstep'
    """
    from .tools.query import get_event_actions as _fn
    return _format_result(await _fn(event_path))


@mcp.tool()
async def get_soundbank_info(soundbank_name: Optional[str] = None) -> str:
    """获取 SoundBank 信息。不传参数时返回所有 SoundBank 列表。

    Args:
        soundbank_name: SoundBank 名称（可选，不传则列出所有）
    """
    from .tools.query import get_soundbank_info as _fn
    return _format_result(await _fn(soundbank_name))


@mcp.tool()
async def get_rtpc_list(max_results: int = 50) -> str:
    """获取项目中所有 Game Parameter（RTPC）列表。

    Args:
        max_results: 最大结果数，默认 50
    """
    from .tools.query import get_rtpc_list as _fn
    return _format_result(await _fn(max_results))


@mcp.tool()
async def get_selected_objects() -> str:
    """获取 Wwise Authoring 中当前选中的对象列表。不需要知道路径，直接读取用户选中的内容。"""
    from .tools.query import get_selected_objects as _fn
    return _format_result(await _fn())


@mcp.tool()
async def get_effect_chain(object_path: str) -> str:
    """获取对象或 Bus 的 Effect 插件链（最多 4 个插槽）。

    Args:
        object_path: 对象或 Bus 路径
    """
    from .tools.query import get_effect_chain as _fn
    return _format_result(await _fn(object_path))


# ============================================================
# Action 工具 (10)
# ============================================================

@mcp.tool()
async def create_object(
    name: str,
    obj_type: str,
    parent_path: str,
    on_conflict: str = "rename",
    notes: str = "",
) -> str:
    """在指定父节点下创建 Wwise 对象（Sound、ActorMixer、BlendContainer 等）。

    Args:
        name: 对象名称
        obj_type: 对象类型，如 'Sound', 'ActorMixer', 'BlendContainer', 'RandomSequenceContainer', 'SwitchContainer', 'Folder' 等
        parent_path: 父节点路径，如 '\\Actor-Mixer Hierarchy\\Default Work Unit'
        on_conflict: 同名冲突策略，'rename' 或 'fail'，默认 'rename'
        notes: 备注（可选）
    """
    from .tools.action import create_object as _fn
    return _format_result(await _fn(name, obj_type, parent_path, on_conflict, notes))


@mcp.tool()
async def set_property(
    object_path: str,
    property: Optional[str] = None,
    value: Optional[Union[float, str, bool]] = None,
    properties: Optional[dict] = None,
    platform: Optional[str] = None,
) -> str:
    """设置对象的一个或多个属性。设置前请先用 get_object_properties 确认正确的属性名。

    Args:
        object_path: 对象路径
        property: 属性名（单个属性时使用）
        value: 属性值（单个属性时使用）
        properties: 批量设置：属性名→值的字典（可替代 property+value）
        platform: 目标平台（可选）
    """
    from .tools.action import set_property as _fn
    return _format_result(await _fn(object_path, property, value, properties, platform))


@mcp.tool()
async def create_event(
    event_name: str,
    action_type: str,
    target_path: str,
    parent_path: str = "\\Events\\Default Work Unit",
) -> str:
    """创建 Wwise Event 及其 Action。自动创建 Event + Action 并设置 Target 引用。

    Args:
        event_name: Event 名称
        action_type: Action 类型，可选 'Play', 'Stop', 'Pause', 'Resume', 'Break', 'Mute', 'UnMute'
        target_path: Action 目标对象路径
        parent_path: Event 父路径，默认 '\\Events\\Default Work Unit'
    """
    from .tools.action import create_event as _fn
    return _format_result(await _fn(event_name, action_type, target_path, parent_path))


@mcp.tool()
async def assign_bus(object_path: str, bus_path: str) -> str:
    """将对象路由到指定 Bus（设置 OverrideOutput + OutputBus 引用）。

    Args:
        object_path: 对象路径
        bus_path: 目标 Bus 路径
    """
    from .tools.action import assign_bus as _fn
    return _format_result(await _fn(object_path, bus_path))


@mcp.tool()
async def delete_object(object_path: str, force: bool = False) -> str:
    """删除 Wwise 对象。默认会检查是否被 Action 引用，传 force=true 跳过检查。

    Args:
        object_path: 要删除的对象路径
        force: 是否跳过引用检查，默认 false
    """
    from .tools.action import delete_object as _fn
    return _format_result(await _fn(object_path, force))


@mcp.tool()
async def move_object(object_path: str, new_parent_path: str) -> str:
    """将对象移动到新的父节点。

    Args:
        object_path: 要移动的对象路径
        new_parent_path: 新父节点路径
    """
    from .tools.action import move_object as _fn
    return _format_result(await _fn(object_path, new_parent_path))


@mcp.tool()
async def preview_event(event_path: str, action: str = "play") -> str:
    """通过 Wwise Transport API 试听 Event。

    Args:
        event_path: Event 路径
        action: 操作类型，'play', 'stop', 'pause', 'resume'，默认 'play'
    """
    from .tools.action import preview_event as _fn
    return _format_result(await _fn(event_path, action))


@mcp.tool()
async def set_rtpc_binding(
    object_path: str,
    game_parameter_path: str,
    property_name: str = "Volume",
    curve_points: Optional[list[dict]] = None,
    notes: str = "",
) -> str:
    """将 Game Parameter（RTPC）绑定到对象属性，设置驱动曲线。

    Args:
        object_path: 目标对象路径
        game_parameter_path: Game Parameter 路径
        property_name: 要绑定的属性名，默认 'Volume'
        curve_points: 曲线控制点列表，每个点含 x, y, shape（如 'Linear'）
        notes: 备注（可选）
    """
    from .tools.action import set_rtpc_binding as _fn
    return _format_result(await _fn(object_path, game_parameter_path, property_name, curve_points, notes))


@mcp.tool()
async def add_effect(
    object_path: str,
    effect_name: str,
    effect_plugin: str,
    effect_slot: int = 0,
    effect_params: Optional[dict] = None,
) -> str:
    """为对象或 Bus 添加 Effect 插件。可用插件：RoomVerb, Delay, Compressor, Expander, PeakLimiter, ParametricEQ, MeterFX, GainFX 等。

    Args:
        object_path: 目标对象或 Bus 路径
        effect_name: Effect 实例名称
        effect_plugin: 插件类型名称（如 'RoomVerb', 'Compressor'）或 classId 数字
        effect_slot: 插槽索引 0~3，默认 0
        effect_params: Effect 参数字典（可选）
    """
    from .tools.action import add_effect as _fn
    return _format_result(await _fn(object_path, effect_name, effect_plugin, effect_slot, effect_params))


@mcp.tool()
async def remove_effect(object_path: str) -> str:
    """清空对象上的所有 Effect 插槽。

    Args:
        object_path: 目标对象路径
    """
    from .tools.action import remove_effect as _fn
    return _format_result(await _fn(object_path))


# ============================================================
# Verify 工具 (2)
# ============================================================

@mcp.tool()
async def verify_structure(scope_path: Optional[str] = None) -> str:
    """结构完整性验证：检查孤儿 Event、Action 无 Target、Sound 无 Bus 等问题。可指定 scope_path 限制检查范围。

    Args:
        scope_path: 检查范围路径（可选，不传则检查全局）
    """
    from .tools.verify import verify_structure as _fn
    return _format_result(await _fn(scope_path))


@mcp.tool()
async def verify_event_completeness(event_path: str) -> str:
    """验证 Event 完整性：检查 Action 是否有 Target、音频文件是否存在、SoundBank 包含状态。任务结束前必调用。

    Args:
        event_path: Event 路径
    """
    from .tools.verify import verify_event_completeness as _fn
    return _format_result(await _fn(event_path))


# ============================================================
# Fallback 工具 (1)
# ============================================================

@mcp.tool()
async def execute_waapi(
    uri: str,
    args: Optional[dict] = None,
    opts: Optional[dict] = None,
) -> str:
    """直接执行原始 WAAPI 调用（兜底工具）。当其他工具不能满足需求时使用。受黑名单保护。

    Args:
        uri: WAAPI URI，如 'ak.wwise.core.object.get'
        args: WAAPI 调用参数
        opts: WAAPI 调用选项（可选）
    """
    from .tools.fallback import execute_waapi as _fn
    return _format_result(await _fn(uri, args or {}, opts or {}))


# ============================================================
# Prompt 资源
# ============================================================

@mcp.prompt()
def wwise_system_prompt() -> str:
    """Wwise 领域 System Prompt — 包含角色定义、对象模型、版本特性、操作规范。自动适配当前连接的 Wwise 版本。"""
    from .prompts.system_prompt import STATIC_SYSTEM_PROMPT
    return STATIC_SYSTEM_PROMPT


# ============================================================
# 入口
# ============================================================

def main():
    """启动 MCP Server（stdio 传输）。"""
    logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
    logger.info("Wwise MCP Server 启动中 (stdio)...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
