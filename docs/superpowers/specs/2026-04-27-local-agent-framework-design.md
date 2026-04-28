# 本地 Agent 框架设计文档

## 概述

基于本地离线 `google/gemma-4-31B-it` 构建的模块化 Agent 框架，支持文本 + 多模态（图像、PDF）输入，自建 ReAct Agent Loop，可插拔工具系统，技能调用，以及基于向量库的长期记忆。CLI 优先，后续支持 Web UI。

**硬件**: Apple Silicon (MPS)
**模型运行时**: Transformers + accelerate
**语言**: Python

---

## 架构

选定方案：**模块化 Agent 框架 + 插件系统**

核心 Agent Loop 与工具/技能解耦，插件式工具注册，内置记忆系统（短期对话 + 向量库长期记忆），清晰的分层架构。

---

## 项目结构

```
xx/
├── src/
│   └── agent/
│       ├── __init__.py
│       ├── core/                # 核心循环
│       │   ├── loop.py          # Agent Loop 主循环 (ReAct)
│       │   └── state.py         # 对话状态管理
│       ├── model/               # 模型层
│       │   ├── loader.py        # 模型加载 (Transformers+MPS)
│       │   ├── chat.py          # 聊天接口 (文本+多模态)
│       │   └── prompt.py        # Prompt 模板构建
│       ├── tools/               # 工具系统
│       │   ├── registry.py      # 工具注册中心
│       │   ├── base.py          # 工具基类
│       │   ├── filesystem.py    # 文件系统操作
│       │   ├── shell.py         # Shell 命令执行
│       │   ├── web_request.py   # 网络请求
│       │   ├── code_exec.py     # 代码执行 (沙箱)
│       │   ├── data_query.py    # 数据查询
│       │   └── skill.py         # 技能调用
│       ├── memory/              # 记忆系统
│       │   ├── short_term.py    # 短期对话记忆
│       │   └── long_term.py     # 长期向量库记忆
│       ├── multimodal/          # 多模态处理
│       │   ├── image.py         # 图像预处理
│       │   └── pdf.py           # PDF 解析
│       └── cli/                 # CLI 界面
│           └── interface.py     # 交互式命令行
├── config/
│   ├── default.yaml             # 默认配置
│   └── skills/                  # 技能定义目录
├── data/
│   └── vectorstore/             # 向量库存储目录
├── tests/
├── pyproject.toml
└── README.md
```

**核心依赖**:
- `transformers` + `accelerate` — 模型推理
- `chromadb` — 本地向量库
- `PyMuPDF` — PDF 解析
- `Pillow` — 图像处理
- `rich` — CLI 渲染
- `pydantic` — 数据验证/配置
- `sentence-transformers` — 本地嵌入模型（向量库用）

---

## Agent Loop（核心）

采用 ReAct（Reasoning + Acting）模式：

```
用户输入
  ↓
┌─────────────────────────────┐
│  1. Observe（观察）           │  ← 接收观察（用户消息 / 工具结果 / 多模态内容）
│  2. Think（思考）             │  ← 模型推理：分析 + 决定下一步
│  3. Act（行动）               │  ← 执行工具调用 或 返回最终回答
│     ├─ 工具调用 → 回到 1      │
│     └─ 最终回答 → 退出循环    │
└─────────────────────────────┘
  ↓
输出结果
```

**循环控制**:
- 最大迭代次数: 15（可配置），防止死循环
- 每轮超时: 120s（可配置）
- 迭代计数器在 AgentState 中跟踪

**工具调用格式**: 利用 gemma-4-it 的 function calling 能力，解析模型输出中的 tool_call JSON：
```json
{"name": "shell", "arguments": {"command": "ls -la"}}
```

**多模态注入**: 图像/PDF 在 Observe 阶段预处理，转为模型可接受的输入格式（Gemma4 原生支持图像 token）。

**状态管理** (`AgentState`):
- 对话历史 (messages list)
- 当前迭代轮次
- 已用工具记录
- 执行上下文（工作目录等）

**系统提示词结构**:
```
[角色定义] 你是一个智能助手，具备以下工具...
[可用工具列表]（从注册中心动态生成）
[输出格式] 思考过程 + 工具调用 JSON / 最终回答
[约束] 最大步骤数、安全边界
```

---

## 工具系统

### 工具基类

```python
class BaseTool:
    name: str           # 工具名称
    description: str    # 给模型的描述
    parameters: dict    # JSON Schema 参数定义

    def execute(self, **kwargs) -> str:
        """执行工具，返回结果文本"""
        ...
```

### 注册中心

- `registry.register(tool)` — 注册工具
- `registry.get(name)` — 按名称获取
- `registry.get_all_schemas()` — 生成给模型的工具列表
- `registry.execute(name, args)` — 路由执行

### 内置工具

| 工具 | 功能 | 安全措施 |
|------|------|----------|
| `filesystem` | 读写文件、列目录、搜索 | 限制在允许目录内，禁止写系统文件 |
| `shell` | 执行 shell 命令 | 命令白名单 + 危险命令黑名单（rm -rf 等） |
| `web_request` | HTTP GET/POST | URL 白名单/超时限制，离线模式可禁用 |
| `code_exec` | Python 代码执行 | 沙箱（subprocess + timeout + 资源限制） |
| `data_query` | SQL/数据查询 | 只读模式，限制查询行数 |
| `vector_search` | 向量库语义搜索 | 只读，返回 top-k 结果 |

### 技能调用系统

- 技能 = 预定义的工具组合序列（如"分析项目" = 读文件 + 搜索 + 总结）
- 以 YAML 配置存储在 `config/skills/` 目录，定义步骤链
- Agent 通过 `skill` 工具调用已注册技能
- 技能执行：按步骤依次调用工具，汇总结果

---

## 记忆系统

### 短期记忆

- 存储当前会话的对话历史 (messages list)
- 滑动窗口策略：保留最近 N 轮完整对话 + 更早轮次的摘要
- 摘要由模型自身生成（上下文压缩时触发）
- 每轮对话包含：role, content, tool_calls, tool_results

### 长期记忆

- 基于 ChromaDB 本地向量库
- 存储内容：重要对话片段、用户偏好、项目知识
- 入库策略：当对话中出现"记住这个"等信号，或工具执行产生重要结果时自动入库
- 检索：每轮思考前，用当前查询语义搜索 top-k 相关记忆注入上下文
- 嵌入模型：`sentence-transformers` 本地模型（`all-MiniLM-L6-v2`），不依赖外部 API

---

## 多模态处理

### 图像理解流程

```
用户输入图片路径/URL
  ↓
Pillow 加载 + 预处理（缩放到模型支持尺寸）
  ↓
转为 base64 / 像素张量
  ↓
构建 Gemma4 多模态消息格式（图像 token + 文本）
  ↓
送入模型推理
```

### PDF 文档流程

```
用户输入 PDF 路径
  ↓
PyMuPDF 提取：文本页 + 页面图片
  ↓
文本部分 → 直接注入 prompt
图片部分 → 走图像理解流程
  ↓
合并为多模态消息送入模型
```

- 大 PDF 分页处理，每页独立提取后合并
- 支持混合内容（文字页 + 图表页）

---

## 模型层

### loader.py — 模型加载

- `transformers` AutoModelForCausalLM + AutoProcessor
- 自动检测 MPS 可用性，回退到 CPU
- 支持 4-bit/8-bit 量化加载（Apple Silicon 内存有限时）
- 模型路径：HuggingFace 缓存目录 或 本地路径

### chat.py — 统一聊天接口

- `chat(messages, tools=None, images=None) → Response`
- 消息格式兼容 OpenAI 风格
- 自动处理多模态内容（图像 + 文本混合）
- 工具调用结果解析：检测模型输出中的 tool_call，提取 name + arguments
- 支持流式输出（逐 token）

### prompt.py — Prompt 构建

- 系统提示词模板
- 工具描述注入（从注册中心动态生成）
- 记忆上下文注入

---

## 配置

`config/default.yaml`:

```yaml
model:
  name: "google/gemma-4-31B-it"
  device: "mps"          # auto / mps / cpu
  quantization: null     # null / 4bit / 8bit
  max_new_tokens: 2048

agent:
  max_iterations: 15
  iteration_timeout: 120
  allowed_directories: ["."]

memory:
  short_term_window: 20  # 保留最近 20 轮
  long_term:
    embedding_model: "all-MiniLM-L6-v2"
    top_k: 5

tools:
  shell:
    enabled: true
    blocked_commands: ["rm -rf", "mkfs", "dd"]
  web_request:
    enabled: true
    timeout: 30
  code_exec:
    enabled: true
    timeout: 60
  skill:
    skills_dir: "config/skills"
```

---

## CLI 界面

- 基于 `rich` 库，支持 Markdown 渲染
- 交互模式：`python -m agent` 启动
- 特殊命令：
  - `/image <path>` — 加载图片到对话
  - `/pdf <path>` — 加载 PDF 到对话
  - `/tools` — 列出可用工具
  - `/clear` — 清空对话上下文
  - `/quit` — 退出
- 工具调用过程实时展示（显示调用哪个工具 + 参数 + 结果摘要）

---

## 后续：Web UI

CLI 优先架构天然支持后续 Web UI：
- 模型层和 Agent Loop 与 UI 解耦
- 可用 FastAPI/Gradio 封装 HTTP 接口
- WebSocket 支持流式输出
- CLI 和 Web 共享状态管理
