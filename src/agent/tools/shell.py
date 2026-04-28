"""Shell 命令执行工具 — 带安全过滤和超时"""

import subprocess
from typing import Any

from .base import BaseTool, ToolResult

# 危险命令黑名单
BLOCKED_COMMANDS = [
    "rm -rf",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "chmod 777 /",
    "rm -r /",
    "rm -rf /",
    "> /dev/sda",
    "mv / ",
    "wget.*|.*sh",
    "curl.*|.*sh",
]


class ShellTool(BaseTool):
    name = "shell"
    description = "执行 shell 命令并返回输出。注意：危险命令会被拦截。"
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的 shell 命令",
            },
        },
        "required": ["command"],
    }

    def __init__(
        self,
        blocked_commands: list[str] | None = None,
        timeout: int = 30,
    ) -> None:
        self.blocked_commands = blocked_commands or BLOCKED_COMMANDS
        self.timeout = timeout

    def _is_blocked(self, command: str) -> str | None:
        """检查命令是否在黑名单中，返回拦截原因或 None"""
        cmd_lower = command.lower().strip()
        for blocked in self.blocked_commands:
            if blocked.lower() in cmd_lower:
                return f"命令包含被拦截的模式: '{blocked}'"
        return None

    def execute(self, **kwargs) -> ToolResult:
        command = kwargs.get("command", "").strip()
        if not command:
            return ToolResult(output="", success=False, error="命令不能为空")

        # 安全检查
        blocked_reason = self._is_blocked(command)
        if blocked_reason:
            return ToolResult(output="", success=False, error=blocked_reason)

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout)
            if result.stderr:
                output_parts.append(f"[stderr]\n{result.stderr}")
            if result.returncode != 0:
                output_parts.append(f"[退出码: {result.returncode}]")

            output = "\n".join(output_parts) or "(无输出)"
            success = result.returncode == 0

            return ToolResult(
                output=output,
                success=success,
                error=None if success else f"命令退出码: {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                output="",
                success=False,
                error=f"命令执行超时 ({self.timeout}s)",
            )
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
