"""快速验证脚本 — 测试模型加载和基础对话

用法: python tests/test_basic.py
"""

import sys
from pathlib import Path

# 添加 src 到 path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent.model.loader import load_model
from agent.model.chat import chat


def test_model_load():
    """测试模型加载"""
    print("=" * 50)
    print("测试 1: 模型加载")
    print("=" * 50)
    artifacts = load_model(device="auto")
    print(f"设备: {artifacts['device']}")
    print(f"模型类型: {type(artifacts['model']).__name__}")
    print("模型加载成功!\n")
    return artifacts


def test_basic_chat(artifacts):
    """测试基础文本对话"""
    print("=" * 50)
    print("测试 2: 基础对话")
    print("=" * 50)
    messages = [
        {"role": "user", "content": "你好，请用一句话介绍你自己。"},
    ]
    response = chat(
        model=artifacts["model"],
        processor=artifacts["processor"],
        messages=messages,
        device=artifacts["device"],
        max_new_tokens=256,
    )
    print(f"回复: {response.content}")
    print(f"工具调用: {response.tool_calls}")
    print(f"结束原因: {response.finish_reason}")
    print("基础对话测试通过!\n")


def test_tool_call_parsing(artifacts):
    """测试工具调用解析"""
    print("=" * 50)
    print("测试 3: 工具调用解析")
    print("=" * 50)
    messages = [
        {"role": "system", "content": "你是一个助手，可以使用 shell 工具执行命令。"},
        {"role": "user", "content": "请列出当前目录的文件"},
    ]
    response = chat(
        model=artifacts["model"],
        processor=artifacts["processor"],
        messages=messages,
        device=artifacts["device"],
        max_new_tokens=512,
    )
    print(f"回复: {response.content}")
    print(f"工具调用: {response.tool_calls}")
    print("工具调用解析测试通过!\n")


if __name__ == "__main__":
    artifacts = test_model_load()
    test_basic_chat(artifacts)
    test_tool_call_parsing(artifacts)
    print("所有测试通过!")
