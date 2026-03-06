# -*- coding: utf-8 -*-
"""直接执行原始 WAAPI 调用（兜底工具）"""

SKILL_INFO = {
    "name": "execute_waapi",
    "description": "直接执行原始 WAAPI 调用（兜底工具），受黑名单保护。当其他工具无法满足需求时使用。",
    "parameters": {
        "uri": {"type": "string", "description": "WAAPI URI", "required": True},
        "args": {"type": "object", "description": "WAAPI arguments 字典", "required": False},
        "opts": {"type": "object", "description": "WAAPI options 字典", "required": False},
    },
}


def run(uri, args=None, opts=None):
    from ._waapi_helpers import waapi_call, BLACKLISTED_URIS, ok, err

    if args is None:
        args = {}
    if opts is None:
        opts = {}

    for blocked_uri in BLACKLISTED_URIS:
        if uri.startswith(blocked_uri):
            return err(
                "forbidden",
                f"操作 '{uri}' 在安全黑名单中，已被拒绝执行",
                "如需执行此操作，请直接在 Wwise 界面操作，或联系管理员修改黑名单配置",
            )

    try:
        result = waapi_call(uri, args, opts)
        return ok(result)
    except Exception as e:
        return err("unexpected_error", str(e))
