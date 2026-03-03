"""
Layer 4 — 兜底工具：execute_waapi
"""

import logging
from typing import Any

from ..core.adapter import WwiseAdapter
from ..core.exceptions import WwiseMCPError, WwiseForbiddenOperationError
from ..config import settings

logger = logging.getLogger("wwise_mcp.tools.fallback")


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


async def execute_waapi(uri: str, args: dict = {}, opts: dict = {}) -> dict:
    """直接执行原始 WAAPI 调用（兜底工具），受黑名单保护。"""
    for blocked_uri in settings.blacklisted_uris:
        if uri.startswith(blocked_uri):
            forbidden_error = WwiseForbiddenOperationError(uri)
            logger.warning("拒绝黑名单操作：%s", uri)
            return forbidden_error.to_dict()

    try:
        adapter = WwiseAdapter()
        result = await adapter.call(uri, args, opts)
        return _ok(result)
    except WwiseMCPError as e:
        return _err(e)
    except Exception as e:
        return _err_raw("unexpected_error", str(e))
