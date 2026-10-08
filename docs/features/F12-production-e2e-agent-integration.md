# F12 Production E2E Agent Integration

本文档是 **F12 Requirement**。
它不是 Resource Gate Closure Record，不是 Technical Design，不是 Code-Reading，不是实现说明。

## 1. Status

| 项 | 状态 |
|----|------|
| Feature | F12 Production E2E Agent Integration（provisional name） |
| Stage | Requirement |
| F12 Resource Gate | **CLOSED** @ `57b899e50fd3a4306f106ad7562b6e4261650b7c` |
| F12 Requirement | **APPROVED / FROZEN** |
| Requirement maturity | **FROZEN** |
| Owner Review | **APPROVED** |
| Requirement Finalization | **NOT REQUIRED** |
| Technical Design | **NOT STARTED** |
| Implementation | NOT STARTED |

Owner-approved Requirement.
Requirement scope, FR/NFR/AC, terminal scope and business boundaries are frozen.
Any later semantic Requirement change requires a new Owner-authorized Requirement Reopen / Finalization action.

## 2. Background

F03–F11 已分别交付 Decision Graph、确定性推进、语义检索、LLM Provider 与数据策略、AgentState、缺失槽位交互、终点确认、以及 Session API / checkpoint / audit。
它们尚未由真实 Session API 驱动成一条 Production 多轮业务主链路。
F11 明确：Concrete Government Agent Turn Processor 与应用级 activation 属于 F12。

## 3. Resource Preconditions

本 Requirement 不重新验证资源。沿用已关闭 Resource Gate：

| 资源 | 状态 |
|------|------|
| PostgreSQL + pgvector | READY |
| Redis | READY |
| Embedding runtime | READY |
| F06 Semantic Retrieval | READY |
| Production LLM Provider | READY |
| F07 DEMO_APPROVED | READY |
| F09 Production Mapping | READY |
| RG-F12-006 | READY / VERIFIED |
| Docker | NOT REQUIRED FOR REQUIREMENT |
| New port | NONE |
| New environment variable | NONE EXPECTED |
| Resource blocker | NONE |

远程 LLM 必须继续走既有 F07 Remote Data Policy。
Phase-1 Demo 获批 profile 为 `DEMO_APPROVED`。
F12 不得绕过 policy、不得直接发 HTTP、不得另建第二套 Provider client。

## 4. Business Goal

F12 建立第一条可由真实 Session API 驱动的 Production Agent 多轮业务链路，使用户输入能够在既有确定性业务控制边界下，经过允许场景中的语义检索、Decision Graph、槽位交互、终点候选及显式确认，形成受控 `confirmed_business_id`，并将状态持久化到既有会话 / checkpoint / audit 体系。

Agent **编排**这条链路。
Decision Graph **控制**业务路径。
F04 **确定性推进**。
F10 **确认**终点候选。
LLM **不**决定办理哪个事项。

## 5. Architecture Boundaries

以下原则不可改变：

1. Business Decision Graph 决定业务流程。
2. LLM 不决定 `next_node`。
3. LLM 不决定 `business_id`。
4. LLM 不创造业务规则。
5. F04 是 deterministic transition / rule readiness。
6. F09 负责 missing-slot interaction。
7. F10 负责 terminal candidate validation 与用户显式确认。
8. `TERMINAL_CANDIDATE` 不等于 `confirmed_business_id`。
9. 只有用户显式确认之后才能形成 `confirmed_business_id`。
10. F06 Semantic Retrieval 只负责找方向 / candidate，不能作为最终事项判定。
11. 可执行业务事实继续来自既有约束（VERIFIED 且 `usable_by_rule_engine`，或当前等价规则）。`TO_CONFIRM` 或非受控文本不得被 F12 自动变成确定性规则。
12. F12 是集成 Feature，不新增办理规则、资格条件或社保政策判断。

### 5.1 F11 / F12

F11 已提供：Session API、request idempotency、Redis TTL、lock hierarchy、checkpoint、audit、`AgentTurnProcessor` Protocol。
F11 没有提供：Production concrete Agent turn execution，也没有把 Session router 接到正式应用入口。

F12 必须提供一个 Production-capable turn processing integration，满足现有 `AgentTurnProcessor` Protocol，并被正常 Session API Production path 使用。
`PRODUCTION_ACTIVATION_REQUIRED = YES`。
本 Requirement 不规定类名、模块名、构造方式、依赖注入或 `main.py` 的具体改法。

当前 Protocol 事实（只引用，不重新设计）：

`process_turn(session_id, request_id, input_text, restored_state) -> AgentTurnResult`

`AgentTurnResult` 含恢复后应继续使用的 `AgentState`、对用户可见的 `response_text`、`requires_user_input`、`public_status`。

### 5.2 F08

F08 已提供 `AgentState` 与 LangGraph 编排基础。
F12 不得另建一套 Agent 状态模型。
Production turn processing 必须复用当前 `AgentState` / 既有 workflow 能力，以及 F04 / F09 / F10 的既有行为。
当前未见因此必须改 `AgentState` 才能表达本 Requirement 的缺口。

## 6. In Scope

- Production `AgentTurnProcessor` integration，并由 Session API Production path 调用
- checkpoint restore / save
- 复用 `AgentState` 编排
- F06 仅在冻结触发条件下使用
- Decision Graph 入口与既有确定性推进
- F09 槽位处理（含解释旁路与非接受结果）
- F04 在已接受业务状态上的确定性推进
- F10 终点校验与显式确认
- `confirmed_business_id`
- 既有 audit、idempotency、lock 语义的保持
- 多轮状态连续
- Production E2E 验收场景（本阶段只定义场景，不定义测试实现）

## 7. Out of Scope

- 新的 Decision Graph 能力
- 新的 F09 语义校准、Prompt 调整、confidence threshold、Business Data 区分规则
- 新的 LLM Provider 或 Embedding 模型
- 新的 Redis schema 或 PostgreSQL schema（除非后续 TD 证明当前集成无法成立；本 Requirement 不预期需要）
- Business Knowledge 查询：materials、location、channel、legal basis
- Navigation Graph
- ASR、微信或其它前端、RPA、UI
- 新的业务事实或政策规则

`confirmed_business_id` 是后续确定性知识查询的稳定输入。
该查询属于 future feature / later authorized scope。
本文件不指定编号 Feature 去实现它。

## 8. E2E Input

优先复用当前 F11 合同，不新增平行字段。

当前 `SessionTurnRequest`：

| 字段 | 语义 |
|------|------|
| `request_id` | UUID4；本轮请求身份；也是既有幂等身份的一部分 |
| `session_id` | 可选 UUID4；缺省表示新会话 |
| `input_text` | 本轮用户自然语言；非空、有长度上限 |

客户端不得把完整 `AgentState`、`current_node`、`candidate_business_id`、`confirmed_business_id` 或 pending slot 作为权威提交，以覆盖服务端 checkpoint。
Checkpoint authority 在服务端。

F12 必须能从上述既有输入，加上 F11 已恢复的 checkpoint，完成一个 turn。

## 9. E2E Output

优先复用当前 `SessionTurnSuccess`，不无依据新增对外字段。

当前成功响应语义：

| 字段 | 语义 |
|------|------|
| `session_id` | 会话身份 |
| `request_id` | 请求身份 |
| `status` | `AWAITING_USER_INPUT` 或 `COMPLETED` |
| `response_text` | 本轮对用户可见结果 |
| `requires_user_input` | 与 `status` 的既有矩阵一致 |

对用户可见结果必须能表达：

- pending slot：继续询问当前问题
- explanation side route：给出受控解释并恢复原问题
- terminal candidate：要求显式确认，且尚未确认事项
- `confirmed_business_id` 已写入：表达事项确认完成

默认仍不得返回完整 `AgentState`、artifacts dump、Redis key、内部 trace。
精确 HTTP 细节沿用 F11 已实现的 `POST /api/v1/session/turn`；本 Requirement 不重新设计 JSON。

`PUBLIC_API_CHANGE_EXPECTATION = NO_UNNECESSARY_BREAKING_CHANGE`。
现有 Session turn 合同足以表达本 E2E。
把已有 router 接到正式应用入口属于 activation，不是新的公开字段。

## 10. Production Flow

业务顺序如下。本段只冻结行为，不规定实现。

用户请求
→ F11 Session API（`request_id` / 可选 `session_id` / `input_text`）
→ 既有 idempotency 与 lock
→ checkpoint restore（新会话则为空恢复）
→ Production Agent processing（复用 `AgentState`）
→ 仅在允许场景调用 F06
→ Decision Graph
→ 缺槽时 F09
→ 仅当槽位被接受后 F04
→ `TERMINAL_CANDIDATE`
→ F10 PREPARE，且本轮输入不得被当成确认
→ 后续轮次用户显式确认后 F10 RESOLVE
→ `confirmed_business_id`
→ checkpoint persist
→ audit
→ Session API response。

当前 Demo Decision Graph（`social_security`）核心槽位以仓库为准：

- `service_action`
- `payment_actor`
- `employment_type`

不得再使用历史别名 `employer_status` / `no_employer` / `payment_mode` 作为本 E2E 合同。

## 11. F06 Retrieval Boundary

`F06_RETRIEVAL_TRIGGER_REQUIREMENT`：

允许：

- 新会话，或尚未形成 domain / business direction
- 明确发生事项切换
- 既有 graph context 无法继续，且现有架构允许 fallback

不允许：

- 每个普通槽位回答都重新做 semantic retrieval
- Decision Graph context 已经稳定后，用检索取代 Graph 控制权

F06 Top-K 只提供 candidate / direction。
semantic similarity 不是业务事实。
检索不得直接形成 `confirmed_business_id`，不得绕过 Decision Graph，不得绕过 F10。

## 12. F09 Interaction Requirements

完整 E2E 保留当前 F09 行为，不重新定义 mapper schema，不新增 threshold，不新增 allowed value。

当前路径至少覆盖：`SLOT_ANSWER`、`EXPLANATION_REQUEST`、`UNCERTAIN`、`OTHER`，以及校验状态 `LOW_CONFIDENCE` / `INVALID_VALUE` / `NOT_SLOT_ANSWER`。
既有 confidence threshold 保持 `0.80`。

### 12.1 Accepted

仅当 utterance 属于可接受的 slot answer、mapped value 属于 `allowed_values`、confidence 达到既有 threshold、且 validation 为 `ACCEPTED` 时，才允许写入 validated slot 并进入 F04。

### 12.2 Ambiguous / non-accepted

`UNCERTAIN`、`LOW_CONFIDENCE` 以及其它既有非接受正常结果：

- 不写 validated slot
- 不调用 F04
- 不错误改变 candidate
- 不改变 `confirmed_business_id`
- 停留在当前 pending slot，并继续向用户询问

不得为了走通 E2E 自动选择“最接近”的 allowed value。

### 12.3 Explanation

询问选项含义不等于选择该选项。
`EXPLANATION_REQUEST` 不得写 validated slot、不得推进 F04、不得改变 candidate 或 confirmed business。
解释结束后恢复 pending slot 与当前问题。
F12 不得把解释变成 graph transition。

## 13. F04 Deterministic Transition Requirements

F04 只在已接受的业务状态满足既有调用条件时执行。
F12 不得让 LLM 改写 F04 结果，不得让 F04 调用 LLM 猜测下一节点，不得绕过既有边。
继续 Graph 或到达 terminal candidate，必须来自既有确定性规则。

## 14. F10 Confirmation Requirements

`TERMINAL_CANDIDATE` 只是候选。
F10 必须保留当前两阶段语义：`PREPARE` 与 `RESOLVE`。

导致 terminal candidate 的那一条用户输入，不得在同一轮被解释为“确认该事项”。

`confirmed_business_id` 只有在 terminal candidate 已经形成，且**后续**用户做出有效显式确认之后才能写入。
不得从 terminal candidate 自动确认。
不得因为模型认为用户已经同意而写入。

## 15. Session / Checkpoint / Idempotency

每个成功完成控制流的 turn，必须通过既有 checkpoint 持久化新的受控状态。
下一 turn 必须能恢复：current node、已校验槽位、candidate、confirmed business（若已有）、pending interaction state，以及 `AgentState` 中当前已有的必要状态。

`EXPLANATION_REQUEST`、`UNCERTAIN`、`LOW_CONFIDENCE` 也必须保持可继续会话。
非接受结果不得丢失 current node、pending slot 或 question context。

F12 必须尊重 F11 既有 request idempotency。
同一 `request_id` 与既有 fingerprint 的重复提交，不得重复写 slot、重复 F04、重复产生 candidate 或重复确认。
缓存与锁的机制仍由 F11 负责。

F12 不得绕过 F11 lock hierarchy。
同一 session 的并发 turn 不得造成 checkpoint lost update、状态乱序或重复 transition。

## 16. Audit / Data Policy

每个 Production turn 继续进入 F11 Audit。
审计至少能表达该 turn 成功或失败，以及当前 audit contract 已覆盖的阶段 / 结果。
不得把完整 raw `USER_FREE_TEXT`、secret、credential 写入 audit 或 checkpoint。
该禁止沿用 F11：checkpoint 与 audit 默认不保存完整历史 raw 用户原文。

失败时不得伪造业务结果，包括：Provider / runtime 失败、该轮所必需的检索失败、repository / data 失败、非法 mapping 输出、checkpoint 失败、意外 workflow 错误。
不得用 fallback 猜测 `business_id`、`next_node` 或 slot value。
具体错误码留给 TD；失败时应保留上一份有效 checkpoint 的既有 F11 语义。

## 17. Terminal Scope

`F12_TERMINAL_SCOPE = CONFIRMED_BUSINESS_ID`

`BUSINESS_KG_IN_F12 = NO`

证据：

- F10 明确不查询 materials / location / channel / legal basis，并标为 Future Knowledge capability。
- F06 明确 Business Knowledge Graph 与 Navigation 不是检索的最终答案源。
- 仓库中不存在已关闭的 Business Knowledge Feature。
- F12 当前缺口是把 F11 接到 Agent / F04 / F09 / F10。
- `confirmed_business_id` 已构成事项判定闭环。

F11 文中“完整 Demo E2E（……后续业务查询等串联）”不构成已冻结的 materials / location / channel / legal basis 交付。
本 Requirement 将其解释为：E2E 串联既有已关闭能力，而不是在 F12 新建知识查询。
`TERMINAL_SCOPE_CONFLICT = NO`。

## 18. Functional Requirements

| ID | 要求 |
|----|------|
| FR-F12-001 | Session API Production path 必须调用满足 `AgentTurnProcessor` 的 Production turn processing，而不是 Fake / Stub processor。 |
| FR-F12-002 | 业务处理前必须先按既有 checkpoint 恢复；新会话没有历史 checkpoint。 |
| FR-F12-003 | Semantic Retrieval 只在第 11 节冻结的触发条件下使用。 |
| FR-F12-004 | Decision Graph 保持确定性权威；检索与 LLM 都不能直接确认事项。 |
| FR-F12-005 | F09 非接受结果不得推进业务状态。 |
| FR-F12-006 | F09 `ACCEPTED` 结果才可以写入槽位并进入 F04。 |
| FR-F12-007 | `EXPLANATION_REQUEST` 不得改变 graph 业务状态，并在结束后恢复原问题。 |
| FR-F12-008 | terminal candidate 必须经过后续独立的显式确认，才能写入 `confirmed_business_id`。 |
| FR-F12-009 | 成功 turn 的受控状态通过既有 checkpoint 持久化，使下一 turn 可恢复。 |
| FR-F12-010 | 既有 idempotency 与 lock 语义保持有效，重复请求不重复产生业务效果。 |
| FR-F12-011 | Audit 继续生效，且不记录被禁止的 raw 用户原文或 secret。 |
| FR-F12-012 | 运行失败必须安全失败，不得发明 `next_node`、slot value 或 `business_id`。 |

## 19. Non-Functional Requirements

| ID | 要求 |
|----|------|
| NFR-F12-001 | 确定性业务权威保持不变。 |
| NFR-F12-002 | 不记录 raw credential / secret。 |
| NFR-F12-003 | 保持 F11 已有并发与幂等语义。 |
| NFR-F12-004 | 普通槽位 turn 不得无必要重复调用 LLM 或 Semantic Retrieval。 |
| NFR-F12-005 | 集成必须能在测试中替换外部依赖，且不得用替身改写 Production 业务规则。 |

本 Requirement 不规定 TPS、延迟 SLA 或可用性百分比。

## 20. Acceptance Scenarios

下列场景定义业务验收，不定义测试文件、fixture 或 mock。
除已有受控措辞外，不在本阶段编造“必然映射”的用户答案。
`service_action` 与 `payment_actor` 的自然语言样本，在 TD / Test 按当前 Graph 的 `allowed_values` 与当时已有受控语义冻结。
`employment_type` 的明确正例可使用已验证受控措辞「无雇工的个体工商户」。

### 20.1 Golden E2E

起点使用既有示例：「我辞职了，现在没单位，想自己交社保」。

必须能走到：

初始方向 / candidate
→ Decision Graph
→ 缺失槽位提问
→ 被接受的槽位回答（含 `employment_type` 的受控明确回答）
→ 确定性 F04 推进
→ terminal candidate（当前 Demo 图上对应 `DEMO_SS_001` 候选）
→ 单独的显式确认轮
→ `confirmed_business_id`。

该起点句本身不是某个槽位的唯一必达映射。

### 20.2 Ambiguity Safety

在 `employment_type` 等待回答时，用户说「平时接零活，没有固定单位」。
按当前 Business Data，该句不是自动 ACCEPT 的必然事实。
不得写 slot、不得 F04 推进、不得改变 candidate 或 confirmed business，并继续当前问题。

### 20.3 Explanation Side Route

在等待槽位时，用户问「什么叫灵活就业？」。
不得写 slot、不得 F04 推进、不得改变 candidate 或 confirmed business。
解释后恢复原 pending slot 与原问题。

### 20.4 F10 Confirmation

Turn N：最后一个仍缺的 required slot 被 `ACCEPTED`，F04 到达 terminal candidate。
此时 `confirmed_business_id` 仍为空，响应要求确认。
Turn N+1：用户显式确认，进入 F10 `RESOLVE`，此后才写入 `confirmed_business_id`。

### 20.5 Checkpoint Resume

完成若干已接受槽位后，下一请求通过 Session API 使用同一 `session_id` 恢复。
恢复后的 current node、已校验槽位、candidate 与 pending slot 必须与上一成功 turn 一致。
本阶段不要求现场重启 Redis。

### 20.6 Idempotent Replay

同一 `request_id` 与相同 `input_text` 再次提交。
业务状态只推进一次。
响应遵循 F11 既有幂等合同。
不得重复 LLM 业务效果、F04 transition 或 confirmed 写入。

## 21. Acceptance Criteria

| ID | 标准 |
|----|------|
| AC-F12-REQ01 | Production Session API 能调用真实 Production turn-processing path。 |
| AC-F12-REQ02 | 处理前恢复既有 checkpoint。 |
| AC-F12-REQ03 | 初始 Semantic Retrieval 不能直接确认事项。 |
| AC-F12-REQ04 | Graph context 建立后，普通槽位 turn 不无必要重跑检索。 |
| AC-F12-REQ05 | F09 接受的槽位回答被写入，并可进入 F04。 |
| AC-F12-REQ06 | uncertain / low-confidence 不写槽位、不调用 F04。 |
| AC-F12-REQ07 | explanation request 不改变 graph 业务状态，并恢复原问题。 |
| AC-F12-REQ08 | F04 保持确定性。 |
| AC-F12-REQ09 | terminal candidate 不写入 `confirmed_business_id`。 |
| AC-F12-REQ10 | 必须有单独的显式确认，之后才写入 `confirmed_business_id`。 |
| AC-F12-REQ11 | 下一 Session turn 能通过既有 checkpoint 恢复状态。 |
| AC-F12-REQ12 | 重放请求不重复业务效果。 |
| AC-F12-REQ13 | Audit 仍可用，且不含被禁止的 raw 内容或 secret。 |
| AC-F12-REQ14 | 运行失败不发明 `next_node`、slot value 或 `business_id`。 |
| AC-F12-REQ15 | E2E 到达冻结终点：`confirmed_business_id`，且不包含 Business Knowledge 查询。 |

## 22. Open Decisions

无阻塞性未决项。

已冻结：`F12_TERMINAL_SCOPE`、`BUSINESS_KG_IN_F12`、公开 API 不必要破坏性变更。
槽位自然语言样本的测试冻结留给 TD / Test，不改变本 Requirement 的业务权威。

## 23. Requirement Status

**APPROVED / FROZEN**

Owner Review = APPROVED。
Requirement Finalization = NOT REQUIRED。
Technical Design = NOT STARTED。
Resource Gate = CLOSED。

后续若要改变 terminal scope、Business KG inclusion、FR/NFR/AC、F11/F12 职责、F06 触发权威或 F09/F04/F10 业务边界，必须由 Owner 明确授权 Requirement Reopen / Finalization。
不得在未获该授权时进入 Technical Design。
