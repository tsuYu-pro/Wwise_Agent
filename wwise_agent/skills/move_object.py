# -*- coding: utf-8 -*-
"""将对象移动到新父节点"""

SKILL_INFO = {
    "name": "move_object",
    "description": "将对象移动到新的父节点。",
    "parameters": {
        "object_path": {"type": "string", "description": "要移动的对象路径", "required": True},
        "new_parent_path": {"type": "string", "description": "新父节点路径", "required": True},
    },
}


def run(object_path, new_parent_path):
    from ._waapi_helpers import move_object, ok, err

    try:
        move_object(object_path, new_parent_path)
        obj_name = object_path.split("\\")[-1]
        new_path = f"{new_parent_path}\\{obj_name}"

        return ok({
            "original_path": object_path,
            "new_path": new_path,
            "new_parent": new_parent_path,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
