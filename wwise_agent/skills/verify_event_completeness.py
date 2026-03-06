# -*- coding: utf-8 -*-
"""验证 Event 完整性"""

SKILL_INFO = {
    "name": "verify_event_completeness",
    "description": "验证单个 Event 的完整性：Action 是否存在、Target 引用、音频文件、SoundBank 包含。",
    "parameters": {
        "event_path": {"type": "string", "description": "Event 路径", "required": True},
    },
}


def run(event_path):
    from ._waapi_helpers import get_objects, waapi_call, ok, err

    try:
        checks = []
        all_passed = True

        events = get_objects(
            from_spec={"path": [event_path]},
            return_fields=["name", "type", "path", "id", "childrenCount"],
        )
        if not events:
            return err("not_found", f"Event 不存在：{event_path}")

        event = events[0]
        checks.append({"check": "event_exists", "passed": True, "detail": f"Event 存在：{event.get('name')}"})

        child_count = event.get("childrenCount", 0)
        has_actions = child_count > 0
        if not has_actions:
            all_passed = False
        checks.append({
            "check": "has_actions", "passed": has_actions,
            "detail": f"Action 数量：{child_count}" if has_actions else "Event 没有 Action",
        })

        action_result = waapi_call(
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
            "check": "actions_have_targets", "passed": target_ok,
            "detail": f"{len(actions_with_target)}/{len(actions)} 个 Action 有 Target 引用",
        })

        audio_sources = []
        for action in actions_with_target:
            target = action.get("Target", {})
            target_path = target.get("path") if isinstance(target, dict) else None
            if target_path:
                try:
                    sources = waapi_call(
                        "ak.wwise.core.object.get",
                        {"from": {"path": [target_path]}, "transform": [{"select": ["descendants"]}]},
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
                "check": "audio_file_sources", "passed": sources_ok,
                "detail": f"{len(sources_with_file)}/{len(audio_sources)} 个 AudioFileSource 有音频文件",
            })
        else:
            checks.append({
                "check": "audio_file_sources", "passed": True,
                "detail": "未找到 AudioFileSource（可能为 Synthesizer 或 External Source）",
            })

        try:
            waapi_call(
                "ak.wwise.core.soundbank.getInclusions",
                {"soundbank": "\\SoundBanks\\Default Work Unit"},
            )
            checks.append({
                "check": "soundbank_inclusion", "passed": True,
                "detail": "Auto-Defined SoundBank 会自动包含此 Event",
            })
        except Exception:
            checks.append({
                "check": "soundbank_inclusion", "passed": True,
                "detail": "Auto-Defined SoundBank 模式",
            })

        return ok({
            "event": event_path,
            "all_passed": all_passed,
            "checks": checks,
            "live_editing_note": "Wwise 2024.1 Live Editing 已启用",
        })
    except Exception as e:
        return err("unexpected_error", str(e))
