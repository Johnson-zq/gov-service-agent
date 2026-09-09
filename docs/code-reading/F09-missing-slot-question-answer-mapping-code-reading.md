# F09 Missing Slot / Question / Answer Mapping 代码阅读指南

缺失槽位交互、解释旁路、受控答案映射与 LangGraph 编排。

---

## 文档定位

这不是 Requirement、Technical Design，也不是 API Reference。

本文按**真实源码执行顺序**，带你从用户输入一路读到：

1. F04 确定性业务推进（`advance_until_blocked`）
2. Explanation Side Route（解释旁路，不推进业务图）

面向：项目维护、F10/F11/F12 后续开发、答辩、简历讲解、Agent/LangGraph 面试、以及几个月后重新打开项目时恢复上下文。

权威 Feature 文档：`docs/features/F09-missing-slot-question-answer-mapping.md`

| 验证项 | 结果 |
|--------|------|
| Interaction Targeted | **63 / 63 PASS** |
| Workflow Targeted | **24 / 24 PASS** |
| Combined Targeted | **87 / 87 PASS** |
| Full Regression | **469 passed / 13 skipped / 0 failed / 0 warnings** |
| Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 4；Review Fix = NOT REQUIRED） |
| Real LLM / Company network | **NOT RUN / 0** |

---

## 1. 先知道 F09 在系统里干什么

**F04** 负责 Business Decision。它已经知道：当前节点、缺什么 slot、允许什么值、问用户什么问题。

**F09** 负责理解用户**当前这句话**。例如：

- 「平时接零活，没有固定单位」→ 可能是槽位回答
- 「什么是社保转移？」→ 是解释请求，不是选择 transfer

F09 **不会**自己决定业务图走哪里。

```text
用户自然语言
        ↓
F09 理解当前 utterance
        ↓
 ┌────────────────────┐
 │                    │
真正回答槽位         解释当前概念
 │                    │
 ↓                    ↓
AnswerMapper      Local Detector
 ↓                    ↓
受控 mapping      ExplanationService
 ↓                    ↓
membership        safety guard
confidence             ↓
 ↓                  resume
ACCEPTED?
 │
 yes
 ↓
F04.advance_until_blocked
        ↓
Business Decision Graph
```

### 两个 Graph 不是一回事

| Graph | 决定什么 |
|-------|----------|
| **LangGraph（Agent）** | 调用哪个程序能力：解释 / 校验 / 推进 / resume |
| **Business Decision Graph（F04）** | 业务流程下一节点、候选事项 |

LangGraph 不会因为 `mapped_value=transfer` 就自行 `goto transfer_node`。

---

## 2. 推荐阅读顺序

| 顺序 | 文件 | 为什么 |
|------|------|--------|
| 1 | `interaction.py` | F09 的“语言”：enum、context、policy、detector、validation |
| 2 | `explanation.py` | 解释旁路的隐私边界与 Demo backend |
| 3 | `nodes.py` | 能力如何变成 LangGraph execution nodes |
| 4 | `workflow.py` | 节点如何连线；F08 默认图如何保留 |
| 5 | `__init__.py` | 稳定 Public API vs private |
| 6 | `tests/test_agent_interaction.py` | domain / security contract |
| 7 | `tests/test_agent_workflow.py` | 真实 LangGraph + 真实 F04 集成 |

**为什么先读 `interaction.py`：**
若不先理解 `UtteranceKind` / `SlotInteractionContext` / `MappingPolicy` / `ValidatedSlot`，直接读 `nodes.py` 会看不懂 `artifacts["f09"]` 里传的是什么。

---

## 3. `interaction.py` — F09 的语言

路径：`src/gov_service_agent/agent/interaction.py`

职责总览（按真实代码）：

- Enum：`UtteranceKind` / `MapperUtteranceKind` / `MappingValidationStatus` / `InteractionFailureKind`
- Models：`UtteranceInterpretation` / `AnswerMapperOutput` / `SlotInteractionContext` / `AnswerMappingRequest` / `ValidatedSlot` / `MappingValidationResult` / `InteractionFailure`
- Policy：`MappingPolicy`
- Protocol：`AnswerMapper`
- Backend：`LlmAnswerMapper`
- Validation：`validate_slot_mapping`
- Detector：`detect_explanation_request`
- Composition：`compose_*_response`
- Serialization / artifacts helpers：`serialize_*` / `merge_f09_artifacts` / `empty_f09_namespace` 等

> Note（RF-F09-003）：存在未使用 helper `interpretation_from_mapper_safe`；主链使用 `mapper_output_to_interpretation`。当前不影响功能，**本阶段不删**。

### 3.1 `UtteranceKind`：这句话是什么性质？

| 值 | 含义 | 例子 |
|----|------|------|
| `SLOT_ANSWER` | 在回答当前槽位 | System 问职工/灵活就业；User：「平时接零活，没有固定单位。」 |
| `EXPLANATION_REQUEST` | 在问当前选项含义 | System 问缴费/转移/查询；User：「什么是社保转移？」 |
| `UNCERTAIN` | 无法可靠理解 | 「我也说不清楚。」 |
| `OTHER` | 与当前槽位无关 | 当前问办理类别；User：「大厅几点下班？」——F09 不负责通用大厅问答 |

这是 **Agent 作用分类**，不是业务类目。

### 3.2 `MapperUtteranceKind`：为什么没有 `EXPLANATION_REQUEST`

Mapper 只有：`SLOT_ANSWER` / `UNCERTAIN` / `OTHER`。

解释识别权必须留在 **Local Detector**。若先把原话发给 Remote LLM 问“这是回答还是解释？”，已违反 F07：`USER_FREE_TEXT` → Company Remote = **DENY**。

### 3.3 `UtteranceInterpretation` 严格矩阵

| kind | mapped_value | confidence | explanation_topic |
|------|--------------|------------|-------------------|
| `SLOT_ANSWER` | 必填非空 | 必填 finite∈[0,1] | 必须 None |
| `EXPLANATION_REQUEST` | 必须 None | 必须 None | 必填非空 |
| `UNCERTAIN` / `OTHER` | 必须 None | 必须 None | 必须 None |

**为什么严格：** `EXPLANATION_REQUEST` 若同时带 `mapped_value=transfer`，会同时意味着“用户在提问”和“用户已选择 transfer”——危险。

### 3.4 `SlotInteractionContext`：F04 → F09 桥梁

**不是** Conversation Memory。它是一次 Slot Interaction 所需的确定性业务上下文。

来源：`build_slot_interaction_context(TransitionResult, current_slots)` —— F04 adapter。

| 字段 | 含义 |
|------|------|
| `transition_status` | 仅 `NEED_SLOT` / `INVALID_SLOT`——只有业务图需要用户输入时 F09 才介入 |
| `current_node_id` | 当前业务节点（来自 F04） |
| `required_slot` | 如 `employment_type`——来自 Business Graph，不是 LLM 猜 |
| `allowed_values` | 确定性允许集合；Mapper 只提候选，Controller 做 membership |
| `question_text` | 确定性业务问句——F09 **不让 LLM 自由生成** slot question |
| `invalid_value` | `INVALID_SLOT` 时非空；`NEED_SLOT` 时必须 None |
| `current_slots` | 已填槽位副本；ACCEPTED 后需「原 slots + 新 validated」交回 F04 |

### 3.5 `AnswerMappingRequest` / `AnswerMapper` / `LlmAnswerMapper`

```text
AnswerMappingRequest(required_slot, allowed_values, user_text)
        ↓
AnswerMapper.map_answer  （Protocol；orchestration 不绑厂商）
        ↓
LlmAnswerMapper：构造 LlmRequest → F07 Provider → parse_structured_output
        ↓
AnswerMapperOutput → mapper_output_to_interpretation → UtteranceInterpretation
```

Prompt 边界：只做当前 slot → `allowed_values` mapping；禁止输出 `next_node` / `business_id` / materials 等。

**`USER_FREE_TEXT` Classification（关键）：**
`LlmAnswerMapper` **已实现**，但注入 Company Remote 时，真实用户回答仍 **DENY before network**。因为 `LlmRequest` 明确声明 `USER_FREE_TEXT`。这是策略，不是没做完（`OI-F09-DP-001` OPEN / NON-BLOCKING）。

### 3.6 `MappingPolicy` / `validate_slot_mapping` / `ValidatedSlot`

- `MappingPolicy.min_confidence = 0.80`（frozen dataclass）——**Demo baseline**，未来需 calibration
- threshold 单一来源：不在 Prompt / Graph / Settings / node 散落

`validate_slot_mapping` 步骤：

1. 是否 `SLOT_ANSWER`？否 → `NOT_SLOT_ANSWER`
2. `mapped_value ∈ allowed_values`？否 → `INVALID_VALUE`
3. `confidence >= policy.min_confidence`？否 → `LOW_CONFIDENCE`
4. 两项 PASS → `ACCEPTED` + 创建 `ValidatedSlot`

**Membership first：** `invented_value` + confidence `1.0` → 仍 `INVALID_VALUE`。confidence 是模型自报，**不是** Business Contract。

**`AnswerMapperOutput` ≠ `ValidatedSlot`。** 只有 ValidatedSlot 可交给 F04。

### 3.7 Local Explanation Detector

真实入口：`detect_explanation_request(user_text, question_text)`

```text
user input
  → generic explanation patterns（什么是 X / X是什么意思 / 请解释一下 X …）
  → topic extraction + normalize + 长度 ≤64
  → question_text containment（Topic Trust Gate）
  → EXPLANATION_REQUEST
```

- **高精度优先于召回：**「我要办社保转移」不应误判为 Explanation
- **Generic：** 不是 `if "社保转移"`；「什么是事项A？」也可工作
- **Unknown topic：** question 不含「养老金计算」→ 不进 ExplanationService
- **Comparison deferred：**「缴费和转移有什么区别？」→ 安全 miss

### 3.8 Failure / Response Composition

`InteractionFailureKind`：

- `MAPPER_PROVIDER_ERROR` / `MAPPER_PARSE_ERROR`
- `EXPLANATION_PROVIDER_ERROR` / `EXPLANATION_PARSE_ERROR`
- `EXPLANATION_UNSAFE_OUTPUT`

**不能都叫 UNCERTAIN：**「用户说不清」≠「Provider 挂了」。

Composition 全部 **LOCAL deterministic**（`compose_explanation_response` 等）：

- 成功解释：safe text + **exact original** `question_text`
- 失败 / Uncertain / Other / Invalid / LowConfidence：固定前缀 + 原问句
LLM **不重写** slot question。

---

## 4. `explanation.py` — 如何安全解释

路径：`src/gov_service_agent/agent/explanation.py`

`interaction.py` 回答「这句话是什么性质？」；`explanation.py` 回答「若是解释请求，如何安全解释？」。

### 4.1 `ExplanationRequest` 机械隐私

```text
ExplanationRequest {
  topic            # 本地提取的受控当前业务概念（不是“脱敏用户文本”）
  public_context   # 可选 PUBLIC_BUSINESS_METADATA；Demo 常为空
}
```

**没有** `user_text` / `input_text` / `question_text` / `history` / `reasoning`。

这不是 Prompt 写“别发原话”，而是 **接口本身拿不到** 原始用户输入。

### 4.2 Status / Result / Protocol

| `ExplanationStatus` | 含义 |
|---------------------|------|
| `ANSWERED` | 有非空 text（≤500） |
| `UNSUPPORTED` | 不支持 / 不安全；`text` 必须 None |
| `UNAVAILABLE` | Provider/Parse 失败；`text` 必须 None |

`ExplanationService` Protocol：`explain(request) -> ExplanationResult`。

```text
F09 Workflow
      ↓
ExplanationService
      ↓
当前：LlmExplanationService
未来：GovernmentEncyclopediaExplanationService
      ↓
FAQ / Public RAG / Knowledge Graph → controlled facts →（可选）LLM wording
```

F09 orchestration **无需推倒重写**。

### 4.3 `LlmExplanationService` 与 Data Policy

```text
ExplanationRequest
  → controlled prompt（topic + optional public_context）
  → LlmRequest（SYSTEM_CONTROL_DATA + PUBLIC_BUSINESS_METADATA；无 USER_FREE_TEXT）
  → Provider → parse_structured_output(ExplanationStructuredOutput)
  → ExplanationResult(ANSWERED, text=...)
```

对比：

| 路径 | 输入 | Classification | Company Remote |
|------|------|----------------|----------------|
| Answer Mapping | raw `user_text` | `USER_FREE_TEXT` | **DENY** |
| Explanation | local controlled topic | ALLOW classes | **可用（Demo）** |

Remote **不发送** raw user sentence / full `question_text` / conversation history。

Strict JSON：仅 `{"explanation":"..."}`，`extra="forbid"`——不能接受 materials / location / `business_id`。Company LLM **不是** Business Knowledge Source。

### 4.4 Safety Guard（Demo）

`is_safe_explanation_text` + `_HIGH_RISK_MARKERS`（材料、携带、窗口、地址、费用、金额、时限、工作日、法律/政策依据、资格条件、符合条件、办理条件等）。

- **Whole-response fail-closed**：命中则整条不展示，不是删一句继续说
- **Guard 在 Agent node 统一执行**（`_make_explain_current_topic_node` + `_resume_current_slot_node` 二次检查）——未来换 Encyclopedia 也不能自动绕过当前 F09 guard
- RF-F09-004：这是 Demo guardrail，不是正式政策审查器；正式知识权威归未来 Encyclopedia

---

## 5. `nodes.py` — 编排节点

路径：`src/gov_service_agent/agent/nodes.py`
**不定义 Business Truth**；把 domain capability 组成 LangGraph execution nodes。

### 5.1 七个 Execution Nodes（真实符号）

| Graph 节点名 | 实现 |
|--------------|------|
| `prepare` | `_prepare_node` |
| `interpret_slot_input` | `_make_interpret_slot_input_node(deps)` |
| `explain_current_topic` | `_make_explain_current_topic_node(deps)` |
| `validate_slot_answer` | `_make_validate_slot_answer_node(deps)` |
| `advance_business_graph` | `_make_advance_business_graph_node(deps)` |
| `resume_current_slot` | `_resume_current_slot_node` |
| `complete` | `_complete_node` |

两个 pure routers：`_route_by_interpretation` / `_route_by_validation`。

### 5.2 `interpret_slot_input`（阅读重点）

1. `validate_agent_state`
2. 读 `state["input_text"]`
3. 读 controlled `slot_context`
4. **`detect_explanation_request` FIRST**（安全边界 / Data Policy，不是 UX 优化）
5. hit → `EXPLANATION_REQUEST`；**Mapper 0 call**
6. miss → `deps.answer_mapper.map_answer`
7. 已知错误：仅 catch `LlmProviderError` / `StructuredParseError` → distinct `InteractionFailureKind`；**禁止 broad catch**（编程 Bug 不能伪装成“用户不清楚”）
8. 写入 controlled `interpretation`（JSON-safe）

### 5.3 `explain_current_topic` — **0 F04**

1. 读 `explanation_topic`
2. 构造 `ExplanationRequest(topic=..., public_context={})`
3. `deps.explanation_service.explain`
4. Provider/Parse → UNAVAILABLE + failure kind
5. ANSWERED 时 **node 级** `is_safe_explanation_text`；不安全 → UNSUPPORTED + `EXPLANATION_UNSAFE_OUTPUT`
6. 写 `explanation` artifact

不 merge slots；不调用 Business Graph。

### 5.4 `validate_slot_answer`

纯 deterministic：`validate_slot_mapping` + policy。无 Provider / LLM / network / F04。

### 5.5 `advance_business_graph` — **唯一 F04 调用点**

1. 断言 `mapping_validation.status == ACCEPTED`
2. 读 `ValidatedSlot`
3. `copy.deepcopy(current_slots)` + 写入新值
4. `advance_until_blocked(deps.decision_graph, current_node_id, new_slots)`
5. `serialize_transition_result` → `business_transition`

**禁止** `if value == transfer: next_node = ...`。Business Graph 已在 F04。

序列化字段含：`status` / `current_node_id` / `required_slot` / `invalid_value` / `allowed_values` / `question_text` / `candidate_business_id` / `unsupported_reason` / `visited_node_ids` / `traversed_edge_ids`。

`candidate_business_id` 若存在，**只来自 F04**。`TERMINAL_CANDIDATE` = 候选事项 ≠ 用户已确认（**F10 未做**，故无 `confirmed_business_id`）。

### 5.6 `resume_current_slot` / `complete`

- resume：按 interpretation / explanation / failure 做本地 composition
- `complete`：**Agent invocation complete** ≠ Business complete

### 5.7 `artifacts["f09"]`

```text
artifacts
└── f09
    ├── slot_context
    ├── interpretation
    ├── mapping_validation
    ├── validated_slot
    ├── explanation
    ├── business_transition
    ├── failure
    └── response_text
```

- 为何用 namespace：F08 `AgentState` 仍 7 个 top-level fields，不为每个 Feature 加顶层字段
- JSON-safe：Enum → str；tuple → list；Pydantic → `model_dump(mode="json")`；不把 Exception / Protocol / Graph / Provider 扔进 State
- 不重复存 raw user：`AgentState.input_text` 已有
- `merge_f09_artifacts`：更新 f09 时保留其它 feature namespaces
- `run_slot_interaction_workflow`：每次 **fresh** `empty_f09_namespace`，避免上一轮 explanation/mapping/transition 污染

---

## 6. `workflow.py` — 节点如何连起来

路径：`src/gov_service_agent/agent/workflow.py`

### 6.1 F08 默认图（完全保留）

```text
START → prepare → complete → END
```

`build_agent_workflow` / `run_agent_workflow` 语义未改。F08 = Foundation；F09 = specialized capability；完整 E2E 留给 F12。

### 6.2 `SlotInteractionDependencies`（真实字段名）

| 字段 | 含义 |
|------|------|
| `answer_mapper` | `AnswerMapper` |
| `explanation_service` | `ExplanationService` |
| `decision_graph` | F04 `DecisionGraph` |
| `mapping_policy` | `MappingPolicy`（默认 0.80） |

**不进 AgentState：** Provider / Graph / Service / Policy 不是对话状态，也不可 JSON serialize。

### 6.3 F09 Specialized Topology

```text
START
  ↓
prepare
  ↓
interpret_slot_input
  ↓
 ┌─────────────────────────────────┐
 │               │                 │
Explanation   Slot Answer     Uncertain / Other
 │               │                 │
 ↓               ↓                 ↓
explain       validate            resume
 │               ↓                 │
 ↓          accepted?              │
resume       /       \              │
 │         yes       no             │
 │          ↓         ↓             │
 │        F04       resume           │
 │          ↓         ↓             │
 └──────────┴─────────┴─────────────┘
              ↓
           complete
              ↓
             END
```

- Router 1 `_route_by_interpretation`：按 `interpretation.kind`
- Router 2 `_route_by_validation`：仅 `ACCEPTED` → `advance_business_graph`
- Router **pure**：0 LLM / 0 Provider / 0 F04 / 0 network

### 6.4 `run_slot_interaction_workflow`

1. validate input state
2. deep copy（caller state / slots / artifacts 不被原地修改）
3. fresh `artifacts["f09"]` + 注入 serialized slot context
4. `build_slot_interaction_workflow(deps).invoke`
5. validate final state → return

---

## 7. `__init__.py` — Public vs Private

路径：`src/gov_service_agent/agent/__init__.py`
**不是实现文件**；定义稳定 Python API。

**Public 示例：** `UtteranceKind`、`AnswerMapper`、`LlmAnswerMapper`、`ExplanationService`、`LlmExplanationService`、`MappingPolicy`、`validate_slot_mapping`、`build_slot_interaction_context`、`SlotInteractionDependencies`、`build_slot_interaction_workflow`、`run_slot_interaction_workflow`，以及 F08 `AgentState` / `build_agent_workflow` 等。

**Private（不 export）：** `_EXPLANATION_PATTERNS`、`_HIGH_RISK_MARKERS`、node factories、routers、`detect_explanation_request`（测试可从模块导入）、prompt 拼装细节。

---

## 8. `test_agent_interaction.py` — Domain / Security Contracts

路径：`tests/test_agent_interaction.py`（**63 passed**）

主题（不逐函数抄录）：strict model matrix、confidence finite/range、context NEED_SLOT/INVALID_SLOT、mapping membership/threshold、detector 通用性 / unknown topic / comparison miss、`ExplanationRequest` 禁 raw 字段、Mapper `USER_FREE_TEXT`、Explanation ALLOW 分类、strict JSON、safety markers、composition、serialization。

**为何比“接口能跑”更重要：** F09 最大风险不是语法错误，而是**业务误推进**或**数据越权发送**。

关键断言方向：

- NaN / ±Inf reject
- invented + 1.0 → `INVALID_VALUE`
- 0.79 → `LOW_CONFIDENCE`；0.80 → 可 ACCEPTED
- generic detector；unknown topic 不进服务
- `ExplanationRequest` 拒绝 `user_text` 等
- Mapper 含 `USER_FREE_TEXT`；Explanation 不含

---

## 9. `test_agent_workflow.py` — LangGraph 真正串起来

路径：`tests/test_agent_workflow.py`（含 F08 + F09，**24 passed**）

### 9.1 Golden Explanation（核心）

Input：`什么是社保转移？`

| 断言 | 结果 |
|------|------|
| Mapper calls | **0** |
| Explanation calls | **1** |
| F04 calls | **0** |
| `validated_slot` | **None** |
| `business_transition` | **None** |
| current node preserved | **YES** |
| original question resumed | **YES** |

**为什么核心：** 证明「提到一个选项」≠「选择这个选项」。

Generic「什么是事项A？」证明 **非社保 hardcode**。

### 9.2 Remote Privacy / Question Sentinel

- raw 进入 `AgentState.input_text`
- `CapturingLlmProvider` 最终 payload **无** raw sentence
- `question_text` 放入 local-only sentinel → Remote **无**该 sentinel
- classification **无** `USER_FREE_TEXT`

### 9.3 Accepted Mapping + 真实 F04

Fake Mapper **只返回**预定 `AnswerMapperOutput`（不复制 Production NLU）。然后：

Production `validate_slot_mapping` + **真实** demo graph + **真实** `advance_until_blocked`。

F04 **不能**用假 terminal 冒充——因为架构承诺是：Business next_node 由 F04 决定。

结果可到 `TERMINAL_CANDIDATE`，`candidate_business_id=DEMO_SS_001`（来自 F04）；**无** `confirmed_business_id`（F10）。

另有：hallucinated → `INVALID_VALUE`；合法值 0.79 → no F04；Provider/Parse/Unsafe 分 failure kind；other namespace preserved / stale f09 refreshed / caller 不变 / 重复调用隔离。

---

## 10. 三条最重要代码主线

### 主线 A：Answer Path

```text
F04 NEED_SLOT
  → SlotInteractionContext
  → interpret_slot_input
  → AnswerMapper
  → AnswerMapperOutput
  → UtteranceInterpretation(SLOT_ANSWER)
  → validate_slot_mapping
  → membership → confidence >= 0.80
  → ValidatedSlot
  → advance_business_graph
  → F04.advance_until_blocked
  → TransitionResult
```

### 主线 B：Explanation Path

```text
raw input
  → interpret_slot_input
  → Local Explanation Detector
  → normalized topic
  → EXPLANATION_REQUEST
  → explain_current_topic
  → ExplanationRequest（无 raw input）
  → ExplanationService
  → strict structured result
  → local safety guard
  → resume_current_slot
  → safe explanation + original question_text
```

### 主线 C：Security Path

```text
Answer Mapping：
  raw USER_FREE_TEXT → LlmAnswerMapper → LlmRequest(USER_FREE_TEXT)
  → Company Remote → F07 DENY

Explanation：
  raw USER_FREE_TEXT → LOCAL detector → controlled topic
  → ExplanationRequest → SYSTEM_CONTROL_DATA + PUBLIC_BUSINESS_METADATA
  → Company Remote → ALLOW
```

### 主线 D：Business Authority

```text
LLM 只给 candidate value + confidence
  → Controller：membership + confidence
  → F04：business next node / candidate
  → F10（未来）：user final confirmation / confirmed_business_id
```

---

## 11. Feature 边界对照

| Feature | 职责 |
|---------|------|
| **F04** | Business deterministic transition（`advance_until_blocked`） |
| **F06** | Initial semantic retrieval；F09 **不对每轮 slot answer 做 RAG** |
| **F07** | LLM Provider / Parser / Data Policy；F09 消费不改 Policy |
| **F08** | AgentState / base LangGraph；F09 保留默认图 |
| **F09** | Missing-slot interaction + Explanation Side Route |
| **F10** | Terminal confirmation / confirmed business_id |
| **F11** | Session / Redis / checkpoint / audit |
| **F12** | E2E composition |

---

## 12. 常见误解

1. **LangGraph 决定业务流程** → 否；LangGraph 只做 orchestration。
2. **LLM confidence 高就能推进** → 否；必须 membership + threshold。
3. **「什么是社保转移？」= 选择 transfer** → 否；`EXPLANATION_REQUEST`。
4. **实现了 `LlmAnswerMapper` 就能 Company Remote** → 否；`USER_FREE_TEXT` 仍 DENY。
5. **Company LLM Explanation 是政务知识权威** → 否。
6. **`TERMINAL_CANDIDATE` = confirmed business** → 否；F10 未做。

---

## 13. 出问题时从哪里看

### 用户回答没推进

1. `interpretation.kind`
2. `mapped_value`
3. `confidence`
4. `allowed_values` membership
5. `mapping_validation.status`
6. `validated_slot`
7. `business_transition`

### 「什么是 X？」却走 Mapper

1. detector pattern
2. extracted topic
3. topic length
4. `question_text` containment
5. `interpretation.kind`

### Explanation 没显示

`ExplanationResult.status` → `failure.kind` → safety guard → `response_text`

### F04 没被调用

先看是否 `MappingValidationStatus.ACCEPTED`——不要先怀疑 Business Graph。

### Data Policy 被拒

`LlmAnswerMapper` + Company Provider → Policy DENY = **当前预期行为**，不是 Provider bug。

---

## 14. 面试时如何介绍 F09

### 30 秒

> 我把大模型从业务决策层剥离出来。业务图谱负责确定当前缺哪个槽位；LLM 只做自然语言到受控槽位的映射并给 confidence；Controller 再做 allowed-values 和置信度校验，只有通过以后才交给确定性业务图继续推进。另外专门设计了解释旁路，避免用户问「什么是社保转移」时被误判成选择转移。

### 60–90 秒

> 系统里有两张图：LangGraph 做 Agent 能力编排，Business Decision Graph（F04）做业务推进。F09 在 F04 返回 `NEED_SLOT`/`INVALID_SLOT` 之后介入。本地 detector 先识别解释意图，避免把 raw `USER_FREE_TEXT` 发给公司模型去问“这是不是解释”。真正槽位回答走 AnswerMapper，但因为声明了 `USER_FREE_TEXT`，当前 Company Remote 仍 DENY——这是 F07 策略。解释旁路则把本地抽出的受控 topic 做成没有原话字段的 `ExplanationRequest`，用 ALLOW 分类走 Demo Company LLM，再经本地 safety guard fail-closed。未来政务百科只需实现 `ExplanationService` Protocol 替换 `LlmExplanationService`，F09 workflow 不用推倒。候选事项到 `TERMINAL_CANDIDATE` 后，用户确认留给 F10。

### 追问速答

| 追问 | 要点 |
|------|------|
| 为何不用 LLM 决定 `next_node` | 政务要可控、可审计、可复现；边在 Business Graph |
| confidence 有何用 | 第二道 gate，不能代替 membership |
| 为何 detector 用 regex | Demo 要 local-first 高精度、不发 raw USER_FREE_TEXT；未来可换本地模型 |
| 为何 Explanation 可远程 | Remote 不收原句，只收本地受控 concept |
| 未来怎么接百科 | 实现 `ExplanationService`；换后端即可 |
| 为何不每轮 RAG | F06 管初始方向；槽位导航由确定性 Graph 主导 |
| F09 vs F10 | F09 理解当前回答；F10 确认最终候选事项 |

---

## 15. Review INFO / Evidence

| ID | 说明 |
|----|------|
| RF-F09-001 | `OI-F09-DP-001` OPEN / NON-BLOCKING——**不是 defect** |
| RF-F09-002 | Stage drift——已在 Explanation 文档更新 **RESOLVED** |
| RF-F09-003 | unused `interpretation_from_mapper_safe`——**DEFERRED**，不影响主链 |
| RF-F09-004 | Demo substring safety guard——accepted Demo boundary；正式权威归未来 Encyclopedia |

| Gate | Result |
|------|--------|
| Review | **PASS** |
| BLOCKING / MAJOR / MINOR | **0 / 0 / 0** |
| INFO | **4** |
| Review Fix | **NOT REQUIRED** |
| Interaction / Workflow / Combined | **63 / 24 / 87 PASS** |
| Full | **469 passed / 13 skipped / 0 failed / 0 warnings** |

---

## 16. 阅读完成后你应该能回答

1. 为什么「什么是社保转移？」不会进入 transfer
2. 为什么 Mapper 不能输出 `EXPLANATION_REQUEST`
3. 为什么 confidence=1.0 也可能 reject
4. 为什么 `ExplanationRequest` 没有 `input_text`
5. 为什么 `AnswerMapper` 当前不能直接 Company Remote
6. F09 唯一 F04 调用点在哪（`_make_advance_business_graph_node` → `advance_until_blocked`）
7. LangGraph 与 Business Graph 区别是什么
8. `candidate_business_id` 从哪里来
9. 为什么没有 `confirmed_business_id`
10. 未来政务百科替换哪个接口（`ExplanationService`）

---

## 17. Code-Reading Stage Status

| 项 | 结论 |
|----|------|
| Code-Reading | **COMPLETE** |
| Commit / Push | **NOT STARTED** |
| Next | Owner 授权后 **F09 Commit** |
| Production / Tests modified in this stage | **0 / 0** |

**STOP — Do not enter Commit / Push without Owner authorization.**
