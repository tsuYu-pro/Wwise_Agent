# -*- coding: utf-8 -*-
"""将 Game Parameter（RTPC）绑定到对象属性"""

SKILL_INFO = {
    "name": "set_rtpc_binding",
    "description": "将 Game Parameter（RTPC）绑定到对象属性，设置驱动曲线。",
    "parameters": {
        "object_path": {"type": "string", "description": "目标对象路径", "required": True},
        "game_parameter_path": {"type": "string", "description": "Game Parameter 路径", "required": True},
        "property_name": {"type": "string", "description": "要绑定的属性名，默认 Volume", "required": False},
        "curve_points": {"type": "array", "description": "曲线控制点列表", "required": False},
        "notes": {"type": "string", "description": "备注（可选）", "required": False},
    },
}


def run(object_path, game_parameter_path, property_name="Volume", curve_points=None, notes=""):
    from ._waapi_helpers import get_objects, object_set, VALID_CURVE_SHAPES, ok, err

    try:
        target_objs = get_objects(
            from_spec={"path": [object_path]},
            return_fields=["name", "type", "path", "id"],
        )
        if not target_objs:
            return err("not_found", f"目标对象不存在：{object_path}",
                       "请先调用 search_objects 搜索正确路径")

        gp_objs = get_objects(
            from_spec={"path": [game_parameter_path]},
            return_fields=["name", "type", "path", "id"],
        )
        if not gp_objs:
            return err("not_found", f"Game Parameter 不存在：{game_parameter_path}",
                       "请先调用 get_rtpc_list 查看可用的 Game Parameter")
        gp_id = gp_objs[0].get("id")
        if not gp_id:
            return err("waapi_error", "无法获取 Game Parameter 的 ID")

        if curve_points is None:
            curve_points = [
                {"x": 0, "y": 0, "shape": "Linear"},
                {"x": 100, "y": 0, "shape": "Linear"},
            ]

        for i, pt in enumerate(curve_points):
            if "x" not in pt or "y" not in pt:
                return err("invalid_param", f"曲线点 [{i}] 缺少 x 或 y 坐标")
            shape = pt.get("shape", "Linear")
            if shape not in VALID_CURVE_SHAPES:
                return err("invalid_param", f"曲线点 [{i}] 的 shape '{shape}' 不合法",
                           f"可选值：{sorted(VALID_CURVE_SHAPES)}")
            pt["shape"] = shape

        rtpc_entry = {
            "type": "RTPC",
            "name": "",
            "@Curve": {"type": "Curve", "points": curve_points},
            "@PropertyName": property_name,
            "@ControlInput": gp_id,
        }
        if notes:
            rtpc_entry["notes"] = notes

        result = object_set(
            objects=[{"object": object_path, "@RTPC": [rtpc_entry]}],
            list_mode="append",
        )

        return ok({
            "object_path": object_path,
            "game_parameter": {
                "path": game_parameter_path,
                "id": gp_id,
                "name": gp_objs[0].get("name"),
            },
            "property_name": property_name,
            "curve_points_count": len(curve_points),
            "result": result,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
