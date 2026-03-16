"""
Layer 6 — Wwise 领域 System Prompt
固定区块 1-4（可缓存部分），支持多版本动态生成
"""

import sys
import os

# 确保 shared 可以被导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from shared.wwise_version import (
    WwiseVersion,
    version_manager,
    get_role_block,
    get_object_model_block,
    get_features_block,
)


BLOCK_4_RULES = """
## 操作规范

### 必须遵守的操作顺序
1. **创建 Event**：必须严格按顺序：
   - 先 create_object（type=Event）→ 再 create_object（type=Action）→ 最后 set_property 设置 Target
   - 或直接使用 create_event 工具（已封装上述三步）

2. **删除对象**：
   - 先调用 search_objects 确认无其他对象引用该目标
   - 确认安全后再调用 delete_object

3. **每完成一个独立操作目标后**，必须调用 verify_structure 进行结构验证

### 命名规范（推荐）
- Event：动词_名词，如 Play_Explosion, Stop_BGM
- Sound：类型_描述，如 SFX_Explosion_01, Voice_NPC_Hello
- Bus：功能分组，如 Bus_SFX, Bus_Music
- RTPC：描述性名称，如 Distance, Speed, HP_Ratio

### 工具使用优先级
1. 优先使用预定义工具（get_*、create_*、set_*、verify_*）
2. 预定义工具无法满足时，使用 execute_waapi 兜底
3. execute_waapi 调用前确认 URI 不在黑名单中
""".strip()


def get_full_system_prompt(dynamic_context: str = "", version: WwiseVersion | None = None) -> str:
    """组装完整 System Prompt。

    Args:
        dynamic_context: 动态上下文（项目状态、选中对象等）
        version: Wwise 版本，None 时使用 version_manager 的当前版本
    """
    v = version or version_manager.version
    parts = [
        get_role_block(v),
        "",
        get_object_model_block(v),
        "",
        get_features_block(v),
        "",
        BLOCK_4_RULES,
    ]
    if dynamic_context:
        parts += ["", "## 当前项目状态（实时上下文）", dynamic_context]
    return "\n".join(parts)


# 静态缓存（默认版本）— 向后兼容
STATIC_SYSTEM_PROMPT = get_full_system_prompt()
