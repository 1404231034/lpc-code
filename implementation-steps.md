# 实现步骤文档 — Cursor 风格 Mac 桌面客户端

> 本文档记录桌面客户端的详细实现步骤。每个步骤可独立完成和验证，方便中断后下次继续。
> 每个步骤标记 **状态**: ⬜待开始 / 🔵进行中 / ✅已完成

**核心原则**: 不修改现有 `src/agent/core/` 和 `src/agent/model/` 代码。所有 server 专属功能（事件发射、流式输出、会话隔离）通过继承和新模块实现，确保 CLI 零影响。

---

## Phase 1: Python FastAPI + WebSocket 服务器

### Step 1.1: 事件系统 — 类型定义与发射器

**状态**: ⬜待开始

**目标**: 建立事件类型体系和发射器，让 AgentLoop 能发出结构化事件

**具体操作**:

1. 创建 `src/agent/server/` 目录结构：
   ```
   src/agent/server/
       __init__.py
       events/
           __init__.py
           types.py       # 事件类型定义
           emitter.py     # EventEmitter 实现
       observable/
           __init__.py
           observable_loop.py  # 继承 AgentLoop，重写 run()
       streamer/
           __init__.py
           text_streamer.py    # 流式 chat 函数
       sessions/
           __init__.py
           session.py
           manager.py
       approval/
           __init__.py
           gate.py
       routes/
           __init__.py
           session.py
           chat.py
           files.py
           config.py
       app.py
       main.py
   ```
2. 编写 `events/types.py`：
   - `AgentEventType` 枚举：`ITERATION_START`, `MODEL_OUTPUT`, `MODEL_STREAM`, `TOOL_CALL_START`, `TOOL_CALL_END`, `TOOL_APPROVAL_REQUEST`, `AGENT_DONE`, `ERROR`
   - `AgentEvent` Pydantic 模型：`type`, `session_id`, `iteration`, `data: dict`, `timestamp`
   - 各事件的 `data` 字段格式：
     - `MODEL_OUTPUT`: `{"content": "...", "tool_calls_detected": bool}`
     - `MODEL_STREAM`: `{"token": "..."}`
     - `TOOL_CALL_START`: `{"tool_name": "...", "arguments": {...}, "requires_approval": bool}`
     - `TOOL_CALL_END`: `{"tool_name": "...", "success": bool, "output_preview": "...", "duration_ms": int}`
     - `TOOL_APPROVAL_REQUEST`: `{"tool_name": "...", "arguments": {...}, "approval_id": "uuid"}`
     - `AGENT_DONE`: `{"content": "...", "iterations": int, "tool_call_count": int, "reason": "stop|max_iterations|cancelled|error"}`
     - `ERROR`: `{"message": "..."}`
3. 编写 `events/emitter.py`：
   - `EventEmitter` 类，构造函数接收 `asyncio.Queue` 和 `session_id`
   - `emit(event_type, data, iteration)` 方法：创建 `AgentEvent`，通过 `call_soon_threadsafe` 投递到队列
   - 支持从同步线程（AgentLoop 工作线程）安全调用

**验证**: 创建 EventEmitter + asyncio.Queue，从同步线程调用 emit，验证队列收到正确事件

**依赖**: 无

---

### Step 1.2: 可观察 AgentLoop — 继承而非修改

**状态**: ⬜待开始

**目标**: 让 AgentLoop 支持事件发射和用户取消，**不改原始代码，CLI 零影响**

**核心策略**: 不修改 `src/agent/core/loop.py`，而是在 server 层创建子类 `ObservableAgentLoop`，重写 `run()` 方法加入事件发射。CLI 继续用原始 `AgentLoop`，服务器用 `ObservableAgentLoop`，两条路径互不干扰。

**具体操作**:

1. 创建 `src/agent/server/observable/` 目录：
   ```
   src/agent/server/observable/
       __init__.py
       observable_loop.py    # 继承 AgentLoop，重写 run()
   ```
2. 编写 `observable_loop.py`：
   - `ObservableAgentLoop(AgentLoop)` 子类
   - 构造函数增加参数：
     ```python
     event_emitter: EventEmitter | None = None
     cancel_event: threading.Event | None = None
     stream_final_answer: bool = False
     ```
   - 存为 `self._event_emitter`、`self._cancel_event`、`self._stream_final_answer`
   - 重写 `run()` 方法：**复制父类 `run()` 的完整逻辑**，在关键位置插入事件发射：
     - 迭代开始后：`self._emit("iteration_start", {}, iteration)`
     - while 循环开头：检查 `self._cancel_event.is_set()`，如已设置则 emit `agent_done` with `reason: "cancelled"` 并 break
     - 模型输出后：`self._emit("model_output", {"content": ..., "tool_calls_detected": ...}, iteration)`
     - 工具调用前：`self._emit("tool_call_start", {"tool_name": ..., "arguments": ..., "requires_approval": ...}, iteration)`
     - 工具调用后：`self._emit("tool_call_end", {"tool_name": ..., "success": ..., "output_preview": ..., "duration_ms": ...}, iteration)`
     - 最终返回前：`self._emit("agent_done", {"content": ..., "iterations": ..., "tool_call_count": ..., "reason": "stop"}, iteration)`
     - 错误时：`self._emit("error", {"message": ...}, iteration)`
   - 提供 `_emit()` 辅助方法：检查 `self._event_emitter is not None`，是则调用，否则跳过
   - 当最后一轮无工具调用且 `self._stream_final_answer=True` 时，使用 `chat_stream()` 逐 token emit `MODEL_STREAM`

3. **不修改** `src/agent/core/loop.py` — CLI 代码完全不动
4. **不修改** `src/agent/core/state.py` — session_id 在 Session 层管理，不侵入 state

**为什么用继承而非修改**:
- CLI 走原始 `AgentLoop`，代码零改动，不可能被影响
- Server 走 `ObservableAgentLoop`，事件逻辑独立在 server 包内
- 两条路径完全解耦，各自迭代互不干扰

**验证**: 运行 `python -m agent` CLI 完全不受影响；`ObservableAgentLoop` 在有/无 EventEmitter 两种模式下都能正常工作

**依赖**: Step 1.1, Step 1.3（chat_stream 用于流式最终回答，非必须）

---

### Step 1.3: 流式输出 — chat_stream()

**状态**: ⬜待开始

**目标**: 添加逐 token 流式输出能力，**不改原始 chat.py**

**核心策略**: 不修改 `src/agent/model/chat.py`，而是在 server 层新建 `chat_stream()` 函数。原始 `chat()` 给 CLI 用，新 `chat_stream()` 给 server 用。

**具体操作**:

1. 创建 `src/agent/server/streamer/` 目录：
   ```
   src/agent/server/streamer/
       __init__.py
       text_streamer.py    # 流式 chat 函数
   ```
2. 编写 `text_streamer.py`：
   - 新增 `chat_stream()` 函数：
     ```python
     def chat_stream(model, processor, messages, device="cpu",
                     max_new_tokens=2048, temperature=0.7, top_p=0.9,
                     images=None) -> Iterator[str]:
     ```
   - 使用 `transformers.TextIteratorStreamer` + `threading.Thread`
   - Thread 执行 `model.generate()`，主线程迭代 streamer yield token
   - 与原始 `chat()` 参数签名一致，仅返回值改为 token 迭代器
3. 在 `ObservableAgentLoop.run()` 中使用：
   - 当最后一轮无工具调用且 `self._stream_final_answer=True` 时，使用 `chat_stream()` 逐 token emit `MODEL_STREAM`
   - 工具调用解析仍用原始 `chat()`（需要完整输出才能解析 JSON）

**为什么不修改 chat.py**:
- CLI 的 `chat()` 函数完全不动，不可能被影响
- 流式输出是 server 专属需求，不应侵入 model 层

**验证**: 调用 `chat_stream()`，验证能逐 token 获取输出；`python -m agent` CLI 完全不受影响

**依赖**: 无（可与 1.1 并行）

---

### Step 1.4: 会话管理 — SessionManager

**状态**: ⬜待开始

**目标**: 实现多会话管理，每个会话独立状态

**具体操作**:

1. 创建 `src/agent/server/sessions/` 目录：
   ```
   sessions/
       __init__.py
       session.py     # Session 类
       manager.py     # SessionManager 类
   ```
2. 编写 `session.py`：
   - `Session` 类：`session_id: str`, `agent_loop: ObservableAgentLoop`, `event_queue: asyncio.Queue`, `approval_futures: dict[str, asyncio.Future]`, `cancel_event: threading.Event`
   - 每个会话独立 AgentState + cancel_event，共享模型（模型无状态）
3. 编写 `manager.py`：
   - `SessionManager` 类：`_sessions: dict[str, Session]`, `_model_artifacts: dict`, `_config: dict`
   - `create_session() -> str`：创建新 `ObservableAgentLoop` 实例（共享模型），创建事件队列和 cancel_event
   - `destroy_session(session_id) -> None`
   - `get_session(session_id) -> Session | None`
   - `run_agent(session_id, user_input, images) -> None`：提交到 ThreadPoolExecutor
   - `approve_tool(session_id, approval_id, approved) -> None`
   - `cancel_agent(session_id) -> None`：设置 cancel_event
   - 全局 `threading.Lock` 保护 `model.generate()`

**验证**: 创建两个会话，各自独立发送消息，状态互不干扰

**依赖**: Step 1.1, Step 1.2

---

### Step 1.5: 工具审批门 — ToolApprovalGate

**状态**: ⬜待开始

**目标**: 危险工具执行前需用户审批

**具体操作**:

1. 创建 `src/agent/server/approval/` 目录：
   ```
   approval/
       __init__.py
       gate.py
   ```
2. 编写 `gate.py`：
   - `ToolApprovalGate` 类
   - `APPROVAL_REQUIRED_TOOLS = {"shell", "code_exec"}` 常量
   - `request_approval(tool_name, arguments, session) -> bool`：
     - 生成 `approval_id`（UUID）
     - 通过 EventEmitter 发送 `TOOL_APPROVAL_REQUEST` 事件
     - 创建 `threading.Event`，在同步工作线程中 `wait()`
     - 客户端回复后，WebSocket handler 调用 `SessionManager.approve_tool()`，设置 Event
     - 返回 True（批准）或 False（拒绝）
3. 集成到 AgentLoop 的工具调用流程：
   - 在 `emit("tool_call_start")` 后，如果 `requires_approval=True`，调用 `gate.request_approval()`
   - 如果被拒绝，返回 `ToolResult(error="用户拒绝了此操作")`，不执行工具

**验证**: 发送需要审批的工具调用，验证暂停等待 → 客户端批准/拒绝 → 继续/跳过

**依赖**: Step 1.1, Step 1.2, Step 1.4

---

### Step 1.6: FastAPI 应用与 REST 路由

**状态**: ⬜待开始

**目标**: 搭建 FastAPI 应用，实现 REST 端点

**具体操作**:

1. 创建 `src/agent/server/` 下剩余文件：
   ```
   app.py             # FastAPI app 工厂
   main.py            # uvicorn 启动入口
   routes/
       __init__.py
       session.py     # 会话管理端点
       chat.py        # WebSocket 端点（下一步）
       files.py       # 文件操作端点
       config.py      # 配置/工具/技能端点
   ```
2. 编写 `app.py`：
   - `create_app()` 工厂函数
   - CORS 中间件（允许 localhost 渲染器访问）
   - Lifespan 事件：启动时加载模型、创建 SessionManager，关闭时清理
   - 挂载路由
3. 编写 `routes/session.py`：
   - `POST /api/sessions` — 创建会话，返回 `{session_id}`
   - `GET /api/sessions` — 列出活跃会话
   - `DELETE /api/sessions/{id}` — 销毁会话
   - `GET /api/sessions/{id}/history` — 获取对话历史
   - `POST /api/sessions/{id}/clear` — 清空对话
4. 编写 `routes/files.py`：
   - `GET /api/files?path=...` — 读取文件内容
   - `PUT /api/files` — 写入文件（body: `{path, content}`）
   - `POST /api/files/list` — 列出目录内容（body: `{path}`)
5. 编写 `routes/config.py`：
   - `GET /api/tools` — 返回所有工具 schema
   - `GET /api/skills` — 返回技能列表
   - `GET /api/config` — 返回当前配置
   - `GET /api/health` — 健康检查端点 `{"status": "ok", "model_loaded": true}`
6. 编写 `main.py`：
   - `python -m agent.server` 入口
   - 解析命令行参数 `--port`（默认 0，OS 分配）
   - 将实际端口写入临时文件
   - 启动 uvicorn
7. 更新 `pyproject.toml`：
   - 添加依赖：`fastapi>=0.110`, `uvicorn[standard]>=0.29`, `websockets>=12.0`, `python-multipart>=0.0.9`
   - 添加入口：`agent-server = "agent.server.main:main"`

**验证**: `pip install -e .`，`python -m agent.server`，用 curl 测试各 REST 端点返回正确

**依赖**: Step 1.4

---

### Step 1.7: WebSocket 端点 — 实时通信

**状态**: ⬜待开始

**目标**: 实现 WebSocket 端点，实时推送 Agent 事件流

**具体操作**:

1. 编写 `routes/chat.py`：
   - `WebSocket /ws/{session_id}` 端点
   - 连接时：获取 Session，启动两个并发任务：
     - **发送任务**：从 `session.event_queue` 消费事件，序列化为 JSON 发送
     - **接收任务**：读取客户端消息，路由处理：
       - `user_message` → 提交 `session_manager.run_agent()`
       - `tool_approval` → 调用 `session_manager.approve_tool()`
       - `cancel` → 设置 `session.cancel_event`
       - `clear_session` → 重置 AgentState
   - 连接断开时：清理任务
2. 处理边界情况：
   - Agent 运行中客户端断开：取消任务，清理资源
   - 多个客户端连同一会话：仅允许一个 WebSocket 连接
   - 心跳：每 30s 发 ping，超时断开

**验证**: 用 websocat 或 Python websockets 库连接 WS，发送消息，验证收到完整事件流

**依赖**: Step 1.4, Step 1.5, Step 1.6

---

### Step 1.8: 集成测试 — 后端完整验证

**状态**: ⬜待开始

**目标**: 端到端验证后端 API

**具体操作**:

1. 编写 `tests/test_server.py`：
   - 使用 `httpx.AsyncClient` + `pytest-asyncio`
   - 测试创建/销毁会话
   - 测试 WebSocket 连接和事件流
   - 测试工具审批流程
   - 测试文件读写端点
   - 测试并发会话隔离
   - 测试 CLI 仍可正常启动（回归测试）
2. 手动冒烟测试：
   - 启动服务器
   - 创建会话
   - WebSocket 连接发送消息
   - 观察完整事件流顺序

**验证**: 所有测试通过；CLI 不受影响

**依赖**: Step 1.7

---

## Phase 2: Electron 应用壳

### Step 2.1: 项目初始化

**状态**: ⬜待开始

**目标**: 搭建 Electron + TypeScript 项目骨架

**具体操作**:

1. 创建 `desktop/` 目录
2. 初始化项目：
   ```bash
   npm init -y
   npx tsc --init
   ```
3. 安装依赖：
   ```bash
   npm install --save-dev electron electron-builder typescript ts-node
   npm install electron-store
   ```
4. 创建目录结构：
   ```
   desktop/
       package.json
       tsconfig.json
       electron-builder.yml
       src/
           main/
               index.ts
               python-server.ts
               window.ts
               menu.ts
               ipc-handlers.ts
           preload/
               index.ts
           common/
               ipc-channels.ts
               types.ts
       resources/
           icon.icns
   ```
5. 配置 `tsconfig.json`（两个：main 和 preload）
6. 配置 `package.json` scripts：
   - `"dev": "ts-node src/main/index.ts"`
   - `"build": "tsc && electron-builder"`
7. 编写 `electron-builder.yml`：
   - `appId: com.localagent.desktop`
   - `productName: LocalAgent`
   - Mac 目标：dmg + zip
   - `category: public.app-category.developer-tools`

**验证**: `npm run dev` 启动 Electron 窗口（空白页面即可）

**依赖**: 无

---

### Step 2.2: Python 服务器管理

**状态**: ⬜待开始

**目标**: Electron 主进程能启动/停止/监控 Python 服务器

**具体操作**:

1. 编写 `src/main/python-server.ts`：
   - `PythonServerManager` 类
   - `start()`: 
     - 定位 Python 路径（先检查项目 venv，再 `which python3`）
     - spawn: `python3 -m agent.server --port 0 --port-file /tmp/agent-server-port.txt`
     - 轮询端口文件，解析端口号
     - 轮询 `GET http://localhost:{port}/api/health` 直到 200
     - 返回端口号
   - `stop()`: SIGTERM 子进程
   - `isRunning()`: 检查进程状态
   - `onExit(callback)`: 监听进程退出
   - `onStderr(callback)`: 捕获 stderr 输出
   - 错误处理：启动超时、健康检查失败、进程崩溃
2. 在 `index.ts` 中集成：
   - app.whenReady() → 启动 Python 服务器
   - app.on('before-quit') → 停止服务器

**验证**: 启动 Electron，Python 服务器自动启动，控制台显示端口号；退出 Electron，Python 服务器停止

**依赖**: Step 1.6, Step 2.1

---

### Step 2.3: 窗口与菜单

**状态**: ⬜待开始

**目标**: 创建 Cursor 风格的 Mac 窗口和菜单

**具体操作**:

1. 编写 `src/main/window.ts`：
   ```typescript
   const mainWindow = new BrowserWindow({
     width: 1400, height: 900,
     minWidth: 900, minHeight: 600,
     titleBarStyle: 'hiddenInset',
     vibrancy: 'under-window',
     backgroundColor: '#1e1e2e',
     webPreferences: {
       preload: path.join(__dirname, '../preload/index.js'),
       contextIsolation: true,
       nodeIntegration: false,
     },
   });
   ```
   - 开发模式加载 `http://localhost:5173`（Vite dev server）
   - 生产模式加载 `file://...dist/index.html`
2. 编写 `src/main/menu.ts`：
   - LocalAgent: About, Preferences, Quit
   - File: New Session, Open Folder..., Save, Close
   - Edit: Undo, Redo, Cut, Copy, Paste
   - View: Toggle Sidebar (Cmd+B), Toggle AI Panel (Cmd+J), Toggle Status Bar
   - Agent: Clear Session, Show Tools, Show Skills
   - Help: Keyboard Shortcuts
3. 编写 `src/main/ipc-handlers.ts`：
   - `server:ready` → 传递端口到渲染进程
   - `server:restart` → 重启 Python 服务器
   - `file:open` → 原生文件夹选择对话框
   - `file:save` → 写入文件
4. 编写 `src/preload/index.ts`：
   - 通过 `contextBridge` 暴露安全 API
   - `window.electronAPI.getServerPort()`
   - `window.electronAPI.openFolder()`
   - `window.electronAPI.onServerReady()`

**验证**: 启动 Electron，窗口正确显示暗色背景和 Mac 交通灯，菜单项可点击

**依赖**: Step 2.1

---

### Step 2.4: IPC 通道与快捷键

**状态**: ⬜待开始

**目标**: 完善进程间通信和全局快捷键

**具体操作**:

1. 编写 `src/common/ipc-channels.ts`：
   - 定义所有 IPC 通道名常量
2. 编写 `src/common/types.ts`：
   - 定义共享 TypeScript 类型（ServerStatus, SessionInfo 等）
3. 注册全局快捷键：
   - Cmd+B: 切换侧栏
   - Cmd+J: 切换 AI 面板
   - Cmd+L: 聚焦聊天输入
   - Cmd+.: 取消 Agent 运行
   - Cmd+Enter: 发送消息
4. 实现快捷键到渲染进程的转发

**验证**: 各快捷键触发正确行为

**依赖**: Step 2.3

---

## Phase 3: React UI

### Step 3.1: 渲染器项目初始化

**状态**: ⬜待开始

**目标**: 搭建 React + Vite + TypeScript + Tailwind 项目

**具体操作**:

1. 在 `desktop/renderer/` 下初始化：
   ```bash
   npm create vite@latest . -- --template react-ts
   npm install
   npm install -D tailwindcss postcss autoprefixer
   npx tailwindcss init -p
   ```
2. 安装 UI 依赖：
   ```bash
   npm install zustand react-markdown remark-gfm rehype-raw react-syntax-highlighter
   npm install @monaco-editor/react lucide-react framer-motion react-virtuoso
   npm install -D @types/react-syntax-highlighter
   ```
3. 配置 `tailwind.config.js`：暗色模式、自定义颜色
4. 配置 `vite.config.ts`：开发服务器端口 5173，代理 API 请求
5. 创建基础目录结构：
   ```
   renderer/src/
       main.tsx
       App.tsx
       styles/globals.css
       styles/theme.ts
       components/
           Layout/
           Chat/
           Editor/
           FileExplorer/
           Common/
       hooks/
       store/
       lib/
   ```
6. 编写 `styles/theme.ts`：Cursor 暗色主题色值
7. 编写 `styles/globals.css`：Tailwind 基础 + 自定义样式

**验证**: `npm run dev` 启动 Vite，浏览器看到空白暗色页面

**依赖**: 无

---

### Step 3.2: 三栏布局

**状态**: ⬜待开始

**目标**: 实现 Cursor 风格三栏布局（侧栏 + 编辑器 + AI 面板）

**具体操作**:

1. 编写 `components/Layout/AppLayout.tsx`：
   - CSS Grid 三栏布局
   - 可拖拽分割线调整宽度和高度（使用 `components/Common/SplitPane.tsx`）
   - 默认比例：侧栏 250px | 编辑器 50% | AI 面板 50%
2. 编写 `components/Common/SplitPane.tsx`：
   - 可拖拽分割面板组件
   - 支持水平/垂直分割
   - 记住尺寸到 ui-store
3. 编写 `components/Layout/TitleBar.tsx`：
   - Mac 交通灯占位（Electron 自带）
   - 会话选择/切换
   - 居中标题
4. 编写 `components/Layout/StatusBar.tsx`：
   - 左侧：模型名称 + 设备
   - 中间：迭代计数、工具调用计数
   - 右侧：连接状态
5. 编写 `store/ui-store.ts`：
   - `sidebarVisible`, `aiPanelVisible`, `statusBarVisible`
   - `sidebarWidth`, `aiPanelWidth`
   - toggle/set 方法
6. 编写 `App.tsx`：组装布局

**验证**: 渲染器显示三栏布局，分割线可拖拽，侧栏/AI面板可切换显隐

**依赖**: Step 3.1

---

### Step 3.3: AI 聊天面板 — 消息显示

**状态**: ⬜待开始

**目标**: 实现聊天消息列表，支持 Markdown 渲染和代码高亮

**具体操作**:

1. 编写 `store/chat-store.ts`：
   - `Message` 类型：`id, role, blocks: MessageBlock[], timestamp, metadata`
   - `MessageBlock` 联合类型：`text | tool_call | code | image`
   - `ToolCallBlock` 类型：`id, toolName, arguments, result?, status, durationMs`
   - Store 方法：`addMessage`, `addToolCall`, `updateToolCall`, `appendStreamToken`, `finalizeStream`, `clearMessages`
2. 编写 `components/Chat/ChatContainer.tsx`：
   - 使用 `react-virtuoso` 虚拟滚动
   - 自动滚动到底部
3. 编写 `components/Chat/MessageBubble.tsx`：
   - 用户消息：右侧，简洁背景
   - 助手消息：左侧，迭代 blocks 渲染
   - 流式时最后文本块逐字更新
4. 编写 `components/Chat/MarkdownRenderer.tsx`：
   - `react-markdown` + `remark-gfm` + `rehype-raw`
   - 代码块用 `react-syntax-highlighter` 高亮
5. 编写 `components/Chat/CodeBlock.tsx`：
   - 语法高亮 + 复制按钮
   - 匹配 Cursor 风格（暗色代码块背景）
6. 编写 `components/Chat/StreamingIndicator.tsx`：
   - Agent 思考中的动画指示器

**验证**: 用 mock 数据渲染各种消息类型（纯文本、Markdown、代码块），滚动流畅

**依赖**: Step 3.2

---

### Step 3.4: AI 聊天面板 — 工具调用与审批

**状态**: ⬜待开始

**目标**: 实现工具调用显示和审批交互

**具体操作**:

1. 编写 `components/Chat/ToolCallBlock.tsx`：
   - 默认折叠：显示工具图标 + 名称 + 状态 + 一行结果摘要
   - 展开后：完整参数 JSON + 完整输出 + 错误信息 + 耗时
   - 状态图标：pending(旋转)、running(蓝色)、success(绿色)、error(红色)、approval_needed(黄色)
   - 工具图标映射：filesystem→文件夹, shell→终端, web→网络, code→代码, data→数据库, vector→搜索, skill→技能
2. 编写 `components/Chat/ToolApproval.tsx`：
   - 黄色/琥珀色横幅
   - 显示工具名 + 参数摘要
   - "Allow" 和 "Deny" 按钮
   - 点击 Allow → 发送 `tool_approval` WebSocket 消息
3. 集成到 MessageBubble：工具调用块嵌入助手消息中

**验证**: mock 工具调用数据，折叠/展开正常，审批按钮点击触发正确回调

**依赖**: Step 3.3

---

### Step 3.5: AI 聊天面板 — 输入框

**状态**: ⬜待开始

**目标**: 实现聊天输入框，支持附件和快捷键

**具体操作**:

1. 编写 `components/Chat/ChatInput.tsx`：
   - 自动调整高度的 textarea（1-8行）
   - Cmd+Enter 发送
   - 占位文字："Ask anything... (Cmd+Enter)"
   - 发送按钮
   - 附件按钮（图片/PDF）
2. 实现附件功能：
   - 点击附件按钮 → 打开文件选择对话框
   - 支持 drag-and-drop（使用 react-dropzone）
   - 已选附件显示为小标签，可删除
3. 编写 `components/Chat/ImagePreview.tsx`：
   - 消息中的内联图片预览

**验证**: 输入文字 → 发送 → 消息出现；拖拽图片 → 附件显示 → 发送带图片的消息

**依赖**: Step 3.3

---

### Step 3.6: Monaco 代码编辑器

**状态**: ⬜待开始

**目标**: 集成 Monaco Editor，支持文件编辑和保存

**具体操作**:

1. 编写 `store/editor-store.ts`：
   - `openFiles: OpenFile[]`, `activeFileIndex: number`, `workingDirectory: string`
   - 方法：`openFile`, `closeFile`, `setActiveFile`, `updateFileContent`, `setWorkingDirectory`
2. 编写 `components/Editor/MonacoEditor.tsx`：
   - 使用 `@monaco-editor/react`
   - 自定义暗色主题（匹配 Cursor 色值）
   - 根据 `activeFileIndex` 显示文件内容
   - 内容变更 → 更新 store
   - Cmd+S → 保存文件（调用 REST API）
3. 编写 `components/Editor/EditorTabs.tsx`：
   - 打开文件的标签页
   - 点击切换，中间按钮关闭
   - 修改标记（文件有未保存更改时显示点号）
4. 编写 `components/Editor/EditorBreadcrumb.tsx`：
   - 文件路径面包屑导航

**验证**: 打开文件 → Monaco 渲染 → 编辑 → 保存 → 文件内容更新

**依赖**: Step 3.2

---

### Step 3.7: 文件浏览器

**状态**: ⬜待开始

**目标**: 实现左侧文件树，可浏览和打开文件

**具体操作**:

1. 编写 `hooks/useFileExplorer.ts`：
   - 调用 `/api/files/list` 获取目录内容
   - 懒加载：目录展开时才加载子内容
   - 缓存已加载的目录
2. 编写 `components/FileExplorer/FileTree.tsx`：
   - 递归树组件
   - 文件夹点击 → 展开/折叠
   - 文件点击 → 调用 `editor-store.openFile()` + `GET /api/files`
3. 编写 `components/FileExplorer/FileTreeNode.tsx`：
   - 文件/文件夹图标（lucide-react）
   - 文件类型图标映射（.py → Python, .js → JS, .md → Markdown...）
   - 右键上下文菜单（Open, Reveal in Finder）
4. 编写 `components/Layout/Sidebar.tsx`：
   - 包裹 FileTree
   - 顶部：工作目录名称 + 刷新按钮
   - 可折叠

**验证**: 文件树显示，点击文件在编辑器打开，点击文件夹展开/折叠

**依赖**: Step 3.2, Step 3.6

---

### Step 3.8: WebSocket 集成 — 前端连接层

**状态**: ⬜待开始

**目标**: 实现 WebSocket 客户端，连接后端事件流

**具体操作**:

1. 编写 `lib/protocol.ts`：
   - TypeScript 类型定义，对齐服务端事件类型
   - `AgentEvent`, `UserMessage`, `ToolApproval` 等
2. 编写 `lib/ws-client.ts`：
   - WebSocket 连接管理
   - 自动重连（指数退避：1s, 2s, 4s, 最大 30s）
   - 发送/接收消息
   - 心跳检测
3. 编写 `lib/api-client.ts`：
   - REST API 封装（fetch）
   - `createSession()`, `getTools()`, `getFile()`, `saveFile()`, `listDir()` 等
4. 编写 `hooks/useWebSocket.ts`：
   - 连接 WebSocket
   - 监听事件，分发到 chat-store：
     - `MODEL_STREAM` → `appendStreamToken`
     - `MODEL_OUTPUT` → 创建助手消息
     - `TOOL_CALL_START` → `addToolCall`
     - `TOOL_CALL_END` → `updateToolCall`
     - `TOOL_APPROVAL_REQUEST` → `setPendingApproval`
     - `AGENT_DONE` → `finalizeStream`
     - `ERROR` → 错误通知
   - 返回：`{ send, isConnected, reconnecting }`
5. 编写 `hooks/useAgentSession.ts`：
   - 会话创建/销毁
   - 连接状态管理

**验证**: 启动后端，前端 WS 连接成功，发送消息收到事件流，store 正确更新

**依赖**: Step 1.7（后端 WS 端点就绪）, Step 3.3

---

## Phase 4: 集成与打磨

### Step 4.1: 端到端集成

**状态**: ⬜待开始

**目标**: Electron 启动 → Python 服务器 → WebSocket → UI 完整链路

**具体操作**:

1. 连接 Electron 主进程与渲染进程：
   - 主进程启动 Python 服务器获取端口
   - 通过 preload API 传递端口到渲染进程
   - 渲染进程用端口建立 WebSocket 和 REST 连接
2. 完整用户流程调试：
   - 启动应用 → 创建会话 → 输入消息 → 看到流式输出
   - 工具调用展示 → 审批交互
   - 打开文件夹 → 浏览文件树 → 编辑文件 → 保存
3. 错误处理：
   - 服务器崩溃 → 显示错误 + 重启按钮
   - WebSocket 断开 → 自动重连 + 提示
   - 模型 OOM → 建议启用量化

**验证**: 完整流程无报错，所有功能可用

**依赖**: Step 1.8, Step 2.4, Step 3.7, Step 3.8

---

### Step 4.2: UI 打磨 — 细节与动效

**状态**: ⬜待开始

**目标**: 打磨 UI 细节，接近 Cursor 的视觉和交互体验

**具体操作**:

1. 动效：
   - 消息出现动画（framer-motion fade-in）
   - 工具调用块展开/折叠动画
   - 流式输出打字效果
   - 侧栏/面板切换过渡
2. 细节：
   - 消息时间戳 hover 显示
   - 工具调用耗时显示
   - 错误消息红色高亮
   - 连接状态实时指示（绿点/红点）
   - 代码块一键复制
   - 消息输入框聚焦样式
3. 快捷键完善：
   - 所有快捷键可用且无冲突
   - 快捷键提示显示在菜单中
4. 响应式：
   - 窗口缩小时面板自动折叠
   - 最小尺寸下不溢出

**验证**: 视觉体验接近 Cursor，操作流畅无卡顿

**依赖**: Step 4.1

---

### Step 4.3: 构建打包与分发

**状态**: ⬜待开始

**目标**: 打包为 Mac .dmg 安装包

**具体操作**:

1. 配置 `electron-builder.yml`：
   - Mac 代码签名（如有开发者证书）
   - DMG 背景、窗口大小
   - 应用图标
2. 优化打包体积：
   - Monaco Editor 按语言按需加载
   - Tree-shaking
   - ASAR 打包
3. 编写安装说明：
   - 前置条件：Python 3.10+, pip install -e .
   - 首次启动指引
4. 测试安装包：
   - 全新 Mac 上安装
   - 首次启动流程
   - 卸载清理

**验证**: `npm run build` 生成 .dmg，安装后可正常启动使用

**依赖**: Step 4.2

---

## 进度追踪

| Step | 描述 | 状态 | 依赖 |
|------|------|------|------|
| 1.1 | 事件系统 — 类型定义与发射器 | ⬜待开始 | 无 |
| 1.2 | 可观察 AgentLoop — 继承而非修改 | ⬜待开始 | 1.1, 1.3 |
| 1.3 | 流式输出 — chat_stream() | ⬜待开始 | 无 |
| 1.4 | 会话管理 — SessionManager | ⬜待开始 | 1.1, 1.2 |
| 1.5 | 工具审批门 — ToolApprovalGate | ⬜待开始 | 1.1, 1.2, 1.4 |
| 1.6 | FastAPI 应用与 REST 路由 | ⬜待开始 | 1.4 |
| 1.7 | WebSocket 端点 — 实时通信 | ⬜待开始 | 1.4, 1.5, 1.6 |
| 1.8 | 集成测试 — 后端完整验证 | ⬜待开始 | 1.7 |
| 2.1 | Electron 项目初始化 | ⬜待开始 | 无 |
| 2.2 | Python 服务器管理 | ⬜待开始 | 1.6, 2.1 |
| 2.3 | 窗口与菜单 | ⬜待开始 | 2.1 |
| 2.4 | IPC 通道与快捷键 | ⬜待开始 | 2.3 |
| 3.1 | 渲染器项目初始化 | ⬜待开始 | 无 |
| 3.2 | 三栏布局 | ⬜待开始 | 3.1 |
| 3.3 | AI 聊天 — 消息显示 | ⬜待开始 | 3.2 |
| 3.4 | AI 聊天 — 工具调用与审批 | ⬜待开始 | 3.3 |
| 3.5 | AI 聊天 — 输入框 | ⬜待开始 | 3.3 |
| 3.6 | Monaco 代码编辑器 | ⬜待开始 | 3.2 |
| 3.7 | 文件浏览器 | ⬜待开始 | 3.2, 3.6 |
| 3.8 | WebSocket 前端集成 | ⬜待开始 | 1.7, 3.3 |
| 4.1 | 端到端集成 | ⬜待开始 | 1.8, 2.4, 3.7, 3.8 |
| 4.2 | UI 打磨 — 细节与动效 | ⬜待开始 | 4.1 |
| 4.3 | 构建打包与分发 | ⬜待开始 | 4.2 |

---

## 依赖关系图

```
Phase 1 (后端):
  1.1 ──┬──> 1.2 ──┬──> 1.4 ──┬──> 1.5 ──┐
        │          │          ├──> 1.6 ──┤
  1.3 ──┘          │          │          ├──> 1.7 ──> 1.8
                   └──────────┘          ┘

Phase 2 (Electron):
  2.1 ──┬──> 2.2 (需 1.6)
        ├──> 2.3 ──> 2.4

Phase 3 (React UI):
  3.1 ──> 3.2 ──┬──> 3.3 ──┬──> 3.4
                │          ├──> 3.5
                ├──> 3.6 ──┤
                │          └──> 3.7
                └──> 3.8 (需 1.7 + 3.3)

Phase 4 (集成):
  1.8 + 2.4 + 3.7 + 3.8 ──> 4.1 ──> 4.2 ──> 4.3
```

**可并行的步骤**:
- 1.1 和 1.3 和 2.1 和 3.1 可并行（无互相依赖）
- 1.4 和 2.3 可并行
- 3.3 和 3.6 可并行
- 3.4 和 3.5 和 3.7 可并行
