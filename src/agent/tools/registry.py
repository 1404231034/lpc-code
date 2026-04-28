"""工具注册中心 — 管理工具的注册、查询和执行"""

import logging
from typing import Any

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            logger.warning(f"工具 '{tool.name}' 已存在，将被覆盖")
        self._tools[tool.name] = tool
        logger.debug(f"注册工具: {tool.name}")

    def unregister(self, name: str) -> None:
        """注销工具"""
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool | None:
        """按名称获取工具"""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """获取所有工具的 schema 描述（给模型用）"""
        return [tool.get_schema() for tool in self._tools.values()]

    def execute(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        """
        执行指定工具。

        Args:
            name: 工具名称
            args: 工具参数

        Returns:
            ToolResult
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                output="",
                success=False,
                error=f"未知工具: {name}",
            )

        args = args or {}
        try:
            result = tool.execute(**args)
            logger.info(f"工具 '{name}' 执行成功")
            return result
        except Exception as e:
            logger.error(f"工具 '{name}' 执行失败: {e}")
            return ToolResult(
                output="",
                success=False,
                error=str(e),
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
