# -*- coding: utf-8 -*-
"""通过 Wwise Transport API 试听 Event"""

SKILL_INFO = {
    "name": "preview_event",
    "description": "通过 Wwise Transport API 试听 Event。",
    "parameters": {
        "event_path": {"type": "string", "description": "Event 路径", "required": True},
        "action": {"type": "string", "description": "操作类型（play/stop/pause/resume），默认 play", "required": False},
    },
}


def run(event_path, action="play"):
    from ._waapi_helpers import waapi_call, ok, err

    try:
        valid_actions = {"play", "stop", "pause", "resume"}
        if action not in valid_actions:
            return err("invalid_param", f"不支持的 action：'{action}'",
                       f"可用值：{sorted(valid_actions)}")

        if action == "play":
            transport_result = waapi_call(
                "ak.wwise.core.transport.create",
                {"object": event_path},
            )
            if not transport_result:
                return err("waapi_error", "Transport 创建失败，请确认 Event 路径正确且 Wwise 项目已加载")

            transport_id = transport_result.get("transport")
            waapi_call(
                "ak.wwise.core.transport.executeAction",
                {"transport": transport_id, "action": "play"},
            )
            return ok({
                "event_path": event_path,
                "action": "play",
                "transport_id": transport_id,
                "note": "正在 Wwise Authoring 中预览",
            })
        else:
            waapi_call(
                "ak.wwise.core.transport.executeAction",
                {"transport": -1, "action": action},
            )
            return ok({"action": action, "note": "已对所有 Transport 执行操作"})
    except Exception as e:
        return err("unexpected_error", str(e))
