"""单元测试 — 不依赖模型加载，测试纯逻辑组件"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.tools.registry import ToolRegistry
from agent.tools.base import BaseTool, ToolResult
from agent.tools.filesystem import FilesystemTool
from agent.tools.shell import ShellTool
from agent.tools.code_exec import CodeExecTool
from agent.tools.data_query import DataQueryTool
from agent.core.state import AgentState
from agent.model.chat import _parse_tool_calls
from agent.model.prompt import build_system_prompt, build_tool_descriptions


# === 测试工具基类和注册中心 ===

class MockTool(BaseTool):
    name = "mock_tool"
    description = "模拟工具"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "输入文本"},
        },
        "required": ["input"],
    }

    def execute(self, **kwargs) -> ToolResult:
        return ToolResult(output=f"处理了: {kwargs.get('input', '')}")


def test_registry():
    registry = ToolRegistry()
    tool = MockTool()
    registry.register(tool)

    assert "mock_tool" in registry
    assert len(registry) == 1
    assert registry.get("mock_tool") is tool

    schemas = registry.get_all_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "mock_tool"

    result = registry.execute("mock_tool", {"input": "hello"})
    assert result.success
    assert "hello" in result.output

    # 未知工具
    result = registry.execute("nonexistent")
    assert not result.success
    print("Registry 测试通过")


def test_filesystem_tool():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = FilesystemTool(allowed_dirs=[tmpdir])

        # 写文件
        test_file = Path(tmpdir) / "test.txt"
        result = tool.execute(action="write_file", path=str(test_file), content="hello world")
        assert result.success

        # 读文件
        result = tool.execute(action="read_file", path=str(test_file))
        assert result.success
        assert "hello world" in result.output

        # 列目录
        result = tool.execute(action="list_dir", path=tmpdir)
        assert result.success
        assert "test.txt" in result.output

        # 路径安全检查
        result = tool.execute(action="read_file", path="/etc/passwd")
        assert not result.success
        print("Filesystem 工具测试通过")


def test_shell_tool():
    tool = ShellTool()

    # 正常命令
    result = tool.execute(command="echo hello")
    assert result.success
    assert "hello" in result.output

    # 危险命令拦截
    result = tool.execute(command="rm -rf /")
    assert not result.success
    print("Shell 工具测试通过")


def test_code_exec_tool():
    tool = CodeExecTool(timeout=10)

    result = tool.execute(code="print('hello from code exec')")
    assert result.success
    assert "hello from code exec" in result.output

    # 错误代码
    result = tool.execute(code="raise ValueError('test error')")
    assert not result.success
    print("Code exec 工具测试通过")


def test_data_query_tool():
    tool = DataQueryTool()

    # 只读检查
    assert tool._is_read_only("SELECT * FROM users")
    assert tool._is_read_only("  select id from t")
    assert not tool._is_read_only("DROP TABLE users")
    assert not tool._is_read_only("INSERT INTO users VALUES (1)")
    print("Data query 工具测试通过")


def test_agent_state():
    state = AgentState(max_iterations=3)
    state.add_user_message("hello")
    state.add_assistant_message("hi there")

    assert len(state.messages) == 2
    assert state.iteration == 0

    state.increment_iteration()
    assert state.iteration == 1
    assert not state.is_max_iterations()

    state.increment_iteration()
    state.increment_iteration()
    assert state.is_max_iterations()

    state.clear()
    assert len(state.messages) == 0
    assert state.iteration == 0
    print("Agent state 测试通过")


def test_tool_call_parsing():
    # JSON block 格式
    text = '我来执行命令\n```json\n{"name": "shell", "arguments": {"command": "ls"}}\n```'
    calls = _parse_tool_calls(text)
    assert len(calls) == 1
    assert calls[0].name == "shell"
    assert calls[0].arguments["command"] == "ls"

    # 行内 JSON 格式
    text2 = '{"name": "filesystem", "arguments": {"action": "read_file", "path": "/tmp/test.txt"}}'
    calls2 = _parse_tool_calls(text2)
    assert len(calls2) == 1
    assert calls2[0].name == "filesystem"

    # 无工具调用
    text3 = "这是普通回复，没有工具调用"
    calls3 = _parse_tool_calls(text3)
    assert len(calls3) == 0
    print("Tool call 解析测试通过")


def test_prompt_building():
    tools = [
        {
            "name": "shell",
            "description": "执行 shell 命令",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "命令"},
                },
                "required": ["command"],
            },
        }
    ]
    prompt = build_system_prompt(tools=tools, memory_context="用户偏好: 中文")
    assert "shell" in prompt
    assert "中文" in prompt
    assert "可用工具" in prompt
    print("Prompt 构建测试通过")


if __name__ == "__main__":
    test_registry()
    test_filesystem_tool()
    test_shell_tool()
    test_code_exec_tool()
    test_data_query_tool()
    test_agent_state()
    test_tool_call_parsing()
    test_prompt_building()
    print("\n所有单元测试通过!")
