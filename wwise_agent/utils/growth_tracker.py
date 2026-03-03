# -*- coding: utf-8 -*-
"""
成长追踪 + 个性形成 (Growth Tracker + Personality Profile)

核心公式: Growth(t) = -d(Error)/dt
长期预测误差下降 = 成长

追踪指标（滚动窗口统计）：
- error_rate / success_rate 趋势
- avg_tool_calls / avg_retries 趋势
- skill_confidence: 各 Wwise 领域技能置信度

个性 = 策略强化的长期累积结果
"""

import json
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

from .memory_store import MemoryStore, get_memory_store

# ============================================================
# 持久化路径
# ============================================================

_GROWTH_FILE = Path(__file__).parent.parent.parent / "cache" / "memory" / "growth_profile.json"

# ============================================================
# 滚动窗口大小
# ============================================================

WINDOW_SIZE = 30


@dataclass
class TaskMetric:
    """单个任务的度量数据"""
    timestamp: float = 0.0
    success: bool = True
    error_count: int = 0
    retry_count: int = 0
    tool_call_count: int = 0
    reward: float = 0.0
    tags: List[str] = field(default_factory=list)


@dataclass
class PersonalityTraits:
    """个性特征（由 reward 偏向长期累积形成）"""
    efficiency_bias: float = 0.0     # >0 冷静理性, <0 探索创新
    risk_tolerance: float = 0.5      # 高=大胆尝试, 低=保守稳定
    verbosity: float = 0.5           # 回复详细度偏好
    proactivity: float = 0.5         # 主动提供建议 vs 只回答问题

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "PersonalityTraits":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class GrowthTracker:
    """成长追踪器 + 个性形成"""

    def __init__(self, store: Optional[MemoryStore] = None):
        self.store = store or get_memory_store()
        self._metrics: deque = deque(maxlen=WINDOW_SIZE * 2)

        # Wwise 领域技能置信度
        self._skill_confidence: Dict[str, float] = {
            "events": 0.5,
            "buses": 0.5,
            "effects": 0.5,
            "rtpc": 0.5,
            "spatial_audio": 0.5,
            "general": 0.5,
        }

        self.personality = PersonalityTraits()
        self._total_tasks: int = 0
        self._load()

    # ==========================================================
    # 记录任务度量
    # ==========================================================

    def record_task(self, metric: TaskMetric):
        if metric.timestamp == 0.0:
            metric.timestamp = time.time()
        self._metrics.append(metric)
        self._total_tasks += 1
        self._update_skill_confidence(metric)
        self._update_personality(metric)
        self._save()

    # ==========================================================
    # 趋势计算
    # ==========================================================

    def get_growth_metrics(self) -> Dict:
        if not self._metrics:
            return {
                "error_rate": 0.0, "error_rate_trend": 0.0,
                "success_rate": 1.0, "success_rate_trend": 0.0,
                "avg_tool_calls": 0.0, "avg_retries": 0.0,
                "growth_score": 0.0, "total_tasks": self._total_tasks,
            }

        metrics = list(self._metrics)
        n = len(metrics)
        half = n // 2

        recent = metrics[half:] if half > 0 else metrics
        older = metrics[:half] if half > 0 else []

        error_rate = sum(1 for m in recent if m.error_count > 0) / max(len(recent), 1)
        success_rate = sum(1 for m in recent if m.success) / max(len(recent), 1)
        avg_tool_calls = sum(m.tool_call_count for m in recent) / max(len(recent), 1)
        avg_retries = sum(m.retry_count for m in recent) / max(len(recent), 1)

        if older:
            old_error_rate = sum(1 for m in older if m.error_count > 0) / max(len(older), 1)
            old_success_rate = sum(1 for m in older if m.success) / max(len(older), 1)
            error_rate_trend = error_rate - old_error_rate
            success_rate_trend = success_rate - old_success_rate
        else:
            error_rate_trend = 0.0
            success_rate_trend = 0.0

        growth_score = -error_rate_trend + success_rate_trend

        return {
            "error_rate": round(error_rate, 3),
            "error_rate_trend": round(error_rate_trend, 3),
            "success_rate": round(success_rate, 3),
            "success_rate_trend": round(success_rate_trend, 3),
            "avg_tool_calls": round(avg_tool_calls, 1),
            "avg_retries": round(avg_retries, 1),
            "growth_score": round(growth_score, 3),
            "total_tasks": self._total_tasks,
        }

    # ==========================================================
    # 技能置信度
    # ==========================================================

    def _update_skill_confidence(self, metric: TaskMetric):
        alpha = 0.1

        # Wwise 领域标签映射
        skill_map = {
            "event_related": "events",
            "object_creation": "events",
            "bus_related": "buses",
            "effect_related": "effects",
            "rtpc_related": "rtpc",
            "spatial_related": "spatial_audio",
        }

        affected_skills = set()
        for tag in metric.tags:
            skill = skill_map.get(tag)
            if skill:
                affected_skills.add(skill)

        affected_skills.add("general")

        for skill in affected_skills:
            current = self._skill_confidence.get(skill, 0.5)
            target = 1.0 if metric.success else 0.0
            new_val = (1 - alpha) * current + alpha * target
            self._skill_confidence[skill] = round(max(0.0, min(1.0, new_val)), 3)

    def update_skill_confidence_batch(self, updates: Dict[str, float]):
        for skill, confidence in updates.items():
            current = self._skill_confidence.get(skill, 0.5)
            blended = 0.7 * current + 0.3 * confidence
            self._skill_confidence[skill] = round(max(0.0, min(1.0, blended)), 3)
        self._save()

    def get_skill_confidence(self) -> Dict[str, float]:
        return dict(self._skill_confidence)

    # ==========================================================
    # 个性形成
    # ==========================================================

    def _update_personality(self, metric: TaskMetric):
        alpha = 0.05

        if metric.success and metric.tool_call_count <= 3:
            self.personality.efficiency_bias += alpha
        elif not metric.success and metric.retry_count > 2:
            self.personality.efficiency_bias -= alpha

        if "error_correction" in metric.tags:
            self.personality.risk_tolerance = min(1.0, self.personality.risk_tolerance + alpha)
        elif "unresolved_error" in metric.tags:
            self.personality.risk_tolerance = max(0.0, self.personality.risk_tolerance - alpha)

        if "complex_task" in metric.tags and metric.success:
            self.personality.proactivity = min(1.0, self.personality.proactivity + alpha * 0.5)

        self.personality.efficiency_bias = max(-1.0, min(1.0, self.personality.efficiency_bias))

    def get_personality(self) -> PersonalityTraits:
        return self.personality

    def get_personality_description(self) -> str:
        """生成个性描述文本（注入 system prompt）"""
        p = self.personality
        skills = self._skill_confidence

        if p.efficiency_bias > 0.3:
            style = "efficiency-first, prefers concise direct solutions"
        elif p.efficiency_bias < -0.3:
            style = "exploratory, prefers trying multiple approaches"
        else:
            style = "balanced style, blending efficiency and exploration"

        if p.risk_tolerance > 0.7:
            risk = "high risk tolerance"
        elif p.risk_tolerance < 0.3:
            risk = "low risk tolerance, conservative"
        else:
            risk = "moderate risk tolerance"

        skill_parts = []
        for skill_name, conf in sorted(skills.items(), key=lambda x: -x[1]):
            if conf > 0.1:
                skill_parts.append(f"{skill_name}: {conf:.2f}")
        skills_text = ", ".join(skill_parts) if skill_parts else "no data"

        return (
            f"[Self-Awareness] Current style: {style}, {risk}.\n"
            f"Skill confidence: {skills_text}"
        )

    # ==========================================================
    # 持久化
    # ==========================================================

    def _save(self):
        try:
            _GROWTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "total_tasks": self._total_tasks,
                "skill_confidence": self._skill_confidence,
                "personality": self.personality.to_dict(),
                "metrics": [
                    {
                        "timestamp": m.timestamp,
                        "success": m.success,
                        "error_count": m.error_count,
                        "retry_count": m.retry_count,
                        "tool_call_count": m.tool_call_count,
                        "reward": m.reward,
                        "tags": m.tags,
                    }
                    for m in self._metrics
                ],
            }
            with open(_GROWTH_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[GrowthTracker] Save failed: {e}")

    def _load(self):
        if not _GROWTH_FILE.exists():
            return
        try:
            with open(_GROWTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._total_tasks = data.get("total_tasks", 0)
            self._skill_confidence.update(data.get("skill_confidence", {}))
            self.personality = PersonalityTraits.from_dict(data.get("personality", {}))
            for m_data in data.get("metrics", []):
                self._metrics.append(TaskMetric(
                    timestamp=m_data.get("timestamp", 0),
                    success=m_data.get("success", True),
                    error_count=m_data.get("error_count", 0),
                    retry_count=m_data.get("retry_count", 0),
                    tool_call_count=m_data.get("tool_call_count", 0),
                    reward=m_data.get("reward", 0),
                    tags=m_data.get("tags", []),
                ))
            print(f"[GrowthTracker] Loaded: {self._total_tasks} tasks, "
                  f"personality={self.personality.to_dict()}")
        except Exception as e:
            print(f"[GrowthTracker] Load failed: {e}")

    # ==========================================================
    # 综合报告
    # ==========================================================

    def get_full_report(self) -> Dict:
        return {
            "growth_metrics": self.get_growth_metrics(),
            "skill_confidence": self.get_skill_confidence(),
            "personality": self.personality.to_dict(),
            "personality_description": self.get_personality_description(),
        }


# ============================================================
# 全局单例
# ============================================================

_tracker_instance: Optional[GrowthTracker] = None

def get_growth_tracker() -> GrowthTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = GrowthTracker()
    return _tracker_instance
