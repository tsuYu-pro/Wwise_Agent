# -*- coding: utf-8 -*-
"""将对象路由到指定 Bus"""

SKILL_INFO = {
    "name": "assign_bus",
    "description": "将对象路由到指定 Bus（设置 OverrideOutput + OutputBus 引用）。",
    "parameters": {
        "object_path": {"type": "string", "description": "对象路径", "required": True},
        "bus_path": {"type": "string", "description": "目标 Bus 路径", "required": True},
    },
}


def run(object_path, bus_path):
    from ._waapi_helpers import set_property, set_reference, ok, err

    try:
        set_property(object_path, "OverrideOutput", True)
        set_reference(object_path, "OutputBus", bus_path)
        return ok({
            "object_path": object_path,
            "output_bus": bus_path,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
