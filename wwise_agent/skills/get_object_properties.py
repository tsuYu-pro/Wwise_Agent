# -*- coding: utf-8 -*-
"""获取指定对象的属性详情"""

SKILL_INFO = {
    "name": "get_object_properties",
    "description": "获取指定 Wwise 对象的属性详情（支持分页）。设置属性前必须先调用此工具确认正确的属性名和类型。",
    "parameters": {
        "object_path": {"type": "string", "description": "对象路径", "required": True},
        "page": {"type": "integer", "description": "页码（从1开始）", "required": False},
        "page_size": {"type": "integer", "description": "每页属性数量，默认 30", "required": False},
    },
}


def run(object_path, page=1, page_size=30):
    from ._waapi_helpers import get_objects, waapi_call, ok, err

    try:
        basic_fields = ["name", "type", "path", "id", "shortId", "notes"]
        objects = get_objects(
            from_spec={"path": [object_path]},
            return_fields=basic_fields,
        )
        if not objects:
            return err("not_found", f"对象不存在：{object_path}",
                       "请先调用 search_objects 搜索正确路径")

        obj = objects[0]

        try:
            prop_result = waapi_call(
                "ak.wwise.core.object.getPropertyAndReferenceNames",
                {"object": object_path},
            )
            all_props = prop_result.get("return", []) if prop_result else []
        except Exception:
            all_props = []

        total = len(all_props)
        start = (page - 1) * page_size
        end = start + page_size
        paged_props = all_props[start:end]

        return ok({
            "object": obj,
            "all_properties": paged_props,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_properties": total,
                "has_more": end < total,
            },
        })
    except Exception as e:
        return err("unexpected_error", str(e))
