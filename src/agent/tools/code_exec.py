"""代码执行工具 — 沙箱化 Python 代码执行"""

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolResult


class CodeExecTool(BaseTool):
    name = "code_exec"
    description = "在沙箱中执行 Python 代码并返回输出。代码在独立子进程中运行，有超时限制。"
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的 Python 代码",
            },
        },
        "required": ["code"],
    }

    def __init__(self, timeout: int = 60, max_output: int = 20000) -> None:
        self.timeout = timeout
        self.max_output = max_output

    def execute(self, **kwargs) -> ToolResult:
        code = kwargs.get("code", "").strip()
        if not code:
            return ToolResult(output="", success=False, error="代码不能为空")

        # 将代码写入临时文件并执行
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                prefix="agent_exec_",
                delete=False,
                encoding="utf-8",
            ) as f:
                f.write(code)
                temp_path = f.name

            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(Path(temp_path).parent),
            )

            # 清理临时文件
            Path(temp_path).unlink(missing_ok=True)

            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr}")
            if result.returncode != 0:
                output_parts.append(f"[退出码: {result.returncode}]")

            output = "\n".join(output_parts) or "(无输出)"

            # 截断过长输出
            if len(output) > self.max_output:
                output = output[:self.max_output] + f"\n\n... (输出过长，已截断)"

            return ToolResult(
                output=output,
                success=result.returncode == 0,
                error=None if result.returncode == 0 else f"退出码: {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            Path(temp_path).unlink(missing_ok=True)
            return ToolResult(
                output="",
                success=False,
                error=f"代码执行超时 ({self.timeout}s)",
            )
        except Exception as e:
            Path(temp_path).unlink(missing_ok=True)
            return ToolResult(output="", success=False, error=str(e))
