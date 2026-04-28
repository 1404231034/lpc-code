"""CLI 交互界面 — 基于 rich 的交互式命令行"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import print as rprint

from ..core.loop import AgentLoop
from ..core.state import AgentState
from ..model.loader import load_model
from ..tools.registry import ToolRegistry
from ..tools.filesystem import FilesystemTool
from ..tools.shell import ShellTool
from ..tools.web_request import WebRequestTool
from ..tools.code_exec import CodeExecTool
from ..tools.data_query import DataQueryTool
from ..tools.vector_search import VectorSearchTool
from ..tools.skill import SkillTool
from ..memory.short_term import ShortTermMemory
from ..memory.long_term import LongTermMemory
from ..multimodal.image import load_and_preprocess
from ..multimodal.pdf import parse_pdf, build_pdf_messages

logger = logging.getLogger(__name__)

console = Console()


def load_config(config_path: str = "config/default.yaml") -> dict[str, Any]:
    """加载配置文件"""
    path = Path(config_path)
    if not path.exists():
        # 尝试项目根目录
        path = Path(__file__).parent.parent.parent.parent / config_path
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return {}


def setup_tools(config: dict[str, Any]) -> ToolRegistry:
    """初始化并注册所有工具"""
    registry = ToolRegistry()
    tools_cfg = config.get("tools", {})
    agent_cfg = config.get("agent", {})

    # 文件系统
    allowed_dirs = agent_cfg.get("allowed_directories", ["."])
    registry.register(FilesystemTool(allowed_dirs=allowed_dirs))

    # Shell
    shell_cfg = tools_cfg.get("shell", {})
    if shell_cfg.get("enabled", True):
        registry.register(ShellTool(
            blocked_commands=shell_cfg.get("blocked_commands", None),
            timeout=30,
        ))

    # 网络请求
    web_cfg = tools_cfg.get("web_request", {})
    if web_cfg.get("enabled", True):
        registry.register(WebRequestTool(
            enabled=True,
            timeout=web_cfg.get("timeout", 30),
        ))

    # 代码执行
    code_cfg = tools_cfg.get("code_exec", {})
    if code_cfg.get("enabled", True):
        registry.register(CodeExecTool(timeout=code_cfg.get("timeout", 60)))

    # 数据查询
    data_cfg = tools_cfg.get("data_query", {})
    if data_cfg.get("enabled", True):
        registry.register(DataQueryTool(max_rows=data_cfg.get("max_rows", 100)))

    # 向量搜索（先注册，后续注入 memory）
    registry.register(VectorSearchTool())

    # 技能调用
    skill_cfg = tools_cfg.get("skill", {})
    skill_tool = SkillTool(
        skills_dir=skill_cfg.get("skills_dir", "config/skills"),
        registry=registry,
    )
    registry.register(skill_tool)

    return registry


def setup_memory(config: dict[str, Any]) -> LongTermMemory | None:
    """初始化长期记忆"""
    mem_cfg = config.get("memory", {}).get("long_term", {})
    try:
        return LongTermMemory(
            embedding_model=mem_cfg.get("embedding_model", "all-MiniLM-L6-v2"),
            persist_directory=config.get("memory", {}).get("persist_directory", "data/vectorstore"),
            collection_name="agent_memory",
        )
    except Exception as e:
        logger.warning(f"长期记忆初始化失败: {e}")
        return None


def setup_agent(config: dict[str, Any]) -> AgentLoop:
    """初始化完整的 Agent"""
    model_cfg = config.get("model", {})
    agent_cfg = config.get("agent", {})

    # 加载模型
    console.print("[dim]正在加载模型...[/dim]")
    model_artifacts = load_model(
        model_name=model_cfg.get("name"),
        device=model_cfg.get("device", "auto"),
        quantization=model_cfg.get("quantization"),
    )
    console.print("[green]模型加载完成[/green]")

    # 初始化工具
    registry = setup_tools(config)

    # 初始化长期记忆
    long_term_memory = setup_memory(config)

    # 注入长期记忆到向量搜索工具
    vector_tool = registry.get("vector_search")
    if vector_tool and long_term_memory:
        vector_tool.set_memory(long_term_memory)

    # 创建 Agent Loop
    agent = AgentLoop(
        model=model_artifacts["model"],
        processor=model_artifacts["processor"],
        device=model_artifacts["device"],
        registry=registry,
        max_iterations=agent_cfg.get("max_iterations", 15),
        iteration_timeout=agent_cfg.get("iteration_timeout", 120),
        max_new_tokens=model_cfg.get("max_new_tokens", 2048),
        temperature=model_cfg.get("temperature", 0.7),
        top_p=model_cfg.get("top_p", 0.9),
    )

    if long_term_memory:
        agent.set_long_term_memory(long_term_memory)

    return agent


def show_tools(registry: ToolRegistry) -> None:
    """显示可用工具列表"""
    table = Table(title="可用工具")
    table.add_column("名称", style="cyan")
    table.add_column("描述", style="white")

    for schema in registry.get_all_schemas():
        table.add_row(schema["name"], schema["description"])

    console.print(table)


def show_help() -> None:
    """显示帮助信息"""
    help_text = """
## 可用命令

| 命令 | 说明 |
|------|------|
| `/image <路径>` | 加载图片到对话 |
| `/pdf <路径>` | 加载 PDF 到对话 |
| `/tools` | 列出可用工具 |
| `/skills` | 列出可用技能 |
| `/clear` | 清空对话上下文 |
| `/history` | 查看对话历史 |
| `/help` | 显示帮助 |
| `/quit` | 退出 |
"""
    console.print(Markdown(help_text))


def show_skills(skill_tool: SkillTool | None) -> None:
    """显示可用技能"""
    if skill_tool is None:
        console.print("[yellow]技能系统未加载[/yellow]")
        return
    desc = skill_tool.get_skill_schema()
    console.print(Panel(desc, title="可用技能", border_style="green"))


def main() -> None:
    """CLI 主入口"""
    # 加载配置
    config = load_config()

    # 设置日志
    log_level = config.get("log_level", "WARNING")
    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # 显示欢迎
    console.print(Panel(
        "[bold green]本地 Agent 框架[/bold green]\n"
        f"模型: {config.get('model', {}).get('name', 'gemma-4-31B-it')}\n"
        "输入 /help 查看可用命令",
        title="Agent",
        border_style="green",
    ))

    # 初始化 Agent
    try:
        agent = setup_agent(config)
    except Exception as e:
        console.print(f"[red]Agent 初始化失败: {e}[/red]")
        sys.exit(1)

    # 获取 skill 工具引用
    skill_tool = agent.registry.get("skill")

    # 交互循环
    pending_images: list[Any] = []
    pending_pdf_messages: list[dict] = []

    while True:
        try:
            user_input = Prompt.ask("[bold violet]❯[/bold violet]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见[/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # 处理特殊命令
        if user_input.startswith("/"):
            parts = user_input.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""

            if cmd == "/quit":
                console.print("[dim]再见[/dim]")
                break
            elif cmd == "/help":
                show_help()
                continue
            elif cmd == "/tools":
                show_tools(agent.registry)
                continue
            elif cmd == "/skills":
                show_skills(skill_tool)
                continue
            elif cmd == "/clear":
                agent.reset()
                pending_images.clear()
                pending_pdf_messages.clear()
                console.print("[green]对话已清空[/green]")
                continue
            elif cmd == "/history":
                for msg in agent.state.get_history():
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role == "user":
                        console.print(f"[bold violet]❯[/bold violet] {content[:200]}")
                    elif role == "assistant":
                        console.print(f"[bold green]⏺[/bold green] {content[:200]}")
                    else:
                        console.print(f"[dim]{role}: {content[:100]}[/dim]")
                continue
            elif cmd == "/image":
                if not arg:
                    console.print("[yellow]用法: /image <图片路径>[/yellow]")
                    continue
                try:
                    img_msg = load_and_preprocess(arg, text="(用户发送了一张图片)")
                    pending_images.append(img_msg)
                    console.print(f"[green]图片已加载: {arg}[/green]")
                except Exception as e:
                    console.print(f"[red]加载图片失败: {e}[/red]")
                continue
            elif cmd == "/pdf":
                if not arg:
                    console.print("[yellow]用法: /pdf <PDF路径>[/yellow]")
                    continue
                try:
                    pdf_content = parse_pdf(arg)
                    pdf_msgs = build_pdf_messages(pdf_content)
                    pending_pdf_messages.extend(pdf_msgs)
                    console.print(f"[green]PDF 已加载: {arg} ({pdf_content.total_pages} 页)[/green]")
                except Exception as e:
                    console.print(f"[red]加载 PDF 失败: {e}[/red]")
                continue
            else:
                console.print(f"[yellow]未知命令: {cmd}，输入 /help 查看帮助[/yellow]")
                continue

        # 普通对话 — 调用 Agent
        try:
            # 回显用户消息
            timestamp = datetime.now().strftime("%H:%M")
            console.print()
            console.print(f"[bold violet]❯[/bold violet] [dim]{timestamp}[/dim]  {user_input}")

            # 处理待处理的图像
            # 处理待处理的图像
            images = None
            if pending_images:
                # 提取 PIL Image 对象
                images = []
                for img_msg in pending_images:
                    content = img_msg.get("content", [])
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "image":
                            images.append(part["image"])
                pending_images.clear()

            # 处理待处理的 PDF 消息
            if pending_pdf_messages:
                # 将 PDF 内容注入到用户消息前
                pdf_text_parts = []
                for msg in pending_pdf_messages:
                    content = msg.get("content", [])
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            pdf_text_parts.append(part["text"])
                        elif isinstance(part, dict) and part.get("type") == "image":
                            if images is None:
                                images = []
                            images.append(part["image"])
                if pdf_text_parts:
                    user_input = "\n".join(pdf_text_parts) + "\n\n" + user_input
                pending_pdf_messages.clear()

            with console.status("[dim]⏳ 思考中...[/dim]"):
                response = agent.run(user_input, images=images)

            # 渲染回复 — Claude Code 风格
            timestamp = datetime.now().strftime("%H:%M")
            console.print()
            console.print(f"[bold green]⏺ Agent[/bold green] [dim]{timestamp}[/dim]")
            console.print(Markdown(response))
            console.print()

            # 检查是否需要存入长期记忆
            if agent._long_term_memory and agent._long_term_memory.should_store(user_input):
                agent._long_term_memory.store(
                    text=f"用户: {user_input}\n助手: {response}",
                    metadata={"type": "important"},
                )
                console.print("[dim](已存入长期记忆)[/dim]")

        except KeyboardInterrupt:
            console.print("\n[yellow]已中断[/yellow]")
        except Exception as e:
            console.print(f"[red]错误: {e}[/red]")
            logger.exception("Agent 运行错误")


if __name__ == "__main__":
    main()
