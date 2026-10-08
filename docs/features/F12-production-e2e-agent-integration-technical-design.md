# F12 Production E2E Agent Integration — Technical Design

本文档是 **F12 Technical Design**。
它不是 Requirement，不是 Code，不是 Test，不是实现补丁。

## 1. Status

| 项 | 状态 |
|----|------|
| Feature | F12 Production E2E Agent Integration |
| Stage | Technical Design |
| Resource Gate | **CLOSED** |
| Requirement | **APPROVED / FROZEN / REMOTE-FROZEN** @ `b617705e8e2d966540b6733eefe7971c48690798` |
| Requirement SoT | `docs/features/F12-production-e2e-agent-integration.md` |
| Technical Design | **APPROVED / FROZEN** |
| TD maturity | **FROZEN** |
| Owner Review | **APPROVED** |
| TD Finalization | **NOT REQUIRED** |
| Code | **NOT STARTED** |

Owner-approved Technical Design.
Architecture, module responsibilities, state flow, dependency ownership, file scope and test strategy are frozen.
Any later semantic TD change requires Owner-authorized TD Reopen / Finalization.

后续若要改变 Processor responsibilities、file scope、state mapping、F06 trigger、F04 call ownership、F09/LLM ownership、F10 semantics、public API、persistence schema、activation strategy 或 test scope，均须 Owner-authorized TD Reopen / Finalization。

本文件在 Freeze 中只更新状态与治理声明。未改 Production、Tests、Business Data、Decision Graph。

## 2. Frozen Requirement Baseline

| 冻结项 | 值 |
|--------|-----|
| `F12_TERMINAL_SCOPE` | `CONFIRMED_BUSINESS_ID` |
| `BUSINESS_KG_IN_F12` | `NO` |
| `PRODUCTION_ACTIVATION_REQUIRED` | `YES` |
| FR | FR-F12-001 … FR-F12-012 |
| NFR | NFR-F12-001 … NFR-F12-005 |
| Requirement AC | AC-F12-REQ01 … AC-F12-REQ15 |
| 新 Redis / PostgreSQL schema | 不预期 |
| 新环境变量 | 不预期 |
| 公开 API | `PUBLIC_API_CHANGE_EXPECTATION = NO_UNNECESSARY_BREAKING_CHANGE` |

资源沿用 Closure Record，本阶段不重新验证：PostgreSQL + pgvector、Redis、Embedding、F06、Production LLM、F07 `DEMO_APPROVED`、F09 Production Mapping 均为 READY。本阶段 Real LLM = NO，Company HTTP = 0，Redis / PostgreSQL / Embedding / F06 live = NO。

硬边界：

1. Session API 只调用 `AgentTurnProcessor`。不直接调用 F09 / F04 / F10。
2. LLM 不决定 `next_node`，不决定 `business_id`。
3. F06 只提供 direction / candidate。
4. Decision Graph + F04 决定流程推进。
5. F09 负责槽位交互。F09 已调用的 F04 与 LLM，Processor 不得再调用一次。
6. `TERMINAL_CANDIDATE` 经 F10 `PREPARE` 后，必须等后续轮次 `RESOLVE` 才能写入 `confirmed_business_id`。
7. 终点停在 `confirmed_business_id`。不查询 materials / location / channel / legal basis。

F12 是 **INTEGRATION FEATURE**：组合现有 F03–F11，不重写 Graph engine、F04、F09 mapper、F10 confirmation、Session store、lock、idempotency、audit、Embedding、Retrieval engine、LLM provider。

## 3. Existing Architecture Reuse

用户一轮请求在现有代码中的真实边界：

```text
POST /api/v1/session/turn
  session/api.py :: create_session_router / session_turn
    → SessionTurnService.handle_turn
        → fingerprint + replay cache
        → request lock + session lock
        → load_active_session（已有会话）
        → from_persisted(...) → AgentState | None
        → AgentTurnProcessor.process_turn(...)
        → validate AgentTurnResult
        → to_persisted
        → RedisSessionStore.commit_successful_turn
             （checkpoint + TURN_COMPLETED audit + result cache）
        → SessionTurnSuccess
```

失败时 `SessionTurnService` 把非 `SessionDomainError` 的异常转成 `AGENT_TURN_FAILED`，并在已有会话上 `append_failure_audit`。新会话失败不写 checkpoint。Processor 成功返回之后才 `commit_successful_turn`。

已可复用、本设计不改其语义的入口：

| 能力 | 现有入口 |
|------|----------|
| AgentState | `agent/state.py`：`AgentState`、`create_initial_state`、`validate_agent_state` |
| F08 skeleton | `run_agent_workflow`（`START → prepare → complete → END`）。它不跑业务图，F12 主链路不依赖它完成事项 |
| F06 | `SemanticRetrievalService.retrieve(query) -> RetrievalResult` |
| F04 | `advance_until_blocked(graph, current_node_id, slots)` |
| 图加载 | `load_decision_graph`；Demo 图 `data/graphs/demo/social_security.json`，`entry_node_id = social_security_entry` |
| 业务数据 | `JsonBusinessRepository.from_paths`；Demo `data/demo/demo_ss_001.json` |
| F09 | `run_slot_interaction_workflow(state, slot_context, SlotInteractionDependencies)` |
| F10 | `prepare_terminal_confirmation` / `resolve_terminal_confirmation` |
| LLM | `build_llm_provider(settings)`；`LlmAnswerMapper(provider)`；`LlmExplanationService(provider)` |
| Session | `SessionTurnService(store, processor)`；`create_session_router(service)` |
| Redis | `RedisSessionStore(client, RedisSessionConfig)`，client 由调用方注入 |

`main.py` 当前只有 `/health` 与 `RequestContextMiddleware`，没有 `include_router`。

## 4. Integration Gaps

这些缺口是预期中的 F12 集成缺口，不是 Requirement 冲突。

| 缺口 | 设计处理 |
|------|----------|
| 无 Production concrete processor | 新增一个 `GovernmentAgentTurnProcessor` |
| `main.py` 未挂载 Session API | composition helper 组装后 `include_router` |
| F06 未进入 turn path | 仅在确定性 trigger 为真时由 Processor 调用 `retrieve` |
| 无「检索结果 → 图入口」Production adapter | Processor 内最小适配：命中已加载图的 terminal `candidate_business_id` 时，从 `entry_node_id` 进入，再 `advance_until_blocked` |
| 无初始多槽抽取 | 不新增 NLU。首轮只建立方向并问第一个缺失槽 |
| 无事项切换信号 | Phase-1 不检测切换，不让 LLM 清空图。换方向使用新会话 |
| F08 `run_agent_workflow` 不包含 F09/F10 | 主链路调用现有专用 workflow，不改 `workflow.py` |

## 5. Target Architecture

```text
Client
  → Session API
  → SessionTurnService（identity / lock / idempotency / restore / commit / audit）
  → GovernmentAgentTurnProcessor
       → 读 restored AgentState（F11 已恢复）
       → 判定 turn mode
       → 允许时 F06.retrieve
       → Decision Graph entry + F04
       → 缺槽时 run_slot_interaction_workflow（内含 F09，ACCEPTED 时内含一次 F04）
       → terminal 当轮 prepare_terminal_confirmation
       → 后续轮 resolve_terminal_confirmation
  → AgentTurnResult
  → F11 checkpoint + audit
  → SessionTurnSuccess
```

```text
Application composition
  → Settings / 现有 factory
  → GovernmentAgentTurnProcessor
  → SessionTurnService
  → create_session_router
  → app.include_router
```

`main.py` 只做应用组装、路由注册和现有 middleware。不判断槽位，不调用 F04 / F10，不写 `business_id`。

### 5.1 三条主序列

**Initial turn**

```text
Client → Session API → SessionTurnService
  restored_state = None
  → Processor
  → F06.retrieve(input_text)
  → 若 CANDIDATES 且 business_id 属于已加载图的 terminal candidate
       记录 direction（不含用户原文）
       advance_until_blocked(entry, slots={})
       得到 NEED_SLOT（Demo 图：service_action）
  → AgentTurnResult（提问，requires_user_input=true）
  → checkpoint + TURN_COMPLETED audit
  → SessionTurnSuccess
```

**Slot turn**

```text
Client → Session API → SessionTurnService
  from_persisted → restored AgentState
  → Processor 判定 SLOT_INTERACTION（不调用 F06）
  → run_slot_interaction_workflow
       内含解释检测、语义投影、一次 LlmAnswerMapper、校验
       仅 ACCEPTED 时内部 advance_until_blocked 一次
  → 若仍 NEED_SLOT：返回下一问
  → 若 TERMINAL_CANDIDATE：同轮只 prepare_terminal_confirmation
  → AgentTurnResult → F11 commit / audit → SessionTurnSuccess
```

**Terminal confirmation turn**

```text
Client → Session API → SessionTurnService
  restored state 含 f10 terminal_context 且 confirmed_business_id 为空
  → Processor 判定 TERMINAL_CONFIRMATION（不调用 F06 / F09 / F04）
  → resolve_terminal_confirmation
  → CONFIRMED 才写入 confirmed_business_id
  → AgentTurnResult → F11 commit / audit → SessionTurnSuccess
```

## 6. Module Responsibilities

| 模块 | 职责 |
|------|------|
| `session/api.py` + `SessionTurnService` | 保持 F11：身份、幂等、锁、加载、调用 Protocol、成功提交、审计、错误翻译 |
| `GovernmentAgentTurnProcessor` | 唯一业务编排边界。把 restored state 走完一轮，返回 `AgentTurnResult` |
| `composition` helper | 用现有构造函数组装依赖、Service、Router。无业务判断 |
| `main.py` | 调用 composition，`include_router`，保留 `/health` |
| F06 / F04 / F09 / F10 / Redis / Audit | 继续由原模块拥有。Processor 只调用公开入口 |

Processor **不**获取 Redis lock，**不**实现 request idempotency，**不**写 session store，**不**append audit，**不**commit Redis。`AgentTurnResult` 的真实字段里没有 persistence material。持久化材料由 F11 从 `result.state` 经 `to_persisted` 生成。

## 7. Production AgentTurnProcessor

### 7.1 真实协议（只引用）

`AGENT_TURN_PROCESSOR_CURRENT_SIGNATURE`：

```text
AgentTurnProcessor.process_turn(
    *,
    session_id: str,
    request_id: str,
    input_text: str,
    restored_state: AgentState | None,
) -> AgentTurnResult
```

定义于 `src/gov_service_agent/session/service.py`。

`AGENT_TURN_RESULT_CURRENT_FIELDS`：

| 字段 | 类型 |
|------|------|
| `state` | `AgentState` |
| `response_text` | `str` |
| `requires_user_input` | `bool` |
| `public_status` | `SessionTurnPublicStatus` |

定义于 `src/gov_service_agent/session/models.py`。`SessionTurnPublicStatus` 只有 `COMPLETED` 与 `AWAITING_USER_INPUT`。二者与 `requires_user_input` 必须满足 F11 矩阵，否则 `SessionTurnService` 视为 `AGENT_TURN_FAILED` 且不提交新 checkpoint。

`SessionTurnService` 调用点：`_run_and_commit` 在锁内、以及（已有会话时）`from_persisted` 之后，调用 `process_turn`。校验通过后才 `commit_successful_turn`。

返回的 `state["request_id"]` 与 `state["input_text"]` 必须等于本轮 request。F11 在 `from_persisted` 时已经写入这两个瞬态字段。

### 7.2 类与模块

| 项 | 决定 |
|----|------|
| `PROPOSED_PROCESSOR_CLASS` | `GovernmentAgentTurnProcessor` |
| `RATIONALE` | F11 Feature / Code-Reading 已把该名称留给 F12 的唯一具体实现。只建这一个类，不并行建 `ProductionAgentTurnProcessor` |
| `PROPOSED_PROCESSOR_MODULE` | `src/gov_service_agent/agent/turn_processor.py` |
| `WHY_THIS_LAYER` | 它是 Session Protocol 与 Agent 领域编排之间的适配器。`session/` 保持持久化与 HTTP。仓库没有 composition 包可塞业务编排。不放入 `business_graph` / `retrieval` / `terminal` / `interaction` |

Processor 职责：

1. 接收本轮 `session_id`、`request_id`、`input_text`、`restored_state`。
2. 在副本上读取 controlled artifacts，判定 turn mode。
3. 按 mode 调用既有 F06 / Graph / F09 / F10 入口。
4. 得到新的 completed `AgentState`。
5. 用既有 workflow 的 `response_text` 组装 `AgentTurnResult` 交回 F11。

它不创造业务真相，不拥有 Redis、HTTP、audit。

## 8. Turn Mode Decision

Mode 只由 restored controlled state 决定。LLM 不参与。

判定顺序（先匹配先生效）：

| 顺序 | 条件（均来自 artifacts） | Mode |
|------|--------------------------|------|
| 1 | `f10.confirmed_business_id` 为非空字符串 | `ALREADY_CONFIRMED` |
| 2 | `f10.terminal_context.transition_status == TERMINAL_CANDIDATE` 且 `confirmed_business_id` 为空，且 confirmation status 为 `AWAITING_CONFIRMATION` / `UNCERTAIN` / `REJECTED` | `TERMINAL_CONFIRMATION` |
| 3 | `f09` 有可反序列化的 `NEED_SLOT` 或 `INVALID_SLOT` 上下文（`slot_context` 或 `business_transition`） | `SLOT_INTERACTION` |
| 4 | `business_transition.status` 为 `FALLBACK` 或 `UNSUPPORTED` | `SAFE_HOLD` |
| 5 | `restored_state is None`，或尚无 graph context | `INITIAL_OR_DIRECTION_ROUTING` |
| 6 | 其余无法识别的 checkpoint 形状 | 失败，不猜测节点 |

`TURN_MODE_DECISION_TABLE` 即上表。`SAFE_HOLD` 是受控停留，不是自动 RAG。

`TERMINAL_CONFIRMATION_PENDING` 的表达使用当前 F10 合同：`artifacts["f10"].terminal_context` + `confirmation.status`，且 `confirmed_business_id is None`。不新增字段。

该 mode 下本轮只调用 `resolve_terminal_confirmation`。不跑 F06，不跑 F09，不把确认文本当槽位答案。

## 9. State Restore / Persist Mapping

### 9.1 当前三者关系

| 类型 | 真实字段 |
|------|----------|
| `PersistedAgentState` | `phase`、`status`、`artifacts`、`error`（稳定态必须为 `None`） |
| `SessionCheckpoint` | `schema_version`、`session_id`、`revision`、`saved_at`、`state: PersistedAgentState` |
| `AgentState` | `request_id`、`input_text`、`phase`、`status`、`artifacts`、`error`、`orchestration_trace` |

F11 已经完成 checkpoint → `AgentState`：`from_persisted` 写入**本轮** `request_id` / `input_text`，深拷贝 artifacts，`error=None`，`orchestration_trace=[]`。Processor 收到的 `restored_state` 已是 `AgentState | None`。不再做第二套 DTO，也不在 Processor 里重写 `from_persisted`。

### 9.2 STATE_RESTORE_MAPPING

| 来源 | 本轮 AgentState | 说明 |
|------|-----------------|------|
| 新会话 `restored_state is None` | `create_initial_state(request_id, input_text)` | 无历史节点、槽位、candidate、confirmed |
| `PersistedAgentState.artifacts` | `state["artifacts"]` | 直接恢复。业务事实在这里 |
| `phase` / `status` | 同名恢复 | 由 F11 转回枚举 |
| `request_id` / `input_text` | 本轮请求注入 | 瞬态。checkpoint 不保存上一轮原文 |
| `orchestration_trace` | 空列表 | 瞬态。每轮 workflow 自己追加 |
| `error` | `None` | 失败态不能成为稳定 checkpoint |

从 artifacts 读出的业务事实（已有键，不新增 schema）：

| 需求事实 | 现有位置 |
|----------|----------|
| current node | `f09.business_transition.current_node_id` 或 `f09.slot_context.current_node_id`；终态另有 `f10.terminal_context.current_node_id` |
| validated slots | `f09.slot_context.current_slots`，加上本轮 `f09.validated_slot`（仅当 validation 为 `ACCEPTED`） |
| pending slot / question | `slot_context.required_slot` / `allowed_values` / `question_text` |
| candidate | `f09.business_transition.candidate_business_id` 与 `f10.terminal_context.candidate_business_id` |
| confirmed | `f10.confirmed_business_id` |
| 等待确认 | `f10.confirmation.status` |

下一轮进入 F09 前，Processor 用 `build_slot_interaction_context` / `deserialize_slot_context` 重建 `SlotInteractionContext`，并把已接受槽位放进 `current_slots`。`serialize_transition_result` 本身不含 slots 字典，所以 slots 必须继续留在 `slot_context.current_slots` 与 `validated_slot`。这是现有 F09 序列化，不是新 Redis 字段。

### 9.3 STATE_PERSIST_MAPPING

F11 `to_persisted` 已定义反向映射，F12 复用：

| AgentState | PersistedAgentState |
|------------|---------------------|
| `phase` / `status` | 字符串 |
| `artifacts` | 深拷贝。含 f09 / f10 / 方向元数据 |
| `error` | 必须 `None`，否则 F11 拒绝提交 |
| `request_id` / `input_text` / `orchestration_trace` | 不写入 checkpoint |

Processor 成功返回时 `phase=COMPLETED`、`status=COMPLETED`、`error=None`，以便表示本轮受控结果已稳定。Workflow 的 `complete` 节点已经这样做。初始提问路径不经过该节点时，Processor 在**新字典**上设置同一生命周期后再返回。

`PERSISTENCE_MODEL_GAP = NO`。

`CHECKPOINT_SCHEMA_VERSION` 保持 1。不新增 Redis schema，不新增 PostgreSQL schema。方向元数据放在现有 `artifacts` 对象内的新命名空间 `f12`，只存受控枚举与 business_id / rank / direction 标签。**不**写入 `RetrievalResult.query`、用户原文、prompt、模型原文、secret。

## 10. Initial Routing / F06

### 10.1 真实 F06 API

```text
SemanticRetrievalService.retrieve(self, query: str | None) -> RetrievalResult
```

`RetrievalStatus`：`INVALID_QUERY`、`UNAVAILABLE`、`NOT_READY`、`NO_USABLE_CANDIDATE`、`CANDIDATES`。

`RetrievalCandidate` 字段：`business_id`、`display_name`、`score`、`rank`、`direction`、`eligibility_scope`。

没有别的 Production 检索入口。Processor 只调用 `retrieve`。

### 10.2 RETRIEVAL_TRIGGER_TABLE

| 状态 | 调用 F06 |
|------|----------|
| 新会话，或 graph context 尚未建立 | 是 |
| 已有 pending slot（普通槽位回答） | 否 |
| `TERMINAL_CONFIRMATION` | 否 |
| 已有 `confirmed_business_id` | 否 |
| `FALLBACK` / `UNSUPPORTED` | 否 |
| 任意异常 | 否 |
| 明确事项切换 | Phase-1 **无信号，不调用** |

`BUSINESS_SWITCH_SIGNAL_GAP`：当前 `AgentState`、F09、F10 都没有 business-switch 信号。Phase-1 采用最小规则：不新增 intent router，不让 LLM 清空图。更换方向通过新会话重新走 initial routing。这不改变 Golden / 槽位 / 确认 AC。分类为 **NON_BLOCKING**，不构成 Requirement Reopen。

### 10.3 FALLBACK_POLICY

图上的 `TransitionStatus.FALLBACK` / `UNSUPPORTED` 是 F04 的受控结果（Demo 图中 inquiry / other / employer_payment / transfer 会走到这些节点）。Processor 把它们保持为 `SAFE_HOLD`：返回固定的、不含新事项 ID 的说明（优先使用 `unsupported_reason` 若该字段已由 F04 给出），`requires_user_input=true`，不改 candidate，不写 confirmed，不重新检索。

禁止：任何异常自动重新 RAG。Phase-1 不做 retrieval fallback。

### 10.4 RAG authority 与图入口

即使 top candidate 的 `business_id` 是 `DEMO_SS_001`：

- 它只证明「可以进入包含该候选的 Decision Graph」。
- 入口是该图的 `entry_node_id`，不是 terminal 节点。
- 随后 `advance_until_blocked(graph, entry_node_id, {})`。Demo 图会沿唯一 `ENTRY_FORWARD` 停在 `social_security_action`，状态 `NEED_SLOT`，槽位 `service_action`。
- 不得把检索结果写成 `confirmed_business_id`。
- 不得把 top1 直接写成 `TERMINAL_CANDIDATE`。

Graph context established：成功写入 `f09.slot_context` 或 `f09.business_transition` 或 `f10.terminal_context` 之后。此后普通槽位轮次 trigger 为假。

若 `retrieve` 得到 `NO_USABLE_CANDIDATE` 或 `INVALID_QUERY`：返回受控澄清，`AWAITING_USER_INPUT`，不写 business_id，不建立 graph context。下一轮仍可按 trigger 检索。

若检索是本轮必需而 status 为 `UNAVAILABLE` / `NOT_READY`：向 F11 传播失败（见第 14 节）。不发明方向。

Phase-1 只加载现有 Demo 图 `social_security`。候选 `business_id` 必须等于该图某个 `TERMINAL_CANDIDATE` 节点上的 `candidate_business_id` 才允许入图。对不上则按无可用方向处理，不新建图。

### 10.5 INITIAL_INPUT_INTERPRETATION_CAPABILITY = MISSING

F09 只解释**已知 pending slot**。F06 返回候选列表。F03/F04 从入口按已验证 slots 前进。仓库没有「从首句抽出 `service_action` / `payment_actor` / `employment_type`」的 Production 能力。

因此首句「我辞职了，现在没单位，想自己交社保」：

- 可以触发检索与入图；
- **不能**被假设成已经填满任何槽位；
- 第一问是图上的 `service_action` 问题原文。

Requirement AC 没有要求首句一次填满所有槽。逐步追问满足 Golden。不新增 multi-slot extractor。

## 11. F09 / F04 Integration

F09 Production 入口：`run_slot_interaction_workflow`。

该 workflow 已经包含：解释检测、`project_allowed_value_semantics`、`LlmAnswerMapper.map_answer`（仅 FULL/NONE 语义覆盖）、`validate_slot_mapping`（membership 然后 confidence ≥ `MappingPolicy.min_confidence`，默认 `0.80`）、`ACCEPTED` 时 `advance_until_blocked`、非接受时 `resume_current_slot`。

Processor 在 `SLOT_INTERACTION` 只调用这一入口，并传入恢复出的 `SlotInteractionContext` 与 `SlotInteractionDependencies`。

| 所有权 | 决定 |
|--------|------|
| `F04_CALL_OWNERSHIP` | 槽位轮：仅 F09 workflow 的 `advance_business_graph` 节点调用一次 `advance_until_blocked`。Processor 不再调用。初始入图轮：Processor 对空 slots 调用一次 `advance_until_blocked`，该轮没有 F09 mapping。两段不会落在同一次用户槽位回答上 |
| `LLM_CALL_OWNERSHIP` | 普通槽位轮最多一次语义映射，发生在 F09 `interpret_slot_input` 内。Processor 不预调用 `map_answer`。解释轮的解释调用也只在 F09 `explain_current_topic` 内发生一次。Processor 不第二次解释 |

### 11.1 Explanation

`UtteranceKind.EXPLANATION_REQUEST` 由 F09 路由到解释旁路再 `resume_current_slot`。`response_text` 来自 `compose_explanation_response`（或失败时的固定恢复问句）。Processor 读取该 `response_text`，保持 node / slots / candidate / confirmed，`requires_user_input=true`。不再跑 F04、F06 或第二次解释。

### 11.2 Ambiguity

`UNCERTAIN`、`LOW_CONFIDENCE`、`INVALID_VALUE`、`NOT_SLOT_ANSWER`、`OTHER` 都停在 `resume_current_slot`。F09 不写新的 validated slot，不调用 `advance_until_blocked`。Processor 不再做 second-chance LLM，不做 best-of-N。返回的问句是现有 `compose_uncertain_response` / `compose_other_response`，其中包含原 `question_text`。

### 11.3 Accepted

`ACCEPTED` 后由 workflow 写入槽位并执行一次 F04。Processor 只读返回状态：

| F04 结果 | Processor 下一步 |
|----------|------------------|
| `NEED_SLOT` / `INVALID_SLOT` | 使用 `question_text` 作为 `response_text`，继续等待 |
| `TERMINAL_CANDIDATE` | **同轮只** `prepare_terminal_confirmation`。`confirmed_business_id` 仍为 `None` |
| `UNSUPPORTED` / `FALLBACK` | `SAFE_HOLD`。不检索，不确认 |
| 异常 | 失败上抛。不发明下一节点 |

F09 在 terminal 结果上把 `response_text` 留空。对用户可见的确认提示以 F10 `PREPARE` 的 `response_text` 为准。

## 12. F10 Integration

| 阶段 | 所有者 | 入口 |
|------|--------|------|
| F10 PREPARE | 产生 terminal candidate 的**同一轮**，在 F09/F04 返回之后 | `prepare_terminal_confirmation` |
| F10 RESOLVE | **下一轮**及之后，mode 为 `TERMINAL_CONFIRMATION` | `resolve_terminal_confirmation` |

`prepare_terminal_confirmation` 使用 `TerminalConfirmationMode.PREPARE`，不把本轮 `input_text` 解释为确认。`READY_FOR_CONFIRMATION` 时 confirmation status 为 `AWAITING_CONFIRMATION`，`confirmed_business_id=None`，文案来自现有模板：请回复「确认」或「不确认」。

`resolve_terminal_confirmation` 使用现有 `interpret_confirmation`。真实意图：

| `ConfirmationIntent` | `ConfirmationStatus` | `confirmed_business_id` |
|----------------------|----------------------|-------------------------|
| `CONFIRMED` | `CONFIRMED` | `assign_confirmed_business_id` 精确传播 candidate |
| `REJECTED` | `REJECTED` | 保持 `None` |
| `UNCERTAIN` | `UNCERTAIN` | 保持 `None` |
| 校验非 `READY_FOR_CONFIRMATION` | `BLOCKED` | 保持 `None` |

不新增 confirmation parser。

`TERMINAL_REJECTION_BEHAVIOR`：复用 F10。否认后 `confirmed_business_id` 仍为空，响应使用 `_MSG_REJECTED_TMPL`（已取消对当前候选的确认，本次不确认该事项）。不删除 session，不清空 checkpoint，不重新 RAG，不改 candidate。后续用户输入仍走 `RESOLVE`（同一 `terminal_context`）。`UNCERTAIN` 继续要求明确回复「确认」或「不确认」。

确认成功后 mode 为 `ALREADY_CONFIRMED`：返回 F10 已生成的确认完成文案，`public_status=COMPLETED`，`requires_user_input=false`。该模式优先于 F10 RESOLVE、F09 与 F06，不再进入这三者，也不查询 Business Knowledge。

校验 `BLOCKED`（候选不存在、ID 不一致、名称不可用、规则未评估）使用 F10 现有失败文案，不写入 confirmed。这是受控业务失败说明，不是猜测出一个 business_id。若 workflow 自身抛错，则按第 14 节失败处理，不提交部分状态。

## 13. Response Mapping

`RESPONSE_TEXT_OWNERSHIP`：

| 路径 | 文案来源 |
|------|----------|
| 初始入图后的第一问 | F04 `TransitionResult.question_text` |
| 槽位接受后的下一问 | F09 `artifacts["f09"].response_text`（即 `question_text`） |
| 解释 / 不确定 / 其它 | F09 `resume_current_slot` 已组合的 `response_text` |
| 无检索方向 | Processor 选用一条固定安全澄清，不调用新的 LLM writer |
| PREPARE / RESOLVE | F10 `compose_terminal_response_text` 写入的 `artifacts["f10"].response_text` |
| 已确认后再入站 | 复用已持久化的 F10 确认完成文案 |

Processor 只选择上述受控字符串。不新增通用 LLM response writer。

### 13.1 AgentTurnResult mapping

| 路由 | `response_text` | `requires_user_input` | `public_status` | persisted 要点 |
|------|-----------------|----------------------|-----------------|----------------|
| pending slot | F09/F04 问句 | `true` | `AWAITING_USER_INPUT` | 当前 node + slots + question |
| explanation | F09 解释+原问 | `true` | `AWAITING_USER_INPUT` | 业务状态不变 |
| low confidence / uncertain / invalid | 原问仍在 | `true` | `AWAITING_USER_INPUT` | 不新增 slot，不改 candidate/confirmed |
| terminal PREPARE | F10 确认提示 | `true` | `AWAITING_USER_INPUT` | candidate 在，`confirmed_business_id=null` |
| RESOLVE uncertain | F10 不确定模板 | `true` | `AWAITING_USER_INPUT` | confirmed 仍空 |
| RESOLVE rejected | F10 否认模板 | `true` | `AWAITING_USER_INPUT` | confirmed 仍空，candidate 保留 |
| CONFIRMED | F10 已确认模板 | `false` | `COMPLETED` | `confirmed_business_id` 已写入 |
| 已确认后的后续轮 | 同一确认完成文案 | `false` | `COMPLETED` | 不重复写业务效果 |
| SAFE_HOLD | F04 reason 或固定说明 | `true` | `AWAITING_USER_INPUT` | 停在 fallback/unsupported |
| 无方向澄清 | 固定澄清 | `true` | `AWAITING_USER_INPUT` | 无 graph context |

`state` 始终是本轮完整 `AgentState`。

### 13.2 SessionTurnSuccess 边界

Processor **不**构造 `SessionTurnSuccess`。F11 在 `commit_successful_turn` 之前用 `AgentTurnResult` 填：

```text
session_id / request_id 来自 Session 层
status = result.public_status
response_text = result.response_text
requires_user_input = result.requires_user_input
```

公开 JSON 仍是现有 `POST /api/v1/session/turn`。不增加 `current_node`、slot map、`candidate_business_id`。用户可见结果只通过 `response_text` 与 `requires_user_input`。

`Public API change required = NO`。

## 14. Failure / Transaction Boundaries

Processor 失败时抛出异常，或抛出已有 `SessionDomainError(AGENT_TURN_FAILED)`。不返回带伪造 `business_id` / `next_node` / slot value 的成功结果。不新增异常类层次。

| 场景 | 行为 |
|------|------|
| A. 必需检索 `UNAVAILABLE` / `NOT_READY` | 失败上抛。无方向、无 confirmed |
| B. Repository 读失败 / 图加载失败 | 失败上抛 |
| C. F09 内 Provider 失败 | 让异常离开 workflow，Processor 不吞掉、不改写槽位 |
| D. 非法 mapper 输出 | 沿用 F09 fail-closed。不选择最近的 allowed value |
| E. F04 `TransitionInvariantError` / node missing | 失败上抛 |
| F. F10 workflow 抛错 | 失败上抛。`BLOCKED` 模板若已由 F10 正常返回，则是成功的受控响应，confirmed 仍空 |
| G. artifact 无法按现有模型反序列化 | 失败上抛（F11 也可在入口把坏 checkpoint 标为 `CHECKPOINT_INVALID`） |

`NO_USABLE_CANDIDATE` 不是基础设施失败，走澄清成功响应。

事务边界：Processor 只计算新的 turn result。Redis commit 仍由 `SessionTurnService._run_and_commit` → `commit_successful_turn` 在校验之后执行。Processor 异常时该提交不会发生。已有会话只追加失败审计，checkpoint revision 不变。新会话失败不留下 checkpoint。

`STATE_MUTATION_SAFETY_DESIGN`：

- `from_persisted` 已经深拷贝 artifacts。
- `run_slot_interaction_workflow`、`prepare_terminal_confirmation`、`resolve_terminal_confirmation` 都 `copy.deepcopy` 入参后再 invoke。
- Processor 仍规定：分类与组装只读 `restored_state`；任何写入发生在 deepcopy 或 `create_initial_state` 得到的新对象上。禁止就地修改 F11 传入的 dict。
- 因此失败前不会把半成品写回 F11 持有的对象，也不会进入 `commit_successful_turn`。

Audit：Processor 不写 audit。成功轮由 F11 记 `TURN_COMPLETED`（phase/status/revision/capability，无 raw input）。失败轮由 F11 记 `TURN_FAILED` / `AGENT_TURN_FAILED`。不把 raw `USER_FREE_TEXT`、prompt、模型原文、secret 放入 `f12` artifacts。

## 15. Dependency Composition

### 15.1 PROCESSOR_DEPENDENCY_SET

**Direct（构造函数注入）：**

| 依赖 | 用途 |
|------|------|
| `DecisionGraph` | 入图与交给 F09 deps |
| `JsonBusinessRepository` | F09 语义投影与 F10 读取 |
| `SemanticRetrievalService` | 仅 trigger 为真时 `retrieve` |
| `SlotInteractionDependencies` | 整个对象交给 `run_slot_interaction_workflow` |
| `TerminalConfirmationDependencies` | 交给 PREPARE / RESOLVE |

**Transitively owned（Processor 不再单独调用）：**

| 依赖 | 所有者 |
|------|--------|
| `AnswerMapper` / `LlmAnswerMapper` | `SlotInteractionDependencies` → F09 workflow |
| `ExplanationService` / `LlmExplanationService` | 同上 |
| `MappingPolicy`（默认 0.80） | 同上 |
| `LlmProvider` | mapper 与 explanation 共享同一 `build_llm_provider` 实例 |
| `select_executable_rules` | F10 `TerminalConfirmationDependencies` 默认 adapter |
| Embedding provider、`ProjectionStore`、PostgreSQL engine | `SemanticRetrievalService.retrieve` 内部按需解析 |
| Redis client / store | `SessionTurnService`，不属于 Processor |

不引入 dependency-injector、container 或 service locator。不用模块级可变单例保存 Processor。

### 15.2 Composition strategy

新增小模块 `src/gov_service_agent/composition.py`，提供一个纯函数组装：

1. `get_settings()`
2. `load_decision_graph(data/graphs/demo/social_security.json)`
3. `JsonBusinessRepository.from_paths([data/demo/demo_ss_001.json])`
4. `build_llm_provider(settings)` → `LlmAnswerMapper` + `LlmExplanationService` → `SlotInteractionDependencies` + `TerminalConfirmationDependencies`
5. `SemanticRetrievalService(settings=settings)`
6. `GovernmentAgentTurnProcessor(...)`
7. 用 settings 中已有 Redis 字段构造 `Redis` client 与 `RedisSessionConfig`，再 `RedisSessionStore`
8. `SessionTurnService(store=..., processor=...)`
9. `create_session_router(service)`

测试可以传入替换后的 store / retrieval / mapper，仍使用同一 Processor 类。Demo 图与 Demo business JSON 在自动测试中保持真实文件，以免换成另一套业务真相。

`NEW_CONFIG_REQUIREMENT = NO`。Redis、PostgreSQL `DATABASE_URL`、Embedding、LLM、`llm_remote_data_policy_profile` 均已在 `Settings`。F12 不新增环境变量。Phase-1 Demo 运行 profile 继续使用现有 `DEMO_APPROVED` 配置，由 F07 provider 执行，Processor 不直接 HTTP。

### 15.3 STARTUP_DEPENDENCY_LIFECYCLE

与现有模式一致：启动时构造对象，不主动连接。

`IMPORT_TIME_EXTERNAL_IO = NO`。import `main` / `app` 不连接 Redis，不连接 PostgreSQL，不加载 Embedding，不发送 LLM HTTP。

`STARTUP_HEAVY_RESOURCE_LOAD = NO`。Redis、PostgreSQL、Embedding 仅在首次真实使用时沿用现有 lazy 行为。`build_llm_provider` 构造不产生网络请求。

| 依赖 | 生命周期 |
|------|----------|
| Settings / 图 JSON / Business JSON | 进程启动时读取本地文件并构建对象 |
| LLM provider | `build_llm_provider` 不发起网络 |
| Redis | client 构造时不作为 F12 设计要求去 PING；首次 turn 由 F11 store 使用连接 |
| PostgreSQL / Embedding | `SemanticRetrievalService` 在真正 `retrieve` 时才解析 store 并加载模型 |
| 图与 repository | 启动时加载，便于缺文件尽早失败；不在 import `main` 时连接数据库 |

不把 Embedding 模型加载放进 import。测试替换 retrieval 实现后不会加载模型。

## 16. Production Activation

`main.py` 在现有 logging、`FastAPI`、middleware、`/health` 之外：

1. 调用 composition 得到 router。
2. `app.include_router(router)`。

不在 `main.py` 写槽位、F04、F10 或 `business_id`。不创建第二个 FastAPI 应用，不新增端口。

激活后路由：

- `GET /health` 保持 `{"status": "ok"}`。
- `POST /api/v1/session/turn` 由 F11 router 提供，其 `SessionTurnService` 持有 `GovernmentAgentTurnProcessor`，不是 `DeterministicTestAgentTurnProcessor`。

## 17. File Scope

Production Python 预算：新增 ≤ 2，修改 ≤ 5。本设计为新增 2、修改 1。`FILE_SCOPE_WARNING` 不适用。`workflow.py` 的公开函数已够用，**不修改**。

### 17.1 Production

| Path | 操作 | Purpose | Why required | Requirement IDs | 可改为只复用？ |
|------|------|---------|--------------|-----------------|----------------|
| `src/gov_service_agent/agent/turn_processor.py` | ADD | `GovernmentAgentTurnProcessor` | 唯一编排边界；现无 concrete 类 | FR-001–012 | 否。Protocol 无实现 |
| `src/gov_service_agent/composition.py` | ADD | 组装依赖、Service、Router | 避免 `main.py` 堆构造，且仓库无现成 composition root | FR-001；NFR-005 | 否。否则业务构造会进入 `main.py` |
| `src/gov_service_agent/main.py` | MODIFY | `include_router`，保留 `/health` | `PRODUCTION_ACTIVATION_REQUIRED=YES` | FR-001；AC-REQ01 | 否。当前未挂载 |

不修改：`session/*`、`agent/workflow.py`、`agent/nodes.py`、`interaction.py`、`terminal.py`、`transition.py`、`retrieval/*`、`llm/*`、Business Data、Decision Graph、Prompt、threshold、Settings。

### 17.2 Tests（后续 Test 阶段，本阶段不创建）

| Path | 操作 | Purpose |
|------|------|---------|
| `tests/test_f12_turn_processor.py` | ADD | Layer 1–2：mode、F06 trigger、F09/F04 一次、F10 分轮、失败不发明 ID |
| `tests/test_f12_session_integration.py` | ADD | Layer 3：经 `SessionTurnService` 的 resume、idempotency、失败不提交 checkpoint |
| `tests/test_f12_app_activation.py` | ADD | Layer 4：真实 composition 注册 turn 路由与 `/health`；processor 类型为 `GovernmentAgentTurnProcessor`；外部依赖可替换 |

现有 F11 lock 测试继续覆盖锁算法。F12 只断言 Production processor 经 `SessionTurnService.handle_turn` 进入，不绕过锁。

### 17.3 Docs

| Path | 操作 | 阶段 |
|------|------|------|
| 本 TD 文件 | ADD | 本阶段唯一文件变更 |
| Requirement | 不修改 | — |
| Code-Reading | 不在本阶段创建 | Explanation / Code-Reading 阶段 |

## 18. Test Strategy

自动测试不把真实 Company LLM 当必需条件。替换 LLM、retrieval、Redis store 时必须实现真实接口，且不得替换 Decision Graph、F04 语义、F09 校验规则、F10 确认规则。

| Layer | 内容 |
|-------|------|
| 1 | Processor 单元：mode 表、trigger 表、结果映射。图与 repository 用真实 Demo 文件 |
| 2 | Processor + 真实 `run_slot_interaction_workflow` / F10 runner。mapper 换受控 stub |
| 3 | `SessionTurnService`：checkpoint resume、幂等回放、失败不提交 |
| 4 | FastAPI app：路由已注册，processor 为 Production 类；store/retrieval/LLM 可替换 |
| 5 | 可选人工 Production smoke。仅未来 Owner 授权。不进入普通 pytest |

### 18.1 GOLDEN_TURN_SEQUENCE

真实图 `social_security`。首句不硬编码到最终事项。`service_action` / `payment_actor` 没有已验证的唯一自然语言映射，测试用受控 mapper 注入**唯一 machine value**，不在本 TD 编造「这句人话必然映射到某值」。

| Turn | 输入 | 受控结果 | 断言 |
|------|------|----------|------|
| 1 | 「我辞职了，现在没单位，想自己交社保」 | 检索候选只作方向；`advance_until_blocked(entry, {})` → `NEED_SLOT` / `service_action`；slots 空 | `confirmed_business_id` 空；不是 terminal；response 为该节点 `question_text` |
| 2 | 槽位回答由受控 mapper 接受为 `service_action=payment` | F09 一次 F04，下一问 `payment_actor` | 检索调用次数不增加 |
| 3 | 受控 mapper 接受为 `payment_actor=self_payment` | 下一问 `employment_type` | candidate 仍空 |
| 4 | 「无雇工的个体工商户」；mapper 接受为 `self_employed_without_employees`（confidence ≥ 0.80） | F04 到达 `terminal_demo_ss_001` / `DEMO_SS_001`；同轮只 PREPARE | `confirmed_business_id is None`；response 要求确认 |
| 5 | 独立轮次，文本为现有正例「确认」 | `RESOLVE` → `CONFIRMED` | `confirmed_business_id=DEMO_SS_001`；`COMPLETED`；无 Knowledge 查询 |

图事实（只读）：三条 `employment_type` 边都进入 `DEMO_SS_001`。Golden 固定走 `self_employed_without_employees`，因为该句是已验证受控措辞。`employer_payment` / `transfer` / `inquiry` / `other` 会进入 fallback 或 unsupported，不是 Golden 路径。

### 18.2 其它场景

**Ambiguity：** `employment_type` pending。输入「平时接零活，没有固定单位」。受控 mapper 返回 `slot_answer` / `other_flexible_employment` / confidence `0.75`。期望现有校验 `LOW_CONFIDENCE`：slot 不变，F04 调用 0，candidate 不变，confirmed 不变，问句仍在。不用真实 LLM。

**Explanation：** 同槽位，输入「什么叫灵活就业？」。走 F09 解释旁路。无 slot 写入，无 F04，pending 仍在。response 含解释与当前 `question_text`（现有 `compose_explanation_response`）。

**F10 两轮：** Turn N 最后槽位 `ACCEPTED` 后 candidate 出现且 confirmed 为空。Turn N+1「确认」后 confirmed 写入。另测「不确认」：`REJECTED`，confirmed 仍空，session 仍在，无第二次检索。

**Resume：** Turn 1 通过 `SessionTurnService` 写入部分槽位。Turn 2 使用同一 `session_id`。恢复后的 node、已校验槽、candidate、pending slot 与上一成功轮一致。不以手工拼 `AgentState` 作为唯一证据。

**Idempotency：** 同一 `request_id` + 相同 `input_text` 走 F11 replay。Processor 业务效果只发生一次。不在 Processor 再做一层 dedupe。

**Concurrency：** 不重测 Redis 锁算法。断言集成路径进入 `handle_turn`，锁仍由 F11 获取。

**Failure：** 检索必需失败、mapper/provider 失败、非法 mapping、F04 错误、F10 抛错。断言无发明的 business 结果，且无新的成功 checkpoint。

**Activation：** composition 构建的 app 含 `POST /api/v1/session/turn`，service 内 processor 类型为 `GovernmentAgentTurnProcessor`。自动测试可替换 Redis / retrieval / LLM。

**Health：** 同一 app 上 `GET /health` 仍返回 ok。

## 19. Requirement Traceability

### 19.1 FR

| FR | 设计 | 验证 |
|----|------|------|
| FR-F12-001 | Production processor + `include_router` | Layer 4 类型断言 |
| FR-F12-002 | F11 `from_persisted` 后再 `process_turn`；新会话 `None` | Layer 3 resume |
| FR-F12-003 | 第 10 节 trigger 表 | Layer 1 计数 |
| FR-F12-004 | 检索只入图入口；LLM 不写 business_id | Golden Turn 1 |
| FR-F12-005 | 非接受停在 F09 resume | Ambiguity |
| FR-F12-006 | 仅 `ACCEPTED` 进入 workflow 内 F04 | Golden Turn 2–4 |
| FR-F12-007 | 解释旁路复用 F09 | Explanation |
| FR-F12-008 | PREPARE 与下一轮 RESOLVE 分离 | F10 两轮 |
| FR-F12-009 | 成功态经现有 `to_persisted` / `commit_successful_turn` | Resume |
| FR-F12-010 | 幂等与锁仍属 F11 | Idempotency + 现有 F11 lock 测试 |
| FR-F12-011 | F11 audit；`f12` artifacts 不含原文与 secret | Audit 断言 |
| FR-F12-012 | 第 14 节失败上抛 | Failure |

### 19.2 NFR

| NFR | 设计 | 验证 |
|-----|------|------|
| NFR-F12-001 | Graph/F04/F10 权威不改写 | Golden + 真实图文件 |
| NFR-F12-002 | 不把 secret / 原文写入新 artifacts 或 audit | 持久化 payload 断言 |
| NFR-F12-003 | 不绕过 `SessionTurnService` | Layer 3–4 |
| NFR-F12-004 | 槽位轮不检索；LLM 仅 F09 内一次 | 调用计数 |
| NFR-F12-005 | 构造函数注入；替身遵守真实接口 | Layer 1–4 |

### 19.3 Requirement AC

| AC | 证据 |
|----|------|
| AC-F12-REQ01 | Activation test |
| AC-F12-REQ02 | `from_persisted` 在 `process_turn` 之前（现有 F11）+ resume test |
| AC-F12-REQ03 | Golden Turn 1 |
| AC-F12-REQ04 | Golden Turn 2–4 的检索计数 |
| AC-F12-REQ05 | Golden 槽位轮 |
| AC-F12-REQ06 | Ambiguity |
| AC-F12-REQ07 | Explanation |
| AC-F12-REQ08 | 真实 `advance_until_blocked`，Processor 不改写结果 |
| AC-F12-REQ09 | Turn N confirmed 为空 |
| AC-F12-REQ10 | Turn N+1 才写入 |
| AC-F12-REQ11 | Resume |
| AC-F12-REQ12 | Idempotency |
| AC-F12-REQ13 | F11 audit 合同 + 无 raw/secret |
| AC-F12-REQ14 | Failure |
| AC-F12-REQ15 | Golden 终点 `DEMO_SS_001`，断言无 Knowledge 调用 |

覆盖：FR 12/12，NFR 5/5，Requirement AC 15/15。

## 20. Open Technical Decisions

| 项 | 分类 | 处理 |
|----|------|------|
| 无 in-session business-switch 检测 | **NON_BLOCKING** | Phase-1 用新会话重入方向。不新增路由器 |
| `artifacts["f12"]` 只存方向元数据 | 已在本 TD 决定 | 不升 checkpoint schema |
| Processor 模块放在 `agent/` | 已决定 | 见第 7 节 |
| composition 独立文件 | 已决定 | 避免 `main.py` 承载构造 |

**BLOCKING open decisions：无。**

`REQUIREMENT_CONFLICT_FOUND = NO`。现有协议、artifacts 与 F09/F10/F04 入口可以在冻结 Requirement 内完成集成。

`TD FINALIZATION REQUIRED = NO`。

## 21. Technical Design Status

| 项 | 值 |
|----|-----|
| F12 Technical Design | **APPROVED / FROZEN** |
| TD maturity | **FROZEN** |
| Owner Review | **APPROVED** |
| TD Finalization | **NOT REQUIRED** |
| Requirement | **APPROVED / FROZEN / REMOTE-FROZEN** |
| Code | **NOT STARTED** |
| 下一阶段 | **OWNER REVIEW** |

未决事项都不改变公开 API、业务权威或终点行为。Code 未授权。
