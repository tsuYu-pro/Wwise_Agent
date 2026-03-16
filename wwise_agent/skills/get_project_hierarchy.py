# -*- coding: utf-8 -*-
"""获取 Wwise 项目顶层结构概览"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.wwise_version import version_manager

SKILL_INFO = {
    "name": "get_project_hierarchy",
    "description": "获取 Wwise 项目顶层结构概览，包括各 Hierarchy 的子节点数量、Wwise 版本等。首次了解项目时调用。",
    "parameters": {},
}


def run():
    from ._waapi_helpers import get_objects, get_info, ok, err

    try:
        root_obj = get_objects(
            from_spec={"path": ["\\"]},
            return_fields=["name", "path"],
        )
        project_name = root_obj[0].get("name", "Unknown") if root_obj else "Unknown"

        known_roots = version_manager.get_known_roots()
        root_children = get_objects(
            from_spec={"path": known_roots},
            return_fields=["name", "type", "childrenCount", "path"],
        )

        summary = {}
        for obj in root_children:
            name = obj.get("name", "")
            summary[name] = {
                "type": obj.get("type", ""),
                "childrenCount": obj.get("childrenCount", 0),
                "path": obj.get("path", ""),
            }

        info = get_info()
        return ok({
            "wwise_version": info.get("version", {}).get("displayName", "Unknown"),
            "project_name": project_name,
            "hierarchy": summary,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
