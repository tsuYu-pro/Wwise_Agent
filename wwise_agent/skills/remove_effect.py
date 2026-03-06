# -*- coding: utf-8 -*-
"""清空对象上的所有 Effect 插槽"""

SKILL_INFO = {
    "name": "remove_effect",
    "description": "清空对象上的所有 Effect 插槽。",
    "parameters": {
        "object_path": {"type": "string", "description": "目标对象路径", "required": True},
    },
}


def run(object_path):
    from ._waapi_helpers import get_objects, object_set, ok, err

    try:
        target_objs = get_objects(
            from_spec={"path": [object_path]},
            return_fields=["name", "type", "path"],
        )
        if not target_objs:
            return err("not_found", f"目标对象不存在：{object_path}",
                       "请先调用 search_objects 搜索正确路径")

        result = object_set(
            objects=[{"object": object_path, "@Effects": []}],
            list_mode="replaceAll",
        )

        return ok({
            "object_path": object_path,
            "action": "removed_all_effects",
            "result": result,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
