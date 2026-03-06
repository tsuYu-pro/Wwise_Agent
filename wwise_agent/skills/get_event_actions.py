# -*- coding: utf-8 -*-
"""获取 Event 下的 Action 详情"""

SKILL_INFO = {
    "name": "get_event_actions",
    "description": "获取指定 Event 下所有 Action 的详情（类型、Target 引用等）。",
    "parameters": {
        "event_path": {"type": "string", "description": "Event 路径", "required": True},
    },
}


def run(event_path):
    from ._waapi_helpers import get_objects, waapi_call, ok, err

    try:
        events = get_objects(
            from_spec={"path": [event_path]},
            return_fields=["name", "type", "path", "id"],
        )
        if not events:
            return err("not_found", f"Event 不存在：{event_path}",
                       "请先调用 search_objects 搜索 Event 的正确路径")

        args = {
            "from": {"path": [event_path]},
            "transform": [{"select": ["children"]}],
        }
        result = waapi_call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id", "ActionType", "Target"]},
        )
        actions = result.get("return", [])

        return ok({
            "event": events[0],
            "action_count": len(actions),
            "actions": actions,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
