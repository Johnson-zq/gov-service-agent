# F03 — Business Graph Domain and JSON Repository

## Metadata

| 字段 | 内容 |
|------|------|
| Feature ID | F03 |
| Feature Name | Business Graph Domain and JSON Repository |
| Current Stage | **Commit — Authorized / In Progress** |
| 前置 Feature | F02 — DEMO_SS_001 Requirement and Data Contract (`69e5190`) |
| 后续 Feature | F04 — Deterministic Graph Transition + Rule Engine（未启动） |
| Demo Graph | `data/graphs/demo/social_security.json` |
| Formal Business | `DEMO_SS_001` only |
| Code Reading Guide | `docs/code-reading/F03-business-graph-and-json-repository-reading-guide.md` |

## Problem

F02 提供了 Runtime BusinessSnapshot，但缺少：

1. 确定性、可校验的 Business Decision Graph Domain（Node / Edge / Slot / Terminal Candidate）
2. 按 exact `business_id` 查询事实的 JsonBusinessRepository，以及 Public Consumption 与 Knowledge Relation View

## Goals

1. Decision Graph Domain（单 Slot Gate、ENTRY_FORWARD、EQ-only SlotMatch）
2. Graph JSON + Structural Validation（唯一 ENTRY、DAG、allowed_values 全覆盖）
3. Graph + Business Cross Validation（与 Domain 分离）
4. JsonBusinessRepository（`from_paths`、exact query、`ConsumptionMode`）
5. Runtime Knowledge Relation View（非第二事实源）

## Non-goals

Graph Transition / `next_node` / session slots / Rule Engine / LLM / Embedding / RAG / Neo4j / PostgreSQL / Redis / 修改 F02 正式 Business 数据。

## Architecture Decisions（冻结）

| 决策 | 结论 |
|------|------|
| Slot Gate | 一期单 slot：`slot_name` + `allowed_values` + `question_text` |
| ENTRY 边 | `EdgeKind.ENTRY_FORWARD`（无 match；ENTRY 有且仅有 1 条） |
| SlotMatch | 仅 `EQ` |
| allowed_values | 必须与 outgoing SLOT_MATCH value 集合严格相等 |
| ENTRY | 整图恰好 1 个；`entry_node_id` 指向它；无 incoming |
| design_basis | `SYSTEM_DESIGNED` / `SOURCE_SUPPORTED` / `TEST_ONLY` |
| SourceConditionRef | `business_id` + `condition_id`（≠ Rule） |
| Loader | `load_decision_graph(path)` 只做结构校验；交叉校验显式调用 |
| Repository | 直接 `JsonBusinessRepository.from_paths`；无 ABC |
| Public | `ConsumptionMode.PUBLIC` 默认；allowlist + fail-closed |
| Knowledge | Runtime `BusinessRelation` 投影；无持久化 relation JSON |

## Files (Code)

| 操作 | 路径 | 用途 |
|------|------|------|
| 新增 | `src/gov_service_agent/business_graph/__init__.py` | 包导出 |
| 新增 | `src/gov_service_agent/business_graph/models.py` | Decision Graph Domain Models |
| 新增 | `src/gov_service_agent/business_graph/validation.py` | Structural + Cross Validation |
| 新增 | `src/gov_service_agent/business_graph/loader.py` | Graph JSON loader |
| 新增 | `src/gov_service_agent/business_data/repository.py` | Repository + Public filter + Relations |
| 新增 | `data/graphs/demo/social_security.json` | Demo Decision Graph（7 nodes / 11 edges） |
| 新增 | `tests/test_business_graph.py` | Graph / Contract / Cross Validation 测试 |
| 新增 | `tests/test_business_repository.py` | Repository 测试 |
| 新增 | `docs/features/F03-business-graph-domain-and-json-repository.md` | 本 Feature 文档 |
| 新增 | `docs/code-reading/F03-business-graph-and-json-repository-reading-guide.md` | Code Reading Guide |

**未修改：** `data/demo/demo_ss_001.json`、`business_data/models.py`、`pyproject.toml`、`business_data/__init__.py`

## Demo Graph Summary

- Nodes (7): ENTRY → `service_action` → `payment_actor` → `employment_type` → TERMINAL(`DEMO_SS_001`)；transfer → UNSUPPORTED；inquiry/other/employer/other → FALLBACK
- Edges (11): 1× ENTRY_FORWARD + 10× SLOT_MATCH (EQ)
- Unique formal terminal: `DEMO_SS_001`
- No `DEMO_SS_002`, no 政务服务中心, no `confirmed_business_id`

## Test Evidence（Review Fix 后）

| 项 | 结果 |
|----|------|
| Python | 3.11.16（govagent） |
| F03 targeted | **45 passed**, 0 failed, 0 skipped |
| Full pytest | **89 passed**, 0 failed, 0 skipped |
| compileall | PASS |
| pip check | PASS |
| warning | 1 个已知 StarletteDeprecationWarning（httpx / starlette.testclient，upstream） |

## Review Findings

| ID | 等级 | 状态 | 说明 |
|----|------|------|------|
| RF-F03-001 | NON-BLOCKING | **CLOSED** | ENTRY_FORWARD from 非 ENTRY 专测已补 |
| RF-F03-002 | NON-BLOCKING | **CLOSED** | SLOT_MATCH from 非 SLOT_GATE 专测已补 |
| RF-F03-003 | NON-BLOCKING | **CLOSED** | SOURCE_SUPPORTED null/empty refs 专测已补 |
| RF-F03-004 | NON-BLOCKING | **CLOSED** | SlotMatch 非 EQ 专测已补 |
| RF-F03-005 | NON-BLOCKING | **CLOSED** | Feature 文档阶段与 Test Evidence 已同步 |
| RF-F03-006 | NON-BLOCKING | **CLOSED** | INACTIVE terminal Cross Validation 专测已补 |
| RF-F03-007 | INFO | **Deferred** | SYSTEM_DERIVED lineage 要求 SOURCE_EXPLICIT 基底；未来 VERIFIED+SYSTEM_DERIVED 组合再定 |
| RF-F03-008 | INFO | **Deferred** | `get_snapshot` 返回共享可变 Snapshot；一期受控消费可接受 |
| RF-F03-009 | INFO | **Deferred** | BusinessRelation RelationType/TargetType 配对 validator；当前仅 Repository 内部生成 |

## Approval Record

| 阶段 | 状态 | 日期 |
|------|------|------|
| Requirement | COMPLETED | 2026-08-31 |
| Requirement Finalization | COMPLETED | 2026-08-31 |
| Technical Design | COMPLETED | 2026-08-31 |
| Confirm | COMPLETED | 2026-08-31 |
| Code | COMPLETED | 2026-08-31 |
| Test | COMPLETED | 2026-08-31 |
| Review | COMPLETED | 2026-08-31 |
| Review Fix | COMPLETED | 2026-08-31 |
| Explanation | COMPLETED | 2026-08-31 |
| Commit | IN PROGRESS | 2026-08-31 |

## Explanation

| 项 | 内容 |
|----|------|
| Code Reading Guide | `docs/code-reading/F03-business-graph-and-json-repository-reading-guide.md` |
| 状态 | COMPLETED |

## Notes

- Decision Edge ≠ Official Eligibility Rule；SOURCE_SUPPORTED 仅设计依据
- Terminal Candidate ≠ confirmed `business_id`
- PUBLIC conditions 设计预期：3（applicant SOURCE_EXPLICIT）；INTERNAL：7
- F04 负责 `next_node` / Rule Engine；F06 负责 Semantic Retrieval
