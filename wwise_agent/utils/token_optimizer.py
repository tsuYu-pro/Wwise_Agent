# -*- coding: utf-8 -*-
"""
Token 优化管理器
系统化减少 token 消耗的多种策略

对齐 Cursor 的 token 统计：
- tiktoken 精准计数（可用时），否则改良估算
- 每模型定价（USD / 1M tokens）
- 费用计算 calculate_cost()
"""

import json
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# ============================================================
# tiktoken 精准计数（可选依赖）
# ============================================================
_tiktoken = None
_encoding_cache: Dict[str, Any] = {}

def _get_encoding(model: str):
    """获取 tiktoken 编码器（带缓存）"""
    global _tiktoken, _encoding_cache
    if _tiktoken is None:
        try:
            import tiktoken as _tk  # type: ignore
            _tiktoken = _tk
        except ImportError:
            _tiktoken = False
    if _tiktoken is False:
        return None
    try:
        key = model or 'gpt-5.2'
        if key not in _encoding_cache:
            try:
                _encoding_cache[key] = _tiktoken.encoding_for_model(key)
            except KeyError:
                if 'cl100k' not in _encoding_cache:
                    _encoding_cache['cl100k'] = _tiktoken.get_encoding('cl100k_base')
                _encoding_cache[key] = _encoding_cache['cl100k']
        return _encoding_cache[key]
    except Exception:
        return None


def count_tokens(text: str, model: str = '') -> int:
    """精准计算 token 数量"""
    if not text:
        return 0
    enc = _get_encoding(model)
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # 改良启发式估算
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]', text))
    code_chars = len(re.findall(r'[{}\[\]:,;()=<>+\-*/|&^~!@#$%]', text))
    other_chars = len(text) - chinese_chars - code_chars
    tokens = chinese_chars / 1.5 + code_chars + other_chars / 3.8
    return max(1, int(tokens))


# ============================================================
# 每模型定价（USD / 1M tokens）
# ============================================================

MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # DeepSeek
    'deepseek-chat':        {'input': 0.27,  'input_cache': 0.07,  'output': 1.10},
    'deepseek-reasoner':    {'input': 0.55,  'input_cache': 0.14,  'output': 2.19, 'reasoning': 2.19},
    # OpenAI
    'gpt-5.2':              {'input': 2.50,  'input_cache': 1.25,  'output': 10.00},
    'gpt-5.3-codex':        {'input': 3.00,  'input_cache': 1.50,  'output': 12.00},
    'o3':                   {'input': 10.00, 'input_cache': 2.50,  'output': 40.00, 'reasoning': 40.00},
    'o3-mini':              {'input': 1.10,  'input_cache': 0.55,  'output': 4.40,  'reasoning': 4.40},
    'o4-mini':              {'input': 1.10,  'input_cache': 0.275, 'output': 4.40,  'reasoning': 4.40},
    # Claude (via Duojie)
    'claude-opus-4-5':      {'input': 15.00, 'input_cache': 1.50,  'output': 75.00, 'reasoning': 75.00},
    'claude-opus-4-5-kiro': {'input': 15.00, 'input_cache': 1.50,  'output': 75.00, 'reasoning': 75.00},
    'claude-opus-4-5-max':  {'input': 15.00, 'input_cache': 1.50,  'output': 75.00, 'reasoning': 75.00},
    'claude-opus-4-6-normal': {'input': 15.00, 'input_cache': 1.50, 'output': 75.00, 'reasoning': 75.00},
    'claude-opus-4-6-kiro': {'input': 15.00, 'input_cache': 1.50,  'output': 75.00, 'reasoning': 75.00},
    'claude-sonnet-4-5':    {'input': 3.00,  'input_cache': 0.30,  'output': 15.00, 'reasoning': 15.00},
    'claude-haiku-4-5':     {'input': 0.80,  'input_cache': 0.08,  'output': 4.00},
    # Gemini
    'gemini-3-pro-image-preview': {'input': 1.25, 'input_cache': 0.30, 'output': 10.00},
    # GLM
    'glm-4.7':              {'input': 0.50,  'input_cache': 0.50,  'output': 0.50},
    # Kimi
    'kimi-k2.5':            {'input': 2.00,  'input_cache': 0.50,  'output': 8.00},
    # MiniMax
    'MiniMax-M2.5':         {'input': 1.00,  'input_cache': 0.25,  'output': 4.00},
    # Qwen
    'qwen3.5-plus':         {'input': 0.80,  'input_cache': 0.20,  'output': 2.00},
    'qwen-plus':            {'input': 0.80,  'input_cache': 0.20,  'output': 2.00},
    'qwen-max':             {'input': 2.00,  'input_cache': 0.50,  'output': 6.00},
    'qwen-turbo':           {'input': 0.30,  'input_cache': 0.05,  'output': 0.60},
}

_DEFAULT_PRICING = {'input': 0.27, 'input_cache': 0.07, 'output': 1.10}


def _match_pricing(model: str) -> Dict[str, float]:
    """模型名 → 定价字典（支持模糊匹配）"""
    if not model:
        return _DEFAULT_PRICING
    m = model.lower().strip()
    if m in MODEL_PRICING:
        return MODEL_PRICING[m]
    for key in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if m.startswith(key):
            return MODEL_PRICING[key]
    if ':' in m:
        return {'input': 0.0, 'input_cache': 0.0, 'output': 0.0}
    return _DEFAULT_PRICING


def calculate_cost(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_hit: int = 0,
    cache_miss: int = 0,
    reasoning_tokens: int = 0,
) -> float:
    """计算单次 API 调用费用（USD）"""
    p = _match_pricing(model)
    M = 1_000_000.0
    if cache_hit > 0 or cache_miss > 0:
        in_cost = (cache_hit * p.get('input_cache', p['input']) + cache_miss * p['input']) / M
    else:
        in_cost = input_tokens * p['input'] / M
    reasoning_price = p.get('reasoning', p['output'])
    normal_out = max(0, output_tokens - reasoning_tokens)
    out_cost = (normal_out * p['output'] + reasoning_tokens * reasoning_price) / M
    return in_cost + out_cost


def calculate_cost_from_stats(model: str, stats: dict) -> float:
    """从聚合统计字典中计算费用"""
    return calculate_cost(
        model=model,
        input_tokens=stats.get('input_tokens', 0),
        output_tokens=stats.get('output_tokens', 0),
        cache_hit=stats.get('cache_read', stats.get('cache_hit', stats.get('cache_hit_tokens', 0))),
        cache_miss=stats.get('cache_write', stats.get('cache_miss', stats.get('cache_miss_tokens', 0))),
        reasoning_tokens=stats.get('reasoning_tokens', 0),
    )


# ============================================================
# 压缩策略 & Token 预算
# ============================================================

class CompressionStrategy(Enum):
    NONE = "none"
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"


@dataclass
class TokenBudget:
    max_tokens: int = 128000
    warning_threshold: float = 0.7
    compression_threshold: float = 0.8
    emergency_threshold: float = 0.9
    keep_recent_messages: int = 4
    strategy: CompressionStrategy = CompressionStrategy.BALANCED


class TokenOptimizer:
    """Token 优化器"""

    def __init__(self, budget: Optional[TokenBudget] = None, model: str = ''):
        self.budget = budget or TokenBudget()
        self.model = model
        self._compression_history: List[Dict[str, Any]] = []

    def estimate_tokens(self, text: str) -> int:
        return count_tokens(text, self.model)

    def calculate_message_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total = 0
        for msg in messages:
            content = msg.get('content', '') or ''
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict):
                        if part.get('type') == 'text':
                            total += self.estimate_tokens(part.get('text', ''))
                        elif part.get('type') == 'image_url':
                            total += 765
                    elif isinstance(part, str):
                        total += self.estimate_tokens(part)
            else:
                total += self.estimate_tokens(content)
            tool_calls = msg.get('tool_calls')
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get('function', {})
                    total += self.estimate_tokens(fn.get('name', ''))
                    total += self.estimate_tokens(fn.get('arguments', ''))
                    total += 8
            total += 4
        return total

    def compress_tool_result(self, result: Dict[str, Any], max_length: int = 200) -> str:
        if not result:
            return ""
        success = result.get('success', False)
        if not success:
            error = result.get('error', 'Unknown error')
            return f"错误: {error[:max_length]}"
        result_text = result.get('result', '')
        if not result_text:
            return "成功"
        if len(result_text) <= max_length:
            return f"{result_text}"
        lines = [l.strip() for l in result_text.split('\n') if l.strip()]
        if len(lines) >= 2:
            summary = f"{lines[0][:max_length//2]} ... {lines[-1][:max_length//2]}"
        elif len(lines) == 1:
            summary = f"{lines[0][:max_length]}"
        else:
            summary = f"{result_text[:max_length]}..."
        return summary

    def compress_messages(
        self,
        messages: List[Dict[str, Any]],
        keep_recent: Optional[int] = None,
        strategy: Optional[CompressionStrategy] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not messages:
            return [], {'compressed': 0, 'saved_tokens': 0}
        keep_recent = keep_recent or self.budget.keep_recent_messages
        strategy = strategy or self.budget.strategy
        if len(messages) <= keep_recent:
            return messages, {'compressed': 0, 'saved_tokens': 0}
        converted_messages = []
        for m in messages:
            if m.get('role') == 'tool':
                tool_name = m.get('name', 'unknown')
                content = m.get('content', '')
                converted_messages.append({
                    'role': 'assistant',
                    'content': f"[工具结果] {tool_name}: {content}"
                })
            else:
                converted_messages.append(m)
        old_messages = converted_messages[:-keep_recent] if len(converted_messages) > keep_recent else []
        recent_messages = converted_messages[-keep_recent:] if len(converted_messages) >= keep_recent else converted_messages
        original_tokens = self.calculate_message_tokens(messages)
        compressed_messages = []
        if old_messages:
            if strategy == CompressionStrategy.AGGRESSIVE:
                summary = self._generate_aggressive_summary(old_messages)
            elif strategy == CompressionStrategy.CONSERVATIVE:
                summary = self._generate_conservative_summary(old_messages)
            else:
                summary = self._generate_balanced_summary(old_messages)
            if summary:
                compressed_messages.append({'role': 'system', 'content': summary})
        compressed_messages.extend(recent_messages)
        compressed_tokens = self.calculate_message_tokens(compressed_messages)
        saved_tokens = original_tokens - compressed_tokens
        stats = {
            'compressed': len(old_messages),
            'kept': len(recent_messages),
            'original_tokens': original_tokens,
            'compressed_tokens': compressed_tokens,
            'saved_tokens': saved_tokens,
            'saved_percent': (saved_tokens / original_tokens * 100) if original_tokens > 0 else 0
        }
        return compressed_messages, stats

    def _generate_balanced_summary(self, messages: List[Dict[str, Any]]) -> str:
        parts = ["[历史对话摘要 - 已压缩以节省 token]"]
        user_requests = []
        ai_responses = []
        tool_calls = []
        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role == 'user':
                req = content[:150].replace('\n', ' ').strip()
                if len(content) > 150:
                    req += "..."
                if req:
                    user_requests.append(req)
            elif role == 'assistant':
                lines = [l.strip() for l in content.split('\n') if l.strip()]
                if lines:
                    res = lines[-1][:100].replace('\n', ' ').strip()
                    if len(lines[-1]) > 100:
                        res += "..."
                    if res:
                        ai_responses.append(res)
            elif role == 'tool':
                tool_call_id = msg.get('tool_call_id', '')
                if tool_call_id:
                    tool_calls.append(f"工具调用: {tool_call_id[:50]}")
        if user_requests:
            parts.append(f"\n用户请求 ({len(user_requests)} 条):")
            for i, req in enumerate(user_requests[:8], 1):
                parts.append(f"  {i}. {req}")
            if len(user_requests) > 8:
                parts.append(f"  ... 还有 {len(user_requests) - 8} 条请求")
        if ai_responses:
            parts.append(f"\nAI 完成 ({len(ai_responses)} 条):")
            for i, res in enumerate(ai_responses[:8], 1):
                parts.append(f"  {i}. {res}")
            if len(ai_responses) > 8:
                parts.append(f"  ... 还有 {len(ai_responses) - 8} 条结果")
        if tool_calls:
            parts.append(f"\n工具调用: {len(tool_calls)} 次")
        return "\n".join(parts)

    def _generate_aggressive_summary(self, messages: List[Dict[str, Any]]) -> str:
        parts = ["[历史对话摘要 - 激进压缩]"]
        user_count = sum(1 for m in messages if m.get('role') == 'user')
        assistant_count = sum(1 for m in messages if m.get('role') == 'assistant')
        tool_count = sum(1 for m in messages if m.get('role') == 'tool')
        parts.append(f"用户请求: {user_count} 条")
        parts.append(f"AI 回复: {assistant_count} 条")
        if tool_count > 0:
            parts.append(f"工具调用: {tool_count} 次")
        if messages:
            last_user = next((m for m in reversed(messages) if m.get('role') == 'user'), None)
            if last_user:
                content = last_user.get('content', '')[:100]
                parts.append(f"\n最后请求: {content.replace(chr(10), ' ')}")
        return "\n".join(parts)

    def _generate_conservative_summary(self, messages: List[Dict[str, Any]]) -> str:
        parts = ["[历史对话摘要 - 保守压缩]"]
        user_requests = []
        ai_responses = []
        for msg in messages:
            role = msg.get('role', '')
            content = msg.get('content', '')
            if role == 'user':
                req = content[:250].replace('\n', ' ').strip()
                if len(content) > 250:
                    req += "..."
                if req:
                    user_requests.append(req)
            elif role == 'assistant':
                lines = [l.strip() for l in content.split('\n') if l.strip()]
                if lines:
                    res = " | ".join(lines[:3])[:200]
                    if len(lines) > 3:
                        res += "..."
                    if res:
                        ai_responses.append(res)
        if user_requests:
            parts.append(f"\n用户请求 ({len(user_requests)} 条):")
            for i, req in enumerate(user_requests[:12], 1):
                parts.append(f"  {i}. {req}")
            if len(user_requests) > 12:
                parts.append(f"  ... 还有 {len(user_requests) - 12} 条")
        if ai_responses:
            parts.append(f"\nAI 完成 ({len(ai_responses)} 条):")
            for i, res in enumerate(ai_responses[:12], 1):
                parts.append(f"  {i}. {res}")
            if len(ai_responses) > 12:
                parts.append(f"  ... 还有 {len(ai_responses) - 12} 条")
        return "\n".join(parts)

    def should_compress(self, current_tokens: int, limit: Optional[int] = None) -> Tuple[bool, str]:
        limit = limit or self.budget.max_tokens
        if current_tokens >= limit * self.budget.emergency_threshold:
            return True, f"紧急压缩: Token 使用 {current_tokens}/{limit} ({current_tokens/limit*100:.1f}%)"
        if current_tokens >= limit * self.budget.compression_threshold:
            return True, f"建议压缩: Token 使用 {current_tokens}/{limit} ({current_tokens/limit*100:.1f}%)"
        if current_tokens >= limit * self.budget.warning_threshold:
            return False, f"警告: Token 使用 {current_tokens}/{limit} ({current_tokens/limit*100:.1f}%)"
        return False, ""
