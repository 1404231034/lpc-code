"""技能调用工具 — 基于 YAML 的技能定义和执行"""

import logging
from pathlib import Path
from typing import Any

import yaml

from .base import BaseTool, ToolResult
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class SkillTool(BaseTool):
    name = "skill"
    description = "调用预定义的技能（工具组合序列）。技能是一组按顺序执行的工具调用步骤。"
    parameters = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "要调用的技能名称",
            },
            "args": {
                "type": "object",
                "description": "传给技能的参数 (可选)",
            },
        },
        "required": ["skill_name"],
    }

    def __init__(
        self,
        skills_dir: str = "config/skills",
        registry: ToolRegistry | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir)
        self._registry = registry
        self._skills: dict[str, dict[str, Any]] = {}
        self._load_skills()

    def set_registry(self, registry: ToolRegistry) -> None:
        """设置工具注册中心（技能执行时需要）"""
        self._registry = registry

    def _load_skills(self) -> None:
        """加载 skills 目录下的所有 YAML 文件"""
        if not self._skills_dir.exists():
            logger.info(f"技能目录不存在: {self._skills_dir}，跳过加载")
            return

        for yaml_file in self._skills_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    skill_def = yaml.safe_load(f)
                if skill_def and "name" in skill_def:
                    self._skills[skill_def["name"]] = skill_def
                    logger.info(f"加载技能: {skill_def['name']}")
            except Exception as e:
                logger.warning(f"加载技能文件 {yaml_file} 失败: {e}")

        for yml_file in self._skills_dir.glob("*.yml"):
            try:
                with open(yml_file, "r", encoding="utf-8") as f:
                    skill_def = yaml.safe_load(f)
                if skill_def and "name" in skill_def:
                    self._skills[skill_def["name"]] = skill_def
                    logger.info(f"加载技能: {skill_def['name']}")
            except Exception as e:
                logger.warning(f"加载技能文件 {yml_file} 失败: {e}")

    def get_skill_schema(self) -> str:
        """返回所有可用技能的描述（供模型参考）"""
        if not self._skills:
            return "(无可用技能)"
        lines = []
        for name, skill in self._skills.items():
            desc = skill.get("description", "无描述")
            lines.append(f"- {name}: {desc}")
        return "\n".join(lines)

    def execute(self, **kwargs) -> ToolResult:
        skill_name = kwargs.get("skill_name", "")
        extra_args = kwargs.get("args", {})

        if not skill_name:
            return ToolResult(output="", success=False, error="技能名称不能为空")

        if skill_name not in self._skills:
            available = ", ".join(self._skills.keys()) or "(无)"
            return ToolResult(
                output="",
                success=False,
                error=f"未知技能: {skill_name}。可用技能: {available}",
            )

        if self._registry is None:
            return ToolResult(output="", success=False, error="工具注册中心未设置")

        skill = self._skills[skill_name]
        steps = skill.get("steps", [])

        if not steps:
            return ToolResult(output="", success=False, error=f"技能 '{skill_name}' 没有定义步骤")

        # 按步骤执行
        results = []
        for i, step in enumerate(steps):
            tool_name = step.get("tool", "")
            tool_args = step.get("args", {})

            # 用额外参数替换模板变量
            if extra_args:
                tool_args = self._resolve_args(tool_args, extra_args)

            result = self._registry.execute(tool_name, tool_args)
            step_desc = f"步骤 {i + 1}: {tool_name}({tool_args})"
            results.append(f"{step_desc}\n结果: {result}")

            # 如果步骤失败，记录但继续
            if not result.success:
                logger.warning(f"技能 '{skill_name}' 步骤 {i + 1} 失败: {result.error}")

        output = f"技能 '{skill_name}' 执行结果:\n\n" + "\n\n".join(results)
        return ToolResult(output=output)

    def _resolve_args(self, args: dict, extra_args: dict) -> dict:
        """解析参数中的模板变量，如 {{var}}"""
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                var_name = value[2:-2].strip()
                resolved[key] = extra_args.get(var_name, value)
            else:
                resolved[key] = value
        return resolved
