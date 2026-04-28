# 本项目 Python 语法指南

> 本文档介绍项目中实际使用的 Python 语法特性，所有示例均取自项目源码。
> 项目要求 Python >= 3.10。

---

## 1. 类型注解（Type Hints）

### 1.1 联合类型 `X | Y`（PEP 604，Python 3.10+）

替代旧写法 `Optional[X]` 或 `Union[X, Y]`，更简洁直观：

```python
# tools/base.py
error: str | None = None

# model/loader.py
def load_model(
    model_name: str = "google/gemma-4-31B-it",
    device: str = "auto",
    quantization: str | None = None,       # 可以是 str 或 None
    local_path: str | None = None,
) -> dict[str, Any]:
```

### 1.2 内置泛型 `list[]`、`dict[]`、`tuple[]`（PEP 585，Python 3.9+）

不再需要从 `typing` 导入 `List`、`Dict`、`Tuple`，直接用内置类型加方括号：

```python
# core/state.py
messages: list[dict[str, Any]] = field(default_factory=list)

# tools/shell.py
def __init__(self, blocked_commands: list[str] | None = None, timeout: int = 30) -> None:

# tools/filesystem.py
def _check_path(self, path: str) -> tuple[Path, str | None]:
```

### 1.3 `typing.Any`

本项目中 `typing` 模块只导入了 `Any`，不再使用 `Optional`、`Union`、`Callable` 等：

```python
from typing import Any

# 用于无法确定具体类型的场景，如模型对象、动态字典
parameters: dict[str, Any] = {}
model: Any  # transformers 模型对象
```

### 1.4 返回值注解

所有函数都有显式返回类型：

```python
def get(self, name: str) -> BaseTool | None:   # 可能返回 None
def list_names(self) -> list[str]:              # 总是返回列表
def execute(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
```

---

## 2. 数据类（dataclass）

### 2.1 `@dataclass` 基本用法

自动生成 `__init__`、`__repr__` 等：

```python
# model/chat.py
@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]

@dataclass
class ChatResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
```

### 2.2 `field(default_factory=...)`

当默认值是可变对象（list、dict）时，必须用 `default_factory` 避免共享引用：

```python
# core/state.py
messages: list[dict[str, Any]] = field(default_factory=list)
tool_log: list[dict[str, Any]] = field(default_factory=list)

# 如果写成 messages: list[...] = []  → 所有实例共享同一个列表！
```

### 2.3 字段默认值

不可变类型可以直接赋默认值：

```python
# tools/base.py — ToolResult
output: str
success: bool = True
error: str | None = None

# core/state.py — AgentState
iteration: int = 0
max_iterations: int = 15
working_directory: str = "."
```

---

## 3. 抽象基类（ABC）

### 3.1 定义抽象类和抽象方法

```python
# tools/base.py
from abc import ABC, abstractmethod

class BaseTool(ABC):
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        ...  # 省略号作方法体，表示"待实现"
```

继承 `BaseTool` 的子类**必须**实现 `execute`，否则实例化时会报 `TypeError`。

### 3.2 省略号 `...` 作方法体

Python 中 `...`（Ellipsis）是合法表达式，常用于抽象方法、占位代码：

```python
@abstractmethod
def execute(self, **kwargs) -> ToolResult:
    ...  # 等价于 pass，但更语义化
```

---

## 4. 类的魔术方法

### 4.1 `__len__` 和 `__contains__`

让对象支持 `len()` 和 `in` 操作符：

```python
# tools/registry.py
class ToolRegistry:
    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

# 使用
print(len(registry))        # 调用 __len__
if "shell" in registry:     # 调用 __contains__
    ...
```

### 4.2 `__str__`

控制 `print()` / `str()` 的输出：

```python
# tools/base.py — ToolResult
def __str__(self) -> str:
    if self.success:
        return self.output
    return f"[错误] {self.error}\n{self.output}"
```

### 4.3 `__all__`

控制 `from module import *` 导出哪些名字：

```python
# __init__.py
__all__ = [
    "AgentLoop", "AgentState", "load_model", "chat",
    "ChatResponse", "ToolCall", "ToolRegistry",
    "BaseTool", "ToolResult", "ShortTermMemory", "LongTermMemory",
]
```

---

## 5. 属性装饰器 `@property`

将方法当属性访问，用于派生值：

```python
# memory/short_term.py
@property
def message_count(self) -> int:
    return len(self._messages)

# 使用
mem.message_count   # 像属性一样访问，不加括号
```

```python
# multimodal/pdf.py — PDFContent
@property
def full_text(self) -> str:
    return "\n\n".join(
        f"--- 第 {p.page_num + 1} 页 ---\n{p.text}"
        for p in self.pages
        if p.text.strip()
    )
```

---

## 6. f-string 格式化

项目中大量使用 f-string，比 `%` 和 `.format()` 更直观：

```python
# 基本变量插入
logger.info(f"正在加载模型: {model_path}")
logger.info(f"工具调用: {tc.name}({tc.arguments})")

# 条件表达式
size_str = f" ({size} bytes)" if size else ""

# 格式化数字
score_str = f" (相关度: {score:.2f})" if isinstance(score, (int, float)) else ""
```

---

## 7. 上下文管理器（with 语句）

### 7.1 文件操作

```python
with open(path, "r", encoding="utf-8") as f:
    return yaml.safe_load(f)
```

### 7.2 临时文件

```python
# tools/code_exec.py
with tempfile.NamedTemporaryFile(
    mode="w", suffix=".py", prefix="agent_exec_",
    delete=False, encoding="utf-8",
) as f:
    f.write(code)
    temp_path = f.name
```

### 7.3 模型推理（关闭梯度计算）

```python
# model/chat.py
with torch.no_grad():
    outputs = model.generate(**inputs, **gen_kwargs)
```

### 7.4 网络请求

```python
# tools/web_request.py
with urllib.request.urlopen(req, timeout=self.timeout) as resp:
    content = resp.read().decode("utf-8", errors="replace")
```

### 7.5 Rich 状态显示

```python
# cli/interface.py
with console.status("[bold green]Agent 思考中...[/bold green]"):
    response = agent.run(user_input, images=images)
```

---

## 8. pathlib 路径操作

项目中统一使用 `pathlib.Path` 替代 `os.path`：

```python
from pathlib import Path

# 创建路径对象
img_path = Path(path)
self._persist_dir = Path(persist_directory)

# 路径检查
img_path.exists()
path.is_file()
path.is_dir()

# 路径操作
resolved = Path(d).resolve()          # 转绝对路径
resolved.relative_to(allowed)         # 判断是否在允许目录下
Path(__file__).parent.parent.parent.parent / config_path  # 向上导航 + 拼接
path.parent.mkdir(parents=True, exist_ok=True)            # 递归创建目录

# 文件读写
path.read_text(encoding="utf-8")
path.write_text(content, encoding="utf-8")

# 目录遍历
sorted(path.iterdir())                # 列出目录内容
path.rglob(pattern)                   # 递归 glob 搜索

# 文件删除
Path(temp_path).unlink(missing_ok=True)  # 删除文件，不存在也不报错
```

---

## 9. `**kwargs` 与字典解包

### 9.1 接收任意关键字参数

```python
# tools/base.py — 抽象方法签名
@abstractmethod
def execute(self, **kwargs) -> ToolResult:
    ...

# state.py — 附加额外字段
def add_message(self, role: str, content: str, **kwargs) -> None:
    msg = {"role": role, "content": content}
    msg.update(kwargs)    # 合并额外字段
```

### 9.2 字典解包传参

```python
# tools/registry.py — 把 dict 解包为关键字参数
result = tool.execute(**args)

# model/chat.py — 双重解包
outputs = model.generate(**inputs, **gen_kwargs)

# model/loader.py — 动态构建参数
kwargs: dict[str, Any] = {}
kwargs.setdefault("device_map", {"": resolve_device})
model = AutoModelForCausalLM.from_pretrained(model_path, **kwargs)
```

### 9.3 列表解包

```python
# core/loop.py — 在列表字面量中展开
messages = [
    {"role": "system", "content": system_prompt},
    *self.state.get_history(),   # 解包已有历史消息
]
```

---

## 10. 异常处理

### 10.1 捕获特定异常

```python
# tools/shell.py
except subprocess.TimeoutExpired:
    return ToolResult(output="", success=False, error=f"命令执行超时 ({self.timeout}s)")

# tools/web_request.py — 多层异常
except urllib.error.HTTPError as e:
    return ToolResult(output=f"HTTP 错误: {e.code} {e.reason}", ...)
except urllib.error.URLError as e:
    return ToolResult(output="", success=False, error=f"URL 错误: {e.reason}")

# model/chat.py
except json.JSONDecodeError:
    continue
```

### 10.2 捕获多种异常

```python
# cli/interface.py
except (EOFError, KeyboardInterrupt):
    console.print("\n[dim]再见[/dim]")
    break
```

### 10.3 通用兜底 + 清理

```python
# tools/code_exec.py — 无论什么异常都清理临时文件
try:
    ...
    result = subprocess.run(...)
    Path(temp_path).unlink(missing_ok=True)
except subprocess.TimeoutExpired:
    Path(temp_path).unlink(missing_ok=True)
    return ToolResult(...)
except Exception as e:
    Path(temp_path).unlink(missing_ok=True)
    return ToolResult(output="", success=False, error=str(e))
```

### 10.4 主动抛出异常

```python
# multimodal/image.py
raise FileNotFoundError(f"图像文件不存在: {path}")
raise ValueError(f"不支持的图像格式: {img_path.suffix}，支持: {SUPPORTED_FORMATS}")
```

---

## 11. 日志（logging）

### 11.1 模块级 Logger

每个模块统一使用此模式：

```python
import logging
logger = logging.getLogger(__name__)  # __name__ 自动对应模块路径
```

### 11.2 日志级别

```python
logger.debug("调试信息，默认不显示")
logger.info(f"正在加载模型: {model_path}")
logger.warning(f"长期记忆初始化失败: {e}")
logger.error(f"模型推理失败: {e}")
logger.exception("Agent 运行错误")  # 自动附带完整堆栈
```

### 11.3 全局配置

```python
# cli/interface.py
logging.basicConfig(
    level=getattr(logging, log_level, logging.WARNING),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
```

---

## 12. 推导式与生成器表达式

### 12.1 列表推导

```python
# tools/registry.py
return [tool.get_schema() for tool in self._tools.values()]

# tools/data_query.py
columns = [desc[0] for desc in cursor.description] if cursor.description else []
```

### 12.2 生成器表达式（省内存，配合 `join()` 等）

```python
# core/loop.py
memory_context = "\n".join(
    item.get("text", item.get("content", str(item)))
    for item in mem_results
)

# multimodal/pdf.py — 带条件过滤
return "\n\n".join(
    f"--- 第 {p.page_num + 1} 页 ---\n{p.text}"
    for p in self.pages
    if p.text.strip()
)
```

---

## 13. 导入模式

### 13.1 相对导入

```python
# 同包内导入（单点）
from .state import AgentState
from .image import preprocess_image

# 跨包导入（双点，向上一级）
from ..model.chat import ChatResponse, chat
from ..tools.registry import ToolRegistry
```

### 13.2 延迟导入（函数体内导入）

按需加载，减少启动时间或避免循环导入：

```python
# model/loader.py — 仅在需要量化时导入
if quantization == "4bit":
    from transformers import BitsAndBytesConfig
    kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)

# memory/long_term.py — 运行时才导入
def store(self, text: str, ...):
    import uuid
    doc_id = str(uuid.uuid4())
```

---

## 14. subprocess 子进程

### 14.1 Shell 模式（执行任意命令）

```python
# tools/shell.py
result = subprocess.run(
    command,
    shell=True,            # 通过 shell 解释命令
    capture_output=True,   # 捕获 stdout + stderr
    text=True,             # 输出为 str 而非 bytes
    timeout=self.timeout,
)
result.stdout       # 标准输出
result.stderr       # 标准错误
result.returncode   # 退出码
```

### 14.2 列表模式（执行 Python 脚本）

```python
# tools/code_exec.py
result = subprocess.run(
    [sys.executable, temp_path],   # 列表形式，不走 shell
    capture_output=True,
    text=True,
    timeout=self.timeout,
)
```

---

## 15. 其他实用模式

### 15.1 元组打包/解包

```python
# tools/filesystem.py — 返回多个值
def _check_path(self, path: str) -> tuple[Path, str | None]:
    if err:
        return resolved, f"路径 '{path}' 不在允许的目录范围内"
    return resolved, None

# 调用方
resolved, err = self._check_path(path)
```

### 15.2 `dict.setdefault()`

键不存在时设置默认值，存在则不动：

```python
# model/loader.py
kwargs.setdefault("device_map", {"": resolve_device})

# memory/long_term.py
meta.setdefault("source", "conversation")
```

### 15.3 `getattr()` 动态属性访问

```python
# cli/interface.py — 根据字符串获取 logging 级别
level = getattr(logging, log_level, logging.WARNING)
# 等价于: logging.INFO / logging.DEBUG / ...，找不到则用默认值
```

### 15.4 `any()` 配合生成器

```python
# memory/long_term.py — 检测是否包含记忆信号
STORE_SIGNALS = ["记住", "记得", "remember", "save"]
return any(signal in msg_lower for signal in STORE_SIGNALS)

# tools/data_query.py — 检测是否只读查询
return any(q.startswith(p) for p in ("SELECT", "PRAGMA", "EXPLAIN", "WITH"))
```

### 15.5 `enumerate()` 指定起始索引

```python
# tools/vector_search.py
for i, item in enumerate(results, 1):  # 从 1 开始编号
    ...
```

### 15.6 `isinstance()` 类型检查

```python
# model/chat.py
if isinstance(data, dict) and "name" in data:
    ...

# tools/vector_search.py
if isinstance(score, (int, float)):  # 检查是否为数字类型
    score_str = f" (相关度: {score:.2f})"
```

### 15.7 `if __name__ == "__main__"` 入口保护

```python
# __main__.py
if __name__ == "__main__":
    main()
```

直接运行 `python -m agent` 时 `__name__` 为 `"__main__"`，被其他模块导入时不会执行。

---

## 16. 正则表达式

### 16.1 `re.finditer()` 迭代匹配

```python
# model/chat.py — 查找所有 JSON 代码块
for match in re.finditer(json_block_pattern, text, re.DOTALL):
    ...
```

### 16.2 `re.sub()` 替换

```python
# model/chat.py — 清除 JSON 代码块标记
content = re.sub(r"```json\s*\n?.*?\n?```", "", response_text, flags=re.DOTALL).strip()
```

`re.DOTALL` 让 `.` 也匹配换行符。

---

## 17. 项目未使用的语法特性

以下是 Python 支持但本项目**未使用**的特性，供参考：

| 特性 | 说明 | 项目中的替代方案 |
|------|------|-----------------|
| `Optional[X]` / `Union[X, Y]` | 旧式联合类型 | `X \| Y`（PEP 604） |
| `List[X]` / `Dict[X, Y]` | 旧式泛型 | `list[X]` / `dict[X, Y]`（PEP 585） |
| `match/case` | 模式匹配（3.10+） | `if/elif/else` |
| 海象运算符 `:=` | 赋值表达式 | 普通赋值 |
| `yield` / 生成器 | 惰性序列 | 列表推导、生成器表达式 |
| `Enum` | 枚举类型 | 字符串常量 |
| Pydantic | 数据验证 | `@dataclass` + `dict` |
| 字典/集合推导 | `{k: v for ...}` | 未遇到适用场景 |
| `Callable` / `Protocol` | 函数类型/协议 | `Any` |
| 自定义装饰器 | `@decorator` | 未使用 |
