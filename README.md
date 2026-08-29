# gov-service-agent

面向政务预约和到厅办理全过程的智能办事 Agent。

本项目不是普通政务聊天机器人。核心链路为：语义检索找方向 → Business Graph 走路径 → LLM 理解自然语言 → Rule Engine 做终审 → 用户确认得到 `business_id`。

## 当前阶段：F01 运行时基础

F00 已完成最小 FastAPI 工程基线。F01 在其上增加：Runtime Settings、基础日志、`request_id` / Access Log。

### 已完成

- 最小 FastAPI 应用与 `GET /health`
- pytest Smoke Test
- **Settings：`APP_ENV`、`LOG_LEVEL`（pydantic-settings）**
- **`.env.example`（可提交）与 `.env`（本地私有，已 ignore）**
- **基础控制台日志（`gov_service_agent` / `gov_service_agent.access`）**
- **HTTP `X-Request-ID` 与 Access Log**

### 尚未实现

- PostgreSQL / pgvector / Redis / Docker
- LangGraph / Agent Core
- Business Graph / Rule Engine
- Semantic Retrieval / Embedding
- LLM Provider / LLM Router
- DEMO_SS_001 业务数据
- OCR、预约、导航、语音、AR 等

## 环境要求

- Windows 10/11
- Python **3.11.x**（须处于隔离环境中）
- VS Code 或 Cursor（可选）

> **说明：** `govagent` 只是当前主开发环境名称，不是程序运行依赖。项目不与 Conda 或特定环境名强绑定。

## 运行配置（F01）

| 变量 | 含义 | 示例 |
|------|------|------|
| `APP_ENV` | 运行环境**语义**（不决定服务器/IP/数据库位置） | `LOCAL` / `DEV` / `TEST` / `DEMO` |
| `LOG_LEVEL` | 日志级别 | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |

默认：`APP_ENV=LOCAL`，`LOG_LEVEL=INFO`。

可参考仓库中的 `.env.example`：

```env
APP_ENV=LOCAL
LOG_LEVEL=INFO
```

复制为本地 `.env`（**不要提交** `.env`）。非法值或 `.env` 中未知键会导致启动 **fail-fast**。

**Local-First：** 无 PostgreSQL / Redis / LLM / Embedding / Docker 时，应用仍应能本地启动并通过 `/health`。

## 快速开始

在项目根目录执行以下命令。

### 1. 环境检查

```powershell
python --version
```

确认输出为 Python 3.11.x。

### 2. 激活 Python 3.11 隔离环境

**推荐（当前主开发环境）：**

```powershell
conda activate govagent
```

**亦可使用标准虚拟环境：**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. 安装项目及开发依赖

```powershell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### 4. 运行测试

```powershell
pytest -v
```

### 5. 启动 FastAPI 服务

```powershell
uvicorn gov_service_agent.main:app --host 127.0.0.1 --port 8000
```

### 6. 验证健康检查

```
GET http://127.0.0.1:8000/health
```

期望：

```json
{
  "status": "ok"
}
```

响应头包含服务端生成的：

```text
X-Request-ID: <uuid>
```

（客户端传入的 `X-Request-ID` 不会被复用。）

控制台可见 key-value 风格日志，例如：

```text
message=application_initialized app_env=LOCAL log_level=INFO
```

以及 Access Log：`request_id` / `method` / `path` / `status_code` / `duration_ms`（`path` 不含 query string）。

## 项目结构（F01）

```
gov-service-agent/
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── AGENTS.md
├── docs/
│   ├── development-playbook.md
│   └── features/
│       ├── F00-project-minimum-initialization.md
│       └── F01-runtime-settings-logging-environment.md
├── src/
│   └── gov_service_agent/
│       ├── __init__.py
│       ├── main.py
│       ├── settings.py
│       ├── logging_config.py
│       └── middleware/
│           ├── __init__.py
│           └── request_context.py
└── tests/
    ├── test_health.py
    ├── test_settings.py
    └── test_logging_and_request_id.py
```

## 开发规则

- 采用 Feature 驱动的渐进式开发
- 未经确认不得自动进入 Design / Code / Test / Commit 等下一阶段
- 详细流程见 `AGENTS.md` 与 `docs/development-playbook.md`

## Git 状态

当前处于 **PRE_REMOTE** 阶段：仅本地 Git 管理，尚未配置公司远程仓库。

## 下一 Feature

**F02 — DEMO_SS_001 Requirement and Data Contract**
