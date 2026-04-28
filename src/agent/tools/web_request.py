"""网络请求工具 — HTTP GET/POST，支持超时和离线模式"""

import json
import urllib.request
import urllib.error
from typing import Any

from .base import BaseTool, ToolResult


class WebRequestTool(BaseTool):
    name = "web_request"
    description = "发起 HTTP 请求获取网页内容或调用 API。支持 GET 和 POST 方法。"
    parameters = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP 方法: GET 或 POST",
            },
            "url": {
                "type": "string",
                "description": "请求 URL",
            },
            "headers": {
                "type": "object",
                "description": "请求头 (可选)",
            },
            "body": {
                "type": "string",
                "description": "POST 请求体 (可选, JSON 字符串)",
            },
        },
        "required": ["method", "url"],
    }

    def __init__(self, enabled: bool = True, timeout: int = 30) -> None:
        self.enabled = enabled
        self.timeout = timeout

    def execute(self, **kwargs) -> ToolResult:
        if not self.enabled:
            return ToolResult(output="", success=False, error="网络请求已禁用（离线模式）")

        method = kwargs.get("method", "GET").upper()
        url = kwargs.get("url", "")
        headers = kwargs.get("headers", {})
        body = kwargs.get("body")

        if not url:
            return ToolResult(output="", success=False, error="URL 不能为空")

        try:
            req = urllib.request.Request(url, method=method)

            # 设置请求头
            for key, value in headers.items():
                req.add_header(key, value)

            if method == "POST" and body:
                if isinstance(body, str):
                    req.data = body.encode("utf-8")
                    if "Content-Type" not in req.headers:
                        req.add_header("Content-Type", "application/json")
                else:
                    req.data = json.dumps(body).encode("utf-8")

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                content = resp.read().decode("utf-8", errors="replace")
                # 截断过长响应
                max_chars = 30000
                if len(content) > max_chars:
                    content = content[:max_chars] + f"\n\n... (响应过长，已截断，共 {len(content)} 字符)"
                return ToolResult(output=content)

        except urllib.error.HTTPError as e:
            return ToolResult(
                output=f"HTTP 错误: {e.code} {e.reason}",
                success=False,
                error=f"HTTP {e.code}",
            )
        except urllib.error.URLError as e:
            return ToolResult(output="", success=False, error=f"URL 错误: {e.reason}")
        except Exception as e:
            return ToolResult(output="", success=False, error=str(e))
