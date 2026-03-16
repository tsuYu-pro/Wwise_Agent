"""
WwiseMCP 异常分类
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from shared.wwise_version import version_manager, get_connection_suggestion, get_api_error_suggestion


class WwiseMCPError(Exception):
    """所有 WwiseMCP 异常的基类"""
    def __init__(self, message: str, code: str = "unknown", suggestion: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.suggestion = suggestion

    def to_dict(self) -> dict:
        return {
            "success": False,
            "data": None,
            "error": {
                "code": self.code,
                "message": self.message,
                "suggestion": self.suggestion,
            },
        }


class WwiseConnectionError(WwiseMCPError):
    """WAAPI WebSocket 连接失败或断线"""
    def __init__(self, message: str = "无法连接到 Wwise WAAPI"):
        v = version_manager.version if version_manager.is_detected else None
        super().__init__(
            message=message,
            code="connection_error",
            suggestion=get_connection_suggestion(v),
        )


class WwiseAPIError(WwiseMCPError):
    """WAAPI 调用返回错误"""
    def __init__(self, message: str, waapi_code: int | None = None):
        v = version_manager.version if version_manager.is_detected else None
        super().__init__(
            message=message,
            code="waapi_error",
            suggestion=get_api_error_suggestion(v),
        )
        self.waapi_code = waapi_code


class WwiseObjectNotFoundError(WwiseMCPError):
    """目标对象路径不存在"""
    def __init__(self, path: str):
        super().__init__(
            message=f"对象不存在：{path}",
            code="not_found",
            suggestion=f"请先调用 search_objects 搜索 '{path}' 的正确路径",
        )


class WwiseInvalidPropertyError(WwiseMCPError):
    """属性名不合法"""
    def __init__(self, prop: str, valid_props: list[str] | None = None):
        suggestion = f"合法属性名参考：{', '.join(valid_props[:10])}" if valid_props else "请调用 get_object_properties 获取合法属性列表"
        super().__init__(
            message=f"属性名不合法：{prop}",
            code="invalid_param",
            suggestion=suggestion,
        )


class WwiseForbiddenOperationError(WwiseMCPError):
    """触发黑名单，禁止操作"""
    def __init__(self, uri: str):
        super().__init__(
            message=f"操作 '{uri}' 在安全黑名单中，已被拒绝执行",
            code="forbidden",
            suggestion="如需执行此操作，请直接在 Wwise 界面操作，或联系管理员修改黑名单配置",
        )


class WwiseTimeoutError(WwiseMCPError):
    """WAAPI 请求超时"""
    def __init__(self):
        super().__init__(
            message="WAAPI 请求超时",
            code="timeout",
            suggestion="请确认 Wwise 正在运行且响应正常，可尝试增加 timeout 配置值",
        )
