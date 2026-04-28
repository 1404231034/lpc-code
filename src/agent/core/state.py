"""Agent 状态管理 — 对话历史、迭代计数、执行上下文"""

from dataclasses import dataclass, field
from typing import Any

from ..model.chat import ToolCall


@dataclass
class AgentState:
    """Agent 运行状态"""
    messages: list[dict[str, Any]] = field(default_factory=list)
    iteration: int = 0
    max_iterations: int = 15
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    working_directory: str = "."

    def add_message(self, role: str, content: str, **kwargs) -> None:
        """添加消息到历史"""
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)

    def add_user_message(self, content: str) -> None:
        self.add_message("user", content)

    def add_assistant_message(self, content: str) -> None:
        self.add_message("assistant", content)

    def add_tool_result(self, tool_name: str, result: str) -> None:
        """添加工具执行结果到消息历史"""
        self.add_message("tool", result, name=tool_name)
        self.tool_log.append({
            "iteration": self.iteration,
            "tool": tool_name,
        })

    def increment_iteration(self) -> int:
        self.iteration += 1
        return self.iteration

    def is_max_iterations(self) -> bool:
        return self.iteration >= self.max_iterations

    def get_history(self) -> list[dict[str, Any]]:
        """获取完整对话历史"""
        return self.messages.copy()

    def clear(self) -> None:
        """清空状态"""
        self.messages.clear()
        self.iteration = 0
        self.tool_log.clear()
