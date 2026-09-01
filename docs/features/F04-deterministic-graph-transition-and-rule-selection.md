# F04 — Deterministic Graph Transition + Rule Selection / Readiness



## Metadata



| 字段 | 内容 |

|------|------|

| Feature ID | F04 |

| Feature Name | Deterministic Graph Transition + Rule Selection / Readiness |

| Current Stage | **Commit — Authorized / In Progress** |

| 前置 Feature | F03 — Business Graph Domain and JSON Repository (`c70071b`) |

| Code Reading Guide | `docs/code-reading/F04-graph-transition-and-rule-selection-reading-guide.md` |

| External Resource Gate | **PASS — 0 resources** |

| Formal Business | `DEMO_SS_001` |

| Demo Graph | `data/graphs/demo/social_security.json` |



## External Resource Gate



| 资源 | 需求 |

|------|------|

| Redis / PostgreSQL / Docker | 否 |

| LLM / Embedding / 公司 API | 否 |

| 新增端口 / 环境变量 | 否 |

| 结论 | **0 外部资源；禁止调用公司模型** |



## Problem



F03 提供了可校验 Decision Graph 与 JsonBusinessRepository，但缺少：



1. 确定性 Graph Transition（标准 slots → 明确状态）

2. Executable Rule Selection / Readiness（筛选 VERIFIED usable executable；不做求值）



## Goals



1. 实现 `step` + `advance_until_blocked`（同一 `TransitionResult`）

2. 实现 `select_executable_rules`（`NO_RULES` / `RULES_AVAILABLE_UNEVALUATED`）

3. 保持 Decision Edge 与 Official Rule 程序级隔离

4. 0 新依赖；不修改 F02/F03 正式数据与 Contract



## Non-goals



Full Rule Expression Evaluator；PASS / FAIL / NEED_MORE_INFO；Rule Facts；LLM；RAG；Redis；PostgreSQL；LangGraph；用户确认 UI；修改正式 `demo_ss_001.json` / Graph JSON。



## Architecture Boundaries



- **Transition**：只读 `DecisionGraph` + `Mapping[str, str]` slots；不调 Repository / Rule Selection / LLM。

- **Rule Selection**：只读 INTERNAL Conditions + executable 层过滤；不 import DecisionGraph / Edge。

- **Rule Engine（本期）** = Selection / Readiness **only**。

- `NO_RULES` ≠ PASS；`RULES_AVAILABLE_UNEVALUATED` ≠ PASS / FAIL。

- Terminal Candidate ≠ confirmed `business_id`；事项确认属上层。



## Files (Code)



| 操作 | 路径 | 用途 |

|------|------|------|

| 新增 | `src/gov_service_agent/business_graph/transition.py` | TransitionStatus / Result / step / advance |

| 新增 | `src/gov_service_agent/business_rules/__init__.py` | 包导出 |

| 新增 | `src/gov_service_agent/business_rules/selection.py` | Rule Selection API |

| 修改 | `src/gov_service_agent/business_graph/__init__.py` | 导出 Transition 公共符号 |

| 新增 | `tests/test_graph_transition.py` | Transition 测试 |

| 新增 | `tests/test_rule_selection.py` | Selection 测试 |

| 新增 | `docs/features/F04-deterministic-graph-transition-and-rule-selection.md` | 本 Feature 文档 |



**未修改：** `pyproject.toml`、`business_data/models.py`、`repository.py`、Graph models/validation/loader、`demo_ss_001.json`、`social_security.json`。



## Key Behaviors



### Transition



- Status：`NEED_SLOT` / `INVALID_SLOT` / `ADVANCED` / `TERMINAL_CANDIDATE` / `UNSUPPORTED` / `FALLBACK`

- Trace invariant：`visited` 非空；`current == visited[-1]`；`len(edges) == len(visited) - 1`

- `NEED_SLOT` / `INVALID_SLOT` **允许**累计历史 `traversed_edge_ids`（advance 后阻塞）

- `advance_until_blocked` 复用 `step`；合并 trace 时追加 `visited[1:]` 避免重复当前节点



### Rule Selection



- Status：仅 `NO_RULES` / `RULES_AVAILABLE_UNEVALUATED`

- Filter：仅 `executable != null` ∧ VERIFIED ∧ usable

- 不要求 Layer1 / Layer2 VERIFIED

- DEMO_SS_001 预期：`NO_RULES`，`selected=[]`，`skipped=7`



## Test Evidence



| 项 | 结果 |

|----|------|

| Python | 3.11.16（govagent） |

| F04 targeted | **36 collected, 36 passed**, 0 failed, 0 skipped |

| Full pytest | **125 collected, 125 passed**, 0 failed, 0 skipped |

| compileall | PASS |

| pip check | PASS |

| warning | 1 个已知 StarletteDeprecationWarning（httpx / starlette.testclient，upstream） |



## Review Findings



| ID | 等级 | 状态 | 说明 |

|----|------|------|------|

| RF-F04-001 | NON-BLOCKING | **CLOSED** | Feature 文档 Test 状态已同步 |

| TG-F04-01 | NON-BLOCKING | **CLOSED** | 部分推进 INVALID_SLOT 历史 trace 专测已补 |

| TG-F04-02 | NON-BLOCKING | **CLOSED** | current UNSUPPORTED / FALLBACK step 专测已补 |

| TG-F04-03 | NON-BLOCKING | **CLOSED** | TransitionResult validator 负向 / mixed-state 专测已补（9 cases） |

| TG-F04-04 | NON-BLOCKING | **CLOSED** | UNSUPPORTED 完整 visited / edge trace 断言已补 |

| RF-F04-002 | INFO | **Deferred** | `transition.py` 部分 Contract 字段使用 `assert`；合法 Graph 路径无影响 |



## Approval Record



| 阶段 | 状态 | 日期 |

|------|------|------|

| Requirement | COMPLETED | 2026-09-01 |

| Requirement Finalization | COMPLETED | 2026-09-01 |

| Technical Design | COMPLETED | 2026-09-01 |

| Confirm | COMPLETED | 2026-09-01 |

| Code | COMPLETED | 2026-09-01 |

| Test | COMPLETED | 2026-09-01 |

| Review | COMPLETED | 2026-09-01 |

| Review Fix | COMPLETED | 2026-09-01 |

| Explanation | COMPLETED | 2026-09-01 |

| Commit | **IN PROGRESS** | |



## Explanation



| 项 | 内容 |

|----|------|

| Code Reading Guide | `docs/code-reading/F04-graph-transition-and-rule-selection-reading-guide.md` |

| 状态 | COMPLETED |



## Notes



- 完整 Rule Evaluator 为后续独立 Feature；启动前置：F02 Executable Contract 可计算扩展 + 业务方 VERIFIED Rule + Rule Facts Contract。


