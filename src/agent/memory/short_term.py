"""短期对话记忆 — 滑动窗口 + 上下文压缩"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """短期对话记忆，滑动窗口策略"""

    def __init__(self, window_size: int = 20) -> None:
        self.window_size = window_size
        self._messages: list[dict[str, Any]] = []
        self._summary: str = ""

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """添加消息"""
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self._messages.append(msg)

        # 超出窗口时压缩
        if len(self._messages) > self.window_size:
            self._compress()

    def get_messages(self) -> list[dict[str, Any]]:
        """获取当前窗口内的消息（包含早期摘要）"""
        result = []
        if self._summary:
            result.append({"role": "system", "content": f"[早期对话摘要]\n{self._summary}"})
        result.extend(self._messages)
        return result

    def _compress(self) -> None:
        """压缩早期消息：保留最近的消息，对更早的生成摘要"""
        if len(self._messages) <= self.window_size:
            return

        # 保留最近的一半消息
        keep_count = self.window_size // 2
        to_compress = self._messages[:-keep_count]
        self._messages = self._messages[-keep_count:]

        # 生成简单摘要（拼接早期消息的关键内容）
        # 注：理想情况下应由模型生成摘要，这里先用简单拼接
        summary_parts = []
        for msg in to_compress:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                summary_parts.append(f"用户: {content[:100]}")
            elif role == "assistant":
                summary_parts.append(f"助手: {content[:100]}")
            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                summary_parts.append(f"工具({tool_name}): {content[:80]}")

        new_summary = "\n".join(summary_parts)
        if self._summary:
            self._summary = f"{self._summary}\n{new_summary}"
        else:
            self._summary = new_summary

        # 摘要也限制长度
        if len(self._summary) > 2000:
            self._summary = self._summary[:2000] + "\n...(摘要已截断)"

        logger.debug(f"短期记忆压缩: 保留 {len(self._messages)} 条消息")

    def compress_with_model(self, model_generate_fn) -> None:
        """
        使用模型生成更高质量的摘要。

        Args:
            model_generate_fn: callable，输入 prompt 返回生成的摘要文本
        """
        if not self._summary and len(self._messages) <= self.window_size:
            return

        try:
            all_text = self._summary + "\n" + "\n".join(
                f"{m.get('role', '')}: {m.get('content', '')[:200]}"
                for m in self._messages
            )
            prompt = f"请简洁总结以下对话的关键信息：\n\n{all_text}\n\n摘要："
            self._summary = model_generate_fn(prompt)
            logger.info("使用模型生成了对话摘要")
        except Exception as e:
            logger.warning(f"模型摘要生成失败: {e}，使用简单摘要")

    def clear(self) -> None:
        """清空记忆"""
        self._messages.clear()
        self._summary = ""

    @property
    def message_count(self) -> int:
        return len(self._messages)
