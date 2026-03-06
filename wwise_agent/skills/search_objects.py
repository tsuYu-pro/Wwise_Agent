# -*- coding: utf-8 -*-
"""按关键词模糊搜索 Wwise 对象"""

SKILL_INFO = {
    "name": "search_objects",
    "description": "按关键词模糊搜索 Wwise 对象。返回匹配的对象列表（名称、类型、路径）。",
    "parameters": {
        "query": {"type": "string", "description": "搜索关键词", "required": True},
        "type_filter": {"type": "string", "description": "按类型过滤（可选）", "required": False},
        "max_results": {"type": "integer", "description": "最大结果数，默认 20", "required": False},
    },
}


def run(query, type_filter=None, max_results=20):
    from ._waapi_helpers import waapi_call, ok, err

    try:
        args = {
            "from": {
                "ofType": [type_filter] if type_filter else [
                    "Sound", "Event", "Bus", "AuxBus",
                    "GameParameter", "ActorMixer", "BlendContainer",
                    "RandomSequenceContainer", "SwitchContainer",
                ]
            },
        }

        result = waapi_call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id"]},
        )
        all_objects = result.get("return", []) if result else []

        query_lower = query.lower()
        objects = [o for o in all_objects if query_lower in o.get("name", "").lower()]
        objects.sort(key=lambda x: x.get("path", ""))
        objects = objects[:max_results]

        return ok({
            "query": query,
            "type_filter": type_filter,
            "count": len(objects),
            "objects": objects,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
