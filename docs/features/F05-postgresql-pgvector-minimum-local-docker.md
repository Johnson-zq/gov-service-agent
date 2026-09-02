# F05 — PostgreSQL + pgvector Minimum Local Docker

## Metadata

| 字段 | 内容 |
|------|------|
| Feature ID | F05 |
| Feature Name | PostgreSQL + pgvector Minimum Local Docker |
| Current Stage | **Commit — Completed / Awaiting Push Authorization** |
| 前置 Feature | F04 — Deterministic Graph Transition + Rule Selection / Readiness (`72298e3`) |
| External Resource Gate | **READY** |
| Docker Desktop / WSL2 | READY（Resource Gate preflight） |
| localhost:5432 | Available at preflight |

## Stage Status

| 阶段 | 状态 |
|------|------|
| Requirement | Completed |
| Requirement Finalization | Completed |
| Technical Design | Completed |
| Technical Design Finalization | Completed |
| Code | Completed |
| Test | **Completed** |
| Review | **Completed**（PASS WITH DEFERRED MINOR） |
| Explanation | **Completed** |
| Commit | **Completed** |
| Push | NOT STARTED |

## Problem

F00–F04 提供应用与业务决策基础，但缺少可复现的本机 PostgreSQL + pgvector 基础设施，以及 Optional DATABASE_URL、SQLAlchemy / Alembic 地基。

## Goals

1. 本地 Docker Compose：PostgreSQL 16 + `pgvector/pgvector:0.8.6-pg16`
2. Optional `DATABASE_URL`（Local-First；`GET /health` 保持 DB-free）
3. 同步 SQLAlchemy 2.x + psycopg3：lazy Engine / Session factory
4. Alembic 为唯一 schema authority；baseline 仅 `CREATE EXTENSION vector`
5. `check_db()` connectivity 三态：`NOT_CONFIGURED` / `UNAVAILABLE` / `READY`
6. Integration tests：`TEST_DATABASE_URL` + `@pytest.mark.integration` + test DB guard

## Non-goals

业务 table、`vector(N)`、向量 index、Semantic Retrieval、Embedding、HTTP DB readiness endpoint、`main.py` DB 集成、Redis、LLM、Repository / UoW。

## Architecture Boundaries

- Local-First：无 DB / DB down 时应用仍可启动；`/health` 不依赖 DB
- Compose 只启动 `postgres`；无 `container_name`；无 init.sql
- Alembic Only：无 Docker init SQL 双入口
- `check_db` = connectivity only（不查 `pg_extension` / `alembic_version`）
- Integration migration 目标必须精确为 `gov_service_agent_test`
- Alembic Config 非空 `sqlalchemy.url` 优先于 Settings `DATABASE_URL`
- **F02 JSON Business Data 仍是当前 Demo Runtime Business Data Source of Truth**；F05 未将业务数据迁移到 PostgreSQL
- F05 只建立基础设施层：PostgreSQL 16、pgvector extension、SQLAlchemy runtime、DB readiness、Alembic baseline、本地 Docker

## F06 Deferred

Embedding Provider / Model / Dimension、documents / chunks / embeddings、`vector(N)`、HNSW / IVFFlat、similarity search、Semantic Retrieval、LLM、Redis、HTTP DB readiness endpoint。

## Test Evidence

### Runtime / Dependency

| 项 | 值 |
|----|-----|
| Python | 3.11.16（govagent Conda） |
| SQLAlchemy | 2.0.52 |
| Alembic | 1.19.1 |
| psycopg | 3.3.5 |
| Docker | 29.7.2 |
| Docker Compose | v5.5.0 |
| PostgreSQL | 16.15 (Debian 16.15-1.pgdg12+2) |
| pgvector extension | 0.8.6 |
| Image | `pgvector/pgvector:0.8.6-pg16` |
| Dev DB | `gov_service_agent` |
| Test DB | `gov_service_agent_test` |
| Alembic revision | `0001` |
| Dev DB final revision | `0001` |
| Test DB final revision | `0001` |
| Postgres final state | running / healthy（保留 container + pgdata，供 F06） |

### No-Docker

| 项 | 结果 |
|----|------|
| Settings-only | 31 collected / 31 passed / 0 failed / 0 skipped |
| Phase A targeted | 44 collected / 44 passed / 0 failed / 0 skipped |
| No-Docker Full | 153 collected / 152 passed / 0 failed / 1 skipped |
| No-Docker skip 说明 | integration round-trip 因未设置 `TEST_DATABASE_URL` 按设计 skip |
| Phase A compileall | PASS |

### Docker Integration

| 项 | 结果 |
|----|------|
| `docker compose config` | PASS |
| Local image（无持续 Hub / 代理依赖） | PASS |
| `docker compose up` | PASS |
| postgres healthy | YES |
| Alembic dev upgrade | PASS |
| vector extension | PASS（0.8.6） |
| `check_db` READY | PASS → `READY localhost 5432 gov_service_agent` |
| Integration file | 3 collected / 3 passed / 0 failed / 0 skipped |
| Guards | wrong DB / wrong driver 均在 migration 前 FAIL |
| Migration round-trip | PASS；downgrade 后 extension 保留；再 upgrade head |
| Target isolation | Test DB / Dev DB 最终均为 `0001`；Dev DB **未被** integration downgrade |

### Local-First

| 场景 | `check_db` | `/health` |
|------|------------|-----------|
| DB configured + running | READY | PASS |
| DB configured + stopped | UNAVAILABLE | PASS |
| No DATABASE_URL | NOT_CONFIGURED | PASS |

### Final Regression

| 项 | 结果 |
|----|------|
| Final Full pytest | **153 collected / 153 passed / 0 failed / 0 skipped** |
| Warning | 1 known StarletteDeprecationWarning（非 failure） |
| Final compileall | PASS |
| Final pip check | PASS |

## Test Findings

### TF-F05-001 — CLOSED

| 字段 | 内容 |
|------|------|
| Root Cause | Pydantic `ValidationError` 默认字符串可能含 `input_value`，回显 `DATABASE_URL` |
| Fix | `SettingsConfigDict(hide_input_in_errors=True)` |
| Verification | 非法 scheme / malformed URL 仍为 ValidationError；`str(exc)` 不含原始 URL |

### TF-F05-002 — CLOSED

| 字段 | 内容 |
|------|------|
| Root Cause | 首次从 Docker Hub 获取镜像受开发机网络影响 |
| Resolution | 精确镜像 `pgvector/pgvector:0.8.6-pg16` 已入本机 image store；Integration 使用本地镜像完成 |
| Note | 项目运行不依赖持续外部代理 |

### TF-F05-003 — CLOSED

| 字段 | 内容 |
|------|------|
| Root Cause | 程序化 Alembic 调用 `logging.config.fileConfig`（默认 `disable_existing_loggers=True`），污染 pytest 进程中 application logger |
| Fix | `alembic/env.py` 支持 `config.attributes["configure_logger"]`（默认 True）；Integration 显式 `False`；CLI 仍走 fileConfig |
| Verification | Integration 3/3 PASS；关键 reproducer 由 5 passed / 4 failed → **9/9 PASS**；F01 logging 8/8 PASS；Final Full **153/153 PASS** |

## Review Summary

| 项 | 结论 |
|----|------|
| Decision | **PASS WITH DEFERRED MINOR** |
| BLOCKING / MAJOR | 0 / 0 |
| Deferred MINOR | **RF-F05-M01** — module-level Engine cache 无锁（Local Demo 可延后） |
| INFO | **RF-F05-I01** — `check_db` 未强制 `connect_timeout`（非 `/health` / startup） |
| Review Fix | NOT REQUIRED |

## Explanation Coverage

已覆盖：整体架构定位；15 paths；Settings Two-Stage 与三类配置；DATABASE_URL 安全（含 TF-F05-001）；Engine / SessionFactory 生命周期与失效；`check_db` 三态与 Local-First；Compose / volume / pgvector 关系；Alembic URL precedence、Test DB guard、downgrade no-op；TF-F05-001/002/003；Test 分层；F06 handoff；RF-F05-M01 / RF-F05-I01。

## Current Stage

**Commit — Completed / Awaiting Push Authorization**
