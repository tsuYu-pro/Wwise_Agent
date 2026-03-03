"""
WwiseMCP Server 配置
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class WwiseSettings:
    # WAAPI 连接参数
    host: str = "127.0.0.1"
    port: int = 8080
    timeout: float = 10.0
    reconnect_interval: float = 3.0
    max_reconnect: int = 5

    # execute_waapi 黑名单
    blacklisted_uris: List[str] = field(default_factory=lambda: [
        "ak.wwise.core.project.open",
        "ak.wwise.core.project.close",
        "ak.wwise.core.project.save",
        "ak.wwise.ui.project.open",
        "ak.wwise.core.undo.beginGroup",
        "ak.wwise.core.remote.connect",
        "ak.wwise.core.remote.disconnect",
    ])

    @property
    def waapi_url(self) -> str:
        return f"ws://{self.host}:{self.port}/waapi"


# 全局单例
settings = WwiseSettings()
