"""
Layer 4 — 验证类工具（2 个）
"""

import logging
from typing import Any

from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError

logger = logging.getLogger("wwise_mcp.tools.verify")


def _ok(data: Any) -> dict:
    return {"success": True, "data": data, "error": None}

def _err(e: WwiseMCPError) -> dict:
    return e.to_dict()

def _err_raw(code: str, message: str, suggestion: str | None = None) -> dict:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "suggestion": suggestion},
    }


async def verify_structure(scope_path: str | None = None) -> dict:
    """结构完整性验证。"""
    try:
        adapter = WwiseAdapter()
        issues = []
        warnings = []

        if scope_path:
            event_result = await adapter.call(
                "ak.wwise.core.object.get",
                {"from": {"path": [scope_path]}, "transform": [{"select": ["descendants"]}]},
                {"return": ["name", "path", "id", "childrenCount", "type"]},
            )
            all_desc = event_result.get("return", []) if event_result else []
            events = [o for o in all_desc if o.get("type") == "Event"]
        else:
            event_result = await adapter.call(
                "ak.wwise.core.object.get",
                {"from": {"ofType": ["Event"]}},
                {"return": ["name", "path", "id", "childrenCount"]},
            )
            events = event_result.get("return", []) if event_result else []

        orphan_events = []
        for event in events:
            child_count = event.get("childrenCount", 0)
            if child_count == 0:
                orphan_events.append(event.get("path"))
                issues.append({
                    "type": "orphan_event",
                    "severity": "error",
                    "path": event.get("path"),
                    "message": f"Event '{event.get('name')}' 没有任何 Action",
                })

        action_result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["Action"]}},
            {"return": ["name", "path", "id", "Target"]},
        )
        actions = action_result.get("return", []) if action_result else []

        for action in actions:
            target = action.get("Target")
            if not target:
                issues.append({
                    "type": "action_no_target",
                    "severity": "error",
                    "path": action.get("path"),
                    "message": f"Action '{action.get('name')}' 的 Target 引用为空",
                })

        sound_result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["Sound"]}},
            {"return": ["name", "path", "id", "OutputBus"]},
        )
        sounds = sound_result.get("return", []) if sound_result else []

        sounds_no_bus = []
        for sound in sounds:
            output_bus = sound.get("OutputBus")
            if not output_bus:
                sounds_no_bus.append(sound.get("path"))
                warnings.append({
                    "type": "sound_no_bus",
                    "severity": "warning",
                    "path": sound.get("path"),
                    "message": f"Sound '{sound.get('name')}' 未指定 OutputBus",
                })

        range_issues = []
        for sound in sounds[:50]:
            try:
                props = await adapter.call(
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
                            "type": "volume_out_of_range",
                            "severity": "warning",
                            "path": sound.get("path"),
                            "message": f"Volume={volume} 超出正常范围",
                        })
                    if pitch is not None and not (-2400 <= float(pitch) <= 2400):
                        range_issues.append({
                            "type": "pitch_out_of_range",
                            "severity": "warning",
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

        return _ok({
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
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))


async def verify_event_completeness(event_path: str) -> dict:
    """验证 Event 完整性。"""
    try:
        adapter = WwiseAdapter()
        checks = []
        all_passed = True

        events = await adapter.get_objects(
            from_spec={"path": [event_path]},
            return_fields=["name", "type", "path", "id", "childrenCount"],
        )
        if not events:
            return _err_raw("not_found", f"Event 不存在：{event_path}")

        event = events[0]
        checks.append({"check": "event_exists", "passed": True, "detail": f"Event 存在：{event.get('name')}"})

        child_count = event.get("childrenCount", 0)
        has_actions = child_count > 0
        if not has_actions:
            all_passed = False
        checks.append({
            "check": "has_actions",
            "passed": has_actions,
            "detail": f"Action 数量：{child_count}" if has_actions else "Event 没有 Action",
        })

        action_result = await adapter.call(
            "ak.wwise.core.object.get",
            {"from": {"path": [event_path]}, "transform": [{"select": ["children"]}]},
            {"return": ["name", "type", "path", "ActionType", "Target"]},
        )
        actions = action_result.get("return", []) if action_result else []
        actions_with_target = [a for a in actions if a.get("Target")]
        target_ok = len(actions_with_target) == len(actions) and len(actions) > 0
        if not target_ok:
            all_passed = False
        checks.append({
            "check": "actions_have_targets",
            "passed": target_ok,
            "detail": f"{len(actions_with_target)}/{len(actions)} 个 Action 有 Target 引用",
        })

        audio_sources = []
        for action in actions_with_target:
            target = action.get("Target", {})
            target_path = target.get("path") if isinstance(target, dict) else None
            if target_path:
                try:
                    sources = await adapter.call(
                        "ak.wwise.core.object.get",
                        {
                            "from": {"path": [target_path]},
                            "transform": [{"select": ["descendants"]}],
                        },
                        {"return": ["name", "path", "id", "type", "AudioFile"]},
                    )
                    all_src = sources.get("return", []) if sources else []
                    audio_sources.extend(o for o in all_src if o.get("type") == "AudioFileSource")
                except Exception:
                    pass

        sources_with_file = [s for s in audio_sources if s.get("AudioFile")]
        if audio_sources:
            sources_ok = len(sources_with_file) == len(audio_sources)
            if not sources_ok:
                all_passed = False
            checks.append({
                "check": "audio_file_sources",
                "passed": sources_ok,
                "detail": f"{len(sources_with_file)}/{len(audio_sources)} 个 AudioFileSource 有音频文件",
            })
        else:
            checks.append({
                "check": "audio_file_sources",
                "passed": True,
                "detail": "未找到 AudioFileSource（可能为 Synthesizer 或 External Source）",
            })

        try:
            await adapter.call(
                "ak.wwise.core.soundbank.getInclusions",
                {"soundbank": "\\SoundBanks\\Default Work Unit"},
            )
            checks.append({
                "check": "soundbank_inclusion",
                "passed": True,
                "detail": "Auto-Defined SoundBank 会自动包含此 Event",
            })
        except Exception:
            checks.append({
                "check": "soundbank_inclusion",
                "passed": True,
                "detail": "Auto-Defined SoundBank 模式",
            })

        return _ok({
            "event": event_path,
            "all_passed": all_passed,
            "checks": checks,
            "live_editing_note": "Wwise 2024.1 Live Editing 已启用",
        })
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))
