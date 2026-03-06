# -*- coding: utf-8 -*-
"""获取 Bus 拓扑结构"""

SKILL_INFO = {
    "name": "get_bus_topology",
    "description": "获取 Master-Mixer Hierarchy 中所有 Bus 的拓扑结构。用于了解音频路由。",
    "parameters": {},
}


def run():
    from ._waapi_helpers import waapi_call, ok, err

    try:
        args = {
            "from": {"path": ["\\Master-Mixer Hierarchy"]},
            "transform": [{"select": ["descendants"]}],
        }
        result = waapi_call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id", "childrenCount"]},
        )
        all_descendants = result.get("return", []) if result else []
        buses = [o for o in all_descendants if o.get("type") == "Bus"]

        return ok({
            "total_buses": len(buses),
            "buses": buses,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
