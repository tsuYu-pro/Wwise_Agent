# -*- coding: utf-8 -*-
"""获取 Wwise 当前选中对象"""

SKILL_INFO = {
    "name": "get_selected_objects",
    "description": "获取 Wwise Authoring 中当前选中的对象列表。不需要知道路径，直接读取用户选中的内容。",
    "parameters": {},
}


def run():
    from ._waapi_helpers import waapi_call, ok, err

    try:
        result = waapi_call(
            "ak.wwise.ui.getSelectedObjects",
            {},
            {"return": ["name", "type", "path", "id", "notes", "childrenCount"]},
        )
        objects = result.get("objects", []) if result else []
        return ok({
            "count": len(objects),
            "objects": objects,
            "hint": (
                "No objects selected"
                if not objects
                else f"{len(objects)} object(s) selected - paths ready for use with other tools"
            ),
        })
    except Exception as e:
        return err("unexpected_error", str(e))
