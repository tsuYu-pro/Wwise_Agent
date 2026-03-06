# -*- coding: utf-8 -*-
"""为对象或 Bus 添加 Effect 插件"""

SKILL_INFO = {
    "name": "add_effect",
    "description": "为对象或 Bus 添加 Effect 插件。可用类型：RoomVerb, Delay, Compressor, Expander, PeakLimiter, ParametricEQ, MeterFX, GainFX 等。",
    "parameters": {
        "object_path": {"type": "string", "description": "目标对象或 Bus 路径", "required": True},
        "effect_name": {"type": "string", "description": "Effect 实例名称", "required": True},
        "effect_plugin": {"type": "string", "description": "插件类型名称或 classId", "required": True},
        "effect_slot": {"type": "integer", "description": "插槽位置 0~3，默认 0", "required": False},
        "effect_params": {"type": "object", "description": "额外的 Effect 参数（可选）", "required": False},
    },
}


def run(object_path, effect_name, effect_plugin, effect_slot=0, effect_params=None):
    from ._waapi_helpers import get_objects, object_set, EFFECT_CLASS_IDS, ok, err

    try:
        target_objs = get_objects(
            from_spec={"path": [object_path]},
            return_fields=["name", "type", "path", "id"],
        )
        if not target_objs:
            return err("not_found", f"目标对象不存在：{object_path}",
                       "请先调用 search_objects 搜索正确路径")

        if isinstance(effect_plugin, int):
            class_id = effect_plugin
        elif isinstance(effect_plugin, str) and effect_plugin.isdigit():
            class_id = int(effect_plugin)
        elif effect_plugin in EFFECT_CLASS_IDS:
            class_id = EFFECT_CLASS_IDS[effect_plugin]
        else:
            return err("invalid_param", f"未知的 Effect 插件类型：'{effect_plugin}'",
                       f"可用类型：{sorted(EFFECT_CLASS_IDS.keys())}")

        if not (0 <= effect_slot <= 3):
            return err("invalid_param", f"effect_slot 必须在 0~3 之间，收到 {effect_slot}")

        effect_obj = {"type": "Effect", "name": effect_name, "classId": class_id}
        if effect_params:
            effect_obj.update(effect_params)

        result = object_set(
            objects=[{
                "object": object_path,
                "@Effects": [{"type": "EffectSlot", "name": "", "@Effect": effect_obj}],
            }],
            list_mode="append",
        )

        return ok({
            "object_path": object_path,
            "effect": {
                "name": effect_name,
                "plugin": effect_plugin,
                "classId": class_id,
                "slot": effect_slot,
            },
            "result": result,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
