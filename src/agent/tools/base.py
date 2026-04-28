"""工具基类 — 所有工具的抽象定义"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果"""
    output: str
    success: bool = True
    error: str | None = None

    def __str__(self) -> str:
        if self.success:
            return self.output
        return f"[错误] {self.error}\n{self.output}"


class BaseTool(ABC):
    """工具基类，所有工具必须继承此类"""

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具，返回结果"""
        ...

    def get_schema(self) -> dict[str, Any]:
        """返回工具的 JSON Schema 描述（给模型用）"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
