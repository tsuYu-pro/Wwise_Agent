# -*- coding: utf-8 -*-
"""
训练数据导出器
将当前聊天对话记录转换为大模型微调格式的训练数据
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


class ChatTrainingExporter:
    """聊天记录训练数据导出器
    
    将对话历史转换为 OpenAI 微调格式。
    支持多轮对话、工具调用等复杂场景。
    """
    
    @staticmethod
    def _extract_text_content(content) -> str:
        """从 content 中提取纯文本
        
        content 可能是 str 或 list（多模态消息，含 text/image_url 部分）。
        训练数据只保留文本，丢弃图片等二进制内容。
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
            return "\n".join(parts)
        return str(content) if content else ""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """初始化导出器
        
        Args:
            output_dir: 输出目录，默认为项目根目录下的 trainData
        """
        if output_dir is None:
            current_file = Path(__file__)
            project_root = current_file.parent.parent.parent
            output_dir = project_root / "trainData"
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def export_conversation(
        self, 
        conversation_history: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        split_by_user: bool = True
    ) -> str:
        """导出对话历史为训练数据
        
        Args:
            conversation_history: 对话历史列表
            system_prompt: 系统提示词（可选）
            split_by_user: 是否按用户消息分割成多个训练样本
        
        Returns:
            导出的文件路径
        """
        if not conversation_history:
            raise ValueError("对话历史为空")
        
        if split_by_user:
            samples = self._split_by_user_turns(conversation_history, system_prompt)
        else:
            samples = [self._create_single_sample(conversation_history, system_prompt)]
        
        samples = [s for s in samples if s and s.get("messages")]
        
        if not samples:
            raise ValueError("无法生成有效的训练样本")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_train_{timestamp}_{len(samples)}samples.jsonl"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        
        return str(filepath)
    
    def _split_by_user_turns(
        self, 
        history: List[Dict[str, Any]], 
        system_prompt: Optional[str]
    ) -> List[Dict[str, Any]]:
        """按用户消息分割成多个训练样本"""
        samples = []
        
        base_system = {
            "role": "system",
            "content": system_prompt or self._get_default_system_prompt()
        }
        
        context_messages = []
        current_sample_messages = []
        
        i = 0
        while i < len(history):
            msg = history[i]
            role = msg.get("role", "")
            
            if role == "user":
                if current_sample_messages:
                    sample = self._finalize_sample(base_system, context_messages, current_sample_messages)
                    if sample:
                        samples.append(sample)
                    context_messages.extend(current_sample_messages)
                    context_messages = self._trim_context(context_messages)
                
                current_sample_messages = [self._clean_message(msg)]
                
            elif role == "assistant":
                cleaned = self._clean_assistant_message(msg)
                if cleaned:
                    current_sample_messages.append(cleaned)
                    
            elif role == "tool":
                tool_msg = self._convert_tool_message(msg)
                if tool_msg:
                    current_sample_messages.append(tool_msg)
            
            i += 1
        
        if current_sample_messages:
            sample = self._finalize_sample(base_system, context_messages, current_sample_messages)
            if sample:
                samples.append(sample)
        
        return samples
    
    def _create_single_sample(
        self, 
        history: List[Dict[str, Any]], 
        system_prompt: Optional[str]
    ) -> Dict[str, Any]:
        """创建单个完整的训练样本"""
        messages = []
        
        messages.append({
            "role": "system",
            "content": system_prompt or self._get_default_system_prompt()
        })
        
        for msg in history:
            cleaned = self._clean_message(msg)
            if cleaned:
                messages.append(cleaned)
        
        return {"messages": messages} if len(messages) > 1 else None
    
    def _finalize_sample(
        self, 
        system_msg: Dict, 
        context: List[Dict], 
        current: List[Dict]
    ) -> Optional[Dict[str, Any]]:
        """完成一个训练样本"""
        if not current:
            return None
        
        has_user = any(m.get("role") == "user" for m in current)
        has_assistant = any(m.get("role") == "assistant" for m in current)
        
        if not has_user or not has_assistant:
            return None
        
        messages = [system_msg.copy()]
        
        if context:
            recent_context = context[-6:]
            messages.extend(recent_context)
        
        messages.extend(current)
        messages = self._validate_tool_calls(messages)
        
        return {"messages": messages}
    
    def _clean_message(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """清理消息格式"""
        role = msg.get("role", "")
        content = self._extract_text_content(msg.get("content", ""))
        
        if role == "user":
            if not content or not content.strip():
                return None
            return {"role": "user", "content": content.strip()}
        
        elif role == "assistant":
            return self._clean_assistant_message(msg)
        
        elif role == "tool":
            return self._convert_tool_message(msg)
        
        elif role == "system":
            return None
        
        return None
    
    def _clean_assistant_message(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """清理 assistant 消息"""
        content = self._extract_text_content(msg.get("content", ""))
        tool_calls = msg.get("tool_calls")
        
        result = {"role": "assistant"}
        
        if tool_calls:
            result["content"] = None
            result["tool_calls"] = self._clean_tool_calls(tool_calls)
        elif content and content.strip():
            result["content"] = content.strip()
        else:
            return None
        
        return result
    
    def _clean_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """清理工具调用格式"""
        cleaned = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                tool_id = tc.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                function = tc.get("function", {})
                
                cleaned.append({
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": function.get("name", ""),
                        "arguments": function.get("arguments", "{}")
                    }
                })
        return cleaned
    
    def _convert_tool_message(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """转换 tool 消息格式"""
        content = self._extract_text_content(msg.get("content", ""))
        tool_call_id = msg.get("tool_call_id")
        
        if not content:
            return None
        
        if not tool_call_id:
            tool_call_id = f"call_{uuid.uuid4().hex[:12]}"
        
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content[:500]
        }
    
    def _validate_tool_calls(self, messages: List[Dict]) -> List[Dict]:
        """验证并修复工具调用配对"""
        result = []
        pending_tool_calls = {}
        
        for msg in messages:
            role = msg.get("role")
            
            if role == "assistant" and msg.get("tool_calls"):
                for tc in msg.get("tool_calls", []):
                    tc_id = tc.get("id")
                    if tc_id:
                        pending_tool_calls[tc_id] = tc
                result.append(msg)
                
            elif role == "tool":
                tc_id = msg.get("tool_call_id")
                if tc_id in pending_tool_calls:
                    result.append(msg)
                    del pending_tool_calls[tc_id]
                else:
                    content = msg.get("content", "")
                    tool_name = "execute_tool"
                    if ":" in content:
                        tool_name = content.split(":")[0].strip()
                    
                    new_tc_id = f"call_{uuid.uuid4().hex[:12]}"
                    assistant_msg = {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": new_tc_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": "{}"
                            }
                        }]
                    }
                    result.append(assistant_msg)
                    
                    tool_msg = msg.copy()
                    tool_msg["tool_call_id"] = new_tc_id
                    result.append(tool_msg)
            else:
                result.append(msg)
        
        return result
    
    def _trim_context(self, context: List[Dict], max_messages: int = 10) -> List[Dict]:
        """限制上下文长度"""
        if len(context) <= max_messages:
            return context
        return context[-max_messages:]
    
    def _get_default_system_prompt(self) -> str:
        """获取默认系统提示词"""
        return """你是Wwise音频中间件助手。直接执行操作，不解释。

规则:
-直接调用工具执行
-不输出思考过程
-先查询对象存在再操作
-使用WAAPI进行所有Wwise操作
-完成后调用verify_structure或verify_event_completeness验证"""


def export_chat_training_data(
    conversation_history: List[Dict[str, Any]],
    system_prompt: Optional[str] = None,
    split_by_user: bool = True
) -> str:
    """导出聊天训练数据的便捷函数"""
    exporter = ChatTrainingExporter()
    return exporter.export_conversation(conversation_history, system_prompt, split_by_user)
