# F00 — Project Minimum Initialization

## Metadata

| 字段 | 内容 |
|------|------|
| Feature ID | F00 |
| Feature Name | Project Minimum Initialization |
| Current Stage | Commit — Authorized / In Progress |
| Git 模式 | PRE_REMOTE |
| 前置 Feature | 无 |
| 后续 Feature | F01 — Runtime Settings + Basic Logging + Environment Foundation |
| Code Reading Guide | `docs/code-reading/F00-project-minimum-initialization-reading-guide.md` |

## Problem

项目工作区为空，缺少最小 Python / FastAPI 工程基线，开发人员无法在 Windows 本地安装、启动和测试。

## Goals

1. 建立最小开发规则与文档机制
2. 建立最小 Python / FastAPI 工程运行基线（src layout）
3. 建立最小 Smoke Test 代码
4. 使项目可在 Windows + VS Code/Cursor 环境中开发

## Non-goals

- APP_ENV / Settings / 结构化日志（F01）
- PostgreSQL / pgvector / Redis / Docker / Alembic
- LangGraph / Business Graph / Rule Engine
- LLM / Embedding Provider
- DEMO_SS_001 业务数据
- OCR、预约、导航、语音、AR
- `.vscode/` / `launch.json`

## Technical Design 摘要

- **包布局：** src layout（`src/gov_service_agent/`）
- **依赖：** pyproject.toml + hatchling；`pip install -e ".[dev]"`
- **接口：** `GET /health` → `200` + `{"status":"ok"}`
- **测试：** pytest + TestClient，2 个 Smoke 用例
- **文档：** README.md、AGENTS.md、docs/development-playbook.md
- **禁止：** 使用 `pythonpath=["."]` 掩盖 packaging 问题

## Files Created

| 文件 | 职责 |
|------|------|
| README.md | 项目说明与本地运行指南 |
| pyproject.toml | 依赖与 packaging 配置 |
| .gitignore | Git 忽略规则 |
| AGENTS.md | 核心开发规则 |
| docs/development-playbook.md | 详细 Feature 开发流程 |
| docs/features/F00-project-minimum-initialization.md | 本 Feature 文档 |
| docs/code-reading/F00-project-minimum-initialization-reading-guide.md | F00 代码阅读指南 |
| src/gov_service_agent/__init__.py | 包声明 |
| src/gov_service_agent/main.py | FastAPI 应用与 /health |
| tests/test_health.py | Smoke Test |

## Completion Criteria

- [x] Windows 本地 `pip install -e ".[dev]"` 成功
- [x] `pytest` 全部通过
- [x] uvicorn 启动后可访问 `GET /health`
- [x] 未引入 F00 Non-goals 中的能力
- [x] 未按 Blueprint 预建未来目录

## Test 结果摘要

| 项 | 结果 |
|----|------|
| Python | 3.11.16 |
| Conda environment | govagent |
| pip editable install | PASS |
| pytest | 2 passed, 0 failed, 1 non-blocking warning |
| uvicorn | PASS |
| GET /health | HTTP 200, `{"status":"ok"}` |

## Review Finding 状态

| ID | 等级 | 状态 | 说明 |
|----|------|------|------|
| RF-F00-001 | NON-BLOCKING | **CLOSED** | README Conda / venv 文档不一致 — 已修复并验证 |
| RF-F00-002 | NON-BLOCKING | **CLOSED** | README 本机绝对路径 — 已修复并验证 |
| RF-F00-003 | NON-BLOCKING | **CLOSED** | Feature 文档状态过时 — 已修复并验证 |
| RF-F00-004 | INFO | **Deferred** | Smoke Test 类型断言增强 — 不在 F00 处理 |
| RF-F00-005 | INFO | **Deferred** | StarletteDeprecationWarning — 不在 F00 处理 |
| RF-F00-006 | INFO | **Deferred** | README Local-First 可选补充 — 不在 F00 处理 |
| RF-F00-007 | INFO | **Deferred** | `*.log` ignore 后续处理 — 不在 F00 处理 |

## Approval Record

| 阶段 | 状态 | 日期 |
|------|------|------|
| Requirement | COMPLETED | 2026-08-28 |
| Technical Design | COMPLETED | 2026-08-28 |
| Confirm | COMPLETED | 2026-08-28 |
| Code（Initial） | COMPLETED | 2026-08-28 |
| Test | PASSED | 2026-08-28 |
| Review | PASSED WITH NON-BLOCKING FINDINGS | 2026-08-28 |
| Code（Documentation Fix） | COMPLETED | 2026-08-28 |
| Documentation Verification | PASSED | 2026-08-28 |
| Explanation | COMPLETED | 2026-08-28 |
| Commit | AUTHORIZED | 2026-08-28 |

**Commit Message：** `feat(F00): 初始化最小FastAPI工程`

**Notes：** Commit hash 以 Git 历史和 Commit 完成报告为准。

## 与 F01 边界

| F00 | F01 |
|-----|-----|
| 最小 FastAPI + /health | Settings + APP_ENV |
| 无结构化日志 | 基础日志 |
| 无 .env | 环境配置加载 |
| Smoke Test | 可扩展配置/日志测试 |
