# -*- coding: utf-8 -*-
"""删除 Wwise 对象"""

SKILL_INFO = {
    "name": "delete_object",
    "description": "删除 Wwise 对象。默认会检查是否被 Action 引用，传 force=true 跳过检查。",
    "parameters": {
        "object_path": {"type": "string", "description": "要删除的对象路径", "required": True},
        "force": {"type": "boolean", "description": "是否跳过引用检查，默认 false", "required": False},
    },
}


def run(object_path, force=False):
    from ._waapi_helpers import waapi_call, delete_object, ok, err

    try:
        if not force:
            search_result = waapi_call(
                "ak.wwise.core.object.get",
                {"from": {"ofType": ["Action"]}},
                {"return": ["name", "path", "Target"]},
            )
            all_actions = search_result.get("return", []) if search_result else []
            obj_name = object_path.split("\\")[-1]
            referencing_actions = [
                a for a in all_actions
                if a.get("Target", {}).get("name") == obj_name
            ]
            if referencing_actions:
                return err(
                    "has_references",
                    f"对象 '{object_path}' 被 {len(referencing_actions)} 个 Action 引用",
                    f"引用该对象的 Action：{[a.get('path') for a in referencing_actions[:5]]}。"
                    f"确认要强制删除请传入 force=True",
                )

        delete_object(object_path)
        return ok({"deleted": object_path})
    except Exception as e:
        return err("unexpected_error", str(e))
