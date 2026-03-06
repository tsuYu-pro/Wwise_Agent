# -*- coding: utf-8 -*-
"""在指定父节点下创建 Wwise 对象"""

SKILL_INFO = {
    "name": "create_object",
    "description": "在指定父节点下创建 Wwise 对象（Sound、ActorMixer、BlendContainer 等）。",
    "parameters": {
        "name": {"type": "string", "description": "对象名称", "required": True},
        "obj_type": {"type": "string", "description": "对象类型", "required": True},
        "parent_path": {"type": "string", "description": "父节点路径", "required": True},
        "on_conflict": {"type": "string", "description": "同名冲突策略，默认 rename", "required": False},
        "notes": {"type": "string", "description": "备注（可选）", "required": False},
    },
}


def run(name, obj_type, parent_path, on_conflict="rename", notes=""):
    from ._waapi_helpers import get_objects, create_object, ok, err

    try:
        existing = get_objects(
            from_spec={"path": [parent_path]},
            return_fields=["name", "path"],
            transform=[{"select": ["children"]}],
        )
        existing_names = {obj.get("name") for obj in existing}
        if name in existing_names and on_conflict == "fail":
            return err(
                "conflict",
                f"父节点 '{parent_path}' 下已存在同名对象 '{name}'",
                "可将 on_conflict 设为 'rename' 自动重命名，或先删除已有对象",
            )

        result = create_object(
            name=name,
            obj_type=obj_type,
            parent_path=parent_path,
            on_conflict=on_conflict,
            notes=notes,
        )
        return ok({
            "id": result.get("id"),
            "name": result.get("name"),
            "path": result.get("path"),
            "type": obj_type,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
