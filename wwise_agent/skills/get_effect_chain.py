# -*- coding: utf-8 -*-
"""获取对象/Bus 的 Effect 链"""

SKILL_INFO = {
    "name": "get_effect_chain",
    "description": "获取对象或 Bus 的 Effect 插件链（最多 4 个插槽）。",
    "parameters": {
        "object_path": {"type": "string", "description": "对象或 Bus 路径", "required": True},
    },
}


def run(object_path):
    from ._waapi_helpers import get_objects, ok, err

    try:
        objects = get_objects(
            from_spec={"path": [object_path]},
            return_fields=["name", "type", "path", "id",
                           "Effect0", "Effect1", "Effect2", "Effect3"],
        )
        if not objects:
            return err("not_found", f"对象不存在：{object_path}",
                       "请先调用 search_objects 搜索正确路径")

        obj = objects[0]

        effects = []
        for slot_idx in range(4):
            slot_key = f"Effect{slot_idx}"
            slot_data = obj.get(slot_key)
            if slot_data and isinstance(slot_data, dict) and slot_data.get("name"):
                effects.append({
                    "slot": slot_idx,
                    "name": slot_data.get("name", ""),
                    "id": slot_data.get("id", ""),
                })
            elif slot_data and isinstance(slot_data, dict) and slot_data.get("id"):
                effects.append({
                    "slot": slot_idx,
                    "name": slot_data.get("name", "(unnamed)"),
                    "id": slot_data.get("id", ""),
                })

        return ok({
            "object_path": object_path,
            "object_name": obj.get("name"),
            "object_type": obj.get("type"),
            "effect_count": len(effects),
            "effects": effects,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
