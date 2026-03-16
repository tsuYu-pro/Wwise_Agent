# -*- coding: utf-8 -*-
"""获取 SoundBank 信息"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.wwise_version import version_manager, get_soundbank_note

SKILL_INFO = {
    "name": "get_soundbank_info",
    "description": "获取 SoundBank 信息。不传参数时返回所有 SoundBank 列表。",
    "parameters": {
        "soundbank_name": {"type": "string", "description": "SoundBank 名称（可选）", "required": False},
    },
}


def run(soundbank_name=None):
    from ._waapi_helpers import waapi_call, get_info, ok, err

    try:
        if soundbank_name:
            args = {"from": {"path": [f"\\SoundBanks\\{soundbank_name}"]}}
        else:
            args = {
                "from": {"path": ["\\SoundBanks"]},
                "transform": [{"select": ["children"]}],
            }

        result = waapi_call(
            "ak.wwise.core.object.get",
            args,
            {"return": ["name", "type", "path", "id"]},
        )
        banks = result.get("return", [])

        try:
            project_info = get_info()
            auto_soundbank = project_info.get("projectSettings", {}).get("autoSoundBank", True)
        except Exception:
            auto_soundbank = "unknown"

        return ok({
            "auto_defined_soundbank_enabled": auto_soundbank,
            "soundbank_count": len(banks),
            "soundbanks": banks,
            "note": get_soundbank_note(version_manager.version),
        })
    except Exception as e:
        return err("unexpected_error", str(e))
