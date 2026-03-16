# -*- coding: utf-8 -*-
"""
Wwise 版本兼容层 — 所有版本相关逻辑的单一真相源

支持 Wwise 2022.x ~ 2025.x，提供：
- 版本号解析与比较
- 版本特定特性查询（Auto-Defined SoundBank、Live Editing、Blend Container WAAPI 等）
- 层级路径映射（兼容 2025.1 的命名空间重构）
- 动态提示文本生成（System Prompt、工具返回消息等）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("shared.wwise_version")


# ============================================================
# 版本号解析
# ============================================================

@dataclass(frozen=True, order=True)
class WwiseVersion:
    """Wwise 版本号（可排序、可比较）。"""
    major: int
    minor: int
    patch: int = 0

    @classmethod
    def parse(cls, version_string: str) -> Optional["WwiseVersion"]:
        """从版本字符串中提取主版本号。

        支持格式：
          - "2024.1.0.8897"  (displayName)
          - "2024.1"
          - "v2024.1.0"
        """
        m = re.search(r"(\d{4})\.(\d+)(?:\.(\d+))?", version_string)
        if m:
            return cls(
                major=int(m.group(1)),
                minor=int(m.group(2)),
                patch=int(m.group(3)) if m.group(3) else 0,
            )
        return None

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}" + (f".{self.patch}" if self.patch else "")

    def at_least(self, major: int, minor: int = 0) -> bool:
        """判断是否 ≥ 指定版本。"""
        return (self.major, self.minor) >= (major, minor)

    @property
    def year(self) -> int:
        return self.major


# 常量
WWISE_2022 = WwiseVersion(2022, 1)
WWISE_2023 = WwiseVersion(2023, 1)
WWISE_2024 = WwiseVersion(2024, 1)
WWISE_2025 = WwiseVersion(2025, 1)

# 最低支持版本
MIN_SUPPORTED = WWISE_2022
MAX_KNOWN = WWISE_2025


# ============================================================
# 版本特性查询
# ============================================================

@dataclass(frozen=True)
class WwiseFeatures:
    """当前 Wwise 版本支持的特性集合。"""
    version: WwiseVersion

    @property
    def has_auto_defined_soundbank(self) -> bool:
        """Auto-Defined SoundBank（2022+ 默认开启）。"""
        return self.version.at_least(2022, 1)

    @property
    def has_live_editing(self) -> bool:
        """Live Editing 完整支持（2023+ 完整，2022 部分）。"""
        return self.version.at_least(2023, 1)

    @property
    def has_blend_container_waapi(self) -> bool:
        """Blend Container 完整 WAAPI 管理（2024.1+）。"""
        return self.version.at_least(2024, 1)

    @property
    def has_new_waql_accessors(self) -> bool:
        """WAQL 新增访问器（extractEvents 等，2025.1+）。"""
        return self.version.at_least(2025, 1)

    @property
    def has_hierarchy_rename(self) -> bool:
        """2025.1 层级命名空间重构。"""
        return self.version.at_least(2025, 1)


def get_features(version: WwiseVersion) -> WwiseFeatures:
    return WwiseFeatures(version=version)


# ============================================================
# 层级路径映射（兼容 2025.1 重命名）
# ============================================================

# 逻辑名 → 各版本实际路径
_HIERARCHY_PATHS: dict[str, dict[str, str]] = {
    "actor_mixer": {
        "legacy": "\\Actor-Mixer Hierarchy",
        "2025": "\\Property Container",
    },
    "master_mixer": {
        "legacy": "\\Master-Mixer Hierarchy",
        "2025": "\\Busses",
    },
    "interactive_music": {
        "legacy": "\\Interactive Music Hierarchy",
        "2025": "\\Containers",  # 合并到 Containers
    },
}

# 不受版本影响的路径
_STABLE_PATHS = {
    "events": "\\Events",
    "soundbanks": "\\SoundBanks",
    "game_parameters": "\\Game Parameters",
    "switches": "\\Switches",
    "states": "\\States",
    "effects": "\\Effects",
    "attenuations": "\\Attenuations",
}


def resolve_path(logical_name: str, version: WwiseVersion) -> str:
    """将逻辑名解析为当前版本的实际路径。

    Args:
        logical_name: 逻辑路径名，如 "actor_mixer", "master_mixer", "events" 等
        version: 当前 Wwise 版本

    Returns:
        实际的 Wwise 层级路径字符串
    """
    if logical_name in _STABLE_PATHS:
        return _STABLE_PATHS[logical_name]

    mapping = _HIERARCHY_PATHS.get(logical_name)
    if not mapping:
        raise ValueError(f"未知的逻辑路径名: {logical_name}")

    if version.at_least(2025, 1):
        return mapping["2025"]
    return mapping["legacy"]


def get_known_roots(version: WwiseVersion) -> list[str]:
    """获取当前版本的所有顶层 Hierarchy 路径。"""
    roots = []
    for logical_name in _HIERARCHY_PATHS:
        roots.append(resolve_path(logical_name, version))
    for path in _STABLE_PATHS.values():
        roots.append(path)
    return roots


# ============================================================
# 动态提示文本生成
# ============================================================

def get_version_display(version: WwiseVersion) -> str:
    """获取用于 UI / 日志显示的版本字符串。"""
    return str(version)


def get_connection_suggestion(version: Optional[WwiseVersion] = None) -> str:
    """生成连接失败时的建议文本。"""
    if version:
        return f"请确认 Wwise {version} 正在运行，且 WAAPI 已在 User Settings 中启用（默认端口 8080）"
    return "请确认 Wwise 正在运行，且 WAAPI 已在 User Settings 中启用（默认端口 8080）"


def get_api_error_suggestion(version: Optional[WwiseVersion] = None) -> str:
    """生成 API 错误时的建议文本。"""
    if version:
        return f"检查 WAAPI 调用参数是否符合 Wwise {version} 规范"
    return "检查 WAAPI 调用参数是否符合当前 Wwise 版本规范"


def get_soundbank_note(version: WwiseVersion) -> str:
    """生成 SoundBank 相关的提示文本。"""
    features = get_features(version)
    if features.has_auto_defined_soundbank:
        return f"Wwise {version} 默认开启 Auto-Defined SoundBank，无需手动管理 Bank 加载/卸载"
    return "请手动管理 SoundBank 的 Inclusion 和生成"


def get_live_editing_note(version: WwiseVersion) -> str:
    """生成 Live Editing 相关的提示文本。"""
    features = get_features(version)
    if features.has_live_editing:
        return f"Wwise {version} Live Editing 已启用，无需重新生成 SoundBank 即可立即验证"
    return "修改后需要重新生成 SoundBank 并在游戏中加载才能验证"


def get_create_event_note(version: WwiseVersion) -> str:
    """生成创建 Event 后的提示文本。"""
    return get_live_editing_note(version)


def get_verify_live_editing_note(version: WwiseVersion) -> str:
    """生成验证工具中的 Live Editing 状态文本。"""
    features = get_features(version)
    if features.has_live_editing:
        return f"Wwise {version} Live Editing 已启用"
    return "Live Editing 不可用，请手动生成 SoundBank 验证"


# ============================================================
# System Prompt 动态文本块
# ============================================================

def get_role_block(version: WwiseVersion) -> str:
    """BLOCK_1: 角色定义。"""
    return f"""你是一位专业的 Wwise 音频设计 AI 助手，专门操作 Wwise {version} Authoring Tool。

你的职责：
- 通过 WAAPI 工具帮助音频设计师创建、修改、验证 Wwise 项目中的音频资产
- 每次操作后主动验证结果，确保结构完整性
- 遵守 Wwise {version} 的最佳实践和操作规范

操作边界：
- 你只能通过提供的工具操作 Wwise，不能直接修改文件系统
- 危险操作（项目打开/关闭/保存）由用户在 Wwise 界面手动执行
- 删除操作前必须先确认无悬空引用""".strip()


def get_object_model_block(version: WwiseVersion) -> str:
    """BLOCK_2: 对象模型。根据版本动态调整层级名称和路径示例。"""
    features = get_features(version)

    # 层级名称
    actor_mixer_name = "Property Container" if features.has_hierarchy_rename else "Actor-Mixer Hierarchy"
    master_mixer_name = "Busses" if features.has_hierarchy_rename else "Master-Mixer Hierarchy"
    interactive_music_name = "Containers" if features.has_hierarchy_rename else "Interactive Music Hierarchy"

    # 路径前缀
    am_path = resolve_path("actor_mixer", version)
    mm_path = resolve_path("master_mixer", version)

    # Blend Container 描述
    blend_desc = (
        f"Blend Container：{version} 支持完整 WAAPI 管理，多轨混合"
        if features.has_blend_container_waapi
        else "Blend Container：多轨混合（WAAPI 支持有限）"
    )

    return f"""## Wwise 对象模型

### 核心层级结构

**{actor_mixer_name}**（音频内容）：
- Work Unit → Folder → Container/Sound
- Sound SFX / Sound Voice：叶节点，包含 AudioFileSource
- Random/Sequence Container：随机/顺序播放多个子 Sound
- {blend_desc}
- Switch Container：根据 Switch/State 选择播放分支
- Actor-Mixer：批量属性继承的组织容器

**Events Hierarchy**（触发逻辑）：
- Event → Action → Target（Sound/Container）
- Action 类型：Play(1) / Stop(2) / Pause(3) / Resume(4) / Break(28) / Mute(6) / UnMute(7)
- 一个 Event 可包含多个 Action，依次执行

**{master_mixer_name}**（混音路由）：
- Master Audio Bus（顶层）
- 自定义子 Bus：SFX / Music / Voice / Ambient 等常见分组
- Auxiliary Bus：用于 Send/Reverb 等空间效果
- Sound 通过 OutputBus 属性路由到指定 Bus

**{interactive_music_name}**：
- Music Switch Container / Music Playlist Container
- Music Segment → Music Track → Music Clip

**Game Syncs**：
- Game Parameter（RTPC）：驱动音量/音调等连续变化
- Switch Group / State Group：驱动 Switch Container 分支选择

### WAAPI 路径格式规范

```
{am_path}\\Default Work Unit\\<对象名>
\\Events\\Default Work Unit\\<Event 名>
{mm_path}\\Master Audio Bus\\<Bus 名>
\\Game Parameters\\Default Work Unit\\<RTPC 名>
\\SoundBanks\\Default Work Unit\\<Bank 名>
```

所有路径以双反斜杠 `\\` 开头，节点之间用 `\\` 分隔。

### RTPC 系统

RTPC（Real-Time Parameter Control）将 Game Parameter 驱动到对象属性：
- 常用绑定：Distance → Volume（衰减）、Speed → Pitch、HP → Lowpass
- 曲线类型：Linear / Log1~3 / Exp1~3 / SCurve / InvertedSCurve
- RTPC 绑定可通过 set_rtpc_binding 工具自动完成
- 绑定前确保 Game Parameter 已存在

### Effect 系统

Effect 插件可挂载到 Sound/Bus 的 Effect 插槽（Effect0~Effect3）：
- 常用 Effect：RoomVerb、Delay、Compressor、ParametricEQ
- 通过 add_effect 工具添加，通过 remove_effect 移除
- 通过 get_effect_chain 查询对象当前的 Effect 链""".strip()


def get_features_block(version: WwiseVersion) -> str:
    """BLOCK_3: 当前版本关键特性。"""
    features = get_features(version)
    sections = [f"## Wwise {version} 关键特性"]

    # Auto-Defined SoundBank
    if features.has_auto_defined_soundbank:
        sections.append("""
### Auto-Defined SoundBank
- **默认开启**：每个 Event 自动对应一个同名 SoundBank
- **不要**主动调用 generate_soundbank，除非用户明确要求
- User-Defined SoundBank 只在用户明确要求时创建""")
    else:
        sections.append("""
### SoundBank 管理
- 需要手动管理 SoundBank 的 Inclusion 列表
- 创建新 Event 后需要将其加入 SoundBank 并重新生成""")

    # Live Editing
    if features.has_live_editing:
        sections.append("""
### Live Editing
- 属性修改**实时同步**到已连接的游戏实例
- 操作完成后建议用户在游戏中直接验证音效""")
    else:
        sections.append("""
### SoundBank 验证流程
- 属性修改后需要重新生成 SoundBank
- 在游戏中重新加载 Bank 后才能验证效果""")

    # Blend Container WAAPI
    if features.has_blend_container_waapi:
        sections.append(f"""
### Blend Container（完整 WAAPI 支持）
- {version} 支持 Blend Track/Child 管理 API
- 创建时使用 type='BlendContainer'""")

    # 2025 新增
    if features.has_new_waql_accessors:
        sections.append("""
### WAQL 新增访问器（2025.1+）
- 新增 18 个访问器：extractEvents、extractBusses 等
- 查询能力大幅增强""")

    if features.has_hierarchy_rename:
        sections.append("""
### 层级命名空间变更（2025.1）
- Actor-Mixer Hierarchy → Property Container
- Master-Mixer Hierarchy → Busses
- Interactive Music Hierarchy → Containers
- 注意：路径查询需使用新名称""")

    sections.append("""
### WAAPI 变化注意事项
- ak.wwise.core.object.setReference 的 platform 字段有调整
- SoundBank 生成 API 在 Auto-Defined 场景下行为变化""")

    return "\n".join(sections).strip()


# ============================================================
# 全局版本状态管理
# ============================================================

class WwiseVersionManager:
    """全局版本管理器 — 在连接建立时检测并缓存版本信息。"""

    _instance: Optional["WwiseVersionManager"] = None

    def __init__(self):
        self._version: Optional[WwiseVersion] = None
        self._features: Optional[WwiseFeatures] = None
        self._raw_info: Optional[dict] = None

    @classmethod
    def get_instance(cls) -> "WwiseVersionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（测试或重连时使用）。"""
        cls._instance = None

    @property
    def version(self) -> WwiseVersion:
        """当前检测到的 Wwise 版本。未检测时返回默认版本。"""
        return self._version or WWISE_2024

    @property
    def features(self) -> WwiseFeatures:
        """当前版本的特性集合。"""
        if self._features is None:
            self._features = get_features(self.version)
        return self._features

    @property
    def is_detected(self) -> bool:
        """是否已完成版本检测。"""
        return self._version is not None

    def set_version(self, version: WwiseVersion) -> None:
        """手动设置版本（连接后由 adapter 调用）。"""
        self._version = version
        self._features = get_features(version)
        logger.info("Wwise 版本已设置: %s", version)

    def set_from_info(self, info: dict) -> WwiseVersion:
        """从 getInfo 返回值中提取并设置版本。

        Args:
            info: ak.wwise.core.getInfo 的返回值

        Returns:
            解析出的版本号
        """
        self._raw_info = info
        display_name = info.get("version", {}).get("displayName", "")
        version = WwiseVersion.parse(display_name)
        if version:
            if version < MIN_SUPPORTED:
                logger.warning(
                    "检测到 Wwise %s，低于最低支持版本 %s，部分功能可能不可用",
                    version, MIN_SUPPORTED,
                )
            self.set_version(version)
            return version
        else:
            logger.warning("无法从 displayName '%s' 解析版本号，使用默认版本 %s", display_name, WWISE_2024)
            self.set_version(WWISE_2024)
            return WWISE_2024

    def resolve_path(self, logical_name: str) -> str:
        """解析逻辑路径名为当前版本的实际路径。"""
        return resolve_path(logical_name, self.version)

    def get_known_roots(self) -> list[str]:
        """获取当前版本的所有顶层 Hierarchy 路径。"""
        return get_known_roots(self.version)


# 便捷访问
version_manager = WwiseVersionManager.get_instance()
