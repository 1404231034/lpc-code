"""Agent Loop — ReAct 核心循环"""

import logging
import time
from typing import Any

from ..model.chat import ChatResponse, chat
from ..model.prompt import build_system_prompt
from ..tools.registry import ToolRegistry
from .state import AgentState

logger = logging.getLogger(__name__)


class AgentLoop:
    """ReAct Agent 循环"""

    def __init__(
        self,
        model: Any,
        processor: Any,
        device: str = "cpu",
        registry: ToolRegistry | None = None,
        max_iterations: int = 15,
        iteration_timeout: int = 120,
        max_new_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> None:
        self.model = model
        self.processor = processor
        self.device = device
        self.registry = registry or ToolRegistry()
        self.max_iterations = max_iterations
        self.iteration_timeout = iteration_timeout
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.state = AgentState(max_iterations=max_iterations)

        # 长期记忆（Step 7 注入）
        self._long_term_memory = None

    def set_long_term_memory(self, memory_store) -> None:
        """设置长期记忆存储"""
        self._long_term_memory = memory_store

    def run(
        self,
        user_input: str,
        images: list[Any] | None = None,
    ) -> str:
        """
        运行 Agent Loop。

        Args:
            user_input: 用户输入文本
            images: 可选的 PIL Image 列表

        Returns:
            Agent 最终回复文本
        """
        # 添加用户消息
        self.state.add_user_message(user_input)

        # 获取长期记忆上下文
        memory_context = ""
        if self._long_term_memory:
            try:
                mem_results = self._long_term_memory.search(user_input)
                if mem_results:
                    memory_context = "\n".join(
                        item.get("text", item.get("content", str(item)))
                        for item in mem_results
                    )
            except Exception as e:
                logger.warning(f"长期记忆检索失败: {e}")

        # 注入系统提示词
        system_prompt = build_system_prompt(
            tools=self.registry.get_all_schemas(),
            memory_context=memory_context,
        )

        # ReAct 循环
        while not self.state.is_max_iterations():
            self.state.increment_iteration()
            iteration_start = time.time()

            logger.info(f"--- 迭代 {self.state.iteration}/{self.max_iterations} ---")

            # 构建消息列表（系统提示 + 历史）
            messages = [
                {"role": "system", "content": system_prompt},
                *self.state.get_history(),
            ]

            # 调用模型
            try:
                response = chat(
                    model=self.model,
                    processor=self.processor,
                    messages=messages,
                    device=self.device,
                    max_new_tokens=self.max_new_tokens,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    images=images,
                )
            except Exception as e:
                logger.error(f"模型推理失败: {e}")
                return f"[模型推理错误] {e}"

            # 超时检查
            if time.time() - iteration_start > self.iteration_timeout:
                logger.warning("迭代超时")
                return response.content or "[超时] Agent 思考时间过长"

            # 如果有工具调用，执行工具
            if response.tool_calls:
                for tc in response.tool_calls:
                    logger.info(f"工具调用: {tc.name}({tc.arguments})")

                    # 执行工具
                    result = self.registry.execute(tc.name, tc.arguments)

                    # 将助手消息和工具结果添加到历史
                    assistant_content = response.content or f"调用工具: {tc.name}"
                    self.state.add_assistant_message(assistant_content)
                    self.state.add_tool_result(tc.name, str(result))

                    logger.info(f"工具结果: {result.output[:200] if result.output else result.error}")

                # 重置 images（只在第一轮使用）
                images = None
                continue

            # 没有工具调用，返回最终回答
            self.state.add_assistant_message(response.content)
            return response.content

        # 达到最大迭代
        return self.state.messages[-1].get("content", "") if self.state.messages else "[Agent 达到最大迭代次数，未能完成任务]"

    def reset(self) -> None:
        """重置 Agent 状态"""
        self.state.clear()
