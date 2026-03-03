# -*- coding: utf-8 -*-
"""
反思模块 (Reflection Module)

混合反思策略：
1. 规则反思（每次任务后）：零成本，从工具调用链提取信号
2. LLM 深度反思（每 N 个任务或条件触发）：使用便宜模型生成抽象规则

Wwise 领域适配：标签检测覆盖 WAAPI 工具链。
"""

import json
import re
import time
import traceback
from typing import Any, Dict, List, Optional

from .memory_store import (
    MemoryStore,
    EpisodicRecord,
    SemanticRecord,
    get_memory_store,
)
from .reward_engine import RewardEngine, get_reward_engine

# ============================================================
# 反思配置
# ============================================================

DEEP_REFLECT_INTERVAL = 5
ERROR_RATE_SPIKE_THRESHOLD = 0.5

REFLECTION_PROMPT = """You are a self-improving AI assistant specializing in Wwise audio middleware. Analyze the following task records and extract reusable experience rules.

## Task Records
{episodic_summaries}

## Requirements
Analyze these tasks and extract:
1. **General rules**: Reusable insights from successes and failures
2. **Strategy updates**: Which problem-solving strategies should be adjusted
3. **Skill confidence**: Rate proficiency in each domain

Output in JSON format (no ```json markers):
{{
  "semantic_rules": [
    {{"rule": "Rule description", "category": "category(error_handling/workflow/events/buses/effects/general)", "confidence": 0.8}}
  ],
  "strategy_updates": [
    {{"name": "strategy_name", "priority_delta": 0.1, "reason": "Adjustment reason"}}
  ],
  "skill_confidence": {{
    "events": 0.8,
    "buses": 0.7,
    "effects": 0.5,
    "rtpc": 0.6,
    "general": 0.7
  }}
}}
"""


class ReflectionModule:
    """混合反思模块：规则反思 + 定期 LLM 深度反思"""

    def __init__(
        self,
        store: Optional[MemoryStore] = None,
        reward_engine: Optional[RewardEngine] = None,
    ):
        self.store = store or get_memory_store()
        self.reward_engine = reward_engine or get_reward_engine()
        self._task_count_since_reflect = 0
        self._recent_error_counts: List[int] = []
        self._max_recent = 10

    # ==========================================================
    # 规则反思（每次任务后，零成本）
    # ==========================================================

    def rule_reflect(self, episodic: EpisodicRecord, tool_calls: List[Dict]) -> EpisodicRecord:
        """规则反思：从工具调用链提取信号并更新 episodic tags"""
        tags = list(episodic.tags)

        retry_count = episodic.retry_count
        if retry_count > 2:
            tags.append("retry_heavy")

        has_error = False
        has_success_after_error = False
        for tc in tool_calls:
            if tc.get("error") or not tc.get("success", True):
                has_error = True
            elif has_error and tc.get("success", True):
                has_success_after_error = True
                break

        if has_error and has_success_after_error and episodic.success:
            tags.append("error_correction")

        if has_error and not episodic.success:
            tags.append("unresolved_error")

        if len(tool_calls) > 10:
            tags.append("complex_task")

        if len(tool_calls) <= 3 and episodic.success:
            tags.append("efficient_task")

        # Wwise 领域标签
        tool_names = [tc.get("name", "") for tc in tool_calls]
        if any("event" in n.lower() for n in tool_names):
            tags.append("event_related")
        if any("create_object" in n for n in tool_names):
            tags.append("object_creation")
        if any("bus" in n.lower() or "assign_bus" in n for n in tool_names):
            tags.append("bus_related")
        if any("effect" in n.lower() for n in tool_names):
            tags.append("effect_related")
        if any("rtpc" in n.lower() or "game_parameter" in n.lower() for n in tool_names):
            tags.append("rtpc_related")
        if any("execute_waapi" in n for n in tool_names):
            tags.append("raw_waapi")

        tags = list(dict.fromkeys(tags))
        episodic.tags = tags
        self.store.update_episodic_tags(episodic.id, tags)
        return episodic

    # ==========================================================
    # 完整的任务后反思流程
    # ==========================================================

    def reflect_on_task(
        self,
        session_id: str,
        task_description: str,
        result_summary: str,
        success: bool,
        error_count: int,
        retry_count: int,
        tool_calls: List[Dict],
        ai_client: Any = None,
        model: str = "deepseek-chat",
        provider: str = "deepseek",
    ) -> Dict:
        result = {
            "episodic_id": None,
            "reward": 0.0,
            "importance": 1.0,
            "tags": [],
            "deep_reflected": False,
            "new_rules": [],
        }

        try:
            episodic = EpisodicRecord(
                session_id=session_id,
                task_description=task_description,
                actions=[
                    {"name": tc.get("name", ""), "success": tc.get("success", True)}
                    for tc in tool_calls
                ],
                result_summary=result_summary,
                success=success,
                error_count=error_count,
                retry_count=retry_count,
            )

            episodic = self.rule_reflect(episodic, tool_calls)
            result["tags"] = episodic.tags

            self.store.add_episodic(episodic)
            result["episodic_id"] = episodic.id

            reward_result = self.reward_engine.process_task_completion(
                episodic_record=episodic,
                tool_call_count=len(tool_calls),
            )
            result["reward"] = reward_result["reward"]
            result["importance"] = reward_result["importance"]

            self._task_count_since_reflect += 1
            self._recent_error_counts.append(error_count)
            if len(self._recent_error_counts) > self._max_recent:
                self._recent_error_counts = self._recent_error_counts[-self._max_recent:]

            should_deep_reflect = self._should_deep_reflect()
            if should_deep_reflect and ai_client is not None:
                try:
                    deep_result = self._deep_reflect(ai_client, model, provider)
                    result["deep_reflected"] = True
                    result["new_rules"] = deep_result.get("new_rules", [])
                except Exception as e:
                    print(f"[Reflection] LLM deep reflection failed: {e}")
                    traceback.print_exc()

        except Exception as e:
            print(f"[Reflection] Reflection process error: {e}")
            traceback.print_exc()

        return result

    # ==========================================================
    # LLM 深度反思
    # ==========================================================

    def _should_deep_reflect(self) -> bool:
        if self._task_count_since_reflect >= DEEP_REFLECT_INTERVAL:
            return True
        if len(self._recent_error_counts) >= 3:
            recent = self._recent_error_counts[-3:]
            error_rate = sum(1 for e in recent if e > 0) / len(recent)
            if error_rate >= ERROR_RATE_SPIKE_THRESHOLD:
                return True
        return False

    def _deep_reflect(self, ai_client: Any, model: str, provider: str) -> Dict:
        self._task_count_since_reflect = 0

        recent_episodes = self.store.get_recent_episodic(limit=DEEP_REFLECT_INTERVAL * 2)
        if not recent_episodes:
            return {"new_rules": []}

        summaries = []
        for i, ep in enumerate(recent_episodes[:10], 1):
            status = "SUCCESS" if ep.success else "FAILED"
            tags_str = ", ".join(ep.tags) if ep.tags else "none"
            summaries.append(
                f"{i}. [{status}] Task: {ep.task_description}\n"
                f"   Result: {ep.result_summary}\n"
                f"   Errors: {ep.error_count}, Retries: {ep.retry_count}, Reward: {ep.reward_score:.2f}\n"
                f"   Tags: {tags_str}"
            )

        episodic_text = "\n\n".join(summaries)
        prompt = REFLECTION_PROMPT.format(episodic_summaries=episodic_text)

        messages = [
            {"role": "system", "content": "You are a self-improving AI assistant. Reply in JSON format."},
            {"role": "user", "content": prompt},
        ]

        full_response = ""
        try:
            for chunk in ai_client.chat_stream(
                messages=messages,
                model=model,
                provider=provider,
                temperature=0.3,
                max_tokens=1500,
                tools=None,
                enable_thinking=False,
            ):
                if chunk.get("type") == "content":
                    full_response += chunk.get("content", "")
                elif chunk.get("type") == "error":
                    print(f"[Reflection] LLM error: {chunk.get('error')}")
                    return {"new_rules": []}
        except Exception as e:
            print(f"[Reflection] LLM call failed: {e}")
            return {"new_rules": []}

        return self._parse_reflection_response(full_response, recent_episodes)

    def _parse_reflection_response(self, response: str, source_episodes: List[EpisodicRecord]) -> Dict:
        result = {"new_rules": [], "strategy_updates": []}

        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    print(f"[Reflection] Cannot parse reflection response")
                    return result
            else:
                print(f"[Reflection] No JSON found in response")
                return result

        source_ids = [ep.id for ep in source_episodes]

        for rule_data in data.get("semantic_rules", []):
            rule_text = rule_data if isinstance(rule_data, str) else rule_data.get("rule", "")
            if not rule_text:
                continue

            category = rule_data.get("category", "general") if isinstance(rule_data, dict) else "general"
            confidence = rule_data.get("confidence", 0.6) if isinstance(rule_data, dict) else 0.6

            existing = self.store.find_duplicate_semantic(rule_text, threshold=0.80)
            if existing:
                new_conf = min(1.0, existing.confidence + 0.1)
                self.store.update_semantic_confidence(existing.id, new_conf)
                self.store.increment_semantic_activation(existing.id)
                print(f"[Reflection] Strengthened rule: {existing.rule[:50]}... (conf={new_conf:.2f})")
            else:
                record = SemanticRecord(
                    rule=rule_text,
                    source_episodes=source_ids[:5],
                    confidence=confidence,
                    category=category,
                )
                self.store.add_semantic(record)
                result["new_rules"].append(rule_text)
                print(f"[Reflection] New rule: {rule_text[:50]}...")

        for update in data.get("strategy_updates", []):
            name = update.get("name", "")
            priority_delta = update.get("priority_delta", 0.0)
            if name and priority_delta != 0:
                existing = self.store.get_procedural_by_name(name)
                if existing:
                    self.store.update_procedural_priority(existing.id, priority_delta)
                    result["strategy_updates"].append(update)
                    print(f"[Reflection] Strategy update: {name} priority += {priority_delta}")

        skill_conf = data.get("skill_confidence", {})
        if skill_conf:
            result["skill_confidence"] = skill_conf

        return result

    # ==========================================================
    # 工具方法
    # ==========================================================

    def get_reflection_stats(self) -> Dict:
        return {
            "tasks_since_reflect": self._task_count_since_reflect,
            "recent_errors": self._recent_error_counts[-5:] if self._recent_error_counts else [],
            "next_deep_reflect_in": max(0, DEEP_REFLECT_INTERVAL - self._task_count_since_reflect),
        }


# ============================================================
# 全局单例
# ============================================================

_reflection_instance: Optional[ReflectionModule] = None

def get_reflection_module() -> ReflectionModule:
    global _reflection_instance
    if _reflection_instance is None:
        _reflection_instance = ReflectionModule()
    return _reflection_instance
