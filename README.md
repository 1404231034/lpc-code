# Local Agent

基于本地离线 `google/gemma-4-31B-it` 构建的模块化 Agent 框架，支持文本 + 多模态（图像、PDF）输入，自建 ReAct Agent Loop，可插拔工具系统，技能调用，以及基于向量库的长期记忆。

## 特性

- **本地离线运行** — 基于 Transformers + accelerate，数据不出本机
- **ReAct 推理循环** — 思考→行动→观察，支持多轮工具调用
- **7 个内置工具** — 文件系统、Shell、网络请求、代码执行、数据查询、向量搜索、技能调用
- **多模态输入** — 支持图像理解（JPG/PNG/WebP）和 PDF 文档解析
- **双层记忆** — 短期对话滑动窗口 + ChromaDB 向量库长期记忆
- **技能系统** — YAML 定义工具组合，一键执行复杂流程
- **MPS 加速** — 自动检测 Apple Silicon MPS / CUDA / CPU
- **量化支持** — 可选 4-bit / 8-bit 量化，降低内存占用
- **Rich CLI** — Markdown 渲染、工具调用实时展示

## 项目结构

```
xx/
├── src/agent/
│   ├── core/          # Agent Loop + 状态管理
│   ├── model/         # 模型加载、聊天接口、Prompt 构建
│   ├── tools/         # 工具基类、注册中心、7 个内置工具
│   ├── memory/        # 短期对话记忆 + 长期向量库记忆
│   ├── multimodal/    # 图像预处理 + PDF 解析
│   └── cli/           # Rich 交互式命令行
├── config/
│   ├── default.yaml   # 默认配置
│   └── skills/        # 技能定义 (YAML)
├── data/vectorstore/  # ChromaDB 持久化目录
└── tests/
```

## 快速开始

### 环境要求

- Python >= 3.10
- Apple Silicon Mac (MPS) / CUDA GPU / CPU
- 至少 32GB 内存（全量加载），或使用量化模式

### 安装

```bash
cd xx
pip install -e .
```

### 配置本地模型路径

编辑 `config/default.yaml`，将 `name` 指向你本地的模型路径：

```yaml
model:
  name: "/path/to/your/gemma-4-31B-it"   # 本地模型路径
```

### 启动

```bash
python -m agent
```

### 量化模式

内存不足时可启用量化：

```yaml
model:
  quantization: "4bit"   # 或 "8bit"
```

## CLI 命令

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

## 内置工具

| 工具 | 功能 | 安全措施 |
|------|------|----------|
| `filesystem` | 读写文件、列目录、搜索文件 | 限制在允许目录内，禁止写系统文件 |
| `shell` | 执行 shell 命令 | 危险命令黑名单（rm -rf 等），超时控制 |
| `web_request` | HTTP GET/POST | 超时限制，可禁用（离线模式） |
| `code_exec` | Python 代码执行 | subprocess 隔离，超时 + 输出截断 |
| `data_query` | SQLite 数据查询 | 只读模式，限制返回行数 |
| `vector_search` | 向量库语义搜索 | 只读，返回 top-k 结果 |
| `skill` | 调用预定义技能 | 按 YAML 步骤链执行 |

## 技能系统

在 `config/skills/` 下创建 YAML 文件定义技能：

```yaml
name: "analyze_project"
description: "分析项目结构和代码"
steps:
  - tool: "filesystem"
    args: { "action": "list_dir", "path": "." }
  - tool: "shell"
    args: { "command": "find . -name '*.py' | head -20" }
```

启动后通过 `/skills` 查看可用技能，对话中 Agent 会自动按步骤执行。

## 记忆系统

**短期记忆**：保留最近 20 轮完整对话，更早的对话自动压缩为摘要。

**长期记忆**：基于 ChromaDB + sentence-transformers 嵌入，对话中出现"记住"等信号时自动入库，每轮思考前检索相关记忆注入上下文。

## 配置

编辑 `config/default.yaml` 自定义行为：

```yaml
model:
  name: "google/gemma-4-31B-it"
  device: "auto"        # auto / mps / cpu / cuda
  quantization: null    # null / 4bit / 8bit
  max_new_tokens: 2048
  temperature: 0.7

agent:
  max_iterations: 15
  iteration_timeout: 120
  allowed_directories: ["."]

memory:
  short_term_window: 20
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
```

## 架构

```
用户输入
  ↓
┌─────────────────────────────┐
│  1. Observe  接收观察       │  ← 用户消息 / 工具结果 / 多模态内容
│  2. Think    模型推理       │  ← 分析 + 决定下一步
│  3. Act      执行行动       │  ← 工具调用 或 返回最终回答
│     ├─ 工具调用 → 回到 1    │
│     └─ 最终回答 → 退出循环  │
└─────────────────────────────┘
  ↓
输出结果
```

## 测试

```bash
# 单元测试（无需模型）
python -m pytest tests/test_units.py -v

# 集成测试（需要模型已下载）
python tests/test_basic.py
```

## 核心依赖

- `transformers` + `accelerate` — 模型推理
- `chromadb` — 本地向量库
- `sentence-transformers` — 嵌入模型
- `PyMuPDF` — PDF 解析
- `Pillow` — 图像处理
- `rich` — CLI 渲染
- `pydantic` — 数据验证
- `pyyaml` — 配置与技能定义

## License

MIT
