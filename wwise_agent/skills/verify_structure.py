# -*- coding: utf-8 -*-
"""结构完整性验证"""

SKILL_INFO = {
    "name": "verify_structure",
    "description": "验证 Wwise 项目结构完整性：孤儿 Event、Action 无 Target、Sound 无 Bus、属性范围检查。",
    "parameters": {
        "scope_path": {"type": "string", "description": "限定范围路径（可选，不传则全局扫描）", "required": False},
    },
}


def run(scope_path=None):
    from ._waapi_helpers import waapi_call, ok, err

    try:
        issues = []
        warnings = []

        if scope_path:
            event_result = waapi_call(
                "ak.wwise.core.object.get",
                {"from": {"path": [scope_path]}, "transform": [{"select": ["descendants"]}]},
                {"return": ["name", "path", "id", "childrenCount", "type"]},
            )
            all_desc = event_result.get("return", []) if event_result else []
            events = [o for o in all_desc if o.get("type") == "Event"]
        else:
            event_result = waapi_call(
                "ak.wwise.core.object.get",
                {"from": {"ofType": ["Event"]}},
                {"return": ["name", "path", "id", "childrenCount"]},
            )
            events = event_result.get("return", []) if event_result else []

        orphan_events = []
        for event in events:
            if event.get("childrenCount", 0) == 0:
                orphan_events.append(event.get("path"))
                issues.append({
                    "type": "orphan_event", "severity": "error",
                    "path": event.get("path"),
                    "message": f"Event '{event.get('name')}' 没有任何 Action",
                })

        action_result = waapi_call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["Action"]}},
            {"return": ["name", "path", "id", "Target"]},
        )
        actions = action_result.get("return", []) if action_result else []

        for action in actions:
            if not action.get("Target"):
                issues.append({
                    "type": "action_no_target", "severity": "error",
                    "path": action.get("path"),
                    "message": f"Action '{action.get('name')}' 的 Target 引用为空",
                })

        sound_result = waapi_call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["Sound"]}},
            {"return": ["name", "path", "id", "OutputBus"]},
        )
        sounds = sound_result.get("return", []) if sound_result else []

        sounds_no_bus = []
        for sound in sounds:
            if not sound.get("OutputBus"):
                sounds_no_bus.append(sound.get("path"))
                warnings.append({
                    "type": "sound_no_bus", "severity": "warning",
                    "path": sound.get("path"),
                    "message": f"Sound '{sound.get('name')}' 未指定 OutputBus",
                })

        range_issues = []
        for sound in sounds[:50]:
            try:
                props = waapi_call(
                    "ak.wwise.core.object.get",
                    {"from": {"path": [sound.get("path")]}},
                    {"return": ["Volume", "Pitch"]},
                )
                prop_list = props.get("return", [{}])
                if prop_list:
                    obj_props = prop_list[0]
                    volume = obj_props.get("Volume")
                    pitch = obj_props.get("Pitch")
                    if volume is not None and not (-200 <= float(volume) <= 200):
                        range_issues.append({
                            "type": "volume_out_of_range", "severity": "warning",
                            "path": sound.get("path"),
                            "message": f"Volume={volume} 超出正常范围",
                        })
                    if pitch is not None and not (-2400 <= float(pitch) <= 2400):
                        range_issues.append({
                            "type": "pitch_out_of_range", "severity": "warning",
                            "path": sound.get("path"),
                            "message": f"Pitch={pitch} 超出正常范围",
                        })
            except Exception:
                pass

        issues.extend(range_issues)
        issues.extend(warnings)

        error_count = sum(1 for i in issues if i.get("severity") == "error")
        warning_count = sum(1 for i in issues if i.get("severity") == "warning")
        passed = error_count == 0

        return ok({
            "passed": passed,
            "summary": {
                "errors": error_count,
                "warnings": warning_count,
                "total_events_checked": len(events),
                "total_actions_checked": len(actions),
                "total_sounds_checked": len(sounds),
            },
            "orphan_events": orphan_events,
            "sounds_without_bus": sounds_no_bus,
            "issues": issues,
            "message": "结构验证通过" if passed else f"发现 {error_count} 个错误，{warning_count} 个警告",
        })
    except Exception as e:
        return err("unexpected_error", str(e))
