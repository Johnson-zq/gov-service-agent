# F10 Terminal Validation / User Confirmation / Confirmed Business ID

## Stage Status

| 阶段 | 状态 |
|------|------|
| F10 Resource Gate | **CLOSED / READY** |
| F10 Requirement | **CLOSED** |
| F10 Requirement Finalization | **NOT REQUIRED** |
| F10 Technical Design | **FINAL / CLOSED** |
| F10 Technical Design Finalization | **NOT REQUIRED** |
| F10 Confirm | **COMPLETE** |
| F10 Code | **COMPLETE** |
| F10 Test | **PASS** |
| F10 Review | **PASS** |
| F10 Review Fix | **NOT REQUIRED** |
| F10 Explanation | **COMPLETE** |
| F10 Code-Reading | **COMPLETE** |
| F10 Commit | **COMPLETE** |
| F10 Push | **NOT STARTED** |

| 字段 | 内容 |
|------|------|
| Feature ID | F10 |
| Feature Name | Terminal Validation / User Confirmation / Confirmed Business ID |
| 中文定位 | 终点校验、用户最终事项确认、受控 confirmed_business_id |
| Current Stage | **Commit = COMPLETE**；Recommended Next = **Push** |
| 前置 Feature | F00–F09 = **CLOSED**；最近关闭 F09 @ `1a9d15d48e1101bebd50d00e6747c1b1ed2671b0` |
| Git Baseline | `develop` @ `1a9d15d48e1101bebd50d00e6747c1b1ed2671b0` |
| Requirement Document | `docs/features/F10-terminal-validation-user-confirmation.md` |
| Code-Reading Document | `docs/code-reading/F10-terminal-validation-user-confirmation-code-reading.md` |
| Acceptance Criteria | **56**（AC-F10-001 … AC-F10-056） |
| Technical Design Decisions | **D01–D20** |
| Final Planned Paths | **8**（8 / 8 present） |
| Code Stage Paths | **5** |
| Test Stage Paths | **7** |
| Explanation Stage Paths | **7** |
| Code-Reading Stage Paths | **8** |
| Commit Stage Paths | **8**（frozen paths 一次提交） |
| Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 3；Review Fix = NOT REQUIRED） |
| Mandatory New Dependency | **NONE** |
| PostgreSQL / Redis / Embedding / LLM | **NOT REQUIRED**（F10 Core） |

**本阶段范围：** Commit（仅 Feature Doc 状态 + 冻结 8 paths 提交）；**禁止**自动 Push。

**明确禁止自动进入：** Push。

**一句话定位：** F10 **不**负责帮用户选事项。F10 负责：接收 F04 已确定的候选事项，做确定性终点校验与最终事项确认；只有在校验允许且用户明确确认后，才生成 `confirmed_business_id`。

---

## 1. Background

项目 Canonical Flow：

```text
用户自然语言
→ Agent Orchestration（F08 foundation）
→ Semantic Retrieval（F06；方向召回）
→ Business Decision Graph（F04 deterministic）
→ Missing slots / answer mapping（F09）
→ Terminal Candidate Validation / 用户确认 / confirmed_business_id   ← F10
→ Session / Redis / Checkpoint / Audit（F11）
→ E2E Demo（F12）
→ Future Business Knowledge Graph（materials / location / channel / legal basis）
```

F04 到达 `TERMINAL_CANDIDATE` 时仅产生 `candidate_business_id`，**不**产生 `confirmed_business_id`。
F09 可将受控 `business_transition` 写入 `artifacts["f09"]`，同样**不**产生 `confirmed_business_id`。

F10 填补中间缺口：在候选事项上执行确定性终点校验，并以本地高精确认语义完成事项身份确认（Matter Identity Confirmation），而非完整资格认证（Eligibility Determination）。

---

## 2. Feature Positioning

### 2.1 负责什么

- Terminal Candidate intake（仅受控 F04 / F09 terminal result）
- Candidate existence / Business ID consistency / canonical_name 解析
- F04 Rule Selection readiness 消费（非 Rule Truth Evaluation）
- Local deterministic Final Matter Confirmation
- `confirmed_business_id` 生命周期与受控 artifact / response

### 2.2 不负责什么

- 事项推荐、语义再检索、业务再选择
- 通用 Rule Evaluator / Rule DSL / AST
- Knowledge Graph 查询（材料、地点、渠道、法律依据等）
- Redis session / checkpoint / audit（F11）
- 完整 E2E 编排（F12）

### 2.3 Ownership 冻结

| 能力 | Owner |
|------|-------|
| `candidate_business_id` | **F04**（Candidate Owner） |
| Rule Selection / Readiness | **F04**（`business_rules.selection.select_executable_rules`） |
| Rule Truth Evaluation | **NONE / DEFERRED** |
| Terminal Validation | **F10** |
| Final Matter Confirmation | **F10** |
| `confirmed_business_id` | **F10**（Confirmation Owner） |

### 2.4 Authority 公式

```text
F04:
  current_node + validated slots + predefined graph edges
  → candidate_business_id

F10:
  candidate_business_id + terminal validation + explicit user confirmation
  → confirmed_business_id
```

---

## 3. Resource Gate Summary

F10 Resource Gate = **CLOSED / READY**（只读核查已完成；Requirement 阶段对真实 symbol 做了必要复核）。

### 3.1 已确认 READY 资源

| 资源 | 状态 | 关键真实事实 |
|------|------|--------------|
| F02 Business Contract | READY | `Business.business_id`；`Business.canonical_name`；`Condition` / `ConditionExecutable`；`verification_status`；`usable_by_rule_engine` |
| F03 Terminal Candidate | READY | `TERMINAL_CANDIDATE` 节点必须具有 `candidate_business_id` |
| F04 Transition | READY | `advance_until_blocked`；`TransitionStatus.TERMINAL_CANDIDATE`；`TransitionResult.candidate_business_id`；**不**产生 `confirmed_business_id` |
| F04 Rule Selection | READY | `RuleSelectionStatus` = `NO_RULES` \| `RULES_AVAILABLE_UNEVALUATED`；owner = `select_executable_rules`；仅 `VERIFIED` + `usable_by_rule_engine=true` 可入 selected |
| Business Repository | READY | `has_business` / `get_business` / `get_snapshot` / `get_conditions` |
| Business ID Contract | READY | Graph `candidate_business_id` = TransitionResult = `Business.business_id`（同一字符串 ID contract） |
| F08 AgentState | READY | 仍为 7 top-level fields；F10 预计使用 `artifacts["f10"]`，无需强制新增 top-level field |
| F09 Terminal Artifact | READY | `artifacts["f09"]["business_transition"]` 受控字段含 `status`、`candidate_business_id` 等；**无** `confirmed_business_id` |

### 3.2 部分就绪 / 缺失

| 资源 | 状态 | 含义 |
|------|------|------|
| Rule Evaluator | **不存在** | Rule Evaluation Owner = **NONE**；F04 只做 Selection / Readiness |
| ConditionExecutable | **PARTIALLY READY** | 可提供部分 deterministic evaluation 信息（如 `Condition.field`、`normalized_values`、`operator`），但**不是**完整通用 Rule DSL / AST |
| DEMO_SS_001 | 已观测 | conditions total = 7；selected executable = 0；skipped non-executable = 7；`RuleSelectionStatus` = `NO_RULES` |

### 3.3 Infrastructure（F10 Core）

| 项 | 要求 |
|----|------|
| PostgreSQL | NOT REQUIRED |
| Redis | NOT REQUIRED |
| Embedding | NOT REQUIRED |
| F07 LLM / Company LLM | NOT REQUIRED |
| Network | NOT REQUIRED |
| New Docker / dependency / env / port | NOT REQUIRED |

### 3.4 Resource Gate Findings（回写）

| ID | Severity | 内容 |
|----|----------|------|
| **RF-F10-RG-001** | INFO | Rule Evaluator absent / ConditionExecutable 仅 PARTIALLY READY；不得在 F10 Phase-1 发明通用 Rule DSL |
| **RF-F10-RG-002** | INFO | DEMO_SS_001 = `NO_RULES`，skipped = 7；可进入事项确认，但不得描述为资格通过 |
| **RF-F10-RG-003** | INFO | `NO_RULES` enum 本身不区分「零 conditions」与「有 conditions 但零 executable」 |
| **RF-F10-RG-004** | INFO | `ConditionExecutable` 不是完整 generic Rule DSL；**不得**为此修改 F02 |

上述 INFO **不阻塞** Requirement CLOSED；**不是** defect。

---

## 4. Goals

1. 仅接受受控 `TERMINAL_CANDIDATE` 输入并 fail-closed 校验。
2. 用 Business Repository 确定性验证候选存在与 ID 一致性。
3. 展示名仅来自 `Business.canonical_name`。
4. 消费 F04 Rule Selection readiness；`RULES_AVAILABLE_UNEVALUATED` fail-closed；`NO_RULES` 允许事项确认但不伪造 eligibility PASS。
5. 本地确定性 Final Matter Confirmation（CONFIRMED / REJECTED / UNCERTAIN）。
6. 仅在校验允许且用户明确确认时，将 `confirmed_business_id` 设为 exact `candidate_business_id`。
7. 通过显式 controlled context + `artifacts["f10"]` 支持跨轮确认 capability，且不依赖 F11 Redis。
8. 保持 capability 可被 unit / integration 测试，无需新基础设施。

---

## 5. Non-Goals

见 §21 Deferred 与 §OUT OF SCOPE。摘要：

- 通用 Rule Evaluator / 新 Rule DSL / AST / Rule authoring UI
- Semantic retrieval / business re-selection
- Materials / locations / channels / legal basis / Knowledge Graph
- Redis session / checkpoint / audit / public HTTP API
- Remote LLM confirmation / ASR / DB persistence / F12 E2E

---

## 6. Architecture Invariants

| ID | 原则 |
|----|------|
| **R-INV-01** | `TERMINAL_CANDIDATE` **绝不等于** `confirmed_business_id` |
| **R-INV-02** | `candidate_business_id` 只能来自 F04 deterministic Business Decision Graph |
| **R-INV-03** | F10 **不得**重新选择 business |
| **R-INV-04** | F10 **不得**运行 Semantic RAG 重新找事项 |
| **R-INV-05** | LLM **不得**决定 candidate 是否有效 |
| **R-INV-06** | LLM **不得**决定用户是否已最终确认事项 |
| **R-INV-07** | LLM **不得**生成 `confirmed_business_id` |
| **R-INV-08** | `confirmed_business_id` 只能来源于已验证存在的 `candidate_business_id` |
| **R-INV-09** | 仅当 Terminal Validation 允许继续 **且** 用户明确确认当前 candidate 后，才能生成 `confirmed_business_id` |
| **R-INV-10** | 用户拒绝：**不得**生成 `confirmed_business_id` |
| **R-INV-11** | 用户表达模糊：**不得**生成 `confirmed_business_id` |
| **R-INV-12** | Rule Layer 只能使用 `VERIFIED` + `usable_by_rule_engine=true` 的 executable rules |
| **R-INV-13** | `TO_CONFIRM` / 未验证 / 不可执行业务条件 **不能**变成自动 Business Decision |
| **R-INV-14** | F10 **不得**修改 F04 Business Graph Authority |
| **R-INV-15** | `confirmed_business_id` 语义是「用户最终确认当前候选事项」；**不**自动等价于「用户一定符合所有办理资格条件」 |

补充：

- Matter Identity Confirmation ≠ Eligibility Determination。
- F10 Phase-1 主要完成前者；Rule Layer 只执行系统当前已具备的 verified executable capability；无 executable rule 时不得伪造 eligibility PASS。

---

## 7. Input Boundary

### 7.1 允许输入

F10 的候选事项输入**必须**来自：

1. F04 `TransitionResult`（`status = TERMINAL_CANDIDATE`），或
2. F09 已序列化的 controlled `business_transition`（由 `serialize_transition_result` 产生的受控字段集）

### 7.2 禁止输入

- LLM raw output
- RAG similarity result
- 用户自己输入的 `business_id`
- 未验证 arbitrary dict

### 7.3 Terminal Candidate Intake

进入 F10 前至少必须满足：

- `status = TERMINAL_CANDIDATE`
- `candidate_business_id` = nonblank

否则：**fail closed**；不得进入 confirmation；不得生成 `confirmed_business_id`。

---

## 8. Terminal Validation Requirements

F10 Terminal Validation **至少**包含：

| # | 校验项 | 失败行为 |
|---|--------|----------|
| A | Terminal status contract（必须为 `TERMINAL_CANDIDATE`） | fail closed；不进入 confirmation |
| B | candidate ID presence（nonblank） | fail closed |
| C | candidate existence（Business Repository） | fail closed；不得询问用户确认无效事项 |
| D | Business ID consistency（`Business.business_id` exact match `candidate_business_id`） | fail closed |
| E | 可用于用户确认的 `canonical_name`（来自 Business Data；可靠非空） | 缺失则 fail closed；不得由 LLM 生成名称 |
| F | F04 Rule Selection readiness | 见 §9–§11 |

用户确认**不能**绕过上述 deterministic validation：即使用户说「确认」，若 Terminal Validation 不允许，`confirmed_business_id` 仍为 `None`。

---

## 9. Rule Selection / Evaluation Boundary

### 9.1 Phase-1 冻结

- **不实现**通用 deterministic Rule Evaluator。
- **不发明**新的通用 Rule DSL / AST。
- Generic Rule Evaluation = **DEFERRED**。
- 原因：当前 `ConditionExecutable` contract 未形成完整通用 DSL；贸然实现会产生未授权业务规则语义。

### 9.2 当前 Ownership

| 角色 | 状态 |
|------|------|
| Rule Selection Owner | F04（`select_executable_rules`） |
| Rule Evaluation Owner | **NONE / DEFERRED** |
| Terminal Confirmation Owner | F10 |
| Confirmed Business ID Owner | F10 |

### 9.3 Selection 消费规则

- F10 使用 F04 Rule Selection 作为 readiness source。
- 只有 `verification_status = VERIFIED` 且 `usable_by_rule_engine = true` 的 executable 才能进入 selected rules（由 F04 已保证；F10 不得放宽）。

---

## 10. NO_RULES Semantics

当 `RuleSelectionStatus = NO_RULES`：

**正确语义：** 当前没有被选中的 VERIFIED executable rule 可由当前 Rule Engine 执行。

**禁止语义：**

- 「规则全部通过」
- 「用户符合资格」
- 「eligibility PASS」

**Phase-1 行为：**

- **允许**继续进入 Matter Confirmation。
- 原因：F10 当前确认的是「用户最终要办理哪个事项」，不是完整资格认证。
- 必须保留：Rule Evaluation Performed = **NO**。
- 不得向用户说：「您符合办理条件」。

**DEMO_SS_001 特化说明：**

- 7 conditions；0 selected executable；7 skipped → `NO_RULES`。
- F10 可继续用户事项确认。
- **不得**描述为「7 条规则全部满足」。
- `NO_RULES` enum 本身不区分「零 conditions」与「有 conditions 但零 executable」（RF-F10-RG-003）。

---

## 11. RULES_AVAILABLE_UNEVALUATED Semantics

当 `RuleSelectionStatus = RULES_AVAILABLE_UNEVALUATED`：

含义：存在 VERIFIED + usable 的 executable rule，但当前**没有** deterministic evaluator 完成 truth evaluation。

**Phase-1 必须 FAIL CLOSED：**

- **不得**创建 `confirmed_business_id`
- **不得**把 UNEVALUATED 当成 PASS
- **不得**完成最终事项确认
- 应产生受控语义：「当前存在尚未完成确定性校验的业务规则，暂不能完成最终事项确认」

具体 Enum 名与 response wording：**留 Technical Design**。Requirement 语义在此冻结。

### 11.1 未来 Rule Evaluator 边界（原则冻结，实现 Deferred）

| 未来结果 | F10 行为 |
|----------|----------|
| deterministic FAIL | **不得**产生 `confirmed_business_id`（即使用户回答「确认」） |
| UNKNOWN / NEED_INPUT / NOT_EVALUATED 或等价未确定 | **不得**当 PASS；`confirmed_business_id` 必须 `None` |

未来引入完整 evaluator 前，必须另行冻结：Rule DSL / operator semantics、facts contract、unknown semantics、multi-condition / AND-OR semantics、missing facts、evaluation trace、versioning。F10 当前 Requirement **不发明**这些规则。

---

## 12. User Confirmation Requirements

### 12.1 确认性质

F10 必须拥有明确的 **Final Matter Confirmation** 语义；**不是**普通 slot mapping。

不得假定 F09 `LlmAnswerMapper` 可直接判断「确认 / 不确认」。真实用户输入属于 `USER_FREE_TEXT`；Company Remote = DENY；F10 Core = **0 Remote LLM dependency**。

### 12.2 解释方式（Phase-1）

Confirmation interpretation 必须：

- **LOCAL**
- **DETERMINISTIC**
- **HIGH PRECISION**

### 12.3 三个核心语义类别

| 语义 | 含义 | `confirmed_business_id` |
|------|------|-------------------------|
| **CONFIRMED** | 用户明确、直接确认当前 candidate | 仅当 Terminal Validation 已允许时 = exact `candidate_business_id` |
| **REJECTED** | 明确否定当前 candidate | `None` |
| **UNCERTAIN** | 模糊 / 冲突 / 仅复述名称等不足以确认 | `None`；pending candidate 保持 |

具体 enum class 名：**留 TD**。

### 12.4 CONFIRMED

- 仅明确确认当前 candidate（例如「确认」「是的，就是这个」属可支持语义）。
- 具体 allowlist / pattern：**留 TD**。
- 必须存在明确确认语义；**不得**仅因用户重复 candidate name 自动确认。

### 12.5 REJECTED

- 例如：「不确认」「不是这个」「我办的不是这个」。
- `confirmed_business_id = None`。
- F10 **不得**自行重新搜索另一个 business。
- 下一步是否重新做 Semantic Retrieval / 重进 Business Graph / 回上层 Agent：属于 **F12 / 上层 orchestration**；F10 不自行决定。

### 12.6 UNCERTAIN

- 例如：「好像是吧」「应该是」「不太确定」「随便」。
- **不得** CONFIRMED。
- 保持 pending candidate；返回受控确认提示。
- 不调用 RAG；不调用 F04 重新选业务。

### 12.7 高精门禁

| 情况 | 要求 |
|------|------|
| 用户只回答事项名称「XXX」 | **不得**仅因此自动 CONFIRMED |
| 一句话同时含确认与否定/不确定 | **不得**自动 CONFIRMED；必须 UNCERTAIN 或 fail closed（解析优先级留 TD） |
| 用户说「确认另一个事项」 | **不得**直接改 `business_id`；confirmation 只针对当前已通过 Terminal Validation 的 candidate |

---

## 13. Confirmed Business ID Lifecycle

### 13.1 默认

`confirmed_business_id = None`

### 13.2 赋值条件（全部满足）

1. valid `TERMINAL_CANDIDATE`
2. candidate exists（Repository）
3. ID consistency PASS
4. terminal validation permits confirmation
5. Rule Selection **不处于** `RULES_AVAILABLE_UNEVALUATED`
6. 用户 explicit **CONFIRMED**

然后且仅然后：

`confirmed_business_id = candidate_business_id`（**exact propagation**）

### 13.3 禁止变换

- 不得生成新的 ID
- 不得 normalize 成另一个业务 ID
- 不得根据 synonym 替换业务 ID
- 必须 exact candidate ID propagation

### 13.4 语义边界

- Confirmed Business ID Owner = **F10**
- 用户确认 ≠ 规则通过；validation 未允许时用户「确认」无效
- `confirmed_business_id` 可作为未来 Knowledge Graph 的稳定入口，但 F10 **不**自动启动 Knowledge Graph

---

## 14. Response Requirements

### 14.1 Confirmation Prompt

- 必须 **LOCAL / deterministic template**
- 核心内容至少：`Business.canonical_name` + 明确 yes/no confirmation request
- **不得**由 LLM 自由生成
- 具体中文 wording：**TD 冻结**

Golden 提示语义示例（Requirement 可用真实 `canonical_name`，不创造新官方名称）：

> 当前候选办理事项为「灵活就业人员社会保险费申报缴费」，请确认是否办理该事项

### 14.2 Prompt 不得包含办理事实

不得提前加入：材料、办理地点、办理渠道、法律依据、办理费用、办理时限。这些属于 `confirmed_business_id` 之后的 Knowledge capability。

### 14.3 顺序冻结

```text
F10 confirmed_business_id
        ↓
Future Business Knowledge Graph
        ↓
materials / location / channel / legal basis / etc.
```

不得倒过来。

---

## 15. State / Artifact Requirements

### 15.1 AgentState

- F10 **不要求**新增 AgentState top-level field
- 继续使用 `artifacts["f10"]`
- AgentState 保持 **7** top-level fields：`request_id` / `input_text` / `phase` / `status` / `artifacts` / `error` / `orchestration_trace`
- 具体 artifact 结构：**TD 冻结**

### 15.2 Controlled Artifact 语义要求

虽具体 Pydantic model 留 TD，但 `artifacts["f10"]` 必须能表达至少：

- terminal input / context
- `candidate_business_id`
- candidate `canonical_name`
- terminal validation status
- rule selection / readiness status
- confirmation status
- `confirmed_business_id`
- failure / status metadata
- `response_text`

### 15.3 禁止内容

- 不得存 provider / graph / repository / exception object
- 默认不得无意义重复保存 raw confirmation text（`AgentState.input_text` 已含当前输入）；只保存 controlled confirmation interpretation
- artifact 必须 JSON-safe

### 15.4 跨轮 Confirmation

最终确认天然可能跨两轮。F10 capability **不依赖** F11 Redis 才能成立；可通过显式 controlled confirmation context + 下一轮 user input 执行。F11 未来负责 Session / Redis / Checkpoint / Audit / 跨 HTTP request 持久化。

---

## 16. F04 / F06 / F07 / F08 / F09 / F11 / F12 Boundaries

| Feature | 边界 |
|---------|------|
| **F04** | Candidate Owner；Transition / Rule Selection；不产生 `confirmed_business_id`；F10 不计算 `next_node`、不修改 F04 authority |
| **F06** | 仅负责前面的 semantic direction / candidate retrieval；F10 Core **0** F06 调用 |
| **F07** | F10 Core **不是** required dependency；`USER_FREE_TEXT` remote policy 不变 |
| **F08** | Agent State / base LangGraph foundation；F10 复用 state / artifact pattern |
| **F09** | 缺失槽位问答与解释旁路；可产生 candidate business transition；**不**产生 confirmed business |
| **F10** | 只做 terminal validation / final matter confirmation / confirmed business ID |
| **F11** | session / persistence；不属于 F10；F10 不得以「还没有 Redis」依赖 F11 |
| **F12** | 将 F06/F04/F09/F10/F11 串成 E2E；F10 不做完整 E2E |

### Topology / Class 名

本 Requirement **不**提前冻结：

- F10 是几个 nodes / routers / specialized graph / service+graph
- 新 class 名 / 新 enum class 名 / 新 file/module 名（Feature Doc 路径除外）

只要求：行为可被 deterministic orchestration。具体留 Technical Design。

---

## 17. Golden Scenarios

### 17.1 Golden Positive（AC-F10-051 / 052）

```text
F09 accepted slot answer
        ↓
F04.advance_until_blocked
        ↓
TERMINAL_CANDIDATE
        ↓
candidate_business_id = DEMO_SS_001
        ↓
F10 validates:
  terminal status
  candidate presence
  repository existence
  business ID
  canonical_name（灵活就业人员社会保险费申报缴费）
  rule selection
        ↓
RuleSelectionStatus = NO_RULES
        ↓
注意：不是 eligibility PASS
        ↓
允许进入事项确认
        ↓
System:
  当前候选办理事项为「灵活就业人员社会保险费申报缴费」
  请确认是否办理该事项
        ↓
User: 「确认」
        ↓
deterministic confirmation = CONFIRMED
        ↓
confirmed_business_id = DEMO_SS_001
```

### 17.2 Golden Reject（AC-F10-053）

同一 candidate。User：「不是这个」→ confirmation = REJECTED；`confirmed_business_id = None`；F10 不重新选业务。

### 17.3 Golden Uncertain（AC-F10-054）

User：「好像是吧」→ UNCERTAIN；`confirmed_business_id = None`；pending candidate 保持。

### 17.4 Rule Unevaluated

若某 candidate `RuleSelectionStatus = RULES_AVAILABLE_UNEVALUATED`，即使用户说「确认」，`confirmed_business_id = None`（Terminal Validation 未通过）。

### 17.5 Candidate Missing

`status = TERMINAL_CANDIDATE` 但 `candidate_business_id` 不存在或空 → fail closed。

### 17.6 Candidate Repository Mismatch / Not Found

`candidate_business_id` 无法 lookup → Data Consistency Failure；fail closed；**不**询问用户是否确认。

---

## 18. Failure Semantics

F10 必须能区分至少：

| 受控失败类别（语义） | 要点 |
|----------------------|------|
| Invalid terminal context | 非 `TERMINAL_CANDIDATE` 等；不进入 confirmation |
| Candidate missing | blank / 缺失 ID |
| Candidate not found | Graph 有 ID 但 Repository 不存在；Data Consistency Failure |
| Candidate ID mismatch | Repository 返回的 `Business.business_id` 与 candidate 不一致 |
| Canonical name missing / unreliable | fail closed；不用 LLM 生成名称 |
| Rule evaluation required（UNEVALUATED） | 阻断确认 |
| Confirmation rejected | `confirmed = None` |
| Confirmation uncertain | `confirmed = None`；pending 保持 |
| Success confirmed | 仅全部门禁通过 |

具体 enum 名：**TD 冻结**。

**Programming Error：** 业务可预期失败使用受控结果；unexpected programming error **不能**全部吞成 UNCERTAIN。具体 exception strategy：**TD**。Requirement 原则：禁止 broad-swallow。

---

## 19. Data / Security Requirements

- 无强制 PostgreSQL / Redis / Embedding / LLM / Network / 新依赖 / 新 env / 新 port / 新 Docker
- 使用现有 deterministic Business Repository
- 日志不得记录明文身份证、手机号、证件全文、密钥、Token 等敏感信息（项目通用规则）
- Feature Doc / 实现不得写入真实 Company endpoint、API key、Authorization、真实 model id、DB password、token
- Secret Gate：本 Requirement 文档合规（无上述秘密）

---

## 20. Acceptance Criteria

### Terminal Input

| ID | 准则 |
|----|------|
| **AC-F10-001** | 只有 `TERMINAL_CANDIDATE` 可进入正常 F10 terminal flow |
| **AC-F10-002** | `candidate_business_id` 必须 nonblank |
| **AC-F10-003** | candidate ID 必须来自受控 F04/F09 terminal result |
| **AC-F10-004** | 不能接受用户直接提交任意 `business_id` 作为确认依据 |
| **AC-F10-005** | invalid terminal context 不得进入 confirmation |
| **AC-F10-006** | invalid terminal context 不得生成 `confirmed_business_id` |

### Candidate Validation

| ID | 准则 |
|----|------|
| **AC-F10-007** | candidate 必须在 Business Repository 存在 |
| **AC-F10-008** | `Business.business_id` 必须与 candidate exact match |
| **AC-F10-009** | `canonical_name` 必须来自 Business Data |
| **AC-F10-010** | candidate not found → fail closed |
| **AC-F10-011** | candidate mismatch → fail closed |
| **AC-F10-012** | LLM 不得生成/修正 candidate ID |

### Rule Layer

| ID | 准则 |
|----|------|
| **AC-F10-013** | 使用 F04 Rule Selection 作为 readiness source |
| **AC-F10-014** | 只有 VERIFIED + usable executable 可进入 selected rules |
| **AC-F10-015** | `NO_RULES` 不得解释为 eligibility PASS |
| **AC-F10-016** | `NO_RULES` 在 Phase-1 允许进入事项确认 |
| **AC-F10-017** | `NO_RULES` 下系统不得声称「符合办理条件」 |
| **AC-F10-018** | `RULES_AVAILABLE_UNEVALUATED` 不得当 PASS |
| **AC-F10-019** | `RULES_AVAILABLE_UNEVALUATED` 不得产生 `confirmed_business_id` |
| **AC-F10-020** | Phase-1 不得发明通用 Rule DSL 实现 evaluator |

### Confirmation

| ID | 准则 |
|----|------|
| **AC-F10-021** | confirmation interpretation local deterministic |
| **AC-F10-022** | Core 不使用 Remote LLM |
| **AC-F10-023** | 必须支持 CONFIRMED semantic |
| **AC-F10-024** | 必须支持 REJECTED semantic |
| **AC-F10-025** | 必须支持 UNCERTAIN semantic |
| **AC-F10-026** | 只有 explicit confirmation 可 CONFIRMED |
| **AC-F10-027** | 模糊表达不得 CONFIRMED |
| **AC-F10-028** | 冲突确认表达不得 CONFIRMED |
| **AC-F10-029** | 单纯重复事项名称不得自动 CONFIRMED |

### Confirmed Business ID

| ID | 准则 |
|----|------|
| **AC-F10-030** | 默认 `confirmed_business_id = None` |
| **AC-F10-031** | 只有 terminal validation permitted 且 explicit CONFIRMED 才产生 |
| **AC-F10-032** | `confirmed_business_id` 必须 exact 等于 validated `candidate_business_id` |
| **AC-F10-033** | 不得创建新 ID |
| **AC-F10-034** | REJECTED → confirmed = None |
| **AC-F10-035** | UNCERTAIN → confirmed = None |
| **AC-F10-036** | Rule unevaluated 即使用户说确认也 confirmed = None |

### Response / State

| ID | 准则 |
|----|------|
| **AC-F10-037** | confirmation question 使用 deterministic local template |
| **AC-F10-038** | business name 来自 `canonical_name` |
| **AC-F10-039** | F10 artifacts 必须 JSON-safe |
| **AC-F10-040** | 不把 provider/repository/graph/exception 存入 State |
| **AC-F10-041** | 不重复保存 raw user confirmation 到 artifacts |
| **AC-F10-042** | AgentState top-level 保持 7 fields |

### Architecture

| ID | 准则 |
|----|------|
| **AC-F10-043** | F10 不重新运行 RAG |
| **AC-F10-044** | F10 不自行选择其它 business |
| **AC-F10-045** | F10 不计算 F04 `next_node` |
| **AC-F10-046** | F10 不修改 F04 authority |
| **AC-F10-047** | F10 不查询 materials/location/channel/legal basis |
| **AC-F10-048** | F10 不依赖 Redis 完成 capability tests |
| **AC-F10-049** | F10 不依赖 PostgreSQL 完成 Demo core |
| **AC-F10-050** | F10 不依赖新增 infra/dependency/env/port |

### Golden / Future

| ID | 准则 |
|----|------|
| **AC-F10-051** | DEMO_SS_001 可以：`NO_RULES` → confirmation |
| **AC-F10-052** | Golden explicit confirm 产生 confirmed `DEMO_SS_001` |
| **AC-F10-053** | Golden reject 不产生 confirmed ID |
| **AC-F10-054** | Golden uncertain 不产生 confirmed ID |
| **AC-F10-055** | confirmed ID 可作为未来 Knowledge Graph 稳定入口 |
| **AC-F10-056** | F10 不自动启动 Knowledge Graph |

**Acceptance Criteria Count = 56。**

---

## 21. Deferred Scope

### IN SCOPE（Requirement）

- Terminal Candidate validation
- Business existence validation
- Business canonical name resolution
- Rule Selection readiness consumption
- `NO_RULES` semantics
- `RULES_AVAILABLE_UNEVALUATED` fail-closed
- Local deterministic confirmation
- Confirmed Business ID lifecycle
- Controlled artifacts
- Response semantics
- Unit / integration-testable capability boundary

### OUT OF SCOPE

- General Rule Evaluator
- New Rule DSL / Rule AST / Rule authoring UI
- Semantic retrieval / Business re-selection
- Materials / Handling locations / Channels / Legal basis
- Knowledge Graph query
- Redis session / Checkpoint / Audit
- Public HTTP API
- Real remote LLM confirmation
- ASR
- Database persistence
- F12 E2E

### Deferred Items

| ID | 内容 |
|----|------|
| **DF-F10-001** | Generic deterministic Rule Evaluator |
| **DF-F10-002** | Complete executable rule DSL / AST |
| **DF-F10-003** | Cross-request persistence → F11 |
| **DF-F10-004** | Automatic upstream re-entry after rejection → F12 orchestration |
| **DF-F10-005** | Knowledge Graph lookup after confirmation |

---

## 22. Open Items

### Requirement-Level Open Items

**Count = 0。**

核心语义（`NO_RULES` 是否可确认、`RULES_AVAILABLE_UNEVALUATED` 是否阻断、`confirmed_business_id` 产生条件、confirmation semantics、F04/F10 authority）均已在本 Requirement 冻结。
→ **Requirement Finalization = NOT REQUIRED。**

### Design-Level Open Items

| ID | 状态 | 决议 |
|----|------|------|
| **OI-F10-001** | **RESOLVED** | Specialized LangGraph capability（`build_terminal_confirmation_workflow`）；domain 逻辑独立于图以便单测；不修改 F08 default workflow |
| **OI-F10-002** | **RESOLVED** | Exact normalized positive/negative allowlist（见 D09）；其它一律 UNCERTAIN；禁止 substring/`contains` 匹配 |
| **OI-F10-003** | **RESOLVED** | `artifacts["f10"]` exact layout（见 D14） |
| **OI-F10-004** | **RESOLVED** | `RuleReadinessSnapshot` 仅保留 selection_status / selected_rule_count / skipped_non_executable_count / evaluation_performed |
| **OI-F10-005** | **RESOLVED** | D16 deterministic 中文 templates |
| **OI-F10-006** | **RESOLVED** | D20 最小 Public API surface |

**New TD Open Items：** 无（OI-F10-TD-* = 0）。

---

## 23. Requirement Closure

| 检查项 | 结果 |
|--------|------|
| 56+ AC | **56** |
| 核心语义全部冻结 | **YES** |
| Requirement-Level unresolved | **0** |
| Generic Rule Evaluator in Phase-1 | **NO**（Deferred） |
| New Rule DSL invented | **NO** |
| Resource Gate INFO 回写 | RF-F10-RG-001 … 004 |
| Production / Tests 修改（Requirement 阶段） | **NONE** |

**判定（Requirement 阶段，历史冻结）：**

- F10 Requirement = **CLOSED**
- Requirement Finalization = **NOT REQUIRED**

---

## 24. Technical Design

### 24.0 TD 前真实 API 复核（只读）

| 区域 | 真实事实（源码为准） |
|------|----------------------|
| F02 `Business` | `business_id: str`；`canonical_name: str`（non-empty validators） |
| F02 `Condition` / `ConditionExecutable` | `executable.operator`；`verification_status`；`usable_by_rule_engine` |
| F02 `VerificationStatus` | `str, Enum`（含 `VERIFIED` 等） |
| Repository | **无**现成 `BusinessRepository` Protocol / ABC；仅有 `JsonBusinessRepository` |
| Repository API | `has_business(business_id) -> bool`；`get_business(business_id) -> Business`；`get_snapshot`；`get_conditions(business_id, *, consumption=...)`；未知 ID → `BusinessNotFoundError` |
| F03 | `NodeType.TERMINAL_CANDIDATE` 要求 non-empty `candidate_business_id` |
| F04 Transition | `TransitionStatus.TERMINAL_CANDIDATE`；`TransitionResult.candidate_business_id`；**无** `confirmed_business_id`；`advance_until_blocked(...)` |
| F04 Rule Selection | 见下方真实签名 |
| F08 | `AgentState` 7 fields；`create_initial_state`；`validate_agent_state`；`artifacts: dict[str, JsonValue]` |
| F09 pattern | `SlotInteractionDependencies`（frozen dataclass）；`build_slot_interaction_workflow`；`run_slot_interaction_workflow`；fresh `artifacts["f09"]`；deepcopy；`serialize_transition_result` 字段集 |

**真实 `select_executable_rules` 签名（禁止发明）：**

```python
def select_executable_rules(
    business_id: str,
    repository: JsonBusinessRepository,
) -> RuleSelectionResult
```

**真实 `RuleSelectionResult` fields：**

- `business_id: str`
- `status: RuleSelectionStatus`（`NO_RULES` \| `RULES_AVAILABLE_UNEVALUATED`）
- `selected_rule_ids: list[str]`
- `skipped_non_executable_count: int`（`ge=0`）

**F04 ownership 保持：** F10 **不得**复制 `_is_executable_verified` / VERIFIED+usable 过滤逻辑；只调用该 selector（或 Production 默认指向它的 callable）。

---

### 24.1 Technical Design Decisions（D01–D20）

#### D01 — Specialized LangGraph Capability；保留 F08 default

- F10 = **Specialized LangGraph Capability**
- **不修改** F08 default：`START → prepare → complete → END`（`build_agent_workflow` / `run_agent_workflow`）
- 新增：`build_terminal_confirmation_workflow(deps)`
- Domain / deterministic services 放在 `agent/terminal.py`，**独立于** LangGraph，便于单测
- F12 未来总编排；F10 不做 E2E
- **OI-F10-001 = RESOLVED**

#### D02 — PREPARE vs RESOLVE 两阶段

| Mode | 输入 | 行为 | `input_text` |
|------|------|------|--------------|
| **PREPARE** | controlled `TerminalCandidateContext` | terminal validation + rule readiness + confirmation prompt | **绝不**作为 confirmation answer 解释（即使值为「确认」） |
| **RESOLVE** | 同一 controlled context + **新一轮** `AgentState.input_text` | **重新** terminal validation + local confirmation interpretation | 本轮 confirmation utterance |

原因：F09 刚到 `TERMINAL_CANDIDATE` 时的 `input_text` 通常是 slot answer（如「平时接零活，没有固定单位」），绝不能被当成事项确认。

RESOLVE 必须重新 validation（existence / ID / canonical_name / rule readiness），不单信上一轮 `AWAITING_CONFIRMATION` artifact（防 stale / forged / mismatched）。

Tests 可用 Invocation A（PREPARE）+ Invocation B（new input + same context → RESOLVE）；**0 Redis / checkpoint**。

#### D03 — `TerminalCandidateContext`

冻结类名：**`TerminalCandidateContext`**

- Pydantic `BaseModel`；`model_config = ConfigDict(extra="forbid", frozen=True)`（对齐 F09 `SlotInteractionContext`）
- 字段：
  - `transition_status: TransitionStatus` — 必须为 `TERMINAL_CANDIDATE`，否则 fail closed
  - `current_node_id: str` — nonblank
  - `candidate_business_id: str` — **strict nonblank**（禁止 `None` / blank）
  - `visited_node_ids: tuple[str, ...]` — non-empty；末元素 = `current_node_id`
  - `traversed_edge_ids: tuple[str, ...]` — `len == len(visited_node_ids) - 1`
- **不携带：** raw user text / LLM result / provider / repository

**Factories（唯一受控构建入口）：**

| Factory | 输入 | 行为 |
|---------|------|------|
| `build_terminal_candidate_context(result: TransitionResult) -> TerminalCandidateContext` | 真实 F04 `TransitionResult` | 非 `TERMINAL_CANDIDATE` 或 blank candidate → raise / fail closed |
| `terminal_candidate_context_from_business_transition(payload: Mapping[str, Any]) -> TerminalCandidateContext` | F09 `serialize_transition_result` 形状 | 严格校验 known fields / values；只取 terminal-safe subset：`status`→`transition_status`、`current_node_id`、`candidate_business_id`、`visited_node_ids`、`traversed_edge_ids`；**拒绝**任意 user dict |

F09 adapter **不**把全部 F09 artifact 当作 F10 State。

#### D04 — `TerminalValidationStatus`

冻结 exact values：

| Value | 含义 |
|-------|------|
| `READY_FOR_CONFIRMATION` | Phase-1 全部门禁通过（含 Rule Selection = `NO_RULES`） |
| `INVALID_TERMINAL_CONTEXT` | 非 terminal / blank candidate / context 契约失败 |
| `CANDIDATE_NOT_FOUND` | Repository 不存在该 ID |
| `CANDIDATE_ID_MISMATCH` | `Business.business_id` ≠ candidate |
| `CANONICAL_NAME_UNAVAILABLE` | 缺少可靠 nonblank `canonical_name` |
| `RULES_UNEVALUATED` | F04 `RULES_AVAILABLE_UNEVALUATED` |

**READY_FOR_CONFIRMATION 条件（全部）：** terminal status + candidate nonblank + repo exists + ID exact match + usable canonical_name + Rule Selection = **`NO_RULES`**。

`RULES_AVAILABLE_UNEVALUATED` → **`RULES_UNEVALUATED`**；不得 `AWAITING_CONFIRMATION`；不得 `CONFIRMED`。

另冻结结果模型：**`TerminalValidationResult`**（extra-forbid / frozen），至少含：`status`、`candidate_business_id`、`canonical_name: str | None`、以及关联的 readiness 引用字段（或由 artifact 并列存放 readiness）。

#### D05 — `RuleReadinessSnapshot`

冻结类名：**`RuleReadinessSnapshot`**（extra-forbid / frozen）

| Field | 语义 |
|-------|------|
| `selection_status: RuleSelectionStatus` | F04 selection 原样 |
| `selected_rule_count: int` | `len(selected_rule_ids)`；**不**存完整 rule objects / Condition objects |
| `skipped_non_executable_count: int` | 来自 F04 result |
| `evaluation_performed: bool` | Phase-1 **恒为 `False`** |

**禁止：** `eligibility_pass=true`；`NO_RULES` **不得**转换为 PASS。selection ≠ evaluation。

**OI-F10-004 = RESOLVED**

#### D06 — `NO_RULES` Mapping

F04 `NO_RULES` → Snapshot：`selected_rule_count=0`，`evaluation_performed=False`，保留 `skipped_non_executable_count`（DEMO_SS_001 预期 skipped=**7**）→ Validation **`READY_FOR_CONFIRMATION`**。

#### D07 — `RULES_AVAILABLE_UNEVALUATED` Mapping

F04 contract：`selected_rule_ids` 必须 non-empty。F10：Validation=`RULES_UNEVALUATED`；`ConfirmationStatus=BLOCKED`；`confirmed_business_id=None`。即使用户说「确认」也不确认。

**不实现** RuleEvaluator / Rule AST / Rule DSL / operator 求值。

#### D08 — `ConfirmationIntent`

冻结 exact：`CONFIRMED` | `REJECTED` | `UNCERTAIN`（`StrEnum`）。仅表示 utterance 本地解释，**不是** Business decision。

#### D09 — Local Deterministic Confirmation Parser

冻结函数：**`interpret_confirmation(user_text: str) -> ConfirmationIntent`**

- LOCAL / SYNC / DETERMINISTIC / ZERO NETWORK / ZERO LLM / HIGH PRECISION
- **不**接受 `canonical_name` 参数（避免名称复述抬高确认概率）
- Matching：**exact normalized match only**；**禁止** `contains("确认")` / `contains("是")`

**Normalization（保守）：**

1. Unicode **NFKC**
2. trim leading/trailing whitespace
3. collapse repeated whitespace → single space
4. strip **仅** leading/trailing 常见 ASCII / 中文标点（如 `。．.!！?？,，、;；:："'""''（）()[]【】`）
5. **不得**删除内部「不/否/没/别」等否定信息
6. **不得** semantic rewriting

**Exact normalized POSITIVE set（最终冻结）：**

```text
确认
确认办理
是的
就是这个
没错
```

**Exact normalized NEGATIVE set（最终冻结）：**

```text
不确认
不办理
不是
不是这个
不是这个事项
不是我要办的
我办的不是这个
不对
```

**Default：** 不在上述集合 → **`UNCERTAIN`**（覆盖：好像是吧 / 应该是 / 好的 / 行 / 可以 / 嗯 / 对 / candidate canonical_name / 「确认，但是我不太确定」等）。

过宽词（好的/好/行/可以/嗯/对）**故意不纳入** POSITIVE。

**OI-F10-002 = RESOLVED**

#### D10 — `ConfirmationStatus`

冻结 lifecycle enum：`AWAITING_CONFIRMATION` | `CONFIRMED` | `REJECTED` | `UNCERTAIN` | `BLOCKED`

| 场景 | status | intent | confirmed_business_id |
|------|--------|--------|------------------------|
| PREPARE + READY | `AWAITING_CONFIRMATION` | `None` | `None` |
| PREPARE + blocking validation | `BLOCKED` | `None` | `None` |
| RESOLVE + READY + CONFIRMED | `CONFIRMED` | `CONFIRMED` | exact candidate |
| RESOLVE + READY + REJECTED | `REJECTED` | `REJECTED` | `None` |
| RESOLVE + READY + UNCERTAIN | `UNCERTAIN` | `UNCERTAIN` | `None` |
| RESOLVE + blocking validation | `BLOCKED` | `None` | `None`（**不**解析 confirmation） |

#### D11 — Confirmed ID Assignment Gate

唯一赋值点：节点 **`finalize_confirmation`**（及同模块内唯一 helper，如 `_assign_confirmed_business_id`）。

- 仅：`confirmed_business_id = candidate_business_id`（exact）
- **禁止：** 生成 / 转换 / normalize / lookup replacement / alias
- **Defense-in-depth：** 节点内再次检查 `validation == READY_FOR_CONFIRMATION` **且** `intent == CONFIRMED`；否则不得赋值（不能只依赖 Router）

#### D12 — Canonical Name / Repository Validation

- `canonical_name` **只**取 `Business.canonical_name`；必须 usable nonblank；否则 `CANONICAL_NAME_UNAVAILABLE`
- 仓库侧：**无**现成 Protocol → F10 新增最小只读 **`BusinessRepositoryReader`（Protocol）**：
  - `has_business(business_id: str) -> bool`
  - `get_business(business_id: str) -> Business`
  - `get_conditions(business_id: str, *, consumption: ConsumptionMode = ...) -> list[Condition]`（若 validation 路径不直接调 get_conditions，仍可保留以对齐 F04 selector 输入能力；**Production 不复制过滤逻辑**）
- `JsonBusinessRepository` 结构性满足该 Protocol；**不新增** Repository backend
- Validation 顺序见 D17 validate node

#### D13 — `TerminalConfirmationDependencies`

```text
@dataclass(frozen=True, slots=True)
class TerminalConfirmationDependencies:
    business_repository: BusinessRepositoryReader
    rule_selector: Callable[[str, BusinessRepositoryReader], RuleSelectionResult]
        # Production default MUST be F04 select_executable_rules
```

- **不含** LLM / Embedding / Redis / DB / F06 Retriever
- Production：`business_repository` 传入真实 `JsonBusinessRepository`；`rule_selector` 默认 = **`select_executable_rules`**
- 允许 test 注入 fake repo / fake selector，但 **不得**弱化 F04 ownership（Production 路径始终指向真实 F04 selector）
- 注：真实 F04 注解为 `JsonBusinessRepository`；Production 调用方必须传入兼容实现

#### D14 — `artifacts["f10"]` Schema

**不新增** AgentState top-level field。Artifact key = **`"f10"`**。

Exact layout：

```json
{
  "mode": "prepare" | "resolve",
  "terminal_context": {
    "transition_status": "TERMINAL_CANDIDATE",
    "current_node_id": "...",
    "candidate_business_id": "...",
    "visited_node_ids": ["..."],
    "traversed_edge_ids": ["..."]
  },
  "terminal_validation": {
    "status": "READY_FOR_CONFIRMATION" | "...",
    "candidate_business_id": "...",
    "canonical_name": "..." | null
  },
  "rule_readiness": {
    "selection_status": "NO_RULES" | "RULES_AVAILABLE_UNEVALUATED" | null,
    "selected_rule_count": 0,
    "skipped_non_executable_count": 0,
    "evaluation_performed": false
  } | null,
  "confirmation": {
    "status": "AWAITING_CONFIRMATION" | "CONFIRMED" | "REJECTED" | "UNCERTAIN" | "BLOCKED",
    "intent": "CONFIRMED" | "REJECTED" | "UNCERTAIN" | null
  },
  "confirmed_business_id": null | "<exact candidate id>",
  "failure": {
    "kind": "<TerminalConfirmationFailureKind>",
    "message": "<safe static message>"
  } | null,
  "response_text": "..."
}
```

- `mode` 序列化为 lowercase snake-case：`prepare` / `resolve`
- **不存** raw confirmation text / Business object / Condition object / repository / exception
- blocking 时 `rule_readiness` 可在已跑 selector 后填写；context 失败时可为 `null`
- **OI-F10-003 = RESOLVED**

#### D15 — Failure Semantics

冻结 **`TerminalConfirmationFailureKind`**：

- `INVALID_TERMINAL_CONTEXT`
- `CANDIDATE_NOT_FOUND`
- `CANDIDATE_ID_MISMATCH`
- `CANONICAL_NAME_UNAVAILABLE`
- `RULES_UNEVALUATED`

| Outcome | 是否 system failure |
|---------|---------------------|
| REJECTED / UNCERTAIN | **否**（合法 interaction；`failure=null`） |
| 上表 blocking kinds | **是**（受控 failure；`confirmation.status=BLOCKED`） |
| Repository / programming / unexpected shape bugs | **propagate**；禁止 `except Exception → UNCERTAIN` |

#### D16 — Deterministic Response Templates

冻结（`{canonical_name}` 来自 Business Data）：

| Key | Template |
|-----|----------|
| Confirmation Prompt | `当前候选办理事项为“{canonical_name}”。请确认是否办理该事项（请回复“确认”或“不确认”）。` |
| Confirmed | `已确认您要办理的事项为“{canonical_name}”。` |
| Rejected | `已取消对当前候选事项“{canonical_name}”的确认。本次不会确认该事项。` |
| Uncertain | `我还不能确定您是否要办理“{canonical_name}”。请明确回复“确认”或“不确认”。` |
| RULES_UNEVALUATED | `当前候选事项“{canonical_name}”存在尚未完成确定性校验的业务规则，暂不能完成最终事项确认。` |
| Candidate not found | `当前候选事项无法在业务数据中验证，暂不能进行最终事项确认。` |
| Invalid context | `当前候选事项状态无效，暂不能进行最终事项确认。` |
| ID mismatch | `当前候选事项的数据标识不一致，暂不能进行最终事项确认。` |
| Canonical unavailable | `当前候选事项缺少可靠的标准名称，暂不能进行最终事项确认。` |

约束：

- 默认 **不**向用户暴露内部 `business_id`（如 `DEMO_SS_001`）；artifact 可存
- **禁止**「符合办理条件 / 审核通过 / 资格通过」
- **禁止**材料 / 地点 / 渠道 / 费用 / 时限 / 法律依据
- **OI-F10-005 = RESOLVED**

#### D17 — Specialized Workflow Topology

**Execution nodes = 6；Routers = 3。**

Nodes：

1. `prepare` — 复用 F08 `_prepare_node` lifecycle helper
2. `validate_terminal_candidate`
3. `interpret_confirmation`
4. `finalize_confirmation`
5. `compose_terminal_response`
6. `complete` — 复用 F08 `_complete_node`

**Topology：**

```text
START
  ↓
prepare
  ↓
validate_terminal_candidate
  ↓
validation ready?
 ┌───────────────┴───────────────┐
 no                              yes
 ↓                                ↓
compose_terminal_response       mode?
 ↓                         ┌──────┴──────┐
complete                  PREPARE      RESOLVE
 ↓                          ↓             ↓
END                    compose_response  interpret_confirmation
                            ↓             ↓
                         complete        intent?
                            ↓        ┌────┼─────────┐
                           END    CONFIRM REJECT  UNCERTAIN
                                   ↓       ↓         ↓
                                finalize  compose   compose
                                   ↓       ↓         ↓
                                compose  complete  complete
                                   ↓       ↓         ↓
                                complete END       END
                                   ↓
                                  END
```

**Routers（pure；0 repository / network / LLM / F04 transition）：**

| Router | 读 | 决策 |
|--------|----|------|
| #1 validation | `terminal_validation.status` | not READY → compose；READY → mode router |
| #2 mode | `mode` | PREPARE → compose；RESOLVE → interpret |
| #3 confirmation | `confirmation.intent` | CONFIRMED → finalize；REJECTED/UNCERTAIN → compose |

**F04 call boundary：**

- **0** calls to `advance_until_blocked`
- Validation node **允许**调用 F04 `select_executable_rules`（Rule Selection / Readiness，**不是** Graph Transition）

**`validate_terminal_candidate` 顺序（冻结）：**

1. validate `TerminalCandidateContext`
2. candidate presence（nonblank；已由 context 保证，再防御检查）
3. repository existence（`has_business`）
4. `get_business`
5. Business ID exact match
6. `canonical_name` usable
7. 调用真实 F04 Rule Selection（via deps.rule_selector；**先 existence，再 selector**）
8. 建立 `RuleReadinessSnapshot`
9. `NO_RULES` → `READY_FOR_CONFIRMATION`
10. `RULES_AVAILABLE_UNEVALUATED` → `RULES_UNEVALUATED`

**`interpret_confirmation`：** 仅 RESOLVE + READY 可达；读 `AgentState.input_text`；写 controlled intent；不改 candidate。

**`finalize_confirmation`：** 唯一 confirmed ID assignment；再检 READY+CONFIRMED；0 Repository / F04 / LLM / RAG。

**`compose_terminal_response`：** 纯 deterministic 模板选择。

节点实现放在 `nodes.py` 私有工厂（对齐 F09）；domain 逻辑在 `terminal.py`。

#### D18 — Runner API

| API | 语义 |
|-----|------|
| `build_terminal_confirmation_workflow(deps)` | 编译 specialized graph；高级/测试/未来 F12 |
| `prepare_terminal_confirmation(initial_state, terminal_context, deps)` | fresh `artifacts["f10"]`；内部 mode=`prepare`；**忽略** `input_text` 作为确认答案 |
| `resolve_terminal_confirmation(initial_state, terminal_context, deps)` | fresh `artifacts["f10"]`；内部 mode=`resolve`；`input_text` = 本轮确认话语 |

- **不**要求 caller 传普通字符串 `mode="prepare"|"resolve"` 作为主入口（降低误用）
- 每次 runner：刷新 `f10`；**保留**其它 artifact namespaces
- Caller immutability：`deepcopy` state / artifacts / context；禁止原地修改

#### D19 — Serialization / Immutability

- 写入 AgentState 必须 JSON-safe：Enum→str；Pydantic→`model_dump(mode="json")`；tuple→list
- 必须可通过 `json.dumps(..., allow_nan=False)`
- **禁止**将 repository / rule_selector / workflow graph / Pydantic instance / Exception / Protocol instance 写入 artifacts

#### D20 — Public API / Feature Boundaries

**Public Surface（`gov_service_agent.agent` re-export）：**

| Symbol | 角色 |
|--------|------|
| `TerminalCandidateContext` | domain context |
| `build_terminal_candidate_context` | factory from F04 |
| `terminal_candidate_context_from_business_transition` | factory from F09 artifact subset |
| `TerminalValidationStatus` | enum |
| `TerminalValidationResult` | validation result model |
| `RuleReadinessSnapshot` | readiness snapshot |
| `ConfirmationIntent` | utterance intent |
| `ConfirmationStatus` | lifecycle status |
| `TerminalConfirmationFailureKind` | controlled failure kind |
| `TerminalConfirmationDependencies` | deps |
| `BusinessRepositoryReader` | minimal read-only Protocol |
| `interpret_confirmation` | local parser（公开便于单测；**不** export 内部 allowlist / normalization helpers / templates） |
| `build_terminal_confirmation_workflow` | graph builder |
| `prepare_terminal_confirmation` | PREPARE runner |
| `resolve_terminal_confirmation` | RESOLVE runner |

**不 export：** private nodes / routers / phrase allowlists / normalization helpers / response template constants / empty_f10_namespace 等内部细节（除非 Confirm 阶段发现测试必需的最小 export——默认 NO）。

**OI-F10-006 = RESOLVED**

---

### 24.2 Data Authority Table

| Data | Owner |
|------|-------|
| `candidate_business_id` | **F04** |
| `canonical_name` | **Business Data**（via Repository） |
| Rule Selection | **F04**（`select_executable_rules`） |
| Rule Evaluation | **NONE / DEFERRED** |
| confirmation interpretation | **F10** deterministic parser |
| `confirmed_business_id` | **F10** |
| materials / location / channel / legal basis | **Future Knowledge capability** |

---

### 24.3 Failure Matrix

| Condition | confirmation_status | confirmed_business_id |
|-----------|---------------------|------------------------|
| Invalid context | BLOCKED | `None` |
| Candidate missing / not found | BLOCKED | `None` |
| ID mismatch | BLOCKED | `None` |
| Canonical missing | BLOCKED | `None` |
| `NO_RULES` | READY path → allow confirmation | 仅 CONFIRMED 后赋值 |
| `UNEVALUATED` | BLOCKED | `None` |
| REJECTED | REJECTED（合法） | `None` |
| UNCERTAIN | UNCERTAIN（合法） | `None` |
| CONFIRMED + READY | CONFIRMED | exact candidate |

### 24.4 PREPARE / RESOLVE Matrix

| Mode | Validation | Intent | Outcome |
|------|------------|--------|---------|
| PREPARE | READY | n/a（不解析） | `AWAITING_CONFIRMATION`；confirmed=`None` |
| PREPARE | BLOCKED | n/a | `BLOCKED`；confirmed=`None` |
| RESOLVE | READY | CONFIRMED | `CONFIRMED`；confirmed=candidate |
| RESOLVE | READY | REJECTED | `REJECTED`；confirmed=`None` |
| RESOLVE | READY | UNCERTAIN | `UNCERTAIN`；confirmed=`None` |
| RESOLVE | BLOCKED | **不解析** | `BLOCKED`；confirmed=`None` |

---

### 24.5 Requirement ↔ TD Traceability

| AC 范围 | Design Owners |
|---------|---------------|
| AC-F10-001…006（Terminal Input） | D03 / D04 |
| AC-F10-007…012（Candidate Validation） | D12 / D04 |
| AC-F10-013…020（Rule Layer） | D05 / D06 / D07 |
| AC-F10-021…029（Confirmation） | D08 / D09 / D10 |
| AC-F10-030…036（Confirmed ID） | D11 / D10 |
| AC-F10-037…042（Response / State） | D14 / D16 / D19 |
| AC-F10-043…050（Architecture） | D01 / D13 / D17 / D18 |
| AC-F10-051…056（Golden / Future） | Golden tests / D01 / D16 / boundaries |

**56 AC 分类全部有 Design owner。**

---

### 24.6 Test Strategy（设计；本阶段不写测试）

#### Domain

- `TerminalCandidateContext` strict；non-terminal reject；blank candidate reject
- factory from real F04；from F09 artifact
- candidate not found / ID mismatch / canonical unavailable

#### Rule

- `NO_RULES` → READY；skipped=7 仍 READY 且 `evaluation_performed=False`
- `RULES_AVAILABLE_UNEVALUATED` → BLOCKED
- UNEVALUATED + user「确认」→ confirmed=`None`

#### Parser

| Input | Expected |
|-------|----------|
| 确认 / 确认办理 / 是的 / 就是这个 / 没错 | CONFIRMED |
| 不确认 / 不是这个 / 不办理 | REJECTED |
| 好像是吧 / 应该是 / 好的 | UNCERTAIN |
| candidate canonical_name only | UNCERTAIN |
| 确认，但是我不确定 | UNCERTAIN |

Normalization：spaces / 中英标点 / NFKC / 「确认。」→确认；内部否定保留。

#### PREPARE Safety（关键）

`input_text="确认"` + `prepare_terminal_confirmation` → 仍 `AWAITING_CONFIRMATION`；confirmed=`None`。

#### RESOLVE

- 「确认」+ READY → CONFIRMED + exact ID
- 「不是这个」→ REJECTED + None
- 「好像是吧」→ UNCERTAIN + None
- UNEVALUATED +「确认」→ BLOCKED + None
- not-found +「确认」→ no confirmed

#### Golden Integration

- 真实 F04 demo transition / 已验证 terminal result
- candidate=`DEMO_SS_001`；真实 Business Data；真实 F04 selector
- PREPARE → AWAITING；RESOLVE「确认」→ `confirmed_business_id=DEMO_SS_001`
- `canonical_name` 来自 Repository；Rule=`NO_RULES`；selected=0；skipped=7
- **禁止** fake eligibility PASS

#### Regression / Isolation

- F08 `build_agent_workflow` / `run_agent_workflow` PASS
- F09 specialized workflow 语义不被破坏；现有 F09 tests PASS
- F10 普通 tests：**0** network / LLM / DB

---

### 24.7 Final Planned Paths = 8

| # | Path | 操作 | 引入阶段 |
|---|------|------|----------|
| 1 | `src/gov_service_agent/agent/__init__.py` | MODIFY | Code |
| 2 | `src/gov_service_agent/agent/nodes.py` | MODIFY | Code |
| 3 | `src/gov_service_agent/agent/workflow.py` | MODIFY | Code |
| 4 | `src/gov_service_agent/agent/terminal.py` | **NEW** | Code |
| 5 | `tests/test_agent_terminal.py` | **NEW** | Test |
| 6 | `tests/test_agent_workflow.py` | MODIFY | Test |
| 7 | `docs/features/F10-terminal-validation-user-confirmation.md` | MODIFY | Requirement/TD（当前） |
| 8 | `docs/code-reading/F10-terminal-validation-user-confirmation-code-reading.md` | **NEW** | Code-Reading |

**Stage path counts：**

| Stage 结束 | Expected changed path count |
|------------|------------------------------|
| Code | **5**（paths 1–4 + Feature Doc） |
| Test | **7**（+ paths 5–6） |
| Code-Reading / Commit | **8** |

**明确排除：** `state.py`；F04 包；F09 `interaction.py` / `explanation.py`；F02；Graph JSON；Settings；`pyproject.toml`；新依赖 / env / port / infra。

**为何单文件 `terminal.py`：** F10 domain + confirmation 规模适合单模块；不拆 confirmation.py / terminal_validation.py / rule_readiness.py。

共享可改：`nodes.py` / `workflow.py` / `__init__.py`（Agent orchestration shared）。

---

### 24.8 Security / Privacy / Audit

- F10 **无** Remote provider；不新增 `USER_FREE_TEXT` Remote path
- Raw confirmation 仅 `AgentState.input_text`；artifacts **不**复制
- Artifact 可保留 controlled intent / status / candidate ID / rule readiness / trace
- 真正 audit persistence → **F11**

---

### 24.9 Technical Design Closure

| Gate | 结果 |
|------|------|
| D01–D20 frozen | **YES** |
| OI-F10-001…006 | **全部 RESOLVED** |
| New TD open items | **0** |
| PREPARE/RESOLVE / Context / Validation / Readiness / Phrases / Artifact / Templates / Topology / Runners / Public API / Paths | **全部冻结** |
| Production modified | **0** |
| Tests modified | **0** |
| Changed paths | **1**（本 Feature Doc） |
| BLOCKING / MAJOR | **0 / 0** |

**判定：**

- F10 Technical Design = **FINAL / CLOSED**
- TD Finalization = **NOT REQUIRED**

---

## 25. Confirm

| 字段 | 内容 |
|------|------|
| Date | 2026-09-11 |
| Stage | Confirm |
| Git Baseline | `develop` @ `1a9d15d48e1101bebd50d00e6747c1b1ed2671b0` |
| Changed paths at Confirm | `1`（仅本 Feature Doc） |
| Python（govagent） | **3.11.16** |
| Code Readiness | **READY** |
| Confirm Decision | **COMPLETE** |

### 25.1 Real API Verification

| 区域 | 结果 | 证据 |
|------|------|------|
| F02 `Business.business_id` / `canonical_name` | **PASS** | `business_data/models.py`；non-empty validators 仍在 |
| F02 `Condition` / `ConditionExecutable` / `VerificationStatus` | **PASS** | 含 `VERIFIED`；executable 仍要求 VERIFIED + usable；F10 Phase-1 **不**求值 |
| `JsonBusinessRepository` | **PASS** | `has_business` / `get_business` / `get_snapshot` / `get_conditions` 均存在；`get_business` → `Business` |
| `BusinessRepositoryReader` Protocol | **PASS** | 现有 `JsonBusinessRepository` **结构性满足** TD 最小三方法；不要求无关接口；**不**需新 backend |
| F03 `TERMINAL_CANDIDATE` | **PASS** | 节点要求 non-empty `candidate_business_id`；与 `Business.business_id` 同一字符串 contract |
| F04 Transition | **PASS** | `TransitionStatus.TERMINAL_CANDIDATE`；`TransitionResult.candidate_business_id`；F10 **0** `advance_until_blocked` 仍可行（只消费已有 candidate） |
| F04 Rule Selection | **PASS** | module = `gov_service_agent.business_rules.selection`；public via `business_rules` |
| Selector signature | **PASS** | `select_executable_rules(business_id: str, repository: JsonBusinessRepository) -> RuleSelectionResult` — 与 TD 记录一致 |
| `RuleSelectionResult` fields | **PASS** | `business_id` / `status` / `selected_rule_ids` / `skipped_non_executable_count` 足以构造 `RuleReadinessSnapshot`（`selected_rule_count = len(selected_rule_ids)`） |
| `NO_RULES` / `RULES_AVAILABLE_UNEVALUATED` | **PASS** | 真实 enum 值存在；UNEVALUATED → `RULES_UNEVALUATED` 无需 Evaluator |
| Rule Evaluator | **PASS** | **不存在**；Phase-1 **不需要**；Planned Paths 无 evaluator/DSL/AST/F02 变更 |
| F08 `AgentState` | **PASS** | 严格 **7** fields；`artifacts` 可承载 `artifacts["f10"]`；**不**需改 `state.py` |
| F08 lifecycle / default workflow | **PASS** | `_prepare_node` / `_complete_node` 可复用；`build_agent_workflow` / `run_agent_workflow` 保持不变 |
| F09 specialized pattern | **PASS** | `SlotInteractionDependencies` + `build_*_workflow` + `run_*` + fresh namespace + deepcopy；支持再增一套 F10 specialized graph |
| F09 `business_transition` | **PASS** | `serialize_transition_result` 含 `status` / `current_node_id` / `candidate_business_id` / `visited_node_ids` / `traversed_edge_ids` 等；F10 adapter 只取 terminal-safe subset |
| F09-specific files | **PASS** | Path plan **不含** `interaction.py` / `explanation.py`；F10 可由 `terminal.py` + shared `nodes.py`/`workflow.py`/`__init__.py` 完成 |

### 25.2 Requirement ↔ TD Consistency

| 冻结项 | Confirm |
|--------|---------|
| `TERMINAL_CANDIDATE` ≠ `confirmed_business_id` | **PASS** |
| F04 owns candidate；F10 owns confirmation / confirmed | **PASS** |
| `NO_RULES` ≠ eligibility PASS；Phase-1 允许 matter confirmation | **PASS** |
| `RULES_AVAILABLE_UNEVALUATED` fail closed | **PASS** |
| Generic Rule Evaluator = DEFERRED | **PASS** |
| Confirmation LOCAL deterministic；Remote LLM NOT REQUIRED | **PASS** |
| AC = 56；D01–D20；OI-F10-001…006 = RESOLVED；Req/TD open = 0 | **PASS** |
| AC 分类 → D owners（001–056） | **PASS** |

### 25.3 PREPARE / RESOLVE Readiness

| Gate | Confirm |
|------|---------|
| PREPARE 不读 `input_text` 作确认；parser calls = **0** | **PASS** |
| PREPARE → validate + Business + readiness + prompt → `AWAITING_CONFIRMATION`；confirmed=`None` | **PASS** |
| Stale F09 slot answer（如「平时接零活…」）不能 auto-confirm | **PASS**（结构上由 PREPARE 零解析保证） |
| RESOLVE：先 revalidation，再 `interpret_confirmation`；读 new-turn `input_text` | **PASS** |
| RESOLVE 不盲信旧 `AWAITING` artifact；经 controlled `TerminalCandidateContext` 重验 | **PASS** |
| Factories：`build_terminal_candidate_context` + `terminal_candidate_context_from_business_transition` | **PASS** |
| Arbitrary dict **不**可信；F09 adapter strict validate | **PASS** |

### 25.4 Domain / Parser / Artifact / Workflow Readiness

| Gate | Confirm |
|------|---------|
| `TerminalCandidateContext` fields | transition_status / current_node_id / candidate_business_id / visited_node_ids / traversed_edge_ids |
| `TerminalValidationStatus` 六值完整 | **PASS** |
| Validation order：context → existence → ID → canonical_name → rule selection | **PASS** |
| `RuleReadinessSnapshot`；Phase-1 `evaluation_performed=False`；无 `eligibility_pass` | **PASS** |
| Positive exact set | 确认 / 确认办理 / 是的 / 就是这个 / 没错 |
| Negative exact set | 不确认 / 不办理 / 不是 / 不是这个 / 不是这个事项 / 不是我要办的 / 我办的不是这个 / 不对 |
| Default / 好的 / name-only / 冲突长句 | **UNCERTAIN** |
| substring / contains / startswith 解析 | **禁止** |
| `ConfirmationStatus` 五值；唯一 assignment = `finalize_confirmation` + defense-in-depth | **PASS** |
| confirmed = exact candidate propagation | **PASS** |
| D16 templates（含 AWAITING/CONFIRMED/REJECTED/UNCERTAIN/全部 blocked kinds） | **PASS**；无资格/Knowledge/内部 ID 默认暴露 |
| `artifacts["f10"]` 八字段 layout；无 raw text / Business / Condition / deps / Exception | **PASS** |
| JSON-safe / deepcopy / fresh f10 / preserve other namespaces | **PASS** |
| Dependencies：仅 repository + rule_selector；无 LLM/Redis/DB/Retriever | **PASS** |
| Production `rule_selector` = F04 `select_executable_rules`；不复制 selection authority | **PASS** |
| Nodes=6；Routers=3；topology 符合 D17；interpret 仅 RESOLVE+READY；finalize 仅 CONFIRMED 路径 | **PASS** |
| Runners：`build_` / `prepare_` / `resolve_`；无普通 mode 字符串主 API | **PASS** |
| Public API / Private surface | **PASS**（见 D20） |

### 25.5 Path / Resource / Security Readiness

| Gate | Confirm |
|------|---------|
| Final Planned Paths = **8** | **PASS** |
| Code Stage paths = **5**；Test = **7**；Code-Reading = **8** | **PASS** |
| Path 9 / F02 / F04 / F09-specific / state / Settings / pyproject / Graph JSON | **不需要** |
| New dependency / env / port / Docker / PG / Redis / Embedding / Company LLM / Knowledge | **不需要** |
| F07 `USER_FREE_TEXT` Remote DENY | **不改变** |
| Secret Gate（无 .env / key / endpoint） | **PASS** |
| Golden：`DEMO_SS_001`；canonical_name 来自 Business；`NO_RULES` selected=0 skipped=7（data 仍 7 conditions；Resource Gate evidence） | **PASS** |
| Testing readiness（domain/rule/parser/PREPARE safety/RESOLVE/Golden/F08/F09 regression） | **PASS**（设计层；本阶段未跑 pytest） |

### 25.6 Findings

| ID | Severity | 内容 |
|----|----------|------|
| **CF-F10-001** | INFO | 当前 shell 默认 `python` 可能为 3.12.x；项目环境 **govagent = Python 3.11.16**。Code/Test 须在 govagent 执行。不阻塞 Confirm。 |
| **CF-F10-002** | INFO | F04 `select_executable_rules` 参数注解为 `JsonBusinessRepository`，而 deps 字段类型为 `BusinessRepositoryReader`。Code 可用 Production 传入真实 `JsonBusinessRepository` + 默认绑定真实 selector；若需 typing wrapper，**仅**做类型适配、**不得**重写 selection semantics（TD D13 已说明）。不改变 Public API / Topology / Paths。 |

**BLOCKING = 0；MAJOR = 0；MINOR = 0；INFO = 2。**

**Confirm Doc Fixes：** **0**（无 Requirement/TD 语义或 signature 纠错）。

**Unresolved Findings：** 无。

**Need TD reopen？** **NO**
**Need Requirement reopen？** **NO**

### 25.7 Code Readiness Decision

| 项 | 结果 |
|----|------|
| 全部 Confirm COMPLETE 条件 | **满足** |
| F10 Confirm | **COMPLETE** |
| Code Readiness | **READY** |
| Recommended Next | **Code** |

---

## 26. Code Implementation

| 字段 | 内容 |
|------|------|
| Date | 2026-09-11 |
| Stage | Code |
| Git Baseline | `develop` @ `1a9d15d48e1101bebd50d00e6747c1b1ed2671b0` |
| Python | **govagent / 3.11.16** |
| F10 Code | **COMPLETE** |
| F10 Test | **NOT STARTED** |
| Code Stage changed paths | **5** |
| Deviations | **NONE**（无 AC / Topology / Public API / Path 变更） |

### 26.1 Production Paths

| # | Path | 操作 |
|---|------|------|
| 1 | `src/gov_service_agent/agent/__init__.py` | MODIFY |
| 2 | `src/gov_service_agent/agent/nodes.py` | MODIFY |
| 3 | `src/gov_service_agent/agent/workflow.py` | MODIFY |
| 4 | `src/gov_service_agent/agent/terminal.py` | **NEW** |
| 5 | `docs/features/F10-terminal-validation-user-confirmation.md` | MODIFY |

Final Planned Paths 仍为 **8**（Test / Code-Reading 未创建）。

### 26.2 Public API（已实现）

`TerminalCandidateContext`、`TerminalValidationStatus`、`TerminalValidationResult`、`RuleReadinessSnapshot`、`ConfirmationIntent`、`ConfirmationStatus`、`TerminalConfirmationFailureKind`、`TerminalConfirmationDependencies`、`BusinessRepositoryReader`、`build_terminal_candidate_context`、`terminal_candidate_context_from_business_transition`、`interpret_confirmation`、`build_terminal_confirmation_workflow`、`prepare_terminal_confirmation`、`resolve_terminal_confirmation`。

未 export：private nodes / routers / allowlists / normalizer / templates。

F08 / F09 既有 public API **保留**。

### 26.3 PREPARE / RESOLVE

| Runner | 行为 |
|--------|------|
| `prepare_terminal_confirmation` | fresh `artifacts["f10"]`；mode=`prepare`；**0** confirmation parser calls（图上不可达 `interpret_confirmation`） |
| `resolve_terminal_confirmation` | fresh `f10`；mode=`resolve`；先 revalidation，READY 后才 `interpret_confirmation` |

Stale-input safety：PREPARE 结构上不读 `input_text` 作确认。

### 26.4 Terminal Validation / Rule Selection

- 顺序：context → existence → ID match → canonical_name → F04 `select_executable_rules` → snapshot → status mapping
- `NO_RULES` → `READY_FOR_CONFIRMATION`；`evaluation_performed=False`；**无** `eligibility_pass`
- `RULES_AVAILABLE_UNEVALUATED` → `RULES_UNEVALUATED` / `BLOCKED` / confirmed=`None`
- **0** Rule Evaluator / DSL / AST

### 26.5 CF-F10-002 Typing Solution

- `BusinessRepositoryReader` Protocol（`has_business` / `get_business`）
- Private adapter `_select_executable_rules_adapter`：仅当 repository 为 `JsonBusinessRepository` 时 **委托** F04 `select_executable_rules`
- **不**复制 VERIFIED/usable 筛选；**不**修改 F04

### 26.6 Confirmation Parser

- NFKC + trim + collapse whitespace + strip edge punctuation
- Exact positive / negative allowlists（D09）
- Default `UNCERTAIN`；**无** substring / contains 匹配

### 26.7 Confirmed ID / Artifact / Topology

- 唯一非-None assignment：`finalize_confirmation` → `assign_confirmed_business_id`（READY + CONFIRMED defense-in-depth；exact candidate propagation）
- `artifacts["f10"]`：mode / terminal_context / terminal_validation / rule_readiness / confirmation / confirmed_business_id / failure / response_text
- Execution nodes = **6**；Routers = **3**（validation 调用 mode；confirmation 独立）；**0** `advance_until_blocked`
- F08 default `START→prepare→complete→END` 保留；F09 specialized workflow 保留

### 26.8 Static Checks

| Check | Result |
|-------|--------|
| `py_compile`（4 production files，govagent） | **PASS** |
| Public import smoke | **PASS** |
| pytest | **NOT RUN** |
| compileall | **NOT RUN** |
| Runtime workflow / F04 / Repository / Golden | **NOT RUN** |

### 26.9 Known INFO

| ID | 内容 |
|----|------|
| CF-F10-001 | Code Stage 使用 govagent Python 3.11.16 |
| CF-F10-002 | rule_selector typing adapter 已实现（见 §26.5） |

### 26.10 Code Closure

| Gate | 结果 |
|------|------|
| Production complete | **YES** |
| Tests modified | **NO**（Code 阶段） |
| Extra paths | **NO** |
| BLOCKING / MAJOR | **0 / 0** |
| Recommended Next | **Test** |

---

## 27. Test

| 字段 | 内容 |
|------|------|
| Date | 2026-09-11 |
| Stage | Test |
| Environment | **govagent / Python 3.11.16** |
| F10 Test | **PASS** |
| F10 Review | **NOT STARTED** |
| Production modified during Test | **NO** |
| Production Test Fixes | **0** |
| Test Stage changed paths | **7** |
| Final Planned Paths | **8**（Code-Reading 未创建） |

### 27.1 Production Freeze Hashes

| Path | Before = After |
|------|----------------|
| `agent/__init__.py` | `36ef48c5ac99d1539310c9e51465b37829d2e782` |
| `agent/nodes.py` | `b2d8d1cf7bbefeb336d8aa3f61440d128c0b4cbd` |
| `agent/workflow.py` | `8f5af88300fd860140937ca1b1d25f8669f6d45f` |
| `agent/terminal.py` | `b5ca4c88d3061fd7f530117a6c1ebd11185384a7` |

### 27.2 Target / Combined Results

| Suite | Result |
|-------|--------|
| `tests/test_agent_terminal.py` | **69 passed / 0 skipped / 0 failed / 0 warnings** |
| `tests/test_agent_workflow.py` | **31 passed / 0 skipped / 0 failed / 0 warnings** |
| Combined F10 targets | **100 passed / 0 skipped / 0 failed / 0 warnings** |

### 27.3 Regression / Full Suite

| Suite | Result |
|-------|--------|
| F08-related（`test_agent_state` + workflow excl. F10-only filters as needed） | **PASS**（`test_agent_state` + workflow 基线保留） |
| F09（`test_agent_interaction` + `test_agent_workflow`） | **94 passed / 0 failed / 0 warnings** |
| Full default suite `pytest -q` | **545 passed / 13 skipped / 0 failed / 0 warnings** |
| Historical F09 baseline | 469 passed / 13 skipped / 0 failed / 0 warnings |
| Delta vs historical | +76 passed（合理：F10 domain + workflow tests） |
| `compileall -q src/gov_service_agent` | **PASS** |
| `pip check` | **PASS**（No broken requirements found） |

### 27.4 Golden / Safety Evidence

| Case | Result |
|------|--------|
| Golden DEMO_SS_001 real F04 terminal + real repo + real selector | **PASS** |
| RuleSelectionStatus | `NO_RULES`；selected=0；skipped=7 |
| PREPARE stale `"确认"` / slot answer | **AWAITING**；confirmed=`None`；parser unreachable |
| RESOLVE confirm | confirmed=`DEMO_SS_001` |
| RESOLVE reject / uncertain | confirmed=`None` |
| UNEVALUATED + confirm | **BLOCKED**；parser unreachable |
| Candidate not found | selector calls=0；confirmed=`None` |
| Artifact exact 8 keys / JSON-safe / immutability / fresh f10 | **PASS** |

### 27.5 Findings

| Severity | Count | Notes |
|----------|-------|-------|
| BLOCKING | 0 | |
| MAJOR | 0 | |
| MINOR | 0 | |
| INFO | 0（本 Test 阶段新增） | CF-F10-001/002 仍为历史 INFO |

**Need Return To Code：** **NO**
**Golden Data Drift：** **NO**
**F08/F09 regression introduced：** **NO**

### 27.6 Test Closure

| Gate | 结果 |
|------|------|
| F10 Test | **PASS** |
| Review Readiness | **READY FOR REVIEW** |
| Recommended Next | **Review** |

---

## 28. Explanation

| 字段 | 内容 |
|------|------|
| Date | 2026-09-11 |
| Stage | Explanation |
| F10 Explanation | **COMPLETE** |
| F10 Code-Reading | **NOT STARTED** |
| Production / Tests modified this stage | **NO** |
| Actual changed paths | **7**（Final Planned Paths 仍 = **8**） |

### 28.1 一句话与核心概念

F10 **不**负责帮用户选事项。
F10 负责：接收 F04 已经确定的候选事项，进行确定性终点校验 + 最终事项确认；只有在校验允许且用户明确确认后，才生成 `confirmed_business_id`。

| 概念 | 含义 |
|------|------|
| `candidate_business_id` | Business Decision Graph 已确定的**候选事项**（F04 authority） |
| `confirmed_business_id` | 用户已明确确认「这就是我要办理的事项」（F10 authority） |
| `TERMINAL_CANDIDATE` | 业务图到达候选终点；**不是**最终事项已确认 |

**`TERMINAL_CANDIDATE` ≠ `confirmed_business_id`** — 这是 F10 最核心不变量。

### 28.2 在整体架构中的位置

```text
用户自然语言
        ↓
F06 Semantic Retrieval（找方向 / 候选；非最终事项）
        ↓
F04 Business Decision Graph（确定性推进）
        ↓
F09 Missing Slot Interaction（缺失槽位问答 / 解释旁路）
        ↓
F04.advance_until_blocked → TERMINAL_CANDIDATE + candidate_business_id
        ↓
F10 PREPARE（terminal validation → AWAITING_CONFIRMATION）
        ↓
用户新一轮：「确认 / 不确认 / 其它」
        ↓
F10 RESOLVE（revalidation → local confirmation）
        ↓
confirmed_business_id（仅 READY + CONFIRMED）
        ↓
未来 Knowledge capability / F11 session / F12 E2E
```

说明：F09 与 F04 可交错推进；F10 的输入 authority **始终**来自 F04 已产生的 terminal candidate（或 F09 序列化的受控 `business_transition`），不是 RAG / LLM。

### 28.3 为什么必须 PREPARE / RESOLVE 分离

典型风险链：

1. 用户说：「平时接零活，没有固定单位」（employment_type slot answer）
2. F09 映射为合法槽位 → F04 推进到 `TERMINAL_CANDIDATE`
3. 此时 `AgentState.input_text` **仍可能是**那句 slot answer

若 F10 立刻把当前 `input_text` 当确认语义解析，就会把旧槽位回答误当成「确认办理」。

因此：

| 阶段 | 做什么 | 不做什么 |
|------|--------|----------|
| **PREPARE** | 校验 candidate、生成确认提示 | **不**把当前 `input_text` 当 confirmation；parser calls = **0** |
| **RESOLVE** | 重新校验 + 解析**新一轮** `input_text` | 不信任旧 `artifacts["f10"]` 作为 authority |

### 28.4 PREPARE Runtime Flow（真实主链）

```text
prepare_terminal_confirmation(state, TerminalCandidateContext, deps)
  → deepcopy + fresh artifacts["f10"] (mode=prepare)
  → prepare node（lifecycle）
  → validate_terminal_candidate
      → context / candidate presence
      → repository.has_business / get_business
      → business_id exact match
      → canonical_name usable
      → deps.rule_selector → F04 select_executable_rules
      → NO_RULES → READY_FOR_CONFIRMATION
  → validation router → mode router（PREPARE）
  → 不进入 interpret_confirmation
  → compose_terminal_response → AWAITING_CONFIRMATION
  → confirmed_business_id = None
  → complete → END
```

### 28.5 RESOLVE Runtime Flow（真实主链）

```text
resolve_terminal_confirmation(new_state, same TerminalCandidateContext, deps)
  → fresh artifacts["f10"] (mode=resolve)  ← 不复用旧 confirmation/confirmed
  → prepare → validate（重新 existence / ID / name / rule readiness）
  → READY → mode RESOLVE → interpret_confirmation(input_text)
  → CONFIRMED → finalize_confirmation → assign_confirmed_business_id
  → REJECTED / UNCERTAIN → compose（不 finalize）
  → BLOCKED（validation 失败）→ compose（不 interpret / 不 finalize）
```

**先 validation，后 parsing。** 旧 `AWAITING_CONFIRMATION` artifact **不是**下一轮 authority（防 stale / forged / caller misuse）。

### 28.6 模块职责（按真实代码）

#### `terminal.py`（domain / deterministic services）

- Domain models / enums：`TerminalCandidateContext`、`TerminalValidationStatus`、`TerminalValidationResult`、`RuleReadinessSnapshot`、`ConfirmationIntent`、`ConfirmationStatus`、`TerminalConfirmationFailureKind`、`TerminalConfirmationMode`
- `BusinessRepositoryReader` Protocol + `TerminalConfirmationDependencies`
- Adapters：`build_terminal_candidate_context`、`terminal_candidate_context_from_business_transition`
- Validation：`validate_terminal_candidate`、`rule_readiness_from_selection`
- Parser：`normalize_confirmation_text`、`interpret_confirmation`
- Confirmed ID gate：`assign_confirmed_business_id`
- Response / failure / JSON-safe serialization helpers、`empty_f10_namespace` / `merge_f10_artifacts`
- **不含** LangGraph topology

#### `nodes.py`（6 execution nodes + 3 logical routers）

| Node | 读 input_text | Repository / Selector | 赋 confirmed ID |
|------|---------------|----------------------|-----------------|
| `prepare`（复用 F08） | 否 | 否 | 否 |
| `validate_terminal_candidate` | 否 | 是 | 仅写 `None` |
| `interpret_confirmation` | **是**（仅 RESOLVE+READY） | 否 | 写 `None` |
| `finalize_confirmation` | 否 | 否 | **唯一 non-None 赋值** |
| `compose_terminal_response` | 否 | 否 | 否 |
| `complete`（复用 F08） | 否 | 否 | 否 |

Routers（pure）：`_route_by_terminal_validation` → 调用 `_route_by_terminal_mode`；`_route_by_confirmation_intent`。0 repository / selector / network / LLM。

#### `workflow.py`

- `build_terminal_confirmation_workflow`：specialized graph
- `prepare_terminal_confirmation` / `resolve_terminal_confirmation`：公开 runners（mode 由 runner 固化，非用户普通字符串）
- **不改** `build_agent_workflow` / `run_agent_workflow`
- **不改** F09 `build_slot_interaction_workflow` / `run_slot_interaction_workflow`

#### `__init__.py` Public Surface

Domain：`TerminalCandidateContext`、`TerminalValidationStatus`、`TerminalValidationResult`、`RuleReadinessSnapshot`、`ConfirmationIntent`、`ConfirmationStatus`、`TerminalConfirmationFailureKind`、`TerminalConfirmationDependencies`、`BusinessRepositoryReader`
Adapters：`build_terminal_candidate_context`、`terminal_candidate_context_from_business_transition`
Parser（便于单测）：`interpret_confirmation`
Workflow：`build_terminal_confirmation_workflow`、`prepare_terminal_confirmation`、`resolve_terminal_confirmation`

**非 public：** routers、allowlists、normalizer、templates、private nodes、`_select_executable_rules_adapter`。

### 28.7 TerminalCandidateContext 与两个入口

字段：`transition_status`、`current_node_id`、`candidate_business_id`、`visited_node_ids`、`traversed_edge_ids`。
约束：frozen、extra=forbid、candidate nonblank、trace 契约。
不携带：raw user text / Business / LLM / Repository。

| Factory | 输入 |
|---------|------|
| `build_terminal_candidate_context` | 真实 F04 `TransitionResult`（必须 `TERMINAL_CANDIDATE`） |
| `terminal_candidate_context_from_business_transition` | F09 `serialize_transition_result` 受控子集 |

**arbitrary dict 不可信**：仅有 `{"candidate_business_id":"DEMO_SS_001"}` 不够——必须证明来自合法 `TERMINAL_CANDIDATE` contract。

### 28.8 Terminal Validation 与状态

顺序：context → candidate ID → `has_business` → `get_business` → ID exact match → `canonical_name` → F04 Rule Selection → readiness mapping。
candidate 不存在时：**不**调用 selector。

| Status | 含义 | 可确认？ | confirmed 可能？ |
|--------|------|----------|------------------|
| `READY_FOR_CONFIRMATION` | Phase-1 门禁通过（含 `NO_RULES`） | 可进入确认 | 仅 + CONFIRMED |
| `INVALID_TERMINAL_CONTEXT` | 非 terminal / 契约失败 | 否 | 否 |
| `CANDIDATE_NOT_FOUND` | Repository 无此 ID | 否 | 否 |
| `CANDIDATE_ID_MISMATCH` | Business.business_id ≠ candidate | 否 | 否 |
| `CANONICAL_NAME_UNAVAILABLE` | 无可靠显示名 | 否 | 否 |
| `RULES_UNEVALUATED` | 有 selected executable 但无 evaluator | 否 | 否 |

Repository：不新建 backend；`BusinessRepositoryReader` 最小 Protocol；Production 用现有 `JsonBusinessRepository`。
显示名唯一来源：`Business.canonical_name`（非 LLM / RAG / ID / alias）。

### 28.9 Rule Selection ≠ Rule Evaluation

F04 `select_executable_rules`：选出具备可执行资格的 VERIFIED+usable rules（readiness）。
**不**判断规则最终 true/false。

`RuleReadinessSnapshot`：`selection_status` / `selected_rule_count` / `skipped_non_executable_count` / `evaluation_performed`（Phase-1 恒 `False`）。**无** `eligibility_pass`。

| F04 status | F10 行为 |
|------------|----------|
| `NO_RULES` | selected=0 → `READY_FOR_CONFIRMATION`；**≠** 资格通过 |
| `RULES_AVAILABLE_UNEVALUATED` | → `RULES_UNEVALUATED` / BLOCKED；用户「确认」也**不能**绕过 |

**DEMO_SS_001：** conditions=7，selected=0，skipped=7，`NO_RULES`。有条件但无可执行 VERIFIED rule → 不能做资格结论，但可确认「是不是这个事项」。

通用 Rule Evaluator / DSL / AST：**DEFERRED**（ConditionExecutable 非完整 DSL；不发明政务规则语义）。

Production selector 路径：`_select_executable_rules_adapter` **仅** typing/concrete 适配，委托真实 `select_executable_rules`（CF-F10-002 / RF-F10-REV-002）。

### 28.10 Confirmation Parser

LOCAL / SYNC / DETERMINISTIC / HIGH PRECISION / **exact set membership**（非 LLM）。

Normalization：NFKC → trim → collapse whitespace → strip **仅边缘**标点；**不**删除内部「不/否/没/别」。

**POSITIVE（CONFIRMED）：** 确认 / 确认办理 / 是的 / 就是这个 / 没错

**NEGATIVE（REJECTED）：** 不确认 / 不办理 / 不是 / 不是这个 / 不是这个事项 / 不是我要办的 / 我办的不是这个 / 不对

其余（好的/好/行/可以/嗯/对/好像是吧/只复述 canonical_name/「确认，但是我不太确定」等）→ **UNCERTAIN**。

禁用 substring：若用 `"确认" in text`，则「不确认」也会误命中。

| Intent | 含义 |
|--------|------|
| CONFIRMED / REJECTED / UNCERTAIN | 对本轮 confirmation utterance 的受控解释（非 business decision） |

| Status | 生命周期 |
|--------|----------|
| AWAITING_CONFIRMATION | PREPARE + READY；intent=None |
| CONFIRMED / REJECTED / UNCERTAIN | RESOLVE 合法交互结果 |
| BLOCKED | validation 未允许；intent=None |

### 28.11 confirmed_business_id 生命周期与唯一 authority

默认 `None`。仅当 `READY_FOR_CONFIRMATION` **且** `ConfirmationIntent.CONFIRMED` 时：

`confirmed_business_id = candidate_business_id`（exact propagation；非 UUID / synonym / repository 替换）。

- Physical non-None assignment points = **1**
- Semantic authority = **1**：`assign_confirmed_business_id`，仅由 `_finalize_confirmation_node` 调用
- Finalizer defense-in-depth：再次检查 READY + CONFIRMED
- Router / validate / parser / compose **不**赋最终 ID

### 28.12 Topology（6 nodes / 3 logical routers）

Execution nodes = 6。Logical routers = 3（validation / mode / confirmation）。

**RF-F10-REV-003（INFO, accepted）：** mode router 由 validation router **内部调用**，LangGraph 上无额外独立 mode hop；行为仍符合 validation → mode → confirmation。

```text
PREPARE READY:  START→prepare→validate→compose→complete→END
BLOCKED:        START→prepare→validate→compose→complete→END
RESOLVE OK:     …→validate→interpret→finalize→compose→complete→END
REJECT/UNCERT:  …→interpret→compose→complete→END
```

### 28.13 artifacts["f10"]（exact 8 keys）

`mode` / `terminal_context` / `terminal_validation` / `rule_readiness` / `confirmation` / `confirmed_business_id` / `failure` / `response_text`

- 不存 raw confirmation（已有 `AgentState.input_text`）
- 不存 Business / Condition / RuleSelectionResult / Repository / Dependency / Exception
- Enum/tuple/Pydantic → JSON-safe primitives；`json.dumps(..., allow_nan=False)` 可通过
- 每次 runner **fresh** 替换 `f10`；**保留** `f09` 等其它 namespace
- Caller：deepcopy；不原地改 state / context

Failure kinds（controlled blocked）：INVALID_TERMINAL_CONTEXT / CANDIDATE_NOT_FOUND / CANDIDATE_ID_MISMATCH / CANONICAL_NAME_UNAVAILABLE / RULES_UNEVALUATED。
REJECTED / UNCERTAIN：**不是**系统 failure（`failure=None`）。
无 broad `except Exception → UNCERTAIN`；unexpected bug 应 propagate。

Response：deterministic templates；显示 `canonical_name`；默认不暴露 `DEMO_SS_001`；不声称资格通过；不含材料/地点/渠道/费用/时限/法律依据。

### 28.14 场景

**Golden positive：** F09 slot → F04 terminal `DEMO_SS_001` → PREPARE（canonical_name=灵活就业人员社会保险费申报缴费；`NO_RULES` selected=0 skipped=7；AWAITING；confirmed=None）→ 用户「确认」→ RESOLVE → CONFIRMED → confirmed=`DEMO_SS_001`。**NO_RULES ≠ eligibility PASS。**

**Reject：**「不是这个」→ REJECTED / None；F10 不重做 RAG / 不改选 business（回上层属 F12）。

**Uncertain：**「好像是吧」→ UNCERTAIN / None。

**UNEVALUATED：** BLOCKED；parser/finalizer 不可达。

**Candidate not found：** `CANDIDATE_NOT_FOUND`；selector calls=0；Data Consistency failure。

### 28.15 Feature Boundaries

| Feature | 边界 |
|---------|------|
| F04 | Graph / candidate / Rule Selection；F10 **0** `advance_until_blocked` |
| F06 | Semantic retrieval；F10 **0** RAG |
| F07 | F10 Core **0** LLM；不改变 `USER_FREE_TEXT` Remote DENY |
| F08 | 7-field AgentState / lifecycle；F10 不改 `state.py` |
| F09 | 槽位交互；可产生 terminal transition；**不**产生 confirmed |
| F11 | Session/Redis/Checkpoint/Audit；F10 capability 不依赖 Redis |
| F12 | E2E 编排（含 REJECT 后回退）；非 F10 |
| Knowledge | 仅在 confirmed 之后；F10 不查材料/地点/渠道/法律依据 |

### 28.16 Test Evidence（引用，本阶段不重跑）

| Suite | Result |
|-------|--------|
| `test_agent_terminal.py` | **69 passed** |
| `test_agent_workflow.py` | **31 passed** |
| Combined F10 | **100 passed / 0 failed / 0 warnings** |
| F09 regression | **94 passed** |
| F08（`test_agent_state`） | **63 passed** + workflow baseline PASS |
| Full suite | **545 passed / 13 skipped / 0 failed / 0 warnings** |
| F09 后历史 baseline | 469 / 13 / 0 / 0（+76 passed count；非“全部等于新文件用例数”） |
| compileall / pip check | **PASS** |

关键安全证据：PREPARE stale「确认」/ slot answer；parser=0；RESOLVE revalidation；validation-before-parser；UNEVALUATED bypass；not-found selector=0；artifact exact keys；raw minimization；JSON safety；immutability；Golden DEMO — 均 **PASS**。

### 28.17 Review Evidence

Review = **PASS**；Review Fix = **NOT REQUIRED**；BLOCKING/MAJOR/MINOR = **0**；INFO = **3**。
**未**做 Review 代码修复（仅 INFO accepted）。

| ID | Severity | 内容 |
|----|----------|------|
| RF-F10-REV-001 | INFO | govagent Python 3.11.16 vs shell 默认（= CF-F10-001） |
| RF-F10-REV-002 | INFO | thin rule_selector typing adapter（= CF-F10-002） |
| RF-F10-REV-003 | INFO | logical mode router 由 validation router 内部调用 |

Resource Gate INFO RF-F10-RG-001…004 仍有效：解释为何 Evaluator deferred、`NO_RULES` 语义、DSL deferred。

### 28.18 Debugging Guide

| 现象 | 检查 |
|------|------|
| 一直 AWAITING | 是否调了 PREPARE 而非 RESOLVE |
| 「好的」不确认 | 不在 exact positive allowlist → UNCERTAIN（设计如此） |
| 用户「确认」仍 BLOCKED | `TerminalValidationStatus`（尤其 UNEVALUATED / not found / mismatch） |
| Business 名称不对 | 查 `Business.canonical_name`，勿查 LLM/RAG |
| confirmed 不产生 | READY **且** CONFIRMED 双门禁 |
| 拒绝后不换事项 | 属 F12 / 上层编排，非 F10 |

### 28.19 Interview Explanation

业务决策图到达 terminal 后，没有直接把 candidate 当成最终 `business_id`，而是单独做了 F10 确认层。F10 分 PREPARE / RESOLVE：PREPARE 只做候选校验与确认提示，不读上一轮 slot answer 当确认；下一轮 RESOLVE 才重新校验 candidate，并用本地精确匹配解析用户是否明确确认。只有 terminal validation READY 且用户明确 CONFIRMED，才把原 `candidate_business_id` **原样**赋给 `confirmed_business_id`。这样可避免旧输入误确认、LLM 误判确认、以及规则尚未求值时错误放行。另：`NO_RULES` ≠ eligibility PASS。

**常见追问：**

1. **为何不用 LLM 判确认？** 高风险业务状态变更；本地 high-precision deterministic parser 更可控、可测。
2. **为何两阶段？** 防止上一轮 slot answer 被误当最终确认。
3. **为何 RESOLVE 再 validation？** 防 stale/forged；不信旧 f10。
4. **NO_RULES 为何还能继续？** F10 确认事项身份，不是资格审核。
5. **UNEVALUATED 为何不能继续？** 已有可执行规则但无 deterministic result，不能把 NOT EVALUATED 当 PASS。
6. **confirmed ID 怎么生成？** 不生成；exact propagate validated candidate ID。

### 28.20 Recommended Reading Order（Code-Reading 预告）

1. `terminal.py`（语义中心：models / validation / parser / confirmed gate）
2. `nodes.py`（domain → Agent nodes / routers）
3. `workflow.py`（PREPARE/RESOLVE orchestration）
4. `__init__.py`（public surface）
5. `tests/test_agent_terminal.py`
6. `tests/test_agent_workflow.py`
7. 本 Feature Doc

独立 Code-Reading Guide 文件属于**下一 Stage**；本阶段**不创建**。

### 28.21 Explanation Closure

| Gate | 结果 |
|------|------|
| F10 Explanation | **COMPLETE** |
| Recommended Next（当时） | **Code-Reading** |

---

## 29. Code-Reading

| 字段 | 内容 |
|------|------|
| Date | 2026-09-11 |
| Stage | Code-Reading |
| F10 Code-Reading | **COMPLETE** |
| Document | `docs/code-reading/F10-terminal-validation-user-confirmation-code-reading.md` |
| Production / Tests modified this stage | **NO** |
| Actual changed paths | **8**（Final Planned Paths = **8**） |
| Recommended Next | **Commit** |

### 29.1 完成摘要

独立代码阅读指南已创建，覆盖：推荐阅读顺序（`terminal.py` 优先）、candidate→confirmed / PREPARE / RESOLVE 主线、nodes/workflow 真实 symbol、artifact 8-key、Golden / 安全测试名、边界、调试、面试讲解、常见误区与 Checklist。

本阶段 **未**重跑 pytest / compileall / pip check；继续引用 Test / Review 既有证据。

### 29.2 Code-Reading Closure

| Gate | 结果 |
|------|------|
| F10 Code-Reading | **COMPLETE** |
| Recommended Next（当时） | **Commit** |

---

## 30. Commit

| 字段 | 内容 |
|------|------|
| Date | 2026-09-11 |
| Stage | Commit |
| F10 Commit | **COMPLETE** |
| Commit scope | **8** frozen paths |
| Commit message | `feat(F10): 实现终点校验与事项确认` |
| F10 Push | **NOT STARTED** |
| Production / Tests / Code-Reading modified this stage | **NO**（仅 Feature Doc Stage Status） |

### 30.1 Commit Closure

| Gate | 结果 |
|------|------|
| F10 Commit | **COMPLETE** |
| Recommended Next | **Push** |
| 本阶段 | **STOP**（不得自动 Push） |

---

## Appendix A — 只读 Symbol 复核摘要（Requirement 阶段）

| 区域 | 复核结论 |
|------|----------|
| F02 | `Business.business_id` / `canonical_name`；`ConditionExecutable.operator` / `verification_status` / `usable_by_rule_engine` |
| F03 | `NodeType.TERMINAL_CANDIDATE` 要求 non-empty `candidate_business_id` |
| F04 | `TransitionResult`；`TransitionStatus.TERMINAL_CANDIDATE`；`advance_until_blocked`；无 `confirmed_business_id` |
| Rule Selection | `RuleSelectionStatus.NO_RULES` / `RULES_AVAILABLE_UNEVALUATED`；`select_executable_rules` |
| Rule Evaluator | **absent** |
| F08 | `AgentState` 7 fields；`artifacts: dict[str, JsonValue]` |
| F09 | `serialize_transition_result` → `artifacts["f09"]["business_transition"]` |
| Repository | `JsonBusinessRepository.has_business` / `get_business` / `get_snapshot` / `get_conditions` |
| DEMO_SS_001 | `canonical_name` = `灵活就业人员社会保险费申报缴费`；Rule Selection = `NO_RULES`（skipped=7） |

## Appendix B — TD 阶段真实 API 复核补充

见 §24.0。关键冻结：

```text
select_executable_rules(business_id: str, repository: JsonBusinessRepository) -> RuleSelectionResult
```

F10 Production `rule_selector` 默认必须指向该函数；F10 **0** `advance_until_blocked`。
