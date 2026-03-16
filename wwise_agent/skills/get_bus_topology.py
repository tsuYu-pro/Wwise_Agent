# -*- coding: utf-8 -*-
"""获取 Bus 拓扑结构"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.wwise_version import version_manager

SKILL_INFO = {
    "name": "get_bus_topology",
    "description": "获取 Master-Mixer / Busses Hierarchy 中所有 Bus 的拓扑结构。用于了解音频路由。",
    "parameters": {},
}


def run():
    from ._waapi_helpers import waapi_call, ok, err

    try:
        master_mixer_path = version_manager.resolve_path("master_mixer")
        args = {
            "from": {"path": [master_mixer_path]},
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
