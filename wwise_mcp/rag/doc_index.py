"""
Layer 2 — WwiseDocIndex：WAAPI Schema + 知识库索引
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# 确保 shared 可以被导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from shared.wwise_version import version_manager

logger = logging.getLogger("wwise_mcp.doc_index")

_DOC_DIR = Path(__file__).parent.parent / "doc"


class WwiseDocIndex:
    """WAAPI Schema 和知识库的快速查找索引。"""

    COMMON_PROPERTIES = {
        "Volume", "Pitch", "MakeUpGain",
        "LowPassFilter", "HighPassFilter",
        "OutputBus", "OutputBusVolume", "OutputBusMixerGain",
        "Positioning.EnablePositioning", "Positioning.SpeakerPanning",
        "Positioning.3D.AttenuationID",
        "MaxSoundInstances", "MaxSoundInstancesBehavior",
        "VirtualVoiceBehavior",
        "Volume.Min", "Volume.Max", "Pitch.Min", "Pitch.Max",
        "ActionType", "Target", "Delay", "TransitionTime",
        "IncludeInSoundBank",
        "UseGameDefinedAuxSends", "UserAuxSendVolume0",
        "CrossfadeParameter", "BlendTrackName",
        "Notes", "Color",
        "OverrideOutput",
    }

    WAAPI_FUNCTIONS: dict[str, dict] = {
        "ak.wwise.core.getInfo": {
            "description": "获取 Wwise 版本和项目基础信息",
            "required_args": [],
        },
        "ak.wwise.core.object.get": {
            "description": "查询 Wwise 对象",
            "required_args": ["from"],
        },
        "ak.wwise.core.object.create": {
            "description": "在指定父对象下创建新对象",
            "required_args": ["name", "type", "parent", "onNameConflict"],
        },
        "ak.wwise.core.object.delete": {
            "description": "删除 Wwise 对象",
            "required_args": ["object"],
        },
        "ak.wwise.core.object.move": {
            "description": "将对象移动到新父节点",
            "required_args": ["object", "parent"],
        },
        "ak.wwise.core.object.setProperty": {
            "description": "设置对象属性值",
            "required_args": ["object", "property", "value"],
        },
        "ak.wwise.core.object.setReference": {
            "description": "设置对象的引用类属性",
            "required_args": ["object", "reference", "value"],
        },
        "ak.wwise.core.object.set": {
            "description": "批量设置对象属性（RTPC/Effect 等复杂操作）",
            "required_args": ["objects"],
        },
        "ak.wwise.core.object.getPropertyAndReferenceNames": {
            "description": "获取对象支持的所有属性和引用名称列表",
            "required_args": ["object"],
        },
        "ak.wwise.ui.getSelectedObjects": {
            "description": "获取 Wwise 编辑器中当前选中的对象",
            "required_args": [],
        },
    }

    def __init__(self):
        self._schema: dict = {}
        self._knowledge: list[str] = []
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return

        # 按版本尝试加载 Schema，支持 fallback
        v = version_manager.version
        schema_candidates = [
            _DOC_DIR / f"waapi_schema_{v.major}.{v.minor}.json",
            _DOC_DIR / f"waapi_schema_{v.major}.json",
            _DOC_DIR / "waapi_schema.json",
        ]
        for schema_path in schema_candidates:
            if schema_path.exists():
                try:
                    with open(schema_path, encoding="utf-8") as f:
                        raw_schema = json.load(f)
                    if isinstance(raw_schema, list):
                        for item in raw_schema:
                            uri = item.get("uri") or item.get("id")
                            if uri:
                                self._schema[uri] = item
                    elif isinstance(raw_schema, dict):
                        self._schema = raw_schema
                    logger.info("已加载 WAAPI Schema（%s）：%d 个函数", schema_path.name, len(self._schema))
                    break
                except Exception as e:
                    logger.warning("加载 WAAPI Schema 失败（%s）：%s", schema_path.name, e)

        kb_path = _DOC_DIR / "knowledge_base.txt"
        if kb_path.exists():
            try:
                with open(kb_path, encoding="utf-8") as f:
                    self._knowledge = [
                        line.strip() for line in f if line.strip() and not line.startswith("#")
                    ]
                logger.info("已加载知识库：%d 条", len(self._knowledge))
            except Exception as e:
                logger.warning("加载知识库失败：%s", e)

        self._loaded = True

    def lookup_function(self, uri: str) -> Optional[dict]:
        self.load()
        if uri in self.WAAPI_FUNCTIONS:
            return self.WAAPI_FUNCTIONS[uri]
        return self._schema.get(uri)

    def is_valid_property(self, prop_name: str) -> bool:
        if prop_name in self.COMMON_PROPERTIES:
            return True
        for known in self.COMMON_PROPERTIES:
            if prop_name.startswith(known.split(".")[0]):
                return True
        return False

    def get_similar_properties(self, prop_name: str, limit: int = 5) -> list[str]:
        prop_lower = prop_name.lower()
        matches = [
            p for p in self.COMMON_PROPERTIES
            if prop_lower in p.lower() or p.lower() in prop_lower
        ]
        return matches[:limit]

    def search_knowledge(self, keyword: str, limit: int = 5) -> list[str]:
        self.load()
        keyword_lower = keyword.lower()
        results = [
            line for line in self._knowledge
            if keyword_lower in line.lower()
        ]
        return results[:limit]


doc_index = WwiseDocIndex()
