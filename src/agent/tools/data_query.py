"""数据查询工具 — SQLite 只读查询"""

import sqlite3
import json
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult


class DataQueryTool(BaseTool):
    name = "data_query"
    description = "查询 SQLite 数据库。只支持 SELECT 查询（只读模式），不支持修改操作。"
    parameters = {
        "type": "object",
        "properties": {
            "database": {
                "type": "string",
                "description": "SQLite 数据库文件路径",
            },
            "query": {
                "type": "string",
                "description": "SQL 查询语句（仅 SELECT）",
            },
            "max_rows": {
                "type": "integer",
                "description": "最大返回行数 (默认 100)",
            },
        },
        "required": ["database", "query"],
    }

    def __init__(self, max_rows: int = 100) -> None:
        self.max_rows = max_rows

    def _is_read_only(self, query: str) -> bool:
        """检查 SQL 是否为只读查询"""
        q = query.strip().upper()
        read_prefixes = ("SELECT", "PRAGMA", "EXPLAIN", "WITH")
        return any(q.startswith(p) for p in read_prefixes)

    def execute(self, **kwargs) -> ToolResult:
        database = kwargs.get("database", "")
        query = kwargs.get("query", "").strip()
        max_rows = kwargs.get("max_rows", self.max_rows)

        if not database:
            return ToolResult(output="", success=False, error="数据库路径不能为空")
        if not query:
            return ToolResult(output="", success=False, error="查询语句不能为空")

        db_path = Path(database)
        if not db_path.exists():
            return ToolResult(output="", success=False, error=f"数据库文件不存在: {database}")

        # 安全检查：只允许读操作
        if not self._is_read_only(query):
            return ToolResult(output="", success=False, error="只允许 SELECT 查询（只读模式）")

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query)

            rows = cursor.fetchmany(max_rows)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            if not rows:
                conn.close()
                return ToolResult(output="查询结果为空")

            # 格式化为表格
            result_lines = []
            result_lines.append(" | ".join(columns))
            result_lines.append("-" * len(result_lines[0]))
            for row in rows:
                result_lines.append(" | ".join(str(v) for v in row))

            if len(rows) >= max_rows:
                result_lines.append(f"\n... (结果过多，只显示前 {max_rows} 行)")

            conn.close()
            return ToolResult(output="\n".join(result_lines))

        except sqlite3.Error as e:
            return ToolResult(output="", success=False, error=f"SQL 错误: {e}")
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
