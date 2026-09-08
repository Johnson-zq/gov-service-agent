# F08 — Agent State + LangGraph Orchestration Foundation

## 1. Feature Status

| 字段 | 内容 |
|------|------|
| Feature ID | F08 |
| Feature Name | Agent State + LangGraph Orchestration Foundation |
| Current Stage | **Commit — INCLUDED IN F08 FEATURE COMMIT（Awaiting Push Authorization）** |
| 前置 Feature | F07 — LLM Abstraction + Demo Provider + Real Company Provider + Data Policy（**CLOSED** @ `3b6872657fc4c6a74f74a1432fa2818707476a89`） |
| Git Baseline | `develop` @ `3b6872657fc4c6a74f74a1432fa2818707476a89` |
| External Resource Gate | **CLOSED** |
| F08 Scope | **A**（Agent State + LangGraph orchestration foundation；**不是**完整 E2E Agent） |
| Requirement Document | `docs/features/F08-agent-state-langgraph.md` |
| Code-Reading Document | `docs/code-reading/F08-agent-state-langgraph-code-reading.md` |

### Stage Status

| 阶段 | 状态 |
|------|------|
| Resource Gate | **CLOSED** |
| Requirement | **CLOSED** |
| Requirement Finalization | **NOT REQUIRED** |
| Technical Design | **FINAL / CLOSED** |
| Technical Design Finalization | **PASS**（TD-F08-01 / 02 / 03） |
| Confirm | **DONE**（Owner 授权 Code） |
| Code | **COMPLETE** |
| Test | **PASS** |
| Review | **PASS** |
| Review Fix | **NOT REQUIRED** |
| Explanation | **COMPLETE** |
| Code-Reading | **COMPLETE** |
| Commit | **INCLUDED IN F08 FEATURE COMMIT** |
| Push | **NOT STARTED** |

**本阶段范围：** Commit — 仅 Feature Doc 状态收尾 + 精确 stage 9 paths + 唯一 Feature Commit；**禁止 Push**。

**明确禁止自动进入：** Push。

F08 Feature Doc 与 Code-Reading 文档随 F08 Feature Commit 一并提交；为避免文档自引用提交哈希，Commit SHA 以 Git 历史及 Owner Commit Report 为准。

**一句话定位：** F08 建立「Agent 单次工作流的 typed runtime state，以及基于 LangGraph 的最小本地编排骨架」——解决一次 invocation 如何保存运行上下文、如何经预定义节点与边传播 State。**不**解决用户最终应办理哪个事项。

### Final Feature Scope（9 paths）

| # | Path | 操作 |
|---|------|------|
| 1 | `src/gov_service_agent/agent/__init__.py` | NEW |
| 2 | `src/gov_service_agent/agent/state.py` | NEW |
| 3 | `src/gov_service_agent/agent/nodes.py` | NEW |
| 4 | `src/gov_service_agent/agent/workflow.py` | NEW |
| 5 | `pyproject.toml` | MODIFY |
| 6 | `tests/test_agent_state.py` | NEW |
| 7 | `tests/test_agent_workflow.py` | NEW |
| 8 | `docs/features/F08-agent-state-langgraph.md` | MODIFY |
| 9 | `docs/code-reading/F08-agent-state-langgraph-code-reading.md` | NEW |

**Breakdown：** Production NEW=4；Production MODIFY=1；Test NEW=2；Feature Doc=1；Code-Reading=1；**Total=9**。第 10 path：**禁止**。

### Code Implementation Evidence

| 项 | 结果 |
|----|------|
| Production NEW | **4** |
| Production MODIFY | **1**（`langgraph>=1.2.11,<1.3`） |
| Configured dependency | `langgraph>=1.2.11,<1.3` |
| Verified installed | **1.2.11** |
| Python | govagent / **3.11.x** |
| LangGraph import | **PASS** |
| Public API import | **PASS** |
| LangChain direct dependency | **NO**（可不写「无任何 transitive」；仅声明不直接依赖完整 LangChain） |
| Workflow topology | `START → prepare → complete → END` |

### Test Evidence

| 项 | 结果 |
|----|------|
| F08 Targeted | **73 collected / 73 passed / 0 failed** |
| Full Regression | **392 passed / 0 failed / 13 skipped / 0 warnings** |
| Real LLM | **NOT RUN**（opt-in smoke 默认 SKIP） |
| Company Network | **0** |
| compileall / pip check / `git diff --check` | **PASS** |
| Serialization `allow_nan=False` | **PASS** |
| Secret / Business Boundary / Routing / Checkpoint Gates | **PASS** |
| Design Deviations | **NONE** |
| Production Test Fix | **0** |

### Review Evidence

| 项 | 结果 |
|----|------|
| Review | **PASS** |
| BLOCKING / MAJOR / MINOR | **0 / 0 / 0** |
| INFO | **3**（RF-F08-001 / 002 / 003） |
| Review Fix | **NOT REQUIRED** |

### Review Findings

| ID | Severity | 内容 | Explanation 处理 |
|----|----------|------|------------------|
| **RF-F08-001** | INFO | Feature Doc 曾残留「LangGraph CURRENTLY NOT INSTALLED」 | **已刷新**：当前 Verified installed = **1.2.11**；历史 Resource Gate 快照单独标注 |
| **RF-F08-002** | INFO | F07 Feature Doc 可能仍显示 AWAITING COMMIT；F07 实际 CLOSED | **保留 INFO**；本 Feature **不修改 F07** |
| **RF-F08-003** | INFO | `artifacts` 可存任意 JSON string；F08 不是 DLP | **已记录** future integration boundary；当前无 secret-producing code |

---

## 1b. Architecture Position（Explanation）

项目原则（口号级）：

> 语义检索找方向，业务图谱定事项，规则引擎做终审，知识图谱查办理信息，Agent 统一编排。

**F08 对应「Agent 统一编排」的 foundation 部分。** 其它子系统能力**未**在本 Feature 实现。

| Graph | 职责 |
|-------|------|
| **LangGraph Agent Graph** | Agent orchestration；节点顺序；State 传播；workflow lifecycle |
| **Business Decision Graph（F03/F04）** | `current_node` + validated slots + predefined edges → **deterministic** `next_node` |

**LangGraph END ≠ Business `TERMINAL_CANDIDATE`。** END 只表示本次 Agent orchestration 结束，不表示事项已确认、规则已通过、`business_id` 已确定。

**AgentState** = 单次 invocation 的 typed **runtime context**；**不是** Business Data Source of Truth。

**真实实现拓扑：**

```text
START → prepare → complete → END
```

仅 2 个 orchestration nodes；无 conditional edge / loop / LLM routing / F04 / F06 / F07 runtime 调用。

---

## 1c. Implementation Summary（真实代码）

| 模块 | 职责 |
|------|------|
| `state.py` | TypedDict `AgentState`（7 字段）；`AgentPhase` / `WorkflowStatus` / `WorkflowError`；严格 JSON-safe；lifecycle；`validate_agent_state`；`create_initial_state`（deepcopy）；`AgentStateValidationError` |
| `nodes.py` | `_prepare_node` / `_complete_node`（私有）；入口 validate；返回 partial update + trace delta |
| `workflow.py` | `build_agent_workflow`（construct+compile）；`run_agent_workflow`（validate → deepcopy → invoke → validate）；无 checkpointer |
| `__init__.py` | 最小 Public API；不 export nodes |

**Lifecycle（仅四组合合法）：** RECEIVED+RUNNING+None；ORCHESTRATING+RUNNING+None；COMPLETED+COMPLETED+None；FAILED+FAILED+WorkflowError。

**Ownership：** `create_initial_state` 与 `run_agent_workflow` 均对 caller 数据做防御性 `deepcopy`。

**Trace：** `Annotated[list[str], operator.add]`；节点只返回 delta；期望最终 `["prepare","complete"]`。与 F04 `visited_node_ids` / `traversed_edge_ids` 概念分离。

**Failure：** contract 错误 → `AgentStateValidationError`（不 dump state）；unexpected → 自然向上传播；无 broad `except Exception`。

### Final F08 Planned Paths（9）

| # | Path | 操作 | 阶段 |
|---|------|------|------|
| 1 | `src/gov_service_agent/agent/__init__.py` | NEW | Code |
| 2 | `src/gov_service_agent/agent/state.py` | NEW | Code |
| 3 | `src/gov_service_agent/agent/nodes.py` | NEW | Code |
| 4 | `src/gov_service_agent/agent/workflow.py` | NEW | Code |
| 5 | `pyproject.toml` | MODIFY | Code |
| 6 | `tests/test_agent_state.py` | NEW | Test |
| 7 | `tests/test_agent_workflow.py` | NEW | Test |
| 8 | `docs/features/F08-agent-state-langgraph.md` | MODIFY | Req / TD / … |
| 9 | `docs/code-reading/F08-agent-state-langgraph-code-reading.md` | NEW | Explanation |

**Path Breakdown：** Production NEW = 4；Production MODIFY = 1；Test NEW = 2；Test MODIFY = 0；Feature Doc = 1；Code-Reading = 1；**Total = 9**。

**第 10 Path Rule：** 任何阶段若需第 10 个 path → **DESIGN DEVIATION / STOP**。不得自行新增 `errors.py` / `types.py` / `service.py` / `context.py` / 额外 tests。

**Core Python Count：** `state.py` + `nodes.py` + `workflow.py` = **3**（不计 `__init__.py`）。

---

## 2. One-Sentence Positioning

F08 解决：

> **Agent 如何保存一次工作流中的运行状态，以及如何通过 LangGraph 按预定义编排顺序驱动各能力模块。**

F08 **不**解决：

> **用户最终应该办理哪个事项。**

事项路径与候选仍由 **Business Decision Graph** 确定性决定；用户最终确认与 `business_id` 写入属于后续 Feature（F10）。

---

## 3. Background and Goals

F00–F07 已提供：最小 FastAPI 与 Settings/Logging、DEMO 业务数据契约、Business Decision Graph、确定性 Transition / Rule Selection、PostgreSQL+pgvector、Embedding + Semantic Retrieval、LLM Provider Abstraction + Demo/Real Provider + Data Policy。

尚缺：**Agent 编排层**——在不夺取 Business Decision Graph / Rule Engine / 用户确认决定权的前提下，建立一次工作流的运行状态契约与 LangGraph 基础编排能力。

Canonical Flow（F08 仅负责加粗段中的 **Agent Orchestration Foundation**，不负责完整链路业务语义）：

```
用户自然语言
→ Agent Orchestration（State + LangGraph）     ← F08 foundation
→ NLU / Slot Mapping（F07 capability；F09 业务集成）
→ Semantic Retrieval（F06 capability；编排调用属后续）
→ Business Decision Graph（F04 deterministic）
→ Missing slots / questions（F09）
→ Terminal Candidate Validation / 用户确认（F10）
→ Session / Redis / Checkpoint / Audit（F11）
→ E2E Demo（F12）
```

### Goals

1. **Agent State Contract**：定义一次 Agent Workflow 执行期间的 typed 运行状态契约。
2. **LangGraph 基础编排能力**：可 build / compile / invoke 的最小 Agent Workflow Skeleton。
3. **确定性 State Propagation**：节点按预定义边传播状态；固定输入下可重复。
4. **Node Input / Output Contract**：节点接收 State，返回明确 State Update（或 LangGraph 等价 delta）。
5. **Failure / Validation Boundary**：非法 State 受控失败，不得伪装成功。
6. **稳定编排基础**：为 F09 / F10 / F11 / F12 提供可扩展、可序列化友好的 orchestration foundation。

---

## 4. Resource Gate Conclusion

F08 Resource Gate：**CLOSED**。

| 项 | 冻结结论 |
|----|----------|
| F08 Scope | **A** |
| Git Baseline | `develop` @ `3b68726…`；local/origin/github 一致 |
| Conda env | `govagent` |
| Python | **3.11.x**（Resource Gate 实测 **3.11.16**） |
| F07 Provider Public API | **READY** |
| F07 Demo Provider | **READY** |
| LangGraph | **Resource Gate 时：** NOT INSTALLED（计划 Code 安装）。**当前：** Verified installed **1.2.11**（`langgraph>=1.2.11,<1.3`） |
| LangChain | **NOT REQUIRED**（非 direct dependency） |
| Redis / PostgreSQL / Embedding / ASR / Real LLM（普通测试） | **NOT REQUIRED** |
| BLOCKING / Owner Input（Resource Gate） | **0 / 0** |

**INFO-F08-01：** F07 Feature 文档可能仍显示 AWAITING COMMIT；F07 已 CLOSED。本 Feature 不修改、不重开 F07。

---

## 5. Scope

### 5.1 Scope Freeze

**F08 Scope = A** — Agent State + LangGraph orchestration foundation；**不是**完整 E2E Agent。

### 5.2 In Scope（必须）

见 Requirement CLOSED 正文与下方 Technical Design。摘要：Typed Agent State；2-node skeleton；build/compile/invoke；确定性传播；受控失败；`langgraph` Code 阶段引入；无 HTTP/Redis/DB/Embedding runtime。

### 5.3 Out of Scope

见 §14 Non-Goals。特别：本 Feature **不真实调用** F04 / F06 / F07；**0 LLM calls**；不实现 F09–F12。

---

## 6. Dual-Graph Architecture Boundary（最高优先级）

| Graph | 职责 |
|-------|------|
| **LangGraph Agent Graph** | Agent orchestration；节点顺序；状态传播；工作流生命周期 |
| **Business Decision Graph** | `current_node` + validated slots + predefined edges → **deterministic** `next_node` |

- 两者**绝不能合并**；LangGraph **不替代** F03/F04 Business Decision Graph。
- LangGraph **不计算**业务 `next_node`；**禁止** LLM output → goto business node / 动态建边。
- **LangGraph END ≠ Business `TERMINAL_CANDIDATE`**。
- Agent `orchestration_trace` ≠ F04 `visited_node_ids` / `traversed_edge_ids`。

---

## 7. LLM / Data Policy / Adjacent Feature Boundaries

- LLM 权限继承 F07；F08 **不扩大**。
- `USER_FREE_TEXT` Remote = **DENY**；F08 **不修改**。State 含 `input_text` ≠ 允许 Remote dispatch。
- F08 skeleton：**0 LLM calls**；不 import F07/F06/F04 runtime。
- F09–F12 边界见 Requirement；本 Design 不吞并。

---

## 8–12. Requirement Summary（CLOSED）

Requirement 已 CLOSED。要点保留：

- Agent State = workflow runtime context；非 Business SoT。
- 禁止 module-level mutable workflow state。
- 普通测试：0 Real LLM / Redis / PostgreSQL / Embedding load。
- State serialization-friendly；依赖不入 State。
- Acceptance Criteria：**AC-F08-01 … AC-F08-50**（见 §13）。

---

## 13. Acceptance Criteria

| ID | 准则 |
|----|------|
| **AC-F08-01** | 存在 typed Agent State Contract |
| **AC-F08-02** | Agent State 只表示 workflow runtime context |
| **AC-F08-03** | Agent State 不是 Business Data Source of Truth |
| **AC-F08-04** | Agent State 不保存 secret |
| **AC-F08-05** | Agent State 不保存 raw reasoning |
| **AC-F08-06** | 不存在 module-level mutable current workflow state |
| **AC-F08-07** | 存在 LangGraph Agent workflow |
| **AC-F08-08** | workflow 可 build |
| **AC-F08-09** | workflow 可 compile |
| **AC-F08-10** | workflow 可 invoke |
| **AC-F08-11** | 普通 invoke 可使用 deterministic Demo/Fake dependencies |
| **AC-F08-12** | 普通 tests 0 Real Company LLM network |
| **AC-F08-13** | 普通 tests 0 Redis |
| **AC-F08-14** | 普通 tests 0 PostgreSQL |
| **AC-F08-15** | 普通 tests 0 Embedding model load |
| **AC-F08-16** | LangGraph 只负责编排 |
| **AC-F08-17** | Business Decision Graph 继续确定性决定业务 `next_node` |
| **AC-F08-18** | LLM 不决定业务 `next_node` |
| **AC-F08-19** | LLM 不决定 `business_id` |
| **AC-F08-20** | LLM 不决定 Rule result |
| **AC-F08-21** | LangGraph edge 由代码预定义 |
| **AC-F08-22** | LLM 不动态创建 LangGraph edge |
| **AC-F08-23** | 若存在 conditional routing，条件必须来自受控 deterministic state |
| **AC-F08-24** | workflow node 使用 typed state |
| **AC-F08-25** | node 输出以明确 state update 传播 |
| **AC-F08-26** | 非法 State 受控失败 |
| **AC-F08-27** | Node Failure 不得伪装成功 |
| **AC-F08-28** | Provider Failure 不得伪装成无候选 / 低 confidence / missing slot |
| **AC-F08-29** | LangGraph END 明确不等于 Business `TERMINAL_CANDIDATE` |
| **AC-F08-30** | F08 不实现 F09 slot Q&A |
| **AC-F08-31** | F08 不实现 F10 final business confirmation |
| **AC-F08-32** | F08 不实现 F11 Redis / checkpoint / session / audit |
| **AC-F08-33** | F08 不实现 F12 E2E Demo |
| **AC-F08-34** | F08 不新增 public HTTP endpoint |
| **AC-F08-35** | F08 不新增 port |
| **AC-F08-36** | F08 不新增 DB migration |
| **AC-F08-37** | F08 不新增 Redis dependency |
| **AC-F08-38** | F08 不要求 LangChain |
| **AC-F08-39** | F08 不要求 LangSmith |
| **AC-F08-40** | F08 不要求 LangGraph Cloud |
| **AC-F08-41** | F08 不要求 Tool Calling |
| **AC-F08-42** | F08 不要求 Streaming |
| **AC-F08-43** | F08 不修改 F07 `USER_FREE_TEXT` Remote DENY policy |
| **AC-F08-44** | workflow construction 不要求 Real LLM config |
| **AC-F08-45** | workflow compile 不触发网络 |
| **AC-F08-46** | workflow dependencies 与 workflow state 分离 |
| **AC-F08-47** | Provider / HTTP Client / DB Session 不存入 State |
| **AC-F08-48** | State 设计保持 future persistence / serialization friendly |
| **AC-F08-49** | F08 production 无具体政务事项 hardcode |
| **AC-F08-50** | 固定输入 + deterministic dependency 得到可重复 workflow result |

**Acceptance Criteria 数量：50**

---

## 14. Non-Goals

Full E2E Agent；Real User LLM NLU；`USER_FREE_TEXT` Remote Allow；Missing Slot / Question / Answer Mapping；allowed_values / confidence 业务逻辑；Final Candidate / `business_id` Confirmation；Rule Evaluation 重实现；Knowledge Graph facts；Redis；Checkpoint；Session API；Audit Persistence；PostgreSQL migration；Embedding retrieval runtime；ASR；HTTP Agent API；New Port；Streaming；Tool Calling；LangSmith；LangGraph Cloud；Async+Sync 双实现；Conversation Memory；Production load test；强制真实集成 F04/F06/F07；预实现 F09/F10 业务 schema；conditional edges（本 skeleton）；Checkpointer / InMemorySaver / thread_id / RunnableConfig；LangChain Message types。

---

## 15. Design Open Items — CLOSED（D01–D11）

| ID | 冻结决策 | 状态 |
|----|----------|------|
| **D01** | TypedDict + explicit `validate_agent_state`；不用 Pydantic 作 LangGraph canonical state | **CLOSED** |
| **D02** | 恰好 7 字段：`request_id`, `input_text`, `phase`, `status`, `artifacts`, `error`, `orchestration_trace` | **CLOSED** |
| **D03** | 恰好 2 nodes：`prepare` → `complete` | **CLOSED** |
| **D04** | `agent/{__init__,state,nodes,workflow}.py`（4 Production NEW） | **CLOSED** |
| **D05** | **SYNC ONLY** | **CLOSED** |
| **D06** | `langgraph>=1.2.11,<1.3` | **CLOSED** |
| **D07** | 当前无 DI 容器 / 无外部 runtime dependency；未来 node factory / builder 注入；对象永不进 State | **CLOSED** |
| **D08** | 非法 State → `AgentStateValidationError`；unexpected 向上传播；不 broad-catch Exception | **CLOSED** |
| **D09** | `AgentPhase` / `WorkflowStatus` StrEnum 冻结；不复用 F04 `TransitionStatus` | **CLOSED** |
| **D10** | JSON-safe State + validator；`json.dumps` 可序列化（无 custom encoder / StrEnum 作 str） | **CLOSED** |
| **D11** | **YES** — lightweight `orchestration_trace` + `Annotated[list[str], operator.add]` | **CLOSED** |

---

## 16. Requirement Blocker Assessment

**Requirement Blocker 数量：0**；**Requirement Finalization：NOT REQUIRED**。

---

## 17. Completion Criteria（Commit）

1. Feature Doc Commit 状态已收尾（无自引用 SHA）
2. 精确 stage 并提交 9 个 F08 paths
3. Parent = F07 final commit
4. Working tree clean
5. Push：**等待 Owner 单独授权**（Commit ≠ CLOSED）

---

## 18. Approval Record

| 项 | 状态 |
|----|------|
| Resource Gate | **CLOSED** |
| Requirement | **CLOSED** |
| Technical Design | **FINAL / CLOSED** |
| Code | **COMPLETE** |
| Test | **PASS** |
| Review | **PASS**（BLOCKING/MAJOR/MINOR=0；INFO=3） |
| Review Fix | **NOT REQUIRED** |
| Explanation | **COMPLETE** |
| Code-Reading | **COMPLETE** |
| Commit | **INCLUDED IN F08 FEATURE COMMIT** |
| Push | **NOT STARTED** |

---

## 19. Document Maintenance Notes

| ID | 类型 | 说明 |
|----|------|------|
| INFO-F08-01 / RF-F08-002 | Cross-Feature Docs | F07 Feature 文档可能仍显示 AWAITING COMMIT；F07 已 CLOSED。**不在本 Feature 修改 F07。** |
| INFO-F08-02 / RF-F08-001 | Resource status refresh | Resource Gate 时 LangGraph 未安装；Code 已安装并验证 **1.2.11**。当前状态以 Code/Test Evidence 为准。 |
| RF-F08-003 | Future integration | `artifacts` 是 JSON-safe runtime map，**不是 DLP**。调用方不得写入 secret / Authorization / raw reasoning / raw provider body。F09+ 接入 subsystem 时须继续 enforce（含 F07 Data Policy：`USER_FREE_TEXT` Remote DENY）。 |

---

# Technical Design — FINAL / CLOSED

## TD-0. Technical Design Finalization Record

| ID | 主题 | 状态 |
|----|------|------|
| **TD-F08-01** | Phase / Status / Error Lifecycle Invariant | **CLOSED** |
| **TD-F08-02** | Strict JSON-safe Finite Float Semantics | **CLOSED** |
| **TD-F08-03** | Initial Artifacts Ownership / Defensive Copy | **CLOSED** |

本 Finalization **不**重新打开 D01–D11；**不**改变 State 类型、字段数、节点数、Graph topology、文件布局、dependency version、failure architecture。

---

## TD-1. Architecture Hard Invariants（不变）

1. LangGraph = Agent orchestration graph；Business Decision Graph = business decision graph；**不是同一图**。
2. 业务 `next_node` 仍由：current Business Graph node + validated slots + predefined Business Graph edges → deterministic。
3. **禁止** LLM routing：LLM output → LangGraph goto business node；LLM 返回 `next_node` 被 conditional edge 采用；模型创建 edge。
4. F08 **不真实集成** F04 / F06 / F07；仅保留未来 integration boundary。
5. F08 Workflow：**0 LLM calls**；Unit Test 不依赖 Demo Provider 亦可完全 deterministic。
6. Demo Provider 保持 future injectable；当前 skeleton 不插入无业务意义的 LLM node。

---

## TD-2. D01 — Agent State Type

### Decision

**Canonical LangGraph shared state = `TypedDict`（`AgentState`）。**

**不**使用 Pydantic `BaseModel` 作为 LangGraph canonical state。

### Rationale

1. TypedDict 是 LangGraph Graph API 主流 / 直接 state schema。
2. 节点天然：`State → Partial State Update`。
3. 轻量、serialization-friendly。
4. 避免仅依赖「首节点输入」运行时验证，却无法自动保证每个后续 node update 的完整 contract。

### Why not Pydantic StateGraph

Pydantic 可作为 LangGraph state schema，但当前 LangGraph 运行时 validation 主要发生在 graph **首节点输入**，**不能替代** F08 对最终 state 与跨节点结果的显式 contract validation。

选择 TypedDict **不是**因为 Pydantic 不支持 LangGraph，而是为了：**TypedDict + explicit validator** 成为单一验证策略。

### No Dual Modeling

**禁止**同时维护 Public Pydantic `AgentState` + TypedDict `AgentState`（双 Source of Truth）。

Canonical contract：**仅** `TypedDict AgentState`。
Validation：普通 Python 显式函数 `validate_agent_state(...)`。

---

## TD-3. Runtime Validation Strategy

| 组件 | 职责 |
|------|------|
| `AgentState` (TypedDict) | 静态类型契约 |
| `validate_agent_state(...)` | 显式 runtime validation；**Fail Closed** |
| `create_initial_state(...)` | 工厂；必须经 validation（或同等检查）后返回 |
| Node entry | 每个 public node 入口显式 `validate_agent_state(state)` |
| `run_agent_workflow(...)` | invoke **前** validate initial；invoke **后** validate final |

**不得**：依赖 TypedDict 自身做 runtime validation；依赖裸 `assert`；假定 LangGraph 自动验证所有 node output。

**不**创建独立 LangGraph validation node（会污染 `orchestration_trace`、增加无意义节点）。Validation 是 State Contract 边界，不是业务 orchestration step。

---

## TD-4. D02 — State Minimal Fields（恰好 7）

### Pseudo Schema（非 Production Code）

```text
AgentState:
    request_id: str
    input_text: str
    phase: AgentPhase
    status: WorkflowStatus
    artifacts: dict[str, JsonValue]
    error: WorkflowError | None
    orchestration_trace: Annotated[list[str], operator.add]
```

**核心字段数 = 7。不得超过。**

### Field Semantics

| Field | Type | Semantics / Validation |
|-------|------|------------------------|
| `request_id` | `str` | 单次 workflow invocation 请求级标识；**不是** `session_id`（F11）。调用方提供；F08 **不强制**自动生成 UUID。strip 后 non-empty；最大 **128** 字符。 |
| `input_text` | `str` | 本地 workflow 输入文本；仅 in-memory 传播；**不** Remote dispatch、**不**自动 logging、**不**持久化。必须 `str`；strip 后非空。Tests 仅 synthetic。**存在于 State ≠ 允许发给 Company Provider**（F07 DENY 仍生效）。 |
| `phase` | `AgentPhase` (StrEnum) | 当前编排阶段；**禁止**塞入 Business Graph node id。 |
| `status` | `WorkflowStatus` (StrEnum) | 整个 workflow 生命周期状态。 |
| `artifacts` | `dict[str, JsonValue]` | 受控临时中间结果；**不是** Business SoT。 |
| `error` | `WorkflowError \| None` | 安全错误结构；见 TD-5。 |
| `orchestration_trace` | `list[str]` + add reducer | LangGraph orchestration node names only。 |

### phase vs status

- **phase**：编排所处阶段（如 `ORCHESTRATING`）。
- **status**：workflow 生命周期（如 `RUNNING`）。
- 正常进行中示例：`phase=ORCHESTRATING` + `status=RUNNING`。

### AgentPhase（StrEnum）

| Member | Value |
|--------|-------|
| `RECEIVED` | `received` |
| `ORCHESTRATING` | `orchestrating` |
| `COMPLETED` | `completed` |
| `FAILED` | `failed` |

### WorkflowStatus（StrEnum）

| Member | Value |
|--------|-------|
| `RUNNING` | `running` |
| `COMPLETED` | `completed` |
| `FAILED` | `failed` |

**禁止**加入：`NEED_SLOT` / `TERMINAL_CANDIDATE` / `UNSUPPORTED` / `FALLBACK`（属 Business/F09）。

**禁止**继承 / 复用 / alias F04 `TransitionStatus`。

---

## TD-5. artifacts / error / JSON-safe / Trace

### JsonValue（语义；recursive TypeAlias 实现属 Code）— TD-F08-02

最终冻结：

```text
JsonValue :=
    None
  | str
  | bool
  | int
  | finite float          # math.isfinite(value) is True
  | list[JsonValue]
  | dict[str, JsonValue]  # keys MUST be str
```

**Finite float（严格）：**

- 允许：finite `float`（`math.isfinite(value) == True`）
- **reject：** `NaN`、`+Infinity`、`-Infinity`
- 原因：默认 `json.dumps(float("nan"))` 可能产出非严格 JSON 的 `NaN`；F08 State 必须 serialization-friendly → **fail closed**

**bool / int：** Python `bool` 是 `int` subclass。Validator 实现须稳定允许 `True`/`False` 与普通 `int`；检查顺序属 Code Stage，行为必须稳定。

**禁止：** `tuple`；`set`；`bytes`；`bytearray`；`Path`；`datetime`（除非未来显式序列化）；artifacts 中任意 Enum object（正式 state enum field 上的 StrEnum 除外）；Provider；HTTP Client；DB Session；Repository；`Exception`；`SecretStr`；arbitrary class / `object()`。

**Artifacts 中 Enum：** 为保持 contract 简单，artifacts 内 arbitrary Enum **reject**。未来若需存储，先转为稳定 string value；**不**依赖 custom JSON encoder。

### artifacts 边界

- 仅 workflow temporary result；**不是** Business SoT。
- 正式业务事实仍调用对应 subsystem（未来）。
- **`artifacts` 不是任意 secret bag。** 调用方 contract：不得写入 credential / authorization / API key / raw reasoning / raw provider body。
- F08 当前无外部 capability node → Production 无 secret source；未来 F09+ 由对应 integration design 继续 enforce。
- 这是 **contract boundary**，**不是** F08 DLP。**不**增加 api_key regex / password scanner / credential detector。

### WorkflowError

TypedDict（或等价 JSON-friendly structure），**仅**：

| Field | Type |
|-------|------|
| `code` | `str`（当前最小码集见下） |
| `message` | `str`（安全） |

**禁止：** traceback；Exception object；raw provider body；reasoning；secret。

### WorkflowErrorCode（最小）

当前仅需：

- `INVALID_STATE`

不提前创建 20 个 error codes；F09/F10 可扩展。

### Phase / Status / Error Lifecycle Invariant（TD-F08-01）

仅下列 **4** 种组合合法；其余全部 = `INVALID_STATE`（reject）：

| # | phase | status | error |
|---|-------|--------|-------|
| 1 | `RECEIVED` | `RUNNING` | `None` |
| 2 | `ORCHESTRATING` | `RUNNING` | `None` |
| 3 | `COMPLETED` | `COMPLETED` | `None` |
| 4 | `FAILED` | `FAILED` | `WorkflowError`（非 `None`） |

仍保留并蕴含于上表：

- `status == FAILED` → `error != None`
- `status != FAILED` → `error == None`

**非法组合示例（必须 reject）：**

- `phase=COMPLETED` + `status=RUNNING`
- `phase=RECEIVED` + `status=COMPLETED`
- `phase=FAILED` + `status=RUNNING`
- `phase=ORCHESTRATING` + `status=FAILED`
- `phase=FAILED` + `status=FAILED` + `error=None`
- `phase=COMPLETED` + `status=COMPLETED` + `error!=None`

`validate_agent_state` **必须**检查 phase/status/error **三者一致性**，不得只检查 Enum 是否合法。

**Skeleton 映射：**

| 时刻 | 合法组合 |
|------|----------|
| `create_initial_state` | RECEIVED + RUNNING + error=None |
| `prepare` 之后 | ORCHESTRATING + RUNNING + error=None |
| `complete` 之后 | COMPLETED + COMPLETED + error=None |
| Future FAILED（无 failure node） | FAILED + FAILED + error!=None |

不为了测试 FAILED 新增 node。

### orchestration_trace（D11 = YES）

- 类型：`list[str]`
- 语义：仅记录 LangGraph orchestration **node name**
- **不是** Business Graph `visited_node_ids`
- Reducer：`Annotated[list[str], operator.add]`
- 每个 Node **只返回本节点 delta**（如 `["prepare"]`）；**禁止**每次返回完整 trace（会重复累加）
- F08 仅 2 nodes → **无需** trace max-length setting

---

## TD-6. Initial State Factory（含 TD-F08-03 Ownership）

`create_initial_state(request_id, input_text, *, artifacts=None) -> AgentState`

| 字段 | 默认 |
|------|------|
| `phase` | `RECEIVED` |
| `status` | `RUNNING` |
| `artifacts` | 见 ownership |
| `error` | `None` |
| `orchestration_trace` | `[]`（fresh list） |

必须调用 `validate_agent_state`（或同等 validation）；**不得**返回非法初始 state。固定产生合法组合 #1。

### Artifacts Ownership / Defensive Copy（TD-F08-03）

1. **`artifacts=None`：** 每次创建 **新的** `{}`；禁止 mutable default `artifacts={}`。
2. **调用方传入 artifacts：** 先 validate JSON-safe，再 **`copy.deepcopy`** 写入 State。State 拥有独立 runtime data snapshot。
3. **禁止共享** caller 可变 artifacts 对象引用。示例：caller 在 create 后 `caller_artifacts["x"]["items"].append(3)` **不得**改变 `state["artifacts"]`。
4. **`create_initial_state` 返回 F08-owned fresh state tree**；至少 artifacts / trace 不得共享 caller mutable reference。当前 `error=None`，无 caller-provided WorkflowError copy 问题；不扩大 API。
5. **Nodes（prepare/complete）不更新 artifacts** → Node **不需要** deepcopy artifacts；只需不 direct mutation。LangGraph 对未更新 field 保持现有 state。
6. **`run_agent_workflow` 不得原地修改** 调用方传入 AgentState。Test：保存调用前 copy → run → 确认 caller-owned initial dict 未被 F08 原地修改（LangGraph 内部 merged state 按其语义；目标是 public API 不要求 caller state 承担隐藏 mutation）。

---

## TD-7. validate_agent_state — Fail Closed

至少检查：

1. required fields complete
2. **no extra fields**（unknown key reject；含 `api_key` / `authorization` / `reasoning` / `provider` 等 top-level）
3. `request_id` valid（non-empty strip；≤128）
4. `input_text` valid（non-empty strip）
5. `phase` / `status` valid Enum
6. **phase/status/error lifecycle invariant（TD-F08-01）**
7. `artifacts` 为 dict；keys 为 str；值符合 **strict JsonValue**（含 finite float；TD-F08-02）
8. `error` 结构合法（若存在）
9. `orchestration_trace` 为 `list[str]`；entries non-empty

**Unknown keys reject** 防止 `reasoning` / `api_key` / `provider` / `business_id` 等无意进入基础 State。

**不**做 regex secret 扫描 / DLP（schema 无 credential 字段；unknown key 已 reject；artifacts 靠调用方 contract）。

State **不存在** `reasoning` / `reasoning_content` / `thinking` / `reasoning_present`（F08 不调用 LLM）。

---

## TD-8. D03 — Minimal Nodes（恰好 2）

| Node | 职责 | Update |
|------|------|--------|
| **prepare** | 接收合法 State；进入编排 | `phase=ORCHESTRATING`；`status=RUNNING`；`error=None`；`orchestration_trace+=["prepare"]` |
| **complete** | 结束编排 | `phase=COMPLETED`；`status=COMPLETED`；`error=None`；`orchestration_trace+=["complete"]` |

**不增加：** llm / retrieval / business_graph / rule / knowledge / question / confirmation。

**禁止：** 调用网络、LLM、DB、Redis、Business Graph；生成 `business_id` / candidate / answer。

### Node Contract

- Sync、pure/deterministic Python functions
- Input：完整 merged `AgentState`
- Output：**Partial** AgentState Update
- **禁止**直接 mutation input state；**禁止** module global mutation
- 入口：显式 `validate_agent_state(state)`（优先节点内调用；不建 validation node）

Nodes **不是** Public API（可为 `_prepare_node` / `_complete_node`；仅 `workflow.py` 使用）。

---

## TD-9. D08 — Failure Semantics

| 情况 | 行为 |
|------|------|
| Illegal Agent State | raise **`AgentStateValidationError`**（受控；位于 **`state.py`**） |
| Unexpected programming failure | **原样向上传播**（或由 LangGraph 自然传播） |
| Broad `except Exception` → FAILED state | **禁止**（避免 Bug 伪装为正常 workflow failure） |

`AgentStateValidationError`：仅 safe code/message；**不得** dump 完整 state / `input_text` / secret / artifacts。

**不新增** `errors.py`。

正常 skeleton 路径：`RUNNING → COMPLETED`。State 仍保留 `FAILED` + `error` 作为未来扩展能力；**无需**人为制造 FAILED node。

`AgentStateValidationError` ≠ Provider Failure ≠ Business Graph UNSUPPORTED ≠ No Candidate ≠ Missing Slot。F08 **不统一**这些领域错误。

---

## TD-10. Public Workflow API

### `build_agent_workflow()`

1. `StateGraph(AgentState)`
2. `add_node`（prepare / complete）
3. `add_edge`（预定义拓扑）
4. `compile()` — **不传** checkpointer；**不**使用 InMemorySaver
5. 返回 compiled graph
6. **不** invoke；**不** network；**不** Settings；**不** Real LLM config

Public import（1.2.x 稳定 API）：

```text
from langgraph.graph import START, END, StateGraph
```

不要 internal / private import（如 `_Pregel`）。返回类型用稳定 public/protocol 或轻量 annotation。

### `run_agent_workflow(state) -> AgentState`

1. validate initial state
2. `graph.invoke(...)`（sync）
3. validate final state
4. 返回 canonical AgentState
5. **不**捕获所有 Exception
6. **不**原地修改调用方传入的 AgentState（TD-F08-03）

### Graph Topology（严格冻结）

```text
START → prepare → complete → END
```

- **无** conditional edge
- **无** loop
- **无** dynamic routing

**为何无 conditional edge：** 当前 skeleton 无真实 orchestration branch；不为展示强行加分支。未来 F09/F10 可基于受控 deterministic state 增加。

**LangGraph END** = 本次 Agent workflow invocation 结束；**≠** Business `TERMINAL_CANDIDATE`。

### Deterministic Expected Result

固定合法 initial state → 最终：

| Field | Expected |
|-------|----------|
| `phase` | `COMPLETED` |
| `status` | `COMPLETED` |
| `orchestration_trace` | `["prepare", "complete"]` |
| `error` | `None` |
| `request_id` / `input_text` / `artifacts` | 保持不变（除非明确 node update；本 skeleton 不改） |

---

## TD-11. D05 — Sync / Async

**SYNC ONLY。**

原因：F04 / F05–F06 services / F07 Provider 当前以同步路径为主。F08 **不**同时设计 `ainvoke` / async nodes。未来有明确需要再扩。

Streaming / Tool Calling / LangSmith / LangGraph Cloud：**NOT REQUIRED**。

---

## TD-12. D04 — Module Layout & Dependency Graph

### Production NEW（4）

| File | 职责 |
|------|------|
| `agent/state.py` | `AgentState`；Enums；`WorkflowError`；JSON-safe contract；validator；factory；`AgentStateValidationError` |
| `agent/nodes.py` | `_prepare_node` / `_complete_node` only |
| `agent/workflow.py` | `build_agent_workflow` / `run_agent_workflow`；LangGraph imports |
| `agent/__init__.py` | Public exports only |

**不新增：** `errors.py` / `types.py` / `service.py` / `runtime.py` / `context.py` / `config.py`。

### Public Exports（`__init__.py`）

- `AgentState`
- `AgentPhase`
- `WorkflowStatus`
- `WorkflowError`
- `AgentStateValidationError`
- `create_initial_state`
- `validate_agent_state`
- `build_agent_workflow`
- `run_agent_workflow`

**不 export：** prepare/complete nodes；private validators；internal constants。

### Module Dependency Direction

```text
state.py
    ↑
nodes.py
    ↑
workflow.py
    ↑
agent/__init__.py
```

- `nodes.py` imports `state`
- `workflow.py` imports `state` + `nodes`
- `__init__.py` imports public state/workflow
- **禁止** `state.py` 反向 import `workflow`
- **禁止** import F04 / F06 / F07 / SQLAlchemy / Redis / Embedding / Business repository

### Why No F07 Import

F08 只需 orchestration foundation。Import 却不使用的 `LlmProvider` 只会制造 coupling。真实 LLM Node 由 F09+ 经 DI 接入。

### No Business Hardcode

Production 禁止：`DEMO_SS_001` / `payment_mode` / `self_payment` / `employment_type` / social_security 业务 ID 等。

### Logging

不新增专属 logger。Skeleton nodes **无需**日志；避免记录 `input_text`。

### No Port / HTTP / Settings / .env / main.py

不修改 `settings.py`、`.env.example`、`main.py`；无新端口；无 public HTTP endpoint。

---

## TD-13. D06 — LangGraph Dependency

| 项 | 冻结 |
|----|------|
| Version range | **`langgraph>=1.2.11,<1.3`** |
| Pin `==1.2.11` | **NO**（允许 1.2.x bugfix；对齐项目 bounded ranges） |
| Python | 项目 `>=3.11,<3.12`；Code 必须用 **govagent / 3.11.x**（禁止 base 3.12） |
| LangChain direct | **NO**（即使 transitive 存在，也不写成 direct dependency） |
| LangSmith | **NO** |
| LangGraph Cloud | **NO** |

### Code-Stage Resource Action（本阶段不执行）

1. 确认 Python = govagent / 3.11.x
2. 修改 `pyproject.toml` 加入 `langgraph>=1.2.11,<1.3`
3. `pip install -e ".[dev]"`
4. 验证：installed version；`import langgraph`；`pip check`

**不要**只 `pip install langgraph` 而忘记 pyproject。

本 TD Draft 阶段：**禁止**安装与修改 pyproject。

---

## TD-14. D07 — Dependency Injection

### Current

F08 Skeleton **无**外部 runtime capability dependency。

- **不**创建空 `AgentDependencies`
- **不**提前塞 `LlmProvider`
- **不**创建 DependencyContainer / ServiceRegistry / RuntimeContext / IoC
- **不**使用 LangGraph runtime context（即使新版支持；未来再评估）

### Future Strategy（记录；不实现）

当 F09/F10 节点需要 `LlmProvider` / BusinessGraphController / RetrievalService 等：

- 通过 **node factory / closure** 或 **workflow builder 显式参数**注入
- 这些对象 **永远不进** `AgentState`

---

## TD-15. D10 — Serialization Friendly（含 TD-F08-02）

- AgentState 在 F08 范围内须可通过严格 JSON 序列化（无 custom encoder；或 StrEnum 自然视为 str）。
- Test Stage：**`json.dumps(final_state, allow_nan=False)` PASS**（普通 `json.dumps` 可能接受 NaN；`allow_nan=False` 才证明 strict JSON-safe）。
- artifacts：finite float PASS；NaN / +Inf / -Inf reject；`object()` / Provider / `set` / `bytes` / tuple / arbitrary Enum reject。
- 无 `api_key` / `authorization` / `database_url` / `secret` / `credentials` / `raw_response` / reasoning fields。

### Persistence Semantics

- In-memory = **单次 invoke 内** state propagation
- **不是** Conversation Memory
- **不是** LangGraph Checkpointer / InMemorySaver
- **无** `thread_id` / RunnableConfig public contract

---

## TD-16. Test Design

### Test NEW（2）

| Path | 覆盖要点 |
|------|----------|
| `tests/test_agent_state.py` | Enums；`create_initial_state` / defaults；valid validation；missing/extra fields；blank `request_id`/`input_text`；invalid phase/status；**phase/status/error 合法组合 PASS + 代表性非法组合 reject（TD-F08-01）**；artifacts JSON-safe；**finite float PASS；NaN/+Inf/-Inf reject（TD-F08-02）**；error/status invariant；trace validation；**`json.dumps(..., allow_nan=False)`**；extra keys `api_key`/`reasoning` reject；`object()` reject；**caller nested artifacts mutation 不影响 created state；default `{}` 各 invocation 独立（TD-F08-03）** |
| `tests/test_agent_workflow.py` | build/compile；run valid；final phase/status；trace exact `["prepare","complete"]`；artifacts/`request_id`/`input_text` preserved；repeat determinism（不复用可能被 mutate 的同一 dict）；invalid initial controlled failure；no module global leak；node 不直接 mutate input state；顺序经 trace 证明；**workflow run 不原地修改 caller initial state（TD-F08-03）** |

### Finalization Incremental Cases（A–J）

| ID | Case |
|----|------|
| A | phase/status/error 合法组合 PASS |
| B | 代表性非法组合 reject |
| C | finite float PASS |
| D | NaN reject |
| E | +Infinity reject |
| F | -Infinity reject |
| G | `json.dumps(state, allow_nan=False)` PASS |
| H | caller artifacts nested mutation 不改变 created state artifacts |
| I | default artifacts 不同 invocation 对象独立 |
| J | workflow run 不原地修改 caller initial state |

### Explicitly NOT

- `tests/integration/test_agent_real.py`
- `RUN_LLM_REAL`
- `tests/integration/test_agent_db.py`
- 修改 F07 tests / `tests/test_settings.py`
- hypothesis / pytest-asyncio / 新 mock framework
- 脆弱源码字符串扫描 `business_id`/`next_node` 作为主验证（属 Review）
- 复杂 socket monkeypatch（无网络调用则无需）

### Test Evidence Plan（未来 Test Stage）

Targeted F08 tests；Full Regression（F00–F07；Real LLM 仍 skip）；`compileall`；`pip check`；`git diff --check`；Security/Scope Gate。

**不需要：** Real LLM Smoke；DB integration；Embedding real。

---

## TD-17. AC Mapping（分组）

| AC 组 | Design Component | 验证 |
|-------|------------------|------|
| **01–06** State contract / SoT / secret / reasoning / no global | `state.py` TypedDict + validator + factory；**TD-F08-01 lifecycle**；**TD-F08-03 ownership** | `test_agent_state.py` + A/B/H/I |
| **07–11** build/compile/invoke / deterministic deps | `workflow.py`；0 external deps | `test_agent_workflow.py` |
| **12–15** 0 network/Redis/DB/Embedding | 无相关 import；无 Real 测试 | Review + tests 天然本地 |
| **16–23** orchestration vs business / no LLM routing / predefined edges | 2-node linear graph；无 conditional；无 LLM | Review + topology tests |
| **24–28** node update / invalid / no假成功 / Provider≠业务失败 | node partial updates；`AgentStateValidationError`；lifecycle reject | state + workflow tests |
| **29** END ≠ TERMINAL | TD + docs；无业务 terminal 字段 | Review |
| **30–33** 不实现 F09–F12 | Scope / Non-Goals / path list | Review |
| **34–37** 无 HTTP/port/migration/redis dep | 不改 main；pyproject 仅 langgraph | Review + path list |
| **38–42** 无 LangChain/Smith/Cloud/Tool/Stream | D06/D05 + Non-Goals | Review |
| **43–45** Policy / no Real config / compile no network | 无 F07 import；build 无 Settings | Review + tests |
| **46–48** deps≠state；serialization | validator + **`json.dumps(..., allow_nan=False)`**；**TD-F08-02** | `test_agent_state.py` C–G |
| **49–50** no business hardcode；determinism | domain-neutral nodes；repeat invoke；**caller state 不原地修改（J）** | `test_agent_workflow.py` |

每个 AC-F08-01…50 均映射到上表组件；无未覆盖 AC。Finalization 强化证据：State Validity（01–06/26）、Serialization-friendly（48）、State Propagation（25/50）、No Global Mutable State（06）。

---

## TD-18. Review Focus Plan（未来）

1. State 是否成为新 SoT
2. secret / reasoning 是否进入 State
3. Provider/client/session 是否进入 State/artifacts
4. LangGraph 是否越权业务路由
5. 动态 LLM edge
6. 是否意外接 F04/F06/F07
7. 是否新增 DB/Redis
8. serialization-friendly
9. trace 与 F04 trace 混淆
10. 错误是否伪装成功

---

## TD-19. Design Deferred（非 Blocker）

Future real LLM node；F04/F06 integration；conditional routing；persistent checkpointer；session/thread_id；async workflow；conversation memory；streaming；tool calling；LangGraph runtime context；complex dependency container。

**不**将 phase/status lifecycle 列为 Deferred — **TD-F08-01 已冻结**。

**Design Blocking Open Items：0**

---

## TD-20. Stage Path Counts

| 阶段 | Paths |
|------|-------|
| Requirement / TD | 1（Feature Doc） |
| Code 后 | 6（4 Prod NEW + 1 pyproject + Feature Doc） |
| Test 后 | 8（+2 tests） |
| Explanation / Code-Reading 后 | **9** |

Code-Reading 创建时机：**Explanation 完成后 / Commit 前**；本 TD **只规划不创建**。

---

## TD-21. Technical Design Final Closure Checklist

| 项 | 状态 |
|----|------|
| D01–D11 CLOSED | **YES** |
| TD-F08-01 / 02 / 03 | **PASS / CLOSED** |
| Final paths = 9 | **YES** |
| 第 10 path | **NO** |
| AC mapping | **YES**（含 Finalization 增量） |
| Design Blocking | **0** |
| langgraph installed this stage | **NO** |
| pyproject modified this stage | **NO** |
| Production / Tests created | **NO** |
| Technical Design status | **FINAL / CLOSED** |
| Auto Code | **FORBIDDEN until Owner Confirm** |
