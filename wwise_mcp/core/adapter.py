"""
WwiseAdapter：Layer 1 — WAAPI Host Adapter
封装所有 WAAPI 调用，对上层工具暴露简洁接口。
"""

import logging
from typing import Any, Optional

from .connection import WwiseConnection
from .exceptions import WwiseAPIError, WwiseConnectionError

logger = logging.getLogger("wwise_mcp.adapter")

_connection: Optional[WwiseConnection] = None


def get_connection() -> WwiseConnection:
    """获取全局 WAAPI 连接实例"""
    if _connection is None:
        raise WwiseConnectionError("WwiseAdapter 尚未初始化，请确认 Agent 已正常启动")
    return _connection


def init_connection() -> WwiseConnection:
    """初始化全局连接实例"""
    global _connection
    _connection = WwiseConnection()
    return _connection


class WwiseAdapter:
    """
    WAAPI 调用封装。
    每个工具函数通过此类访问 Wwise，不直接操作底层连接。

    调用约定：
      - args: WAAPI arguments 字典
      - opts: WAAPI options 字典，内部合并为 {"options": opts}
      - 返回字段名不带 @ 前缀
    """

    def __init__(self, connection: Optional[WwiseConnection] = None):
        self._conn = connection or get_connection()

    # ------------------------------------------------------------------
    # 核心调用接口
    # ------------------------------------------------------------------

    async def call(self, uri: str, args: dict = {}, opts: dict = {}) -> dict:
        """执行 WAAPI 调用（async）"""
        payload = dict(args)
        if opts:
            payload["options"] = opts
        return await self._conn.call(uri, payload)

    def call_sync(self, uri: str, args: dict = {}, opts: dict = {}) -> dict:
        """执行 WAAPI 调用（sync — Agent 线程用）"""
        payload = dict(args)
        if opts:
            payload["options"] = opts
        return self._conn.call_sync(uri, payload)

    # ------------------------------------------------------------------
    # 便利方法
    # ------------------------------------------------------------------

    async def get_info(self) -> dict:
        """获取 Wwise 项目基础信息"""
        return await self.call("ak.wwise.core.getInfo")

    async def get_objects(
        self,
        from_spec: dict,
        return_fields: list[str] | None = None,
        transform: list | None = None,
    ) -> list[dict]:
        """通用对象查询"""
        if return_fields is None:
            return_fields = ["name", "type", "path", "id"]

        args: dict[str, Any] = {"from": from_spec}
        if transform:
            args["transform"] = transform

        result = await self.call(
            "ak.wwise.core.object.get",
            args,
            {"return": return_fields},
        )
        return result.get("return", [])

    async def create_object(
        self,
        name: str,
        obj_type: str,
        parent_path: str,
        on_conflict: str = "rename",
        children: list | None = None,
        notes: str = "",
    ) -> dict:
        """创建 Wwise 对象"""
        args: dict[str, Any] = {
            "name": name,
            "type": obj_type,
            "parent": parent_path,
            "onNameConflict": on_conflict,
        }
        if children:
            args["children"] = children
        if notes:
            args["notes"] = notes
        result = await self.call("ak.wwise.core.object.create", args)
        obj_id = result.get("id") if result else None
        if obj_id:
            try:
                objs = await self.get_objects(
                    from_spec={"id": [obj_id]},
                    return_fields=["name", "path", "type"],
                )
                if objs:
                    result = {**result, "path": objs[0].get("path"), "name": objs[0].get("name")}
            except Exception:
                pass
        return result

    async def set_property(
        self, object_path: str, prop: str, value: Any, platform: str | None = None
    ) -> dict:
        """设置对象属性"""
        args: dict[str, Any] = {
            "object": object_path,
            "property": prop,
            "value": value,
        }
        if platform:
            args["platform"] = platform
        return await self.call("ak.wwise.core.object.setProperty", args)

    async def set_reference(
        self, object_path: str, reference: str, value_path: str, platform: str | None = None
    ) -> dict:
        """设置对象引用"""
        args: dict[str, Any] = {
            "object": object_path,
            "reference": reference,
            "value": value_path,
        }
        if platform:
            args["platform"] = platform
        return await self.call("ak.wwise.core.object.setReference", args)

    async def delete_object(self, object_path: str) -> dict:
        """删除对象"""
        return await self.call(
            "ak.wwise.core.object.delete",
            {"object": object_path},
        )

    async def move_object(self, object_path: str, new_parent_path: str) -> dict:
        """移动对象到新父节点"""
        return await self.call(
            "ak.wwise.core.object.move",
            {
                "object": object_path,
                "parent": new_parent_path,
                "onNameConflict": "rename",
            },
        )

    async def get_selected_objects(self) -> list[dict]:
        """获取 Wwise 编辑器中当前选中的对象"""
        result = await self.call(
            "ak.wwise.ui.getSelectedObjects",
            {},
            {"return": ["name", "type", "path", "id"]},
        )
        return result.get("objects", [])

    # ------------------------------------------------------------------
    # object.set — 批量操作（RTPC / Effect / 复杂创建）
    # ------------------------------------------------------------------

    async def object_set(
        self,
        objects: list[dict],
        on_name_conflict: str = "rename",
        list_mode: str = "append",
    ) -> dict:
        """调用 ak.wwise.core.object.set 执行批量操作。"""
        args: dict[str, Any] = {
            "objects": objects,
            "onNameConflict": on_name_conflict,
            "listMode": list_mode,
        }
        return await self.call("ak.wwise.core.object.set", args)
