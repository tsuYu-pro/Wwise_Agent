# -*- coding: utf-8 -*-
"""设置对象的一个或多个属性"""

SKILL_INFO = {
    "name": "set_property",
    "description": "设置对象的一个或多个属性。设置前请先用 get_object_properties 确认正确的属性名。",
    "parameters": {
        "object_path": {"type": "string", "description": "对象路径", "required": True},
        "property": {"type": "string", "description": "属性名（单个属性时使用）", "required": False},
        "value": {"type": "string", "description": "属性值（单个属性时使用）", "required": False},
        "properties": {"type": "object", "description": "批量设置：属性名→值的字典", "required": False},
        "platform": {"type": "string", "description": "目标平台（可选）", "required": False},
    },
}


def run(object_path, property=None, value=None, properties=None, platform=None):
    from ._waapi_helpers import (
        set_property as _set_property,
        is_valid_property, get_similar_properties,
        ok, err,
    )

    try:
        if properties is None:
            if property is None or value is None:
                return err("invalid_param", "必须提供 property+value 或 properties 参数")
            properties = {property: value}

        results = []
        for prop_name, prop_value in properties.items():
            if not is_valid_property(prop_name):
                suggestions = get_similar_properties(prop_name)
                results.append({
                    "property": prop_name, "value": prop_value, "success": False,
                    "error": f"未知属性名 '{prop_name}'，请检查拼写",
                    "suggestion": f"相近的合法属性名：{suggestions}" if suggestions else "请调用 get_object_properties 获取合法属性列表",
                })
                continue
            try:
                _set_property(object_path, prop_name, prop_value, platform)
                results.append({"property": prop_name, "value": prop_value, "success": True})
            except Exception as e:
                results.append({"property": prop_name, "value": prop_value, "success": False, "error": str(e)})

        all_success = all(r["success"] for r in results)
        return ok({
            "object_path": object_path,
            "results": results,
            "all_success": all_success,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
