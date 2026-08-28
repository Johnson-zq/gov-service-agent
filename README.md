# gov-service-agent

面向政务预约和到厅办理全过程的智能办事 Agent。

本项目不是普通政务聊天机器人。核心链路为：语义检索找方向 → Business Graph 走路径 → LLM 理解自然语言 → Rule Engine 做终审 → 用户确认得到 `business_id`。

## 当前阶段：F00 工程基线

F00 仅完成最小 Python / FastAPI 工程初始化，使项目可以在 Windows 本地安装、启动和测试。

### F00 已完成

- 最小 FastAPI 应用
- `GET /health` 健康检查接口
- pytest Smoke Test 代码
- 项目开发规则文档（`AGENTS.md`、`docs/development-playbook.md`）
- src layout 包结构

### F00 尚未实现

以下能力将在后续 Feature 中逐步引入，当前均不存在：

- APP_ENV / Settings / 结构化日志（F01）
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

> **说明：** `govagent` 只是当前主开发环境名称，不是程序运行依赖。项目不与 Conda 或特定环境名强绑定；只要 `python --version` 为 Python 3.11.x，即可使用任何标准隔离环境。

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

### 4. 运行 Smoke Test

```powershell
pytest -v
```

期望结果：`2 passed`

### 5. 启动 FastAPI 服务

```powershell
uvicorn gov_service_agent.main:app --host 127.0.0.1 --port 8000
```

### 6. 验证健康检查

浏览器或命令行访问：

```
GET http://127.0.0.1:8000/health
```

期望响应：

```json
{
  "status": "ok"
}
```

## 项目结构（F00）

```
gov-service-agent/
├── README.md
├── pyproject.toml
├── .gitignore
├── AGENTS.md
├── docs/
│   ├── development-playbook.md
│   └── features/
│       └── F00-project-minimum-initialization.md
├── src/
│   └── gov_service_agent/
│       ├── __init__.py
│       └── main.py
└── tests/
    └── test_health.py
```

## 开发规则

- 采用 Feature 驱动的渐进式开发
- 未经确认不得自动进入 Design / Code / Test / Commit 等下一阶段
- 详细流程见 `AGENTS.md` 与 `docs/development-playbook.md`

## Git 状态

当前处于 **PRE_REMOTE** 阶段：仅本地 Git 管理，尚未配置公司远程仓库。

- 允许：本地 `git init`、`git status`、`git diff`、经授权后的本地 commit
- 禁止：push、自行添加 remote、假设公司分支策略

## 下一 Feature

**F01 — Runtime Settings + Basic Logging + Environment Foundation**
