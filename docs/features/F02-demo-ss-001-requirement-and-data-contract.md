# F02 — DEMO_SS_001 Requirement and Data Contract

## Metadata

| 字段 | 内容 |
|------|------|
| Feature ID | F02 |
| Feature Name | DEMO_SS_001 Requirement and Data Contract |
| Current Stage | **Commit — Authorized / In Progress** |
| 前置 Feature | F01 — Runtime Settings + Basic Logging (`abdf6ac`) |
| 后续 Feature | F03 — Business Graph Domain and JSON Repository（未启动） |
| 正式业务 | `DEMO_SS_001` — 灵活就业人员社会保险费申报缴费 |
| Code Reading Guide | `docs/code-reading/F02-demo-ss-001-business-data-contract-reading-guide.md` |

## Problem

项目缺少可追溯、可验证、可版本管理的 Business Data Source of Truth。Graph / Rule Engine / API 需要结构化事实，但不能把办事指南外推测写成 VERIFIED Rule，也不能让 LLM 决定材料、地点、渠道或规则。

## Goals

1. 定义 Pydantic v2 Business Data Contract
2. 建立 Provenance（EvidenceRef）与 Verification Status 模型
3. 结构化 `DEMO_SS_001` JSON Snapshot
4. 确定性结构校验 + 单元测试
5. 记录跨 Feature Open Items

## Non-goals

Semantic Retrieval、Embedding、LLM Provider、Decision/Knowledge Graph 代码、Rule Engine、Repository、PostgreSQL / Neo4j / Milvus / Redis、OCR、预约、Navigation、企业微信、720yun、FAQ 模型、Rule DSL。

## Requirement Finalization（已确认）

- Authoritative Evidence Source ≠ Runtime Source of Truth（结构化 Business Data）
- 冲突时以 Evidence 为准修正 Business Data；Graph 为可重建投影
- Raw Fact（SOURCE_EXPLICIT）与 Normalized Value（SYSTEM_DERIVED）分离
- Condition 三层：Source Description → Normalized → Executable Rule
- TO_CONFIRM 可存内部数据，**不得**作为面向群众的确定性办理事实
- 群众默认仅消费：SOURCE_EXPLICIT、可追溯 SYSTEM_DERIVED、VERIFIED
- public filtering 留给 F03 Repository

## Technical Design 摘要

- **Schema：** Pydantic v2（唯一代码级 Contract）
- **顶层对象：** `BusinessSnapshot`（平铺关联数组）
- **版本：** `schema_version`（Contract 格式）+ `data_version`（业务内容）
- **溯源：** `EvidenceRef(source_id, source_section, source_excerpt)`
- **依赖：** 显式 `pydantic>=2,<3`
- **数据文件：** `data/demo/demo_ss_001.json`
- **不实现：** Repository、`VerificationStatus.is_public_consumable()`
- **Contract 严格性：** 内部 `ContractModel(extra="forbid")`；Snapshot 内同类 ID 唯一

## Design Corrections（Code 前已应用）

| ID | 修正 |
|----|------|
| DC-1 | `snapshot_version` → `schema_version` |
| DC-2 | 删除 `VerificationStatus.is_public_consumable()` |
| DC-3 | `SourceRef` → `EvidenceRef`（事实级章节/摘录） |
| DC-4 | Business Metadata 增加 `metadata_source_status` |
| DC-5 | `source_file` 忠实记录 `.doc` 文件名 |
| DC-6 | `updated_at` / `ingested_at` 不在 load 时刷新 |

## Files (Code)

| 操作 | 路径 | 用途 |
|------|------|------|
| 新增 | `src/gov_service_agent/business_data/__init__.py` | 包导出 |
| 新增 | `src/gov_service_agent/business_data/models.py` | Enum + Pydantic Models + 校验 + load |
| 新增 | `data/demo/demo_ss_001.json` | DEMO_SS_001 Runtime Snapshot |
| 新增 | `tests/test_business_data_contract.py` | Contract / 验收测试 |
| 修改 | `pyproject.toml` | 显式 `pydantic>=2,<3` |
| 新增 | `docs/features/F02-demo-ss-001-requirement-and-data-contract.md` | 本 Feature 文档 |
| 新增 | `docs/project/open-items.md` | 跨 Feature Open Items |

## Test Evidence

| 项 | 结果 |
|----|------|
| Python | 3.11.16（govagent） |
| F02 targeted（Initial Test） | 12 passed |
| F02 targeted（Review Fix） | **15 passed** |
| Full pytest（Initial Test） | 41 passed, 0 failed, 0 skipped |
| Full pytest（Review Fix） | **44 passed**, 0 failed, 0 skipped |
| compileall | PASS |
| pip check | PASS |
| warning | 1 个已知 StarletteDeprecationWarning（httpx / starlette.testclient） |

## Review Findings

| ID | 等级 | 状态 | 说明 |
|----|------|------|------|
| RF-F02-001 | NON-BLOCKING | **CLOSED** | `extra="forbid"` via 内部 `ContractModel` |
| RF-F02-002 | NON-BLOCKING | **CLOSED** | Snapshot 同类 ID 唯一性 fail-fast |
| RF-F02-003 | NON-BLOCKING | **CLOSED** | Feature 文档阶段与 Test Evidence 已同步 |
| RF-F02-004 | INFO | **CLOSED** | 非 VERIFIED executable 负向测试已补 |
| RF-F02-005 | INFO | **Deferred** | `Material.condition_ref` 引用完整性；CONDITIONAL Material 进入时再处理 |
| RF-F02-006 | INFO | **Deferred** | open-items 负责人列 |
| RF-F02-007 | INFO | **Accepted / No Action** | `updated_at` 整点精度可接受 |

## Completion Criteria

- [x] Requirement 完成并经 Finalization 确认
- [x] Technical Design 完成并经 Confirm
- [x] Code：Contract Models + DEMO JSON + 测试代码 + Open Items
- [x] Test：targeted + full regression PASS
- [x] Review：PASS WITH NON-BLOCKING FINDINGS
- [x] Review Fix：RF-F02-001 / 002 / 003 / 004
- [x] Explanation：Code Reading Guide
- [ ] Commit — 未开始

## Explanation

| 项 | 内容 |
|----|------|
| Code Reading Guide | `docs/code-reading/F02-demo-ss-001-business-data-contract-reading-guide.md` |
| 状态 | COMPLETED |

## Approval Record

| 阶段 | 状态 | 日期 |
|------|------|------|
| Requirement | COMPLETED | 2026-08-31 |
| Requirement Finalization | COMPLETED | 2026-08-31 |
| Technical Design | COMPLETED | 2026-08-31 |
| Design Corrections | APPLIED | 2026-08-31 |
| Confirm | COMPLETED | 2026-08-31 |
| Code | COMPLETED | 2026-08-31 |
| Test | COMPLETED | 2026-08-31 |
| Review | COMPLETED | 2026-08-31 |
| Review Fix | COMPLETED | 2026-08-31 |
| Explanation | COMPLETED | 2026-08-31 |
| Commit | AUTHORIZED / IN PROGRESS | 2026-08-31 |

## Git Gate（Code 前）

| 项 | 结果 |
|----|------|
| branch | `develop` |
| working tree | clean（进入 Code 前） |
| `git fetch origin` | PASS |
| local HEAD | `abdf6aca00d4cea7cfce0400279399cf7b231607` |
| origin/develop | identical（ahead 0 / behind 0） |

## Notes

- DEMO_SS_001 Executable Rule 数 = 0
- DEMO_SS_001 VERIFIED Rule 数 = 0
- 不得写入未确认的政务服务中心地点
- 原始办事指南 `.doc` 不进入源码仓库
- `ContractModel` 为内部基类，不作为业务模型导出
