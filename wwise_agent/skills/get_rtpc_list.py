# -*- coding: utf-8 -*-
"""获取 Game Parameter（RTPC）列表"""

SKILL_INFO = {
    "name": "get_rtpc_list",
    "description": "获取项目中所有 Game Parameter（RTPC）列表。",
    "parameters": {
        "max_results": {"type": "integer", "description": "最大结果数，默认 50", "required": False},
    },
}


def run(max_results=50):
    from ._waapi_helpers import waapi_call, ok, err

    try:
        result = waapi_call(
            "ak.wwise.core.object.get",
            {"from": {"ofType": ["GameParameter"]}},
            {"return": ["name", "type", "path", "id", "Min", "Max", "InitialValue"]},
        )
        rtpcs = result.get("return", [])
        rtpcs.sort(key=lambda x: x.get("path", ""))
        rtpcs = rtpcs[:max_results]

        return ok({
            "total": len(rtpcs),
            "rtpcs": rtpcs,
        })
    except Exception as e:
        return err("unexpected_error", str(e))
