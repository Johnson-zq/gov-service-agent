# F01 — Runtime Settings + Basic Logging + Environment Foundation

## Metadata

| 字段 | 内容 |
|------|------|
| Feature ID | F01 |
| Feature Name | Runtime Settings + Basic Logging + Environment Foundation |
| Current Stage | Commit — Authorized / In Progress |
| Git 模式 | PRE_REMOTE |
| 前置 Feature | F00 — Project Minimum Initialization (`8c1217b`) |
| 后续 Feature | F02 — DEMO_SS_001 Requirement and Data Contract |
| Code Reading Guide | `docs/code-reading/F01-runtime-settings-logging-environment-reading-guide.md` |

## Problem

同一份应用代码需要在不同运行环境中安全、明确、可观察地启动；F00 尚未提供统一 Settings、环境语义与基础日志。

## Goals

- 最小 Settings：`APP_ENV`、`LOG_LEVEL`
- `.env.example` + fail-fast 配置加载
- 标准库 logging（`gov_service_agent` / `gov_service_agent.access`）
- 纯 ASGI middleware：`request_id`、Access Log、`X-Request-ID`
- 保持 `GET /health` → `{"status":"ok"}`
- 无 DB / Redis / LLM / Embedding 时仍可本地运行

## Non-goals

PostgreSQL、Redis、Docker、Alembic、LangGraph、Business Graph、Rule Engine、LLM、Embedding、JSON Logging、OpenTelemetry、全局异常 Handler、lifespan。

## Technical Design 摘要

- `pydantic-settings` + `get_settings()`（`lru_cache`）
- 项目 `.env` 未知键 fail-fast（`StrictDotEnvSettingsSource`）
- 进程无关环境变量不绑定、不报错
- 纯 ASGI `RequestContextMiddleware`（非 BaseHTTPMiddleware）
- 服务端始终生成 UUID4；忽略客户端 `X-Request-ID`
- 初始化日志：`application_initialized`
- runtime 直接依赖：`python-dotenv>=0.21`（供 `dotenv_values` / StrictDotEnv）

## Open Questions

| ID | 状态 |
|----|------|
| OQ-F01-01～10 | **全部 RESOLVED** |

## Completion Criteria

- [x] 统一 Settings：仅 `APP_ENV`、`LOG_LEVEL`
- [x] `APP_ENV`：LOCAL / DEV / TEST / DEMO；默认 LOCAL；非法 fail-fast
- [x] `LOG_LEVEL`：DEBUG～CRITICAL；默认 INFO；非法 fail-fast
- [x] `.env.example` 仅含上述两变量；真实 `.env` 仍 ignore
- [x] 项目 `.env` 未知键 fail-fast；进程无关变量不报错
- [x] Basic Logging：timestamp / level / logger / message；key-value 控制台
- [x] `setup_logging` 幂等（自动化回归已覆盖）
- [x] request_id（服务端 UUID）+ 响应头 `X-Request-ID`
- [x] Access Log：request_id / method / path / status_code / duration_ms
- [x] Secret 安全边界：不记录 body / query / Authorization / Cookie / Token 等
- [x] `GET /health` 仍为 `200` + `{"status":"ok"}`（F00 regression）
- [x] Local-First：无 DB / Redis / LLM / Embedding / Docker 可本地运行
- [x] Automated tests：Settings / logging / request_id / F00 Smoke（29 passed）
- [x] Explanation（Code Reading Guide）— 已完成
- [ ] Commit — 未开始

## Test 结果摘要（Initial）

| 项 | 结果 |
|----|------|
| Python | 3.11.16 |
| pytest | 28 passed, 0 failed, 0 skipped, 1 non-blocking warning |
| Uvicorn Smoke | PASS |
| GET /health | HTTP 200, `{"status":"ok"}` |

## Review Fix Test 结果摘要

| 项 | 结果 |
|----|------|
| Python | 3.11.16 |
| pytest | 29 passed, 0 failed, 0 skipped, 1 non-blocking warning |
| pip check | No broken requirements found |
| gov-service-agent Requires | fastapi, pydantic-settings, python-dotenv, uvicorn |
| 新增用例 | `test_setup_logging_is_idempotent` PASSED |

## Review Finding 最终状态

| ID | 状态 | 说明 |
|----|------|------|
| RF-F01-001 | **CLOSED** | `pyproject.toml` 已声明 `python-dotenv>=0.21`；editable metadata `Requires` 含 `python-dotenv`；`Required-by: gov-service-agent`；`pip check` 通过。经 Review Fix Test 验证关闭。 |
| RF-F01-002 | **CLOSED** | 新增 `test_setup_logging_is_idempotent`：`setup_logging×3` → owned Handler==1、access handlers==0、单次日志 emit 1 次；29 passed。Logging 幂等已升级为正式 regression。 |
| RF-F01-003 | **CLOSED** | Feature 文档阶段与 Finding 状态已在本轮 Review Closure 同步。 |
| RF-F01-004 | **INFO / Deferred** | X-Request-ID append 去重；F01 不处理 |
| RF-F01-005 | **INFO / Deferred** | StarletteDeprecationWarning（NON-BLOCKING upstream）；不升级依赖 |
| RF-F01-006 | **INFO / No Action Required** | StrictDotEnvSettingsSource 必要（说明性） |

## Warning

| Warning | 状态 |
|---------|------|
| StarletteDeprecationWarning（httpx / TestClient） | NON-BLOCKING upstream warning（RF-F01-005） |

## Approval Record

| 阶段 | 状态 | 日期 |
|------|------|------|
| Requirement | COMPLETED | 2026-08-29 |
| Technical Design | COMPLETED | 2026-08-29 |
| Confirm | COMPLETED | 2026-08-29 |
| Code（Initial） | COMPLETED | 2026-08-29 |
| Test（Initial） | PASSED | 2026-08-29 |
| Review | PASS WITH NON-BLOCKING FINDINGS | 2026-08-29 |
| Code（Review Fix） | COMPLETED | 2026-08-29 |
| Review Fix Test | PASSED | 2026-08-29 |
| Review Closure | COMPLETED | 2026-08-29 |
| Explanation | COMPLETED | 2026-08-29 |
| Commit | AUTHORIZED / IN PROGRESS | 2026-08-29 |

**Commit Message：** `feat(F01): 增加运行时配置与基础请求日志`

**Notes：** Commit hash 以 Git 历史和 Commit 完成报告为准。

## Files (Code)

| 操作 | 路径 |
|------|------|
| 新增 | `.env.example` |
| 新增 | `docs/features/F01-runtime-settings-logging-environment.md` |
| 新增 | `src/gov_service_agent/settings.py` |
| 新增 | `src/gov_service_agent/logging_config.py` |
| 新增 | `src/gov_service_agent/middleware/__init__.py` |
| 新增 | `src/gov_service_agent/middleware/request_context.py` |
| 新增 | `tests/test_settings.py` |
| 新增 | `tests/test_logging_and_request_id.py` |
| 修改 | `src/gov_service_agent/main.py` |
| 修改 | `pyproject.toml` |
| 修改 | `README.md` |

## Review Fix Files

| 操作 | 路径 | 用途 |
|------|------|------|
| 修改 | `pyproject.toml` | RF-F01-001：声明 `python-dotenv` |
| 修改 | `tests/test_logging_and_request_id.py` | RF-F01-002：幂等 regression |
| 修改 | `docs/features/F01-runtime-settings-logging-environment.md` | RF-F01-003 / Review Closure / Explanation 状态 |

## Explanation

| 项 | 内容 |
|----|------|
| Code Reading Guide | `docs/code-reading/F01-runtime-settings-logging-environment-reading-guide.md` |
| 状态 | COMPLETED |
