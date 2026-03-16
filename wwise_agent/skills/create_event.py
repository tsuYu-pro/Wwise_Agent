# -*- coding: utf-8 -*-
"""创建 Wwise Event 及其 Action"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.wwise_version import version_manager, get_create_event_note

SKILL_INFO = {
    "name": "create_event",
    "description": "创建 Wwise Event 及其 Action。自动创建 Event + Action 并设置 Target 引用。",
    "parameters": {
        "event_name": {"type": "string", "description": "Event 名称", "required": True},
        "action_type": {"type": "string", "description": "Action 类型（Play/Stop/Pause/Resume/Break/Mute/UnMute）", "required": True},
        "target_path": {"type": "string", "description": "Action 目标对象路径", "required": True},
        "parent_path": {"type": "string", "description": "Event 父路径，默认 \\Events\\Default Work Unit", "required": False},
    },
}


def run(event_name, action_type, target_path, parent_path="\\Events\\Default Work Unit"):
    from ._waapi_helpers import (
        create_object, set_property, set_reference,
        ok, err,
    )

    try:
        event_result = create_object(
            name=event_name,
            obj_type="Event",
            parent_path=parent_path,
            on_conflict="rename",
        )
        event_path = event_result.get("path")
        if not event_path:
            return err("waapi_error", f"创建 Event '{event_name}' 失败：未返回对象路径")

        action_name = f"{action_type}_{event_name}"
        action_result = create_object(
            name=action_name,
            obj_type="Action",
            parent_path=event_path,
            on_conflict="rename",
        )
        action_path = action_result.get("path")
        if not action_path:
            return err("waapi_error", "在 Event 下创建 Action 失败")

        action_type_map = {
            "Play": 1, "Stop": 2, "Pause": 3, "Resume": 4,
            "Break": 28, "Mute": 6, "UnMute": 7,
        }
        action_type_id = action_type_map.get(action_type, 1)
        set_property(action_path, "ActionType", action_type_id)
        set_reference(action_path, "Target", target_path)

        return ok({
            "event": {
                "id": event_result.get("id"),
                "name": event_name,
                "path": event_path,
            },
            "action": {
                "id": action_result.get("id"),
                "name": action_name,
                "path": action_path,
                "type": action_type,
                "target": target_path,
            },
            "note": get_create_event_note(version_manager.version),
        })
    except Exception as e:
        return err("unexpected_error", str(e))
