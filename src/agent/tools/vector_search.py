"""向量库搜索工具 — 语义搜索 ChromaDB 中的记忆"""

from typing import Any

from .base import BaseTool, ToolResult


class VectorSearchTool(BaseTool):
    name = "vector_search"
    description = "在长期记忆向量库中语义搜索相关内容。输入查询文本，返回最相关的记忆片段。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询文本",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量 (默认 5)",
            },
        },
        "required": ["query"],
    }

    def __init__(self, memory_store=None) -> None:
        # memory_store 将在 Step 7 中注入 LongTermMemory 实例
        self._memory = memory_store

    def set_memory(self, memory_store) -> None:
        """设置长期记忆存储"""
        self._memory = memory_store

    def execute(self, **kwargs) -> ToolResult:
        query = kwargs.get("query", "").strip()
        top_k = kwargs.get("top_k", 5)

        if not query:
            return ToolResult(output="", success=False, error="查询文本不能为空")

        if self._memory is None:
            return ToolResult(
                output="",
                success=False,
                error="向量库未初始化，长期记忆功能不可用",
            )

        try:
            results = self._memory.search(query, top_k=top_k)
            if not results:
                return ToolResult(output="未找到相关记忆")

            output_parts = []
            for i, item in enumerate(results, 1):
                text = item.get("text", item.get("content", str(item)))
                score = item.get("distance", item.get("score", ""))
                score_str = f" (相关度: {score:.2f})" if isinstance(score, (int, float)) else ""
                output_parts.append(f"{i}. {text}{score_str}")

            return ToolResult(output="\n\n".join(output_parts))

        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
