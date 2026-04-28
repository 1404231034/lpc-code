"""统一聊天接口 — 文本 + 多模态，支持工具调用解析"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import torch
from transformers import PreTrainedModel, ProcessorMixin

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """工具调用"""
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatResponse:
    """模型回复"""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # stop / tool_call / max_tokens


def _parse_tool_calls(text: str) -> list[ToolCall]:
    """
    从模型输出中解析工具调用。

    支持格式：
    1. 模型原生 function calling 输出
    2. JSON 块: ```json\n{"name": "...", "arguments": {...}}\n```
    3. 行内 JSON: {"name": "...", "arguments": {...}}
    """
    calls = []

    # 方式1: JSON 代码块
    json_block_pattern = r"```json\s*\n?(.*?)\n?```"
    for match in re.finditer(json_block_pattern, text, re.DOTALL):
        try:
            data = json.loads(match.group(1).strip())
            if isinstance(data, dict) and "name" in data:
                calls.append(ToolCall(
                    name=data["name"],
                    arguments=data.get("arguments", {}),
                ))
        except json.JSONDecodeError:
            continue

    if calls:
        return calls

    # 方式2: 行内 JSON (tool_call 格式)
    # 匹配: {"name": "xxx", "arguments": {...}}
    inline_pattern = r'\{\s*"name"\s*:\s*"([^"]+)"\s*,\s*"arguments"\s*:\s*(\{[^}]*\})\s*\}'
    for match in re.finditer(inline_pattern, text):
        try:
            args = json.loads(match.group(2))
            calls.append(ToolCall(name=match.group(1), arguments=args))
        except json.JSONDecodeError:
            continue

    return calls


def chat(
    model: PreTrainedModel,
    processor: ProcessorMixin,
    messages: list[dict[str, Any]],
    device: str = "cpu",
    max_new_tokens: int = 2048,
    temperature: float = 0.7,
    top_p: float = 0.9,
    images: list[Any] | None = None,
) -> ChatResponse:
    """
    统一聊天接口。

    Args:
        model: 已加载的模型
        processor: 已加载的处理器
        messages: 对话消息列表 [{"role": "user/assistant/system", "content": "..."}]
        device: 推理设备
        max_new_tokens: 最大生成 token 数
        temperature: 采样温度
        top_p: top-p 采样
        images: PIL Image 列表（多模态输入）

    Returns:
        ChatResponse
    """
    # 构建输入
    if images:
        # 多模态输入 — 在第一条 user 消息中注入图像
        processed_messages = _inject_images(messages, images)
        inputs = processor.apply_chat_template(
            processed_messages,
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
        ).to(device)
    else:
        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
        ).to(device)

    input_len = inputs.shape[-1] if hasattr(inputs, "shape") else len(inputs["input_ids"][0])

    # 生成
    gen_kwargs = {
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "do_sample": temperature > 0,
    }

    with torch.no_grad():
        outputs = model.generate(**inputs, **gen_kwargs)

    # 解码（只取新生成的部分）
    generated_ids = outputs[0][input_len:]
    response_text = processor.decode(generated_ids, skip_special_tokens=True).strip()

    # 解析工具调用
    tool_calls = _parse_tool_calls(response_text)

    # 如果有工具调用，从文本中移除 JSON 部分获取纯文本
    content = response_text
    if tool_calls:
        # 去掉工具调用 JSON 块，保留推理文本
        content = re.sub(r"```json\s*\n?.*?\n?```", "", response_text, flags=re.DOTALL).strip()
        for tc in tool_calls:
            inline = json.dumps({"name": tc.name, "arguments": tc.arguments}, ensure_ascii=False)
            content = content.replace(inline, "").strip()

    finish_reason = "tool_call" if tool_calls else "stop"

    return ChatResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
    )


def _inject_images(
    messages: list[dict[str, Any]],
    images: list[Any],
) -> list[dict[str, Any]]:
    """将图像注入到第一条 user 消息中"""
    result = []
    injected = False
    for msg in messages:
        if msg["role"] == "user" and not injected:
            # 构建多模态 content
            content_parts = []
            for img in images:
                content_parts.append({"type": "image", "image": img})
            content_parts.append({"type": "text", "text": msg["content"]})
            result.append({"role": "user", "content": content_parts})
            injected = True
        else:
            result.append(msg)
    return result
