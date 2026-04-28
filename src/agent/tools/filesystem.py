"""文件系统工具 — 读写文件、列目录、搜索"""

import os
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = "文件系统操作：读取文件、写入文件、列出目录内容、搜索文件"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型: read_file, write_file, list_dir, search_files",
            },
            "path": {
                "type": "string",
                "description": "文件或目录路径",
            },
            "content": {
                "type": "string",
                "description": "写入文件的内容 (仅 write_file 操作需要)",
            },
            "pattern": {
                "type": "string",
                "description": "搜索模式 (仅 search_files 操作需要, 如 '*.py')",
            },
        },
        "required": ["action", "path"],
    }

    def __init__(self, allowed_dirs: list[str] | None = None) -> None:
        self.allowed_dirs = [Path(d).resolve() for d in (allowed_dirs or ["."])]

    def _check_path(self, path: str) -> tuple[Path, str | None]:
        """检查路径是否在允许范围内"""
        resolved = Path(path).resolve()
        for allowed in self.allowed_dirs:
            try:
                resolved.relative_to(allowed)
                return resolved, None
            except ValueError:
                continue
        return resolved, f"路径 '{path}' 不在允许的目录范围内"

    def execute(self, **kwargs) -> ToolResult:
        action = kwargs.get("action", "")
        path = kwargs.get("path", "")

        resolved, err = self._check_path(path)
        if err:
            return ToolResult(output="", success=False, error=err)

        if action == "read_file":
            return self._read_file(resolved)
        elif action == "write_file":
            content = kwargs.get("content", "")
            return self._write_file(resolved, content)
        elif action == "list_dir":
            return self._list_dir(resolved)
        elif action == "search_files":
            pattern = kwargs.get("pattern", "*")
            return self._search_files(resolved, pattern)
        else:
            return ToolResult(output="", success=False, error=f"未知操作: {action}")

    def _read_file(self, path: Path) -> ToolResult:
        if not path.is_file():
            return ToolResult(output="", success=False, error=f"文件不存在: {path}")
        try:
            content = path.read_text(encoding="utf-8")
            # 限制读取大小
            max_chars = 50000
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n\n... (文件过长，已截断，共 {len(content)} 字符)"
            return ToolResult(output=content)
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))

    def _write_file(self, path: Path, content: str) -> ToolResult:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(output=f"文件已写入: {path}")
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))

    def _list_dir(self, path: Path) -> ToolResult:
        if not path.is_dir():
            return ToolResult(output="", success=False, error=f"目录不存在: {path}")
        try:
            entries = []
            for entry in sorted(path.iterdir()):
                prefix = "[D] " if entry.is_dir() else "[F] "
                size = entry.stat().st_size if entry.is_file() else ""
                size_str = f" ({size} bytes)" if size else ""
                entries.append(f"{prefix}{entry.name}{size_str}")
            return ToolResult(output="\n".join(entries) or "(空目录)")
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))

    def _search_files(self, path: Path, pattern: str) -> ToolResult:
        if not path.is_dir():
            return ToolResult(output="", success=False, error=f"目录不存在: {path}")
        try:
            matches = list(path.rglob(pattern))[:50]
            if not matches:
                return ToolResult(output=f"未找到匹配 '{pattern}' 的文件")
            result = "\n".join(str(m.relative_to(path)) for m in matches)
            if len(matches) >= 50:
                result += "\n... (结果过多，只显示前50条)"
            return ToolResult(output=result)
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
