"""Prompt 模板构建 — 系统提示词、工具描述注入、记忆上下文"""

from typing import Any

SYSTEM_PROMPT_TEMPLATE = """你是一个智能助手，名叫 Agent。你可以使用以下工具来帮助用户完成任务。

{tool_descriptions}

## 输出格式

当你需要使用工具时，请先思考，然后输出如下格式的工具调用：
```json
{{"name": "工具名", "arguments": {{"参数名": "参数值"}}}}
```

如果你已经有足够的信息回答用户，直接给出最终回答，不要包含工具调用 JSON。

## 约束

- 每次只能调用一个工具
- 仔细检查参数，确保格式正确
- 如果工具调用失败，分析原因并重试或换一种方式
- 不要执行危险操作（如删除系统文件）
- 如果无法完成任务，诚实告知用户

{memory_context}"""


def build_tool_descriptions(tools: list[dict[str, Any]]) -> str:
    """从工具 schema 列表生成描述文本"""
    if not tools:
        return "当前没有可用工具。"

    lines = ["## 可用工具\n"]
    for tool in tools:
        lines.append(f"### {tool['name']}")
        lines.append(f"{tool['description']}")
        if "parameters" in tool and tool["parameters"]:
            lines.append("参数:")
            params = tool["parameters"]
            if isinstance(params, dict) and "properties" in params:
                for pname, pinfo in params["properties"].items():
                    required = pname in params.get("required", [])
                    req_mark = " (必填)" if required else ""
                    ptype = pinfo.get("type", "any")
                    pdesc = pinfo.get("description", "")
                    lines.append(f"  - {pname} ({ptype}{req_mark}): {pdesc}")
        lines.append("")
    return "\n".join(lines)


def build_system_prompt(
    tools: list[dict[str, Any]],
    memory_context: str = "",
) -> str:
    """
    构建系统提示词。

    Args:
        tools: 工具 schema 列表 (来自 registry.get_all_schemas())
        memory_context: 长期记忆上下文文本

    Returns:
        完整的系统提示词
    """
    tool_desc = build_tool_descriptions(tools)
    mem_section = ""
    if memory_context:
        mem_section = f"## 相关记忆\n{memory_context}"

    return SYSTEM_PROMPT_TEMPLATE.format(
        tool_descriptions=tool_desc,
        memory_context=mem_section,
    )
