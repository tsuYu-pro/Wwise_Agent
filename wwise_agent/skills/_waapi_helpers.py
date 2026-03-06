# -*- coding: utf-8 -*-
"""
WAAPI 连接 & 通用工具 — Skill 内部模块（以 _ 开头，不会被注册为 Skill）

提供同步的 WAAPI 调用接口，所有 Skill 通过此模块访问 Wwise。
基于官方 waapi-client 库，连接通过 WebSocket 完成。
"""

import logging
from typing import Any, Optional, List

logger = logging.getLogger("wwise_agent.skills")

# 全局连接实例
_client = None

# WAAPI 连接参数
WAAPI_URL = "ws://127.0.0.1:8080/waapi"

# execute_waapi 黑名单
BLACKLISTED_URIS = frozenset({
    "ak.wwise.core.project.open",
    "ak.wwise.core.project.close",
    "ak.wwise.core.project.save",
    "ak.wwise.ui.project.open",
    "ak.wwise.core.undo.beginGroup",
    "ak.wwise.core.remote.connect",
    "ak.wwise.core.remote.disconnect",
})

# 常见合法属性名（用于 set_property 验证）
COMMON_PROPERTIES = {
    "Volume", "Pitch", "MakeUpGain",
    "LowPassFilter", "HighPassFilter",
    "OutputBus", "OutputBusVolume", "OutputBusMixerGain",
    "Positioning.EnablePositioning", "Positioning.SpeakerPanning",
    "Positioning.3D.AttenuationID",
    "MaxSoundInstances", "MaxSoundInstancesBehavior",
    "VirtualVoiceBehavior",
    "Volume.Min", "Volume.Max", "Pitch.Min", "Pitch.Max",
    "ActionType", "Target", "Delay", "TransitionTime",
    "IncludeInSoundBank",
    "UseGameDefinedAuxSends", "UserAuxSendVolume0",
    "CrossfadeParameter", "BlendTrackName",
    "Notes", "Color",
    "OverrideOutput",
}

# Effect 插件 classId 映射
EFFECT_CLASS_IDS = {
    "RoomVerb": 7733251,
    "Delay": 8454147,
    "Compressor": 613752611,
    "Expander": 7471107,
    "PeakLimiter": 7864323,
    "ParametricEQ": 7995395,
    "MeterFX": 7602179,
    "GainFX": 8126467,
    "MatrixReverb": 8257539,
    "Flanger": 8585219,
    "TremoloFX": 8519683,
    "Harmonizer": 8650755,
    "StereoDelay": 8388611,
    "GuitarDistortion": 8716291,
    "TimeStretch": 8323075,
    "PitchShifter": 8192003,
}

# RTPC 合法曲线形状
VALID_CURVE_SHAPES = frozenset({
    "Linear", "Log1", "Log2", "Log3",
    "Exp1", "Exp2", "Exp3",
    "SCurve", "InvertedSCurve", "Constant",
})


def _get_client():
    """获取或创建全局 WAAPI 连接"""
    global _client
    if _client is not None and _client.is_connected():
        return _client
    from waapi import WaapiClient
    from waapi.wamp.interface import CannotConnectToWaapiException
    try:
        _client = WaapiClient(WAAPI_URL)
        logger.info("WAAPI 连接成功: %s", WAAPI_URL)
        return _client
    except CannotConnectToWaapiException as e:
        raise ConnectionError(
            f"无法连接到 Wwise WAAPI ({WAAPI_URL})。"
            f"请确认 Wwise 正在运行且 WAAPI 已启用。错误: {e}"
        )
    except Exception as e:
        raise ConnectionError(f"WAAPI 连接失败: {e}")


def close_connection():
    """关闭全局 WAAPI 连接"""
    global _client
    if _client:
        try:
            _client.disconnect()
        except Exception:
            pass
        _client = None


# ------------------------------------------------------------------
# 核心 WAAPI 调用
# ------------------------------------------------------------------

def waapi_call(uri: str, args: dict = None, opts: dict = None) -> dict:
    """执行 WAAPI 调用（同步）"""
    client = _get_client()
    payload = dict(args) if args else {}
    if opts:
        payload["options"] = opts
    result = client.call(uri, payload)
    if result is None:
        raise RuntimeError(f"WAAPI 调用 '{uri}' 返回 None（参数可能有误）")
    return result


def get_objects(
    from_spec: dict,
    return_fields: list = None,
    transform: list = None,
) -> list:
    """通用对象查询"""
    if return_fields is None:
        return_fields = ["name", "type", "path", "id"]
    args = {"from": from_spec}
    if transform:
        args["transform"] = transform
    result = waapi_call(
        "ak.wwise.core.object.get",
        args,
        {"return": return_fields},
    )
    return result.get("return", [])


def get_info() -> dict:
    """获取 Wwise 项目基础信息"""
    return waapi_call("ak.wwise.core.getInfo")


def create_object(
    name: str,
    obj_type: str,
    parent_path: str,
    on_conflict: str = "rename",
    notes: str = "",
) -> dict:
    """创建 Wwise 对象"""
    args = {
        "name": name,
        "type": obj_type,
        "parent": parent_path,
        "onNameConflict": on_conflict,
    }
    if notes:
        args["notes"] = notes
    result = waapi_call("ak.wwise.core.object.create", args)
    obj_id = result.get("id") if result else None
    if obj_id:
        try:
            objs = get_objects(
                from_spec={"id": [obj_id]},
                return_fields=["name", "path", "type"],
            )
            if objs:
                result = {**result, "path": objs[0].get("path"), "name": objs[0].get("name")}
        except Exception:
            pass
    return result


def set_property(object_path: str, prop: str, value: Any, platform: str = None) -> dict:
    """设置对象属性"""
    args = {"object": object_path, "property": prop, "value": value}
    if platform:
        args["platform"] = platform
    return waapi_call("ak.wwise.core.object.setProperty", args)


def set_reference(object_path: str, reference: str, value_path: str, platform: str = None) -> dict:
    """设置对象引用"""
    args = {"object": object_path, "reference": reference, "value": value_path}
    if platform:
        args["platform"] = platform
    return waapi_call("ak.wwise.core.object.setReference", args)


def delete_object(object_path: str) -> dict:
    """删除对象"""
    return waapi_call("ak.wwise.core.object.delete", {"object": object_path})


def move_object(object_path: str, new_parent_path: str) -> dict:
    """移动对象到新父节点"""
    return waapi_call(
        "ak.wwise.core.object.move",
        {"object": object_path, "parent": new_parent_path, "onNameConflict": "rename"},
    )


def object_set(objects: list, on_name_conflict: str = "rename", list_mode: str = "append") -> dict:
    """调用 ak.wwise.core.object.set 执行批量操作"""
    return waapi_call(
        "ak.wwise.core.object.set",
        {"objects": objects, "onNameConflict": on_name_conflict, "listMode": list_mode},
    )


# ------------------------------------------------------------------
# 属性验证
# ------------------------------------------------------------------

def is_valid_property(prop_name: str) -> bool:
    """检查属性名是否合法"""
    if prop_name in COMMON_PROPERTIES:
        return True
    for known in COMMON_PROPERTIES:
        if prop_name.startswith(known.split(".")[0]):
            return True
    return False


def get_similar_properties(prop_name: str, limit: int = 5) -> list:
    """模糊匹配相近的属性名"""
    prop_lower = prop_name.lower()
    matches = [
        p for p in COMMON_PROPERTIES
        if prop_lower in p.lower() or p.lower() in prop_lower
    ]
    return matches[:limit]


# ------------------------------------------------------------------
# 返回值辅助
# ------------------------------------------------------------------

def ok(data: Any) -> dict:
    return {"success": True, "data": data, "error": None}


def err(code: str, message: str, suggestion: str = None) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "suggestion": suggestion},
    }
