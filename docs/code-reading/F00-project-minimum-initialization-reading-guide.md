# F00 Code Reading Guide — Project Minimum Initialization

本文档面向项目开发人员，帮助理解 F00 最小 FastAPI 工程**为什么能运行起来**，以及各文件之间的关系。

---

## 1. F00 解决了什么问题

本项目最终目标是「政务大厅全过程智能办事 Agent」，包含 Business Graph、Rule Engine、Semantic Retrieval、LangGraph Agent 等复杂能力。但**第一步不是直接开发 Agent**，原因是：

- 若缺少统一的 Python 工程基线，后续每个 Feature 都无法在同一套约定下安装、启动和测试；
- 若一次性按 Architecture Blueprint 创建完整目录，会产生大量无法理解的空代码；
- 渐进式开发要求：每次只解决一个明确问题，验证通过后再进入下一 Feature。

**F00 的目标只是：**

```
Python 工程 → 安装依赖 → FastAPI 启动 → GET /health → pytest 通过
```

F00 是后续所有 Feature（F01 Settings、F02 业务数据、F03 Business Graph……）的**工程基线**。没有 F00，后续 Feature 缺少稳定的起点。

---

## 2. 推荐代码阅读顺序

| 顺序 | 文件 | 为什么先看 | 看什么 | 看懂后应理解 |
|------|------|-----------|--------|-------------|
| 1 | `README.md` | 项目入口文档 | 当前阶段、环境要求、安装/启动/测试命令 | F00 做了什么、没做什么 |
| 2 | `pyproject.toml` | 工程与依赖的「总配置文件」 | 项目名、Python 版本、依赖、打包方式 | 项目如何被 pip 识别和安装 |
| 3 | `src/gov_service_agent/__init__.py` | Python 包声明 | 包 docstring | `gov_service_agent` 是一个可 import 的包 |
| 4 | `src/gov_service_agent/main.py` | 应用核心 | FastAPI app、`/health` 路由 | HTTP 请求如何被处理 |
| 5 | `tests/test_health.py` | 自动化验证 | pytest 用例、TestClient | 如何在不启动 uvicorn 的情况下测试 |
| 6 | `AGENTS.md` | 不可违反的开发规则 | 阶段流程、Scope 边界 | 为什么不能随意扩大范围 |
| 7 | `docs/development-playbook.md` | 详细开发流程 | 各阶段说明 | Feature 如何逐步推进 |
| 8 | `docs/features/F00-project-minimum-initialization.md` | F00 范围权威 | 目标、Non-goals、测试结果 | F00 的完成标准与边界 |

---

## 3. pyproject.toml 详细解释

### 3.1 pyproject.toml 是什么

`pyproject.toml` 是现代 Python 项目的**标准配置文件**（PEP 518 / PEP 621）。它告诉 pip 和构建工具：

- 这个项目叫什么；
- 需要什么 Python 版本；
- 需要哪些第三方库；
- 如何打包成可安装的包。

### 3.2 各段含义

```toml
[project]
name = "gov-service-agent"        # PyPI/安装时的项目名
version = "0.1.0"                 # 当前版本
description = "..."               # 项目描述
requires-python = ">=3.11,<3.12"  # 只允许 Python 3.11.x
dependencies = [                  # 运行时依赖（安装后始终需要）
    "fastapi>=0.100",
    "uvicorn[standard]>=0.23",
]

[project.optional-dependencies]
dev = [                           # 开发时额外依赖（测试用）
    "pytest>=7.4",
    "httpx>=0.24",
]

[build-system]
requires = ["hatchling"]          # 构建时需要 hatchling
build-backend = "hatchling.build" # 使用 hatchling 作为构建后端

[tool.hatch.build]
sources = ["src"]                 # 源码在 src/ 目录下（src layout）

[tool.pytest.ini_options]
testpaths = ["tests"]             # pytest 在 tests/ 目录找测试
```

### 3.3 为什么使用 hatchling，不使用 Poetry

- F00 只需要轻量的打包能力，hatchling 足够；
- 不引入 Poetry 的额外工具链和 lock 文件机制；
- 符合项目「最小实现」原则。

### 3.4 为什么不使用 `pythonpath=["."]`

若在 pytest 配置中写 `pythonpath=["."]`，测试可能**绕过**正确的 packaging，直接从源码目录 import，掩盖「未执行 editable install 时 import 失败」的问题。F00 要求测试必须验证真实的安装路径。

### 3.5 `python -m pip install -e ".[dev]"` 做了什么

这条命令可以拆成几部分理解：

| 部分 | 含义 |
|------|------|
| `python -m pip` | 使用**当前激活环境**的 Python 调用 pip，避免装到错误的 Python |
| `install` | 安装包 |
| `-e` | **editable（可编辑）模式**：源码仍在 `src/`，修改代码后无需重新 install |
| `"."` | 当前目录（含 `pyproject.toml` 的项目根） |
| `[dev]` | 同时安装 `optional-dependencies.dev` 中的依赖（pytest、httpx） |

执行后，pip 会：

1. 读取 `pyproject.toml`；
2. 用 hatchling 构建包元数据；
3. 在 site-packages 中创建指向项目根目录的链接；
4. 安装 fastapi、uvicorn、pytest、httpx 等依赖。

因此，之后在 Python 中：

```python
import gov_service_agent
```

Python 会通过 editable install 的链接找到 `src/gov_service_agent/`，而不是依赖 `PYTHONPATH` 或 `sys.path` 手工修改。

---

## 4. src layout 解释

当前结构：

```
src/
└─ gov_service_agent/
   ├─ __init__.py
   └─ main.py
```

### 4.1 为什么源码放 `src/` 下

- **隔离源码与项目根**：测试、文档、配置与业务代码分离；
- **避免 import 陷阱**：若包直接放根目录，测试可能意外从错误路径 import；
- **行业惯例**：许多 Python 项目采用 src layout，便于 packaging 工具正确发现包。

### 4.2 为什么不是直接放项目根目录

根目录布局（如 `gov_service_agent/` 与 `tests/` 并列）在小型项目中可行，但随着项目扩展，容易与配置文件、文档混在一起。F00 从第一天采用 src layout，**避免未来迁移包结构**。

### 4.3 未来如何扩展

后续 Feature 会在 `src/gov_service_agent/` 下**按需**增加模块（如 F01 的配置/日志模块），但不会一次性创建 Blueprint 中的全部目录。目录随 Feature 实际开发而生长。

---

## 5. `__init__.py` 解释

`__init__.py` 的作用：

- 告诉 Python：`gov_service_agent` 是一个**包（package）**，不是普通文件夹；
- 允许 `import gov_service_agent` 和 `from gov_service_agent.main import app`。

当前内容只有一行 docstring，因为 F00 不需要在包级别暴露 API 或执行初始化逻辑。这不是业务入口，只是包声明。

---

## 6. `main.py` 逐结构解释

```python
from fastapi import FastAPI

app = FastAPI(title="gov-service-agent")


@app.get("/health")
def health():
    return {"status": "ok"}
```

### 6.1 逐行说明

| 代码 | 含义 |
|------|------|
| `from fastapi import FastAPI` | 从 FastAPI 库导入 Web 框架核心类 |
| `app = FastAPI(title="gov-service-agent")` | 创建一个 FastAPI **应用实例**，后续所有路由注册到这个 `app` 上 |
| `@app.get("/health")` | **装饰器**：把下面的函数注册为处理 `GET /health` 请求的路由 |
| `def health():` | 路由处理函数（handler） |
| `return {"status": "ok"}` | 返回 Python 字典，FastAPI 自动转为 JSON 响应 |

### 6.2 完整调用过程

```
浏览器 / HTTP Client
    ↓ 发送 GET /health
Uvicorn（ASGI 服务器）
    ↓ 接收 HTTP 请求，交给 FastAPI
FastAPI app
    ↓ 路径匹配：/health → health 函数
health()
    ↓ 执行，返回 {"status": "ok"}
FastAPI
    ↓ 序列化为 JSON
HTTP 200 Response
    ↓ Content-Type: application/json
{"status": "ok"}
```

### 6.3 为什么使用同步 `def`

F00 的 `/health` 只做内存计算、不访问 IO，`def` 足够简单清晰。异步 `async def` 适用于高并发 IO 场景，F00 不需要。

### 6.4 F00 故意不包含的内容

| 未包含 | 原因 |
|--------|------|
| `APIRouter` | 只有 1 个路由，无需拆分 |
| `Depends` | 无依赖注入需求 |
| 中间件 | F01 才引入日志等 |
| Settings | F01 负责 |
| 数据库 | 后续 Feature |
| LangGraph | 后续 Feature |

这是**有意的最小设计**，不是「缺功能」。

---

## 7. Uvicorn 解释

启动命令：

```powershell
uvicorn gov_service_agent.main:app --host 127.0.0.1 --port 8000
```

| 部分 | 含义 |
|------|------|
| `uvicorn` | ASGI 服务器，负责监听 HTTP 端口、接收请求、交给 FastAPI |
| `gov_service_agent.main` | Python 模块路径（包名.模块名） |
| `:app` | 该模块中的变量名 `app`（FastAPI 实例） |
| `--host 127.0.0.1` | 只监听本机，不对外网暴露 |
| `--port 8000` | 监听 8000 端口 |

**`gov_service_agent.main:app` 为什么能定位到 FastAPI 应用？**

1. editable install 后，`gov_service_agent` 包可被 Python 发现；
2. `main` 是 `gov_service_agent` 包下的 `main.py` 模块；
3. `app` 是该模块中定义的 `FastAPI` 实例；
4. uvicorn 导入该模块，取出 `app` 对象，作为 ASGI 应用运行。

---

## 8. GET /health 数据流

```
GET /health
    ↓
Uvicorn 接收 HTTP 请求
    ↓
交给 FastAPI（ASGI 协议）
    ↓
FastAPI 根据路径和方法匹配路由
    ↓
找到 @app.get("/health") 注册的 health()
    ↓
调用 health()，返回 {"status": "ok"}
    ↓
FastAPI 将 dict 序列化为 JSON
    ↓
HTTP 200 Response，Body: {"status":"ok"}
```

**当前 `/health` 只表示：** FastAPI 应用进程可以正常工作。

**不代表：** PostgreSQL、Redis、LLM、Embedding 等服务可用。这些探针将在后续 Feature 中按需扩展。

---

## 9. `tests/test_health.py` 解释

### 9.1 pytest 是什么

pytest 是 Python 的自动化测试框架。执行 `pytest -v` 时，它会：

1. 发现 `tests/` 目录下以 `test_` 开头的函数；
2. 逐个执行；
3. 报告 PASSED / FAILED。

### 9.2 TestClient 是什么

`TestClient` 来自 FastAPI（底层基于 Starlette），可以在**不启动 uvicorn** 的情况下，在进程内模拟 HTTP 请求，直接调用 FastAPI app。

### 9.3 为什么 `import gov_service_agent` 能成功

因为已执行 `pip install -e ".[dev]"`，Python 的 site-packages 中有指向项目的 editable 链接，import 路径由 packaging 正确配置。

### 9.4 两个测试分别验证什么

| 测试 | 验证内容 |
|------|----------|
| `test_app_importable` | `from gov_service_agent.main import app` 成功，且 `app` 非空 |
| `test_health_returns_ok` | `TestClient(app).get("/health")` 返回 200，JSON 为 `{"status":"ok"}` |

### 9.5 测试调用链

```
pytest 发现 test_health_returns_ok
    ↓
from gov_service_agent.main import app  （editable install 路径）
    ↓
client = TestClient(app)
    ↓
response = client.get("/health")  （进程内模拟 HTTP，不启动 uvicorn）
    ↓
FastAPI 路由 → health() → {"status": "ok"}
    ↓
assert response.status_code == 200
assert response.json() == {"status": "ok"}
    ↓
PASSED
```

---

## 10. F00 的完整运行链

### 10.1 运行时链路

```
Conda / Python 3.11 隔离环境
    ↓
python -m pip install -e ".[dev]"
    ↓
Python 发现 gov_service_agent（editable link → src/gov_service_agent/）
    ↓
uvicorn gov_service_agent.main:app
    ↓
加载 main.py 中的 app 对象
    ↓
FastAPI 启动，监听 127.0.0.1:8000
    ↓
用户 GET /health
    ↓
HTTP 200 {"status":"ok"}
```

### 10.2 测试链路

```
pytest -v
    ↓
发现 tests/test_health.py
    ↓
import app（通过 editable install）
    ↓
TestClient(app)
    ↓
GET /health（进程内）
    ↓
assert 200 + JSON
    ↓
2 passed
```

---

## 11. 当前开发环境

已验证环境：

| 项 | 值 |
|----|-----|
| Conda environment | govagent |
| Python | 3.11.16 |

**重要：** `govagent` 只是当前主开发环境名称，**不是程序运行依赖**。项目不与 Conda 或固定环境名强绑定。任何满足 Python 3.11.x 的合理隔离环境（Conda、venv、virtualenv 等）均可运行。

---

## 12. 如何启动

```powershell
# 1. 激活 Python 3.11 隔离环境（推荐）
conda activate govagent

# 2. 确认 Python 版本
python --version
# 期望：Python 3.11.x

# 3. 安装（首次或依赖变更后）
python -m pip install -e ".[dev]"

# 4. 运行测试
pytest -v

# 5. 启动服务
uvicorn gov_service_agent.main:app --host 127.0.0.1 --port 8000

# 6. 浏览器访问
# http://127.0.0.1:8000/health
# 期望：{"status":"ok"}
```

---

## 13. 如何查看和理解测试

### 13.1 pytest 输出含义

| 输出 | 含义 |
|------|------|
| `collected 2 items` | 发现 2 个测试用例 |
| `PASSED` | 测试通过 |
| `FAILED` | 测试失败 |
| `warning` | 非致命警告，测试仍可能通过 |

### 13.2 当前真实测试证据

```
2 passed, 0 failed, 1 warning
```

### 13.3 当前 warning 说明

```
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated;
install httpx2 instead.
```

| 项 | 说明 |
|----|------|
| 性质 | 上游 FastAPI/Starlette 库的 deprecation warning |
| 影响 F00 | **否** — 测试全部通过，/health 契约正确 |
| F00 处理 | **不修改依赖** — 不为消 warning 擅自升级或安装 httpx2 |
| 后续 | 记录为 INFO 技术债（RF-F00-005），后续 Feature 观察 |

---

## 14. 如何 Debug

### 14.1 推荐断点

在 `src/gov_service_agent/main.py` 的 `health()` 函数内设置断点：

```python
def health():
    return {"status": "ok"}  # ← 在此行设断点
```

### 14.2 最简单 Debug 思路（F00 无 launch.json）

1. **阅读请求** — 确认 URL 是 `/health`，方法是 GET；
2. **找路由** — 在 `main.py` 找 `@app.get("/health")`；
3. **找 handler** — 对应函数 `health()`；
4. **检查返回值** — 应为 `{"status": "ok"}`；
5. **检查测试断言** — `test_health.py` 中的 `assert` 是否与返回值一致。

F00 不强制配置复杂 IDE Debug；理解上述链路即可定位大部分问题。

---

## 15. 常见问题

### ModuleNotFoundError: No module named 'gov_service_agent'

**可能原因：**
- 未执行 `python -m pip install -e ".[dev]"`
- 当前 Python 环境不是安装时的环境（Conda 未激活或 venv 未激活）

**排查：** `python -c "import gov_service_agent; print(gov_service_agent.__file__)"`

### python --version 不是 3.11

F00 要求 Python 3.11.x（`requires-python = ">=3.11,<3.12"`）。请切换到正确的隔离环境。

### pip 安装到了错误 Python

**推荐：** `python -m pip install ...`  
**避免：** 直接使用 `pip`（可能指向其他 Python）

### 8000 端口占用

换端口启动：`uvicorn ... --port 8001`，或关闭占用 8000 的进程。

### /health 返回 404

- 确认 URL 是 `/health` 而非 `/`；
- 确认 uvicorn 加载的是 `gov_service_agent.main:app`。

### pytest 找不到测试

- 确认在项目根目录执行；
- 确认 `tests/test_health.py` 存在；
- 确认已安装 dev 依赖（含 pytest）。

### Conda 环境未激活

执行 `conda activate govagent`（或你使用的 Python 3.11 环境）后再运行命令。

---

## 16. F00 中哪些是业务逻辑

**F00 几乎没有政务业务逻辑。**

| 文件/内容 | 性质 |
|-----------|------|
| `main.py` | 应用入口（基础设施） |
| `health()` | 技术健康检查（非政务业务） |
| `pyproject.toml` | 工程配置 |
| `tests/` | 测试 |
| `AGENTS.md` / Playbook | 开发治理 |

以下**尚未开始**：

- Business Graph
- Rule Engine
- Semantic Retrieval
- Agent / LangGraph
- DEMO_SS_001 业务数据

---

## 17. 为什么现在不实现更多东西

不是因为不知道后续需要数据库、LLM、Embedding，而是：

> **当前 Feature 不需要，所以不提前创建。**

Architecture Blueprint 是**长期目标地图**，不是工程初始化清单。F00 只建立能跑、能测、能继续开发的最小基线。

---

## 18. F01 会在哪些位置继续扩展

F01 — Runtime Settings + Basic Logging + Environment Foundation 可能在现有工程基础上增加：

- 配置加载（Settings / APP_ENV）
- 基础结构化日志
- 环境变量约定

具体文件和模块将在 F01 Feature 文档中定义。**F00 不提前创建 F01 文件或代码。**

---

## 19. F00 学习检查清单

阅读 F00 后，应能够回答：

1. **pyproject.toml 是干什么的？** — Python 项目标准配置，声明依赖、版本、打包方式。
2. **editable install 是什么？** — `pip install -e` 将源码链接到 site-packages，改代码无需重装。
3. **src layout 为什么存在？** — 隔离源码与项目根，便于 packaging，避免未来迁移。
4. **FastAPI app 是什么？** — Web 应用实例，路由注册到 app 上。
5. **uvicorn 的作用是什么？** — ASGI 服务器，监听 HTTP，把请求交给 FastAPI。
6. **`@app.get("/health")` 是什么？** — 路由装饰器，注册 GET /health 的处理函数。
7. **GET /health 怎么执行到 health()？** — Uvicorn → FastAPI 路径匹配 → 调用 handler。
8. **TestClient 为什么不需要真实启动 uvicorn？** — 进程内直接调用 ASGI app，模拟 HTTP。
9. **pytest 在验证什么？** — 包可 import、/health 返回正确状态码和 JSON。
10. **为什么 F00 不创建数据库/Agent/LLM 代码？** — 渐进式 Feature 开发，F00 范围仅工程基线。

---

## 相关文档

- Feature 文档：`docs/features/F00-project-minimum-initialization.md`
- 开发规则：`AGENTS.md`
- 开发流程：`docs/development-playbook.md`
- 本地运行：`README.md`
