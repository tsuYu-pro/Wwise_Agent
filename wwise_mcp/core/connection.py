"""
WAAPI 连接管理 — 基于官方 waapi-client 库
WaapiClient 内部封装了完整的 WAMP 协议，无需手写协议细节。
"""

import asyncio
import logging
from typing import Optional

from waapi import WaapiClient
from waapi.wamp.interface import CannotConnectToWaapiException

from ..config import settings
from .exceptions import WwiseConnectionError, WwiseAPIError

logger = logging.getLogger("wwise_mcp.connection")


class WwiseConnection:
    """
    对 WaapiClient 的薄封装，提供 async 接口供 WwiseAdapter 使用。
    WaapiClient 本身是同步阻塞调用，通过 asyncio.to_thread() 避免阻塞事件循环。
    """

    def __init__(self):
        self._client: Optional[WaapiClient] = None

    async def ensure_connected(self) -> None:
        """确保连接可用，未连接时主动建立连接。"""
        if self._client and self._client.is_connected():
            return
        await self._connect()

    async def _connect(self) -> None:
        try:
            self._client = await asyncio.to_thread(
                lambda: WaapiClient(settings.waapi_url)
            )
            logger.info("WAAPI 连接成功：%s", settings.waapi_url)
        except CannotConnectToWaapiException as e:
            raise WwiseConnectionError(str(e))
        except Exception as e:
            raise WwiseConnectionError(f"连接失败：{e}")

    async def call(self, uri: str, payload: dict) -> dict:
        """
        发送 WAAPI 调用。超时时自动重试一次。
        payload 是 arguments + options 合并后的完整字典，由 WwiseAdapter 负责组装。
        """
        if not self._client or not self._client.is_connected():
            await self.ensure_connected()

        for attempt in range(2):
            try:
                result = await asyncio.to_thread(
                    lambda: self._client.call(uri, payload)
                )
                if result is None:
                    raise WwiseAPIError(
                        f"WAAPI 调用 '{uri}' 返回 None（参数可能有误，请检查 Wwise 日志）"
                    )
                return result
            except WwiseAPIError:
                raise
            except asyncio.TimeoutError:
                if attempt == 0:
                    logger.warning("WAAPI 调用 '%s' 超时，正在重试…", uri)
                    continue
                from .exceptions import WwiseTimeoutError
                raise WwiseTimeoutError()
            except Exception as e:
                raise WwiseAPIError(f"WAAPI 调用 '{uri}' 异常：{e}")

    async def close(self) -> None:
        """断开连接，释放资源。"""
        if self._client:
            await asyncio.to_thread(self._client.disconnect)
            self._client = None

    # ------------------------------------------------------------------
    # 同步接口 — 供 Agent 后台线程直接调用（非 async 环境）
    # ------------------------------------------------------------------

    def call_sync(self, uri: str, payload: dict) -> dict:
        """同步版本的 WAAPI 调用（在 Agent 线程中使用）"""
        if not self._client or not self._client.is_connected():
            self._connect_sync()

        try:
            result = self._client.call(uri, payload)
            if result is None:
                raise WwiseAPIError(
                    f"WAAPI 调用 '{uri}' 返回 None（参数可能有误）"
                )
            return result
        except WwiseAPIError:
            raise
        except Exception as e:
            raise WwiseAPIError(f"WAAPI 调用 '{uri}' 异常：{e}")

    def _connect_sync(self) -> None:
        """同步建立连接"""
        try:
            self._client = WaapiClient(settings.waapi_url)
            logger.info("WAAPI 同步连接成功：%s", settings.waapi_url)
        except CannotConnectToWaapiException as e:
            raise WwiseConnectionError(str(e))
        except Exception as e:
            raise WwiseConnectionError(f"连接失败：{e}")

    def close_sync(self) -> None:
        """同步断开连接"""
        if self._client:
            self._client.disconnect()
            self._client = None
