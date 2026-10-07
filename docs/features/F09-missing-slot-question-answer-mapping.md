# F09 — Missing Slots / Question / Answer Mapping

## 1. Feature Overview

| 字段 | 内容 |
|------|------|
| Feature ID | F09 |
| Feature Name | Missing Slots / Question / Answer Mapping |
| 中文定位 | 缺失槽位交互、受控提问、用户回答解释与槽位映射 |
| Current Stage | **Commit = COMPLETE**；Next = **Push** |
| 前置 Feature | F08 — Agent State + LangGraph Orchestration Foundation（**CLOSED** @ `55c8bfadb33228df7aa97a4a1dbd8a310e6d5a20`） |
| Git Baseline | `develop` @ `55c8bfadb33228df7aa97a4a1dbd8a310e6d5a20` |
| External Resource Gate | **CLOSED / READY** |
| F09 Scope | **A** |
| Requirement Document | `docs/features/F09-missing-slot-question-answer-mapping.md` |
| Acceptance Criteria | **48** |
| Technical Design Decisions | **D01–D20** |
| Final Planned Paths | **9** |
| Code-stage Paths | **6** |
| Mandatory New Dependency | **NONE** |
| Code Readiness | **READY**（Confirm COMPLETE） |
| Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 4；Review Fix = NOT REQUIRED） |

### Stage Status

| 阶段 | 状态 |
|------|------|
| Resource Gate | **CLOSED / READY** |
| Requirement | **CLOSED** |
| Requirement Finalization | **NOT REQUIRED** |
| Technical Design | **FINAL / CLOSED** |
| Technical Design Finalization | **NOT REQUIRED** |
| Confirm | **COMPLETE** |
| Code | **COMPLETE** |
| Test | **PASS** |
| Review | **PASS** |
| Review Fix | **NOT REQUIRED** |
| Explanation | **COMPLETE** |
| Code-Reading | **COMPLETE**（`docs/code-reading/F09-missing-slot-question-answer-mapping-code-reading.md`） |
| Commit | **COMPLETE** |
| Push | **NOT STARTED** |

**本阶段范围：** Commit（精确 9-path 本地提交；Push 未授权）。

**明确禁止自动进入：** Push。

**后续记录：** 第 29 节是已批准的 **F09 Requirement Finalization**，其中的 Q1–Q5 与不变式保持冻结。第 30 节是 **F09 Technical Design Reopen**，状态为 **READY FOR OWNER REVIEW**。这两节都不改写第 1–28 节的原始设计、阶段记录和测试证据。当前 Production Mapper 仍然只向模型提供 `required_slot`、原始 `allowed_values` 和 `user_text`。

**一句话定位：** F09 负责：在 Business Decision Graph 已经确定当前缺失槽位后，把用户自然语言解释为受控槽位答案、解释请求或其它语义，并且只有经过确定性校验的槽位答案才允许交给 F04 继续推进业务图。

---

## 2. Architecture Position

项目原则（口号级）：

> 语义检索找方向，业务图谱定事项，规则引擎做终审，知识图谱查办理信息，Agent 统一编排。

**F09 对应：** Agent 在业务图谱推进过程中，处理用户自然语言与受控槽位之间的交互（提问、语义分类、映射、解释旁路、校验、回交 F04）。

Canonical Flow（F09 负责加粗段）：

```text
用户自然语言
→ Agent Orchestration（F08 foundation + F09 extension）
→ Semantic Retrieval（F06；方向召回，非本 Feature 默认路径）
→ Business Decision Graph（F04 deterministic）
→ Missing slots / questions / answer mapping / explanation side route   ← F09
→ Terminal Candidate Validation / 用户确认（F10）
→ Session / Redis / Checkpoint / Audit（F11）
→ E2E Demo（F12）
```

### Highest Architecture Invariants

LLM / NLU **不得**决定：

- `next_node`
- `business_id` / `candidate_business_id`
- Rule result
- materials / handling location / channels / legal basis

LLM 在 F09 **最多**负责：

- 自然语言理解
- 受控槽位映射
- 解释性意图识别
- confidence
- 基于允许输入的自然语言组织（含 Demo 公共概念通俗说明）

业务决策仍由 **F04 Business Decision Graph** 根据 `current_node` + validated slots + predefined edges **确定性**完成。

| Graph / Layer | 职责 |
|---------------|------|
| **LangGraph Agent Graph** | Agent orchestration；可按 interpretation 路由到 mapping / explanation / clarification 等 **Agent capability** |
| **Business Decision Graph（F04）** | 唯一 Business Transition Authority；更新 `current_node` |
| **Explanation Side Route** | Agent Conversation Response；**不属于** Business Decision Graph |

**LangGraph END ≠ Business `TERMINAL_CANDIDATE`。**
**Agent orchestration routing ≠ Business routing。**

---

## 3. Resource Gate Summary

F09 Resource Gate：**CLOSED / READY**。

| 项 | 冻结结论 |
|----|----------|
| Mandatory Resources | **10** |
| READY | **10** |
| NOT READY | **0** |
| BLOCKING | **0** |
| F09 Scope Classification | **A** |
| Mandatory New Dependency | **NONE** |
| F04 Missing-Slot Contract | **READY**（`NEED_SLOT` / `INVALID_SLOT` + `required_slot` / `allowed_values` / `question_text`） |
| Question Source | **DETERMINISTIC**（Business Graph `SLOT_GATE` 预定义） |
| F07 Provider / Structured Parser / Policy | **READY** |
| F08 AgentState / LangGraph | **READY** |
| Zero-network ordinary tests | **可行** |
| Real `USER_FREE_TEXT` → Remote Company Provider | **DENY**（Open Item；不阻塞本 Feature） |

**INFO-F09-01：** F08 Feature Doc 存在 stage wording drift；F08 实际 **CLOSED**。本 Feature **不修改** F08 文档。

---

## 4. Scope

### 4.1 Scope Freeze

**F09 Scope = A**

### 4.2 In Scope（必须）

1. 消费 F04 `NEED_SLOT`
2. 消费 F04 `INVALID_SLOT`
3. 使用 F04 deterministic `question_text`
4. 保留 `required_slot`
5. 保留 `allowed_values`
6. Interpret User Utterance
7. 区分：Slot Answer / Explanation Request / Uncertain / Other（语义冻结；具体枚举名 TD）
8. Slot Answer Mapping Contract
9. mapped value membership validation（deterministic）
10. confidence validation（Controller-owned）
11. Mapping fail-closed
12. 把 validated slot 交回 F04
13. 必要的 F08 LangGraph orchestration extension
14. Explanation Side Route（解释旁路）
15. Explanation Capability Interface（可替换边界）
16. Demo 阶段：允许通过现有 Company LLM Provider 做**受限公共概念解释**
17. 解释完成后：Resume Current Slot

### 4.3 Scope Clarification — Explanation Side Route

Explanation Side Route：

- **属于** Agent Orchestration
- **不属于** Business Decision Graph
- **不改变** business `current_node` / `required_slot` / validated business slots / candidate / confirmed `business_id` / Rule result / Business terminal state
- 结束后必须 **Resume** 原 Slot Interaction

---

## 5. Non-Goals

明确 **不属于** F09：

| 类别 | 排除项 |
|------|--------|
| Knowledge | 完整政务百科、完整 FAQ、完整知识 RAG、materials/location/channel/legal basis 查询 |
| Re-implementation | 重新实现 F04 / F06；Rule final decision |
| Confirmation | Matter confirmation；confirmed `business_id`（F10） |
| Infra | Redis、Session、Checkpoint、Audit、Public Session API、PostgreSQL runtime、ASR、Embedding（作 Answer Mapping） |
| Product | 完整 E2E（F12）、通用聊天机器人、LangSmith、LangGraph Cloud、Tool Calling、Conversation Memory |
| Policy | 放宽 F07 `USER_FREE_TEXT` Remote DENY；自动授权 Real Remote NLU |
| Presentation abuse | LLM 自由决定「该问什么 slot」；LLM 自由编造正式办理事实 |

**不冻结**本 Feature 最终 changed path 数量 / 模块文件数（Technical Design）。

---

## 6. Existing Contracts

### 6.1 F04 Transition Contract（消费方）

F04 在 `NEED_SLOT` / `INVALID_SLOT` 时提供可供 F09 消费的正式字段：

| 字段 | NEED_SLOT | INVALID_SLOT |
|------|-----------|--------------|
| `status` | 是 | 是 |
| `current_node_id` | 是 | 是 |
| `required_slot` | 非空 | 非空 |
| `allowed_values` | 非空 | 非空 |
| `question_text` | 非空 | 非空 |
| `invalid_value` | 禁止 | 必须 |
| `candidate_business_id` / `unsupported_reason` | 禁止（slot 态） | 禁止（slot 态） |

F09 **只能**向 F04 提供 validated slot；**不能**自行判断业务 `next_node`。

流程：

```text
User Utterance
→ F09 Interpretation
→ （若 Slot Answer）Mapping
→ Application Validation（membership + confidence）
→ validated slot
→ F04 deterministic transition
```

### 6.2 F07 Capability（消费方）

- `LlmProvider` Protocol（含 Demo / Fake / OpenAI-compatible）
- `parse_structured_output`：`DIRECT_JSON` 或 `STRICT_SINGLE_JSON_CODE_FENCE`；无 regex repair / first-JSON / YAML / eval / LLM repair
- Data Policy：Remote ALLOW = `PUBLIC_BUSINESS_METADATA` / `SYSTEM_CONTROL_DATA` / `SYNTHETIC_TEST_DATA`；其余 DENY（含 `USER_FREE_TEXT`）

F09 **不修改** F07 Policy。

### 6.3 F08 Foundation（扩展方）

- `AgentState` 7 fields：`request_id`, `input_text`, `phase`, `status`, `artifacts`, `error`, `orchestration_trace`
- Topology 现状：`START → prepare → complete → END`
- F09 允许扩展 orchestration；**不强制**新增 top-level State 字段（TD 优先考虑 `artifacts`）

### 6.4 Demo Graph Evidence（只读基线）

`data/graphs/demo/social_security.json` 已含：

- `employment_type` SLOT_GATE
- `allowed_values` 含 `other_flexible_employment`
- 中文确定性 `question_text`

本 Requirement **不修改** graph JSON。

---

## 7. Functional Requirements

### 7.1 Missing Slot

F09 必须能够消费 F04：

- `NEED_SLOT`：`required_slot` + `allowed_values` + `question_text`
- `INVALID_SLOT`：同上 + `invalid_value`；允许重新询问 / 再 mapping（具体 UX → TD）

消费后，Agent 必须保留当前 slot 交互上下文，直至：

- 获得 **validated** slot 并交回 F04；或
- 保持未完成并等待下一轮用户输入；或
- 受控失败（Provider / Parse / Policy）且 **不**伪装成业务推进。

### 7.2 Deterministic Question

**Question Source = DETERMINISTIC**（Business Graph `SLOT_GATE` 预定义 `question_text`）。

冻结：

1. 正常 Slot Question **不得**由 LLM 自由生成。
2. 优先 **原样使用** F04 `question_text`。
3. Presentation layer 允许非常轻量格式包装，但 **不得改变业务含义**。
4. LLM **不得**因「更自然」而重新决定当前要问哪个 slot / 问什么。

**LLM Question Generation = NOT REQUIRED。**

### 7.3 User Utterance Interpretation

F09 必须先判断用户当前输入的**作用**，再考虑 slot value。

至少四类语义（**语义冻结；具体 Enum / Class / 字段名 → TD**）：

| 语义 | 定义（Requirement） | 对业务图影响 |
|------|---------------------|--------------|
| **SLOT ANSWER** | 用户确实在回答当前 `required_slot` | 仅当 mapping + validation 通过后，才交 F04 |
| **EXPLANATION REQUEST** | 对当前问题 / slot / allowed option / 相关公共概念提问「是什么意思」等 | **不**产生 validated slot；**不**推进 F04；进入 Explanation Side Route |
| **UNMAPPED / UNCERTAIN** | 无法可靠理解或无法可靠对应当前 slot / 置信不足 | **不**推进；slot 保持未完成 |
| **OTHER** | 既非当前槽位回答，亦非当前选项概念解释 | **不**隐式 mapping；**不**推进；可受控 fallback / future knowledge route marker |

示例：

- 系统问缴费/转移/查询；用户「我想继续交社保。」→ **SLOT ANSWER**
- 系统同样问题；用户「什么是社保转移？」→ **EXPLANATION REQUEST**（**禁止**当作 `transfer`）
- 用户「我也不知道，我刚离职。」→ 可能 **UNMAPPED / UNCERTAIN**
- 用户「大厅几点下班？」→ **OTHER**

**禁止：** 因文本中出现某个 allowed option 字样，就自动将该 option 视为用户选择。

### 7.4 Slot Answer Mapping

仅当 interpretation = SLOT ANSWER 时进入 Answer Mapping。

最小 mapping 输入应来自：

- `required_slot`
- `allowed_values`
- user answer（本地短暂处理）
- 必要的 `SYSTEM_CONTROL_DATA`

Mapper **不得**获得：整个 BusinessSnapshot、全部材料、全部法律依据、全部事项数据库。

Mapping Result **最小语义**（字段名 → TD）：

- `mapped_value`
- `confidence`
- 以及「无法映射」的表示能力

Answer Mapping 必须使用 F07 strict structured parse（或等价 fail-closed contract）：

- 允许：`DIRECT_JSON`、`STRICT_SINGLE_JSON_CODE_FENCE`
- 禁止：regex 修 JSON、提取第一个 JSON、YAML、`eval`、`ast.literal_eval`、LLM auto repair

**当前生产真实 Slot Answer**（如「平时接零活，没有固定单位」）属于 `USER_FREE_TEXT` → **不得**直接 Remote Company LLM。普通开发/测试使用 Fake / Synthetic / Demo / local-safe path。

Production **禁止** hardcode：

```text
if "零活" in answer: value = "other_flexible_employment"
```

或其它 regex/关键词伪装 NLU。Tests 可通过 Fake Provider 返回受控 mapping result。

### 7.5 Membership and Confidence Validation

#### Membership（最高 Acceptance 之一）

无论 LLM confidence 多高，只要 `mapped_value ∉ allowed_values` → **reject**，**不得**推进 F04。

禁止：

- 自动找「最像」的 value
- 用 Embedding 强行修正
- 第二次 LLM auto repair

#### Confidence

- `confidence` 必须是有限数值；建议语义范围 **0.0–1.0**（Pydantic `ge`/`le`、默认 threshold、Settings 字段 → TD）
- 即使 value ∈ `allowed_values`，若 confidence **低于**受控 threshold → **不得**自动推进；slot 保持未完成
- **Ownership：** LLM 返回 confidence；**Application / Agent Controller** 决定是否接受
- LLM **不得**自行宣布「confidence 足够所以推进流程」
- threshold **不得**散落在 Node / Prompt / Business Graph；必须有**单一受控来源**（Settings / Module Config / Policy Object → TD）

#### 语义区分

| 情况 | 语义 |
|------|------|
| 低 confidence | NLU/Mapping 把握不足；**不是** Business `INVALID_SLOT` |
| Hallucinated value | membership fail；fail closed |
| Business `INVALID_SLOT` | 已有 slot value 不属于 Graph 允许范围（F04 返回） |
| Provider Error | 资源/协议失败；**不是** Mapping Uncertain |
| Structured Parse Error | 解析失败；**不是**「用户回答无匹配」 |

### 7.6 Explanation Side Route

正式冻结架构概念：**Explanation Side Route / 解释旁路**。

#### 错误案例（必须）

```text
System: 「您主要想办理社保缴费、社保转移，还是查询或其他业务？」
User:   「什么是社保转移？」
```

**禁止行为：** `service_action = transfer` 并推进 Business Graph。

**正确行为：**

- Interpretation = Explanation Request
- validated slot = NONE / NOT VALIDATED
- Business Graph `current_node` **不变**
- `required_slot` **不变**
- validated slots **不新增**当前 slot
- F04 transition **不得**因该解释请求执行

#### 旁路不变量

解释旁路执行时不得改变：

- Business Graph current node
- `required_slot`
- validated business slot
- candidate business
- confirmed `business_id`
- Rule result
- Business terminal state

它只负责当前 **Agent Conversation Response**。

#### Concept vs Policy Fact

| 类型 | 示例 | Demo Company LLM |
|------|------|------------------|
| **Concept Explanation** | 「什么是社保转移？」 | 允许：受限通俗概念说明 |
| **Actionable Policy Fact** | 「社保转移需要什么材料？」 | **禁止**用模型参数知识编造正式材料事实 |
| **User Eligibility** | 「我这种情况能不能办？」 | **禁止**资格判断 |

B/C 在尚无受控知识能力时必须 **fail safely**：说明当前解释旁路不能提供未经核实的办理事实，并保持业务状态。

#### Topic Normalization

进入 Company LLM 前，应优先得到 **normalized explanation topic**（例如受控 topic id 或受控 display name）。具体 topic contract → TD。

若无法可靠 normalize topic，或 topic 不在受控范围：

- **不得**把原始用户输入发给 Company Remote
- 必须 safe fallback（Unmapped / Other / Knowledge Unavailable 之一；具体 status → TD）

### 7.7 Demo Company LLM Explanation

#### 允许（Demo-specific）

Demo 阶段，Explanation Capability 可通过现有 F07 Company LLM Provider 生成：

- 简洁、自然、易懂的**公共政务概念**一般性说明
- 语言组织 / 口语化解释

#### Remote Payload 规则（关键）

**不是**放宽 `USER_FREE_TEXT` Policy。

允许 Remote 的条件：请求 **不包含** raw user free text，且分类仅限 F07 Remote ALLOW，例如：

- normalized public concept / topic
- `SYSTEM_CONTROL_DATA`（任务约束、禁止范围等）
- `PUBLIC_BUSINESS_METADATA`（若需要）

语义示例（**不冻结真实 Prompt 文本**）：

```text
task = explain_public_concept
topic = 社保转移
constraints = 只做通俗概念说明；禁止给出具体业务办理事实
```

#### 禁止输出（不得依赖模型参数知识直接给出）

具体办理条件、资格判断、材料清单、办理地点、具体窗口、办理时间、费用、缴费金额、精确办理时限、法律依据、政策有效期、用户是否符合条件、推荐具体业务事项、`business_id`、Rule pass/fail。

#### 权威性

Company LLM：

- **不是** Authoritative Evidence Source
- **不是** Runtime Business Source of Truth

Explanation output：

- 只能作为 Conversational Explanation
- **不得**写回 Runtime Source of Truth
- **不得**作为 Business Decision Evidence
- **不得**驱动 Graph / Rule / Knowledge Graph facts

Explanation Output 是否 structured / plain text → TD；但必须受 task scope、data policy、response restrictions 约束。

### 7.8 Resume Current Slot

Explanation Side Route 结束后必须：

1. **Resume** 原来的 `required_slot` / `allowed_values` / `question_text`
2. 可组合输出：Explanation Response + 原始 deterministic `question_text`
3. Explanation 完成 **不等于** Slot Answer
4. 只有后续真正 SLOT ANSWER 且 mapping + validation 通过，才交给 F04

### 7.9 Uncertain / Other

**UNMAPPED / UNCERTAIN：**

- 无法达到 confidence threshold 或无法可靠映射 → slot 未完成；Business Graph 不推进
- 可重新询问、提示可选范围、使用更易理解表达；**不得改变** question 业务含义（UX → TD）

**OTHER：**

- 不要求完整回答所有 OTHER
- 可返回受控 fallback 或 future knowledge route marker
- **不得**因 OTHER 改变 Business Graph
- 当前 F09 **不是**通用聊天机器人；未来百科可扩展 OTHER 中的公共问答

### 7.10 Explanation Capability Interface

F09 必须预留 **implementation-independent** Explanation Capability Interface。

- 具体 Protocol / class / method / result schema → **TD**（可能命名如 GovernmentKnowledgeService / ExplanationService / GovernmentEncyclopediaService，**本阶段不冻结**）
- Demo backend：Company LLM 受限概念解释
- 未来可替换为：Government Encyclopedia QA / Official FAQ / Public RAG / Business Knowledge Graph / Verified Public Knowledge → Controlled Facts →（可选）LLM Response Composer

未来百科：

- **不能**取代 F04 Business Decision Graph
- confirmed `business_id` 之后的 materials / locations / channels / legal basis 仍遵守 Knowledge Graph 确定性事实查询原则

### 7.11 LangGraph Orchestration Extension

允许扩展 F08 LangGraph：

- 可按 interpretation result 做 **Agent Conditional Routing**（mapping / explanation / clarification 等）
- Node 数量、节点名、边、conditional edge → **TD**

强调：

- LangGraph 可决定「下一步调用 Explanation Service 还是 Mapping Validator」
- LangGraph **不能**决定「用户应办理缴费还是社保转移」
- Explanation / Uncertain / Other **不得**自行生成新的 business `current_node`；`current_node` 只能由 F04 更新

### 7.12 AgentState / Artifacts

- Requirement **不强制**扩展 7-field schema
- TD 优先考虑用 `artifacts` 承载受控 mapping / explanation orchestration result
- 若用 artifacts：仅 JSON-safe controlled result
- **禁止**：API Key、Authorization、raw provider body、reasoning、HTTP Client、DB Session、Exception object
- **禁止**在 artifacts 再长期复制 raw user text（`input_text` 已存在）
- F09 写入 runtime context 的受控 result 必须 serialization-friendly（finite number；与 `allow_nan=False` 兼容）

### 7.13 Logging & Privacy

**禁止记录：** raw user answer、raw LLM response、secret、reasoning。

**允许受控 metadata（字段 → TD）：** 如 `request_id`、mapping status、confidence bucket / controlled numeric confidence、mapped controlled enum value、route kind。

真实用户输入即使「看起来无 PII」，当前 Remote Policy 仍为 `USER_FREE_TEXT` **DENY**；不得以「看起来没隐私」作为远程发送依据。

### 7.14 Dependencies & Infra

- Mandatory new dependency：**NONE**（复用 Pydantic / LangGraph / F07 / existing Python）
- 不要求 direct LangChain、Tool Calling、Embedding（Answer Mapping）、ASR
- 不要求 semantic retry / second LLM repair / multi-agent debate / CoT repair（Provider HTTP retry 仍属 F07）
- 不新增 Public HTTP endpoint / New Port
- 不要求 PostgreSQL / Redis / Checkpoint / Session / Conversation Memory

---

## 8. Data Policy & Security

### 8.1 F07 Policy 不变

| Classification | Remote |
|----------------|--------|
| PUBLIC_BUSINESS_METADATA | ALLOW |
| SYSTEM_CONTROL_DATA | ALLOW |
| SYNTHETIC_TEST_DATA | ALLOW |
| USER_FREE_TEXT | **DENY** |
| USER_PII | DENY |
| HIGH_SENSITIVE_IDENTITY | DENY |
| TO_CONFIRM_OR_INTERNAL | DENY |
| UNKNOWN | DENY |

F09 **绝对不修改**该 Policy。当前 Owner **未**授权 F07 Data Policy Change，**未**授权 Remote `USER_FREE_TEXT`。

### 8.2 Two Paths

| Path | 真实用户内容 | 当前 Remote |
|------|--------------|-------------|
| Slot Answer Mapping（生产真实回答） | USER_FREE_TEXT | **DENY** → Fake/Synthetic/local-safe |
| Explanation Side Route（Demo） | 必须先 normalize；Remote **不含** raw user text | 仅 ALLOW 分类 |

### 8.3 Reasoning

继续禁止 `reasoning_content` / thinking / CoT 进入 State / decision / logs。
F07 `reasoning_present` 最多仍是 metadata；**不得**作为 mapping decision 来源。

### 8.4 Formal Open Item

见 **OI-F09-DP-001**（非阻塞）。

---

## 9. Failure Semantics

| 失败 / 结果 | 要求 |
|-------------|------|
| Provider Error | 独立错误语义；**不**解释为「用户回答不确定」；业务状态不变；不推进 F04 |
| Structured Parse Error | 独立；**不**解释为 Mapping Uncertain；不推进 F04 |
| Mapping Uncertain / low confidence | 无 validated slot；不推进 |
| Membership fail / hallucinated value | fail closed；不推进 |
| Business `INVALID_SLOT` | 由 F04 返回；F09 继续消费并允许再问 / 再 map |
| Explanation Service Error / timeout | 节点与 slot 不变；**不**因解释失败推进业务 |
| Explanation Not Found / 非受控 Concept | safe fallback；不得 LLM 擅自补齐正式事实 |
| Policy Fact Inquiry（材料/地点/资格等） | fail safely；不编造正式事实；不隐式选 slot |

四类错误表面必须可区分：

1. Provider Failure
2. Parse Failure
3. Mapping Uncertain
4. Business `INVALID_SLOT`

---

## 10. F04 / F06 / F07 / F08 / F10 / F11 / F12 Boundaries

| Feature | F09 边界 |
|---------|----------|
| **F04** | Business Decision Authority；F09 只交 validated slot；不决定 `next_node` |
| **F06** | 全局业务方向召回；F09 **不**对每次 slot 回答做 global RAG |
| **F07** | Provider / Parser / Policy；F09 消费；**不改** Policy |
| **F08** | State + LangGraph foundation；F09 扩展 missing-slot orchestration；Agent Graph ≠ Business Graph |
| **F10** | Terminal validation / user matter confirmation / `business_id` confirmation；即使 F04 返回 `TERMINAL_CANDIDATE`，F09 **不得** confirmed |
| **F11** | Redis / session / checkpoint / thread_id / audit；跨 HTTP 持久化不在 F09 |
| **F12** | 完整 E2E 串联；F09 不做全链路 Demo |

关于 Demo 多轮：F09 可定义「下一步需要用户回答什么」以及解释后「恢复哪个 Slot」；跨请求持久化属 F11。

---

## 11. Golden Scenarios

### Scenario A — Slot Mapping（Golden）

1. 用户初始：「我辞职了，现在没单位，想自己交社保」
2. 进入 Graph 后需要 `employment_type`；Agent 使用 F04 `question_text`
3. 用户：「平时接零活，没有固定单位」
4. Tests：Fake/Synthetic Mapper → `mapped_value = other_flexible_employment`，confidence 足够
5. Controller：membership PASS + confidence PASS → validated slot 交 F04 → F04 确定性推进
6. **Production 禁止** hardcode「零活」→ `other_flexible_employment`

### Scenario B — Explanation Request（核心）

1. System：`service_action` 的 F04 `question_text`
2. User：「什么是社保转移？」
3. Expected：
   - Interpretation = Explanation Request
   - validated slot = NONE
   - `service_action ≠ transfer`
   - F04 transition **NOT EXECUTED** because of explanation request
   - current business state **UNCHANGED**
   - Explanation Side Route **ENTERED**
4. Demo 可调用 Company LLM；Remote 仅含 normalized topic（如「社保转移」）+ system control + allowed public metadata；**不含**原话「什么是社保转移？」
5. Agent 返回：概念说明 + 原 `question_text`；继续等待 `service_action`

### Scenario C — Hallucinated Mapping

Fake Mapper：`value = invented_value`，`confidence = 1.0` → membership FAIL → F04 NOT ADVANCED。

### Scenario D — Low Confidence

Fake Mapper：allowed value（如 `transfer`），confidence below threshold → slot NOT VALIDATED → F04 NOT ADVANCED。

### Scenario E — Provider Failure

Fake Provider throws provider error → distinct provider failure；no transition；state unchanged。

### Scenario F — Parse Failure

Invalid structured content → Structured Parse Failure（≠ Mapping Uncertain）；no F04 advance。

### Scenario G — Business INVALID_SLOT

F04 返回 `INVALID_SLOT` → F09 继续消费 `required_slot` / `allowed_values` / `question_text`；允许再问 / 再 map（UX → TD）。

### Scenario H — OTHER

当前问 `service_action`；User：「大厅几点下班？」→ 不得自动选 payment/transfer/inquiry/other；Graph 不推进；可为 OTHER / Knowledge Future Route。

### Scenario I — Actionable Fact Safety

User：「社保转移具体要准备哪些材料？」→ 不得仅用 Company LLM 参数知识编材料清单；不得 `service_action=transfer` 自动推进；可识别为非 Slot Answer 且需 Future Government Knowledge Capability。

### Scenario J — Answer After Explanation

解释完成后，User：「明白了，我要办转移。」→ 此时才可为 SLOT_ANSWER → `transfer` → confidence → validation → F04。

---

## 12. Acceptance Criteria

Acceptance Criteria 覆盖类别：

**A** Missing Slot Contract · **B** Question Determinism · **C** Input Semantic Classification · **D** Slot Mapping · **E** Membership Validation · **F** Confidence Validation · **G** Explanation Side Route · **H** Demo Company LLM Explanation · **I** Data Policy · **J** Failure Handling · **K** LangGraph Boundary · **L** Business Graph Boundary · **M** State/Data Safety · **N** Zero-Network Tests · **O** Future Encyclopedia Compatibility

共 **15** 类。

| ID | Category | Criterion |
|----|----------|-----------|
| **AC-F09-01** | A | 能消费 `NEED_SLOT` + `required_slot` + `allowed_values` + `question_text` |
| **AC-F09-02** | A | 能消费 `INVALID_SLOT` + `invalid_value` + 上述 slot 字段 |
| **AC-F09-03** | B | 正常业务询问使用 F04 `question_text`；0 LLM 决定问什么 slot |
| **AC-F09-04** | C | User Utterance 至少区分 SLOT ANSWER / EXPLANATION REQUEST / UNCERTAIN / OTHER 四类语义 |
| **AC-F09-05** | C | 「什么是社保转移？」**不得** mapping 为 validated `transfer` |
| **AC-F09-06** | D | Slot Answer Mapping Contract 存在；最小语义含 mapped value + confidence + 无法映射能力 |
| **AC-F09-07** | D | Mapping 输入不包含整库材料 / 法律依据 / BusinessSnapshot 全量 |
| **AC-F09-08** | D | Production 无 golden-phrase / 关键词 hardcode 伪装 NLU |
| **AC-F09-09** | E | invented value + confidence 1.0 → membership reject；F04 不推进 |
| **AC-F09-10** | E | membership 校验为 deterministic Python；confidence 不能替代 membership |
| **AC-F09-11** | F | allowed value + low confidence → no graph advance |
| **AC-F09-12** | F | confidence 由 Controller 决定是否接受；LLM 不得自行宣布推进 |
| **AC-F09-13** | F | threshold 有单一受控来源（具体位置 TD） |
| **AC-F09-14** | G | Explanation Side Route 属于 Agent Orchestration，不属于 Business Decision |
| **AC-F09-15** | G | Explanation Request 不产生 validated slot；不推进 F04 |
| **AC-F09-16** | G | Explanation 时 business `current_node` 与 `required_slot` 保持不变 |
| **AC-F09-17** | G | Explanation 后 Resume Current Slot（原 `question_text` 等待真实 Slot Answer） |
| **AC-F09-18** | G | Explanation 完成 ≠ Slot Answer |
| **AC-F09-19** | H | Demo 允许 Company LLM 做受限公共概念通俗说明 |
| **AC-F09-20** | H | Company LLM 解释不得生成材料 / 地点 / 资格 / 金额 / 法律依据 / business decision |
| **AC-F09-21** | H | Company LLM explanation **不是**正式事实源 / Runtime SoT / Business Decision Evidence |
| **AC-F09-22** | H | Concept Explanation 与 Policy Fact Inquiry / Eligibility 区分；后两者 fail safely |
| **AC-F09-23** | I | Demo Explanation Remote payload **不得**含 raw `USER_FREE_TEXT` |
| **AC-F09-24** | I | Remote payload 使用 normalized topic + ALLOW 分类（含 `SYSTEM_CONTROL_DATA` / 可用的 `PUBLIC_BUSINESS_METADATA`） |
| **AC-F09-25** | I | `USER_FREE_TEXT` Remote 仍 DENY；F07 Policy 未修改 |
| **AC-F09-26** | I | 无法 normalize topic / 非受控 topic → 不得 Remote 原话；safe fallback |
| **AC-F09-27** | J | Provider failure distinct；no F04 advance |
| **AC-F09-28** | J | Parse failure distinct；no F04 advance |
| **AC-F09-29** | J | Mapping Uncertain distinct；no validated slot；no transition |
| **AC-F09-30** | J | Business `INVALID_SLOT` distinct；可继续消费再问 |
| **AC-F09-31** | J | Explanation service error → 业务状态不变；不推进 |
| **AC-F09-32** | J | OTHER → no implicit mapping；no transition |
| **AC-F09-33** | J | Policy Fact 问题（如材料清单）不得用 Demo Company LLM 编造正式事实 |
| **AC-F09-34** | K | LangGraph 可做 Agent capability routing；不得做 Business routing |
| **AC-F09-35** | K | LLM / Agent 不得决定业务 `next_node` / Rule result / `business_id` |
| **AC-F09-36** | L | F04 仍为唯一 Business Transition Authority |
| **AC-F09-37** | L | F04 返回 `TERMINAL_CANDIDATE` 时 F09 不得 confirmed `business_id`（F10） |
| **AC-F09-38** | M | 写入 Agent runtime 的受控 result JSON-safe / finite / serialization-friendly |
| **AC-F09-39** | M | State / Log / Test：0 real credential；0 reasoning text 参与 mapping/state/logging |
| **AC-F09-40** | M | 不在 artifacts 重复长期存放 raw user text；不写 raw provider body |
| **AC-F09-41** | N | Ordinary test suite：0 Company network；0 Real Company LLM |
| **AC-F09-42** | N | Test / Runtime foundation 不依赖 Postgres / Redis / Embedding / ASR |
| **AC-F09-43** | N | Fake Provider / synthetic response 可支撑 ordinary tests |
| **AC-F09-44** | O | 存在 Explanation Capability Interface；未来政务百科可替换 Demo backend |
| **AC-F09-45** | O | 当前不实现完整政务百科 / FAQ / 知识 RAG |
| **AC-F09-46** | O | Structured Answer Mapping 使用 F07 fail-closed parser（或等价）；无 JSON repair loop |
| **AC-F09-47** | O | 不新增 Public HTTP API / New Port；Mandatory new dependency = NONE |
| **AC-F09-48** | B/L | F06 / F07 / F08 / F10 / F11 / F12 边界遵守（无 global per-answer RAG；无 session；非 E2E） |

**Acceptance Criteria 数量：48**（覆盖上述 15 categories）。

---

## 13. Open Items

| ID | 主题 | Status | Blocking? | Resolved By |
|----|------|--------|-----------|-------------|
| **OI-F09-01** | Confidence schema / range / threshold / config location | **RESOLVED** | NO | D05 / MappingPolicy `min_confidence=0.80` |
| **OI-F09-02** | Interpretation schema | **RESOLVED** | NO | D01 / `UtteranceKind` + `UtteranceInterpretation` + restricted mapper output |
| **OI-F09-03** | Explanation Capability interface | **RESOLVED** | NO | D07 / `ExplanationService` Protocol |
| **OI-F09-04** | Local explanation detection / topic normalization | **RESOLVED** | NO | D03 / local deterministic detector + question_text containment |
| **OI-F09-05** | Explanation output format | **RESOLVED** | NO | D07 / strict JSON `{"explanation":"..."}` + max 500 + safety guard |
| **OI-F09-06** | Response composition | **RESOLVED** | NO | D08 / local deterministic composition |
| **OI-F09-07** | AgentState layout | **RESOLVED** | NO | D09 / keep 7 fields；`artifacts["f09"]` |
| **OI-F09-08** | LangGraph topology | **RESOLVED** | NO | D12 / preserve F08 default；add F09 specialized 7-node workflow |
| **OI-F09-DP-001** | 真实 `USER_FREE_TEXT` → Remote Company LLM：DEFAULT Profile 仍 DENY；F07 Policy Reopen 已落地显式 `DEMO_APPROVED`（Owner Demo 业务分类 MAY ALLOW）。**真实 Company Runtime 尚未验证**（RG-F12-004）。关闭条件 = F12 Resource Gate 真实 Remote USER_FREE_TEXT probe PASS | **OPEN / RUNTIME VALIDATION PENDING** | **NO** | F07 Policy Reopen：Requirement/TD/Code/Test/Review PASS；Runtime validation 仍 PENDING |

**OI-F09-DP-001 进展（F07 Policy Reopen Explanation，不关闭）：**

- F07 Policy Reopen：Requirement COMPLETE · TD COMPLETE · Code COMPLETE · Test PASS · Review PASS
- Demo Remote `USER_FREE_TEXT` **Policy implementation 已具备**（须显式 `LLM_REMOTE_DATA_POLICY_PROFILE=DEMO_APPROVED`）
- 真实 Company LLM Runtime：**尚未验证** → OI **保持 OPEN**
- 真正关闭条件：F12 Resource Gate 真实 Remote USER_FREE_TEXT probe PASS

**禁止（OI-F09-04）：** 仅为单个 Demo 句子做 `if "什么是社保转移"` 特例 hardcode。

**INFO-F09-01：** F08 Feature Doc stage wording drift — **INFO only**；F09 **不修改** F08。

---

## 14. Deferred Items

| 项 | 归属 |
|----|------|
| Real Remote NLU（真实 USER_FREE_TEXT → Company Provider） | F07 Policy Reopen 已就绪 Demo Profile；**Runtime validation** 仍属 F12 / OI-F09-DP-001（OPEN） |
| 完整 Government Encyclopedia / FAQ / Public RAG | 未来 Feature；本 Feature 仅 `ExplanationService` 可替换 |
| Actionable policy facts / eligibility 正式回答 | 未来受控知识能力 |
| Comparison / multi-topic explanation（如「缴费和转移有什么区别」） | DEFERRED；当前 OTHER |
| Redis / Session / Checkpoint / Audit | F11 |
| Matter confirmation / confirmed `business_id` | F10 |
| Full E2E Demo / 合并完整 Agent topology | F12 |
| Public HTTP Agent API | F11/F12 |
| MappingPolicy 由 Settings 构造 | 未来运维需求；本 Feature 不改 Settings |
| Real Company Explanation Smoke | OPTIONAL / EXPLICIT OPT-IN；非 Acceptance blocker |
| Prompt 全文精确措辞 | Code（TD 只冻结合义与约束） |

---

## 15. Requirement Stage Status

| 项 | 结论 |
|----|------|
| Requirement | **CLOSED** |
| Requirement Finalization | **NOT REQUIRED** |
| Owner Input Required（for Requirement） | **NO** |
| BLOCKING | **0** |
| Scope | **A**（保持） |

Requirement Findings 摘要保留：解释旁路正式冻结；Demo 解释≠事实源；Agent vs Business routing 分离；Data Policy 不放宽；48 AC。

---

# TECHNICAL DESIGN（FINAL / CLOSED）

## 16. Technical Design Overview

| 项 | 结论 |
|----|------|
| Technical Design | **FINAL / CLOSED** |
| Technical Design Finalization | **NOT REQUIRED** |
| Decisions | **D01–D20** |
| OI-F09-01…08 | **全部 RESOLVED** |
| OI-F09-DP-001 | **OPEN / RUNTIME VALIDATION PENDING** |
| BLOCKING | **0** |
| Code / Tests this stage | **0** |

### 16.1 Real-Code Baseline（只读确认）

| Subsystem | 真实 Public / Runtime API | TD 用法 |
|-----------|---------------------------|---------|
| **F04** | `DecisionGraph`；`TransitionStatus`（`str, Enum`）；`TransitionResult`；`step(graph, current_node_id, slots)`；`advance_until_blocked(graph, current_node_id, slots)` | 仅 ACCEPTED 后调用 **`advance_until_blocked`** |
| **F07** | `LlmProvider` Protocol；`LlmRequest` / `LlmResponse` / `LlmMessage`；`DataClassification`；`parse_structured_output`；`LlmProviderError`；`StructuredParseError`；`DemoLlmProvider`；`OpenAICompatibleLlmProvider.complete` 在 HTTP **前** `evaluate_request_remote_policy` | Mapper / Explanation 复用；不改 Policy |
| **F08** | `AgentState` 7 fields；`artifacts: dict[str, JsonValue]`（**非 reducer**）；`orchestration_trace` 使用 `operator.add`；`build_agent_workflow` / `run_agent_workflow`；private `_prepare_node` / `_complete_node`；`WorkflowErrorCode.INVALID_STATE` only | 不改 `state.py`；保留默认 workflow；新增 specialized workflow |

### 16.2 Highest Invariants

- LLM **不得**决定：business `next_node` / `business_id` / `candidate_business_id` / Rule result / materials / locations / channels / legal basis
- **Agent Orchestration Routing**（LangGraph）≠ **Business Routing**（F04）
- `EXPLANATION_REQUEST` 必须在 **任何 Company Remote call 之前**由 **本地确定性 detector** 识别
- 真实 `USER_FREE_TEXT` → Company Remote：DEFAULT 仍 DENY；Demo Profile 已落地但 Runtime 未验证（OI-F09-DP-001 **OPEN / RUNTIME VALIDATION PENDING**）

### 16.3 Overall Architecture

```text
F04 NEED_SLOT / INVALID_SLOT
        ↓
SlotInteractionContext
        ↓
F09 Specialized LangGraph
        ↓
interpret_slot_input
        ↓
   Local Explanation Detector
        ↓
 ┌───────────────┬────────────────┐
 ↓               ↓
Explanation      Not Explanation
 ↓               ↓
Explanation      AnswerMapper
Service          ↓
 ↓          SLOT / UNCERTAIN / OTHER
 ↓               ↓
resume        if SLOT
 ↓               ↓
complete      deterministic validate
                 ↓
             accepted?
               /   \
             no     yes
             ↓       ↓
           resume   F04 advance_until_blocked
             ↓       ↓
          complete  complete
```

### 16.4 Explanation Remote Path

```text
USER_FREE_TEXT 「什么是社保转移？」
        ↓
LOCAL detector（0 network / 0 LLM）
        ↓
normalized topic 「社保转移」
        ↓
ExplanationRequest（无 raw user text 字段）
        ↓
F07 Provider（SYSTEM_CONTROL_DATA + PUBLIC_BUSINESS_METADATA）
        ↓
Company LLM → strict JSON → local safety guard
        ↓
safe explanation + original question_text → resume slot
```

### 16.5 Answer Mapper Remote Path

```text
User Slot Answer
        ↓
AnswerMappingRequest（含 USER_FREE_TEXT classification）
        ↓
LlmProvider
        ↓
若 Company Remote Provider → F07 Policy = DENY before network
        ↓
未来 Local / Fake / Demo Provider 可处理
```

---

## 17. Design Decisions D01–D20

### D01 — Interpretation Domain（OI-F09-02 RESOLVED）

**冻结 `UtteranceKind`（StrEnum）exact members：**

- `SLOT_ANSWER`
- `EXPLANATION_REQUEST`
- `UNCERTAIN`
- `OTHER`

**冻结 `UtteranceInterpretation`（Pydantic v2，`extra="forbid"`）：**

| kind | mapped_value | confidence | explanation_topic |
|------|--------------|------------|-------------------|
| `SLOT_ANSWER` | nonblank `str` | finite float ∈ [0.0, 1.0] | `None` |
| `EXPLANATION_REQUEST` | `None` | `None` | nonblank controlled topic |
| `UNCERTAIN` | `None` | `None` | `None` |
| `OTHER` | `None` | `None` | `None` |

非法组合 → fail closed。

**来源边界：**

- `EXPLANATION_REQUEST` ← **仅** Local Explanation Detector
- `SLOT_ANSWER` / `UNCERTAIN` / `OTHER` ← Answer Mapper
- Remote Mapper **不得**产出 `EXPLANATION_REQUEST`

**Remote / Mapper 内部 kind：** 独立 internal enum `MapperUtteranceKind`（exact：`SLOT_ANSWER` / `UNCERTAIN` / `OTHER`），避免 Remote Provider 拥有解释路由权。

---

### D02 — SlotInteractionContext

**冻结 `SlotInteractionContext`（Pydantic v2，`extra="forbid"`）：**

| 字段 | 约束 |
|------|------|
| `transition_status` | 仅 `TransitionStatus.NEED_SLOT` 或 `INVALID_SLOT`（使用真实 F04 enum） |
| `current_node_id` | nonblank `str` |
| `required_slot` | nonblank `str` |
| `allowed_values` | 内部 `tuple[str, ...]`（immutable）；序列化进 artifacts 时 → `list[str]` |
| `question_text` | nonblank `str` |
| `invalid_value` | NEED_SLOT → `None`；INVALID_SLOT → nonblank `str` |
| `current_slots` | `dict[str, str]`（JSON-safe controlled map；已有 validated slots） |

**构造：** 由真实 F04 `TransitionResult` + 调用方持有的 current validated slots 构造。
**禁止：** LLM 创建 `current_node_id` / `required_slot` / `allowed_values` / `question_text`。

---

### D03 — Local Explanation Detector（OI-F09-04 RESOLVED）

| 属性 | 冻结 |
|------|------|
| Location | **LOCAL** |
| Deterministic | **YES** |
| Network / LLM / Embedding | **NO** |
| Priority | **FIRST** in `interpret_slot_input`；命中则 **不**调用 AnswerMapper |

**通用解释意图句式（语义；Code 用 regex 实现，禁止 golden-specific hardcode）：**

- 什么是 X
- X 是什么意思
- X 是指什么
- 请解释一下 X
- 能解释一下 X 吗 / 可以解释一下 X 吗

**Topic pipeline：**

1. 从句式提取 candidate topic
2. Normalize：trim；去掉常见问号/句号；压缩空白；去掉礼貌尾词
3. **Topic Trust Gate：** candidate 必须是当前 `question_text` 中的**明确连续文本**（substring containment）
4. 长度：1～64 Unicode chars；否则 fail safe → `OTHER`
5. 无法唯一确定 / 不在 `question_text` → **不得 Remote** → `OTHER`

**Comparison question**（如「缴费和转移有什么区别」）→ **DEFERRED** → `OTHER`。

Detector **不决定** slot value；不改变 Business Decision。

---

### D04 — AnswerMapper Protocol

```text
AnswerMapper (Protocol, SYNC ONLY)
  map_answer(request: AnswerMappingRequest) -> MapperStructuredOutput
```

**`AnswerMappingRequest` 最小字段：**

- `required_slot: str`
- `allowed_values: tuple[str, ...]`
- `user_text: str`
- 可带少量 system-control instruction

**禁止字段：** `business_id` / materials / locations / legal_basis / 整个 graph。

**`ProviderBackedAnswerMapper`：**

- 复用 F07 `LlmProvider` + `parse_structured_output`
- `LlmRequest` message classifications **必须包含** `DataClassification.USER_FREE_TEXT`
- 若底层为 `OpenAICompatibleLlmProvider`：真实调用在 network 前被 F07 Policy **DENY**
- F09 **不得**绕过 Policy
- 同一 Protocol 可接：Fake / Demo / 未来 Local LLM

**Mapper structured schema（Pydantic，`extra="forbid"`）：**

| kind (`MapperUtteranceKind`) | mapped_value | confidence |
|------------------------------|--------------|------------|
| `SLOT_ANSWER` | nonblank | finite [0,1] |
| `UNCERTAIN` | `None` | `None` |
| `OTHER` | `None` | `None` |

**禁止 mapper 字段：** `next_node` / `business_id` / `candidate_business_id` / `rule_result` / materials / locations / channels / legal_basis。
Parsing：**仅** F07 `DIRECT_JSON` / `STRICT_SINGLE_JSON_CODE_FENCE`；**禁止** repair。

---

### D05 — Confidence（OI-F09-01 RESOLVED）

| 项 | 冻结 |
|----|------|
| Range | finite float **[0.0, 1.0]** |
| Threshold | **`min_confidence = 0.80`** |
| Operator | **`confidence >= 0.80`** |
| Owner | deterministic **Controller / validator**（非 LLM） |
| Storage | immutable **`MappingPolicy(min_confidence=0.80)`** |
| Settings / `.env.example` | **不修改** |

**说明：** 0.80 是 **Demo baseline**，不是统计校准后的生产阈值；正式上线需标注数据 / calibration 后再调。未来可由 Settings 构造 MappingPolicy，不在本 Feature 做。

---

### D06 — Mapping Validation

与 Mapper **分离**；纯 deterministic Python。

**顺序：**

1. 若 `interpretation.kind != SLOT_ANSWER` → 不进入 membership/confidence → `NOT_SLOT_ANSWER`
2. 若 SLOT_ANSWER：先 **membership** `mapped_value ∈ allowed_values`
3. 再 **confidence** `>= policy.min_confidence`

**`MappingValidationStatus`（StrEnum）exact：**

- `ACCEPTED`
- `INVALID_VALUE`
- `LOW_CONFIDENCE`
- `NOT_SLOT_ANSWER`

**`ValidatedSlot`：** 仅 `ACCEPTED` 产生；字段 `slot_name` / `value` / `confidence`；JSON-safe。

**禁止：** fuzzy match / embedding / second LLM / closest option。

Explanation 路径 **不**走 mapping validation。

---

### D07 — ExplanationService（OI-F09-03 / OI-F09-05 RESOLVED）

```text
ExplanationService (Protocol, SYNC ONLY)
  explain(request: ExplanationRequest) -> ExplanationResult
```

**`ExplanationRequest`（机械隐私边界）：**

| 字段 | 允许 |
|------|------|
| `topic: str` | controlled normalized topic |
| `public_context: dict[str, str]` | 仅调用方明确的 PUBLIC_BUSINESS_METADATA；Demo 允许 `{}` |

**类型层禁止：** `user_text` / `raw_query` / `input_text` / `reasoning`。
→ Company implementation **天然拿不到**原始用户问题。

**`ExplanationStatus`：** `ANSWERED` / `UNSUPPORTED` / `UNAVAILABLE`

**`ExplanationResult` matrix：**

| status | text |
|--------|------|
| `ANSWERED` | nonblank safe explanation |
| `UNSUPPORTED` | `None` |
| `UNAVAILABLE` | `None` |

**`LlmExplanationService`（provider-neutral；可注入 Company Provider）：**

- Remote `LlmRequest` classifications：**仅** `SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA`
- Remote 可见：task=`explain_public_concept`；topic；optional public_context；constraints
- **默认不发送**整段 `question_text`（留在 local composition）
- **不发送** raw `input_text`
- Output：**STRICT STRUCTURED JSON** `{"explanation":"..."}`，`extra="forbid"`；禁止 materials/location/eligibility/legal_basis/business_id
- `explanation` trim 后 **1～500** Unicode chars

**Local high-risk wording guard（conservative Demo deny-list semantics）：**
材料 / 提交材料 / 办理地点 / 窗口 / 地址 / 费用 / 金额 / 办理时限 / 工作日 / 法律依据 / 政策依据 / 资格条件 / 符合条件 / 需要携带

命中 → 不展示 remote explanation → `UNSUPPORTED` + local safe fallback + resume。
不是 Business Rule；不是正式政策审查系统。

**Known errors：**

- `LlmProviderError` → Explanation `UNAVAILABLE` / controlled failure；**no F04 advance**
- `StructuredParseError` → distinct；**no F04 advance**

Company LLM **不是**事实源 / Runtime SoT / Business Decision Evidence。

未来：`GovernmentEncyclopediaExplanationService` 实现同一 Protocol → Agent Graph **无需结构性重写**。

---

### D08 — Response Composition（OI-F09-06 RESOLVED）

**LOCAL DETERMINISTIC**；LLM 不得自由重写问题。

| 情况 | `response_text` |
|------|-----------------|
| Explanation success | `{safe_explanation}\n\n{question_text}` |
| Explanation failure / unsafe / unavailable | `这个概念我暂时无法提供可靠解释，我们先继续确认您要办理的业务。\n\n{question_text}` |
| Uncertain | `我还不能确定您的意思，请根据当前选项再说明一下。\n\n{question_text}` |
| Other | `您刚才的内容没有直接回答当前办理选项，我们先继续确认当前事项。\n\n{question_text}` |
| INVALID_VALUE / LOW_CONFIDENCE | Uncertain-style 受控 fallback + `{question_text}` |

第二段 **必须**来自原 F04 `question_text`。

---

### D09 — AgentState / Artifacts（OI-F09-07 RESOLVED）

| 项 | 冻结 |
|----|------|
| Top-level fields | **仍 7**；**不修改** `state.py` |
| Namespace | **`artifacts["f09"]` 唯一** |
| Layout | 见下表 |
| Raw user text | **不**再存（已有 `input_text`） |
| Raw provider body / reasoning | **禁止** |
| Ownership | nodes 不得 in-place mutate input State |
| Merge | artifacts **非 reducer** → node 必须 deep-copy/merge 现有 artifacts，再替换 `f09`；保留其它 Feature namespace |

**`artifacts["f09"]` 语义结构（字段可为 `None`）：**

```text
{
  "slot_context": ...,
  "interpretation": ...,
  "mapping_validation": ...,
  "validated_slot": ...,
  "explanation": ...,
  "business_transition": ...,
  "response_text": ...,
  "failure": ...   # optional controlled metadata
}
```

**`business_transition`：** 将 F04 `TransitionResult` 转为 JSON-safe dict（Enum → `.value`）；最小化受控字段：`status` / `current_node_id` / `required_slot` / `allowed_values` / `question_text` / `candidate_business_id` / `unsupported_reason`（按需）。
`candidate_business_id` 仅来自 F04 deterministic result，**不是** LLM。

**Known interaction failure：** 因 `WorkflowErrorCode` 当前仅 `INVALID_STATE` 且本 Feature **不改** `state.py`，通过 `artifacts["f09"]["failure"]` 表示；不扩展 `WorkflowErrorCode`。

**`InteractionFailureKind` exact：**

- `MAPPER_PROVIDER_ERROR`
- `MAPPER_PARSE_ERROR`
- `EXPLANATION_PROVIDER_ERROR`
- `EXPLANATION_PARSE_ERROR`
- `EXPLANATION_UNSAFE_OUTPUT`

Failure metadata：仅 `kind` + optional safe static message；**禁止** raw exception / provider body / user text / traceback / secret。

---

### D10 — F04 Integration

| 项 | 冻结 |
|----|------|
| 触发条件 | **仅** `MappingValidationStatus.ACCEPTED` |
| Slot merge | `new_slots = copy(current_slots)`；`new_slots[required_slot] = validated.value`；不修改 caller map |
| F04 API | **`advance_until_blocked(graph: DecisionGraph, current_node_id: str, slots: Mapping[str, str]) -> TransitionResult`** |
| 选择理由 | 写入一个 validated slot 后继续确定性推进直至下一 blocking / terminal-like 状态；与真实 F04 语义一致 |
| Authority | F09 **不计算** next node；只调用并消费 `TransitionResult` |
| `TERMINAL_CANDIDATE` | 可记录；**不得**转为 confirmed `business_id`（F10） |
| `UNSUPPORTED` / `FALLBACK` | 只保留 result；不自行改成其它事项 |
| Explanation / Uncertain / Other / invalid / low-confidence / known failure | **不调用** F04 |

注入真实 F04 domain object：`DecisionGraph`（经 `SlotInteractionDependencies`）。

---

### D11 — Dependency Injection

**冻结 `SlotInteractionDependencies`（immutable dataclass / frozen）：**

- `answer_mapper: AnswerMapper`
- `explanation_service: ExplanationService`
- `decision_graph: DecisionGraph`
- `mapping_policy: MappingPolicy`

| 规则 | 冻结 |
|------|------|
| Dependencies 进入 AgentState | **NO** |
| DI framework | **NO**（dataclass / factory / closure） |
| Provider / Graph / Policy / Service 入 State | **NO** |

---

### D12 — LangGraph Topology（OI-F09-08 RESOLVED）

**保持 F08 兼容：**

- `build_agent_workflow()` / `run_agent_workflow()` **语义不变**
- 默认拓扑仍：`START → prepare → complete → END`

**新增 F09 specialized API（`workflow.py`）：**

- `build_slot_interaction_workflow(deps: SlotInteractionDependencies)`
- `run_slot_interaction_workflow(initial_state: AgentState, deps: SlotInteractionDependencies)`

**不覆盖** F08 default builder；完整 E2E topology 留给 F12。

**F09 specialized topology（7 execution nodes）：**

```text
START
 → prepare
 → interpret_slot_input
 → conditional route #1 (interpretation.kind)

EXPLANATION_REQUEST
 → explain_current_topic
 → resume_current_slot
 → complete → END

SLOT_ANSWER
 → validate_slot_answer
 → conditional route #2 (mapping_validation.status)
      ACCEPTED → advance_business_graph → complete → END
      INVALID_VALUE | LOW_CONFIDENCE | NOT_SLOT_ANSWER → resume_current_slot → complete → END

UNCERTAIN → resume_current_slot → complete → END
OTHER     → resume_current_slot → complete → END
```

| 项 | 冻结 |
|----|------|
| Execution nodes | `prepare`, `interpret_slot_input`, `explain_current_topic`, `validate_slot_answer`, `advance_business_graph`, `resume_current_slot`, `complete` = **7** |
| Conditional routers | **2**；纯函数；只读 controlled artifact；**0** LLM / network / business reasoning |
| `explain_current_topic` 调用 F04 | **NO** |
| `advance_business_graph` 调用 F04 | **YES**（仅 ACCEPTED） |
| LangGraph END | **≠** Business `TERMINAL_CANDIDATE` |

**Node 职责摘要：**

- `interpret_slot_input`：validate state → read `input_text` + slot_context → local detector FIRST → else AnswerMapper
- `explain_current_topic`：ExplanationService；不改 `current_slots`
- `validate_slot_answer`：membership + confidence；无 LLM
- `advance_business_graph`：copy-merge slots → `advance_until_blocked` → store controlled result
- `resume_current_slot`：D08 composition → `response_text`
- `prepare` / `complete`：复用 F08 语义

---

### D13 — Error Semantics

| # | Category | Behavior |
|---|----------|----------|
| 1 | Input/Context Contract Error | fail closed（validation error） |
| 2 | Mapper Provider Error | `MAPPER_PROVIDER_ERROR`；resume；no F04 |
| 3 | Mapper Parse Error | `MAPPER_PARSE_ERROR`；resume；no F04 |
| 4 | Mapping Uncertain | resume；no F04 |
| 5 | Mapping Invalid Value | resume；no F04 |
| 6 | Mapping Low Confidence | resume；no F04 |
| 7 | Explanation Provider Error | `EXPLANATION_PROVIDER_ERROR` / UNAVAILABLE；resume；no F04 |
| 8 | Explanation Parse Error | `EXPLANATION_PARSE_ERROR`；resume；no F04 |
| 9 | Explanation Unsafe Output | `EXPLANATION_UNSAFE_OUTPUT`；resume；no F04 |
| 10 | Business `INVALID_SLOT` | F04 返回；可再问/再 map |
| 11 | Unexpected Programming Error | **自然 propagate**；禁止 broad `except Exception` 伪装 UNCERTAIN |

**不修改** `WorkflowErrorCode`。

---

### D14 — Logging

允许（若记录）：`request_id` / route kind / controlled slot name / controlled mapped value / numeric confidence / validation status / failure kind。

**禁止：** `input_text` / raw answer / prompt / remote response / reasoning / credential。

本 Feature **不**新增复杂 logging framework。

---

### D15 — Data Policy（OI-F09-DP-001 保持 OPEN / RUNTIME VALIDATION PENDING）

| Path | Classification | Company Remote |
|------|----------------|----------------|
| Answer Mapper request | **含** `USER_FREE_TEXT` | **DEFAULT：DENY before network**；显式 **DEMO_APPROVED**：Policy 可 ALLOW（Owner Demo 授权）。**真实 Runtime 未验证** |
| Explanation request | **仅** `SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA` | Demo **可行**（因无 raw user text） |

**为什么 Demo Explanation 可行：** Local detector 已 normalize；`ExplanationRequest` 类型无 raw user field；Remote 仅 ALLOW 分类。**不是**放宽 `USER_FREE_TEXT` Policy。

**F07 Policy Reopen 进展：** Demo Profile 实现已 Review PASS；`OI-F09-DP-001` **不关闭**，直至 F12 真实 Remote USER_FREE_TEXT probe PASS。

Real Company Explanation Smoke = **OPTIONAL / OPT-IN**；非 Acceptance blocker。Default pytest：**0 network**。

---

### D16 — Public API

- **不新增** HTTP endpoint / New Port
- `agent/__init__.py` 仅 export 稳定：domain types / policy / Protocols / workflow builder-runner
- **不 export：** private nodes / regex helpers / safety keyword internals

---

### D17 — Dependencies / Config

| 项 | 冻结 |
|----|------|
| Mandatory new dependency | **NONE** |
| `pyproject.toml` | **不修改**（若 Code 发现必须 → DESIGN DEVIATION / STOP） |
| `settings.py` / `.env.example` | **不修改** |
| LangChain / Tool Calling / Embedding / ASR | **不引入** |

---

### D18 — Test Design

**Files：**

| Path | Op |
|------|----|
| `tests/test_agent_interaction.py` | **NEW** |
| `tests/test_agent_workflow.py` | **MODIFY**（保留全部 F08 tests + F09 specialized invoke） |

**不新增**第三个 F09 test file。不冻结最终 pytest 数量；冻结 coverage。

**`test_agent_interaction.py` 至少覆盖：**
UtteranceInterpretation matrix；Mapper output matrix；confidence finite/range；MappingPolicy threshold；membership；low confidence；hallucinated value；SlotInteractionContext NEED_SLOT/INVALID_SLOT；immutability；local explanation detector；generic explanation forms；topic containment；unknown topic denied；topic max length；ExplanationRequest no raw text；ExplanationResult matrix；safety guard；response composition；known error categories；serialization；secret boundary；mapper request 声明 USER_FREE_TEXT；explanation request classifications 仅 ALLOW。

**Detector 必测：**

- 「什么是社保转移？」→ `EXPLANATION_REQUEST` / topic「社保转移」/ **无** validated `transfer`
- Generic synthetic：「什么是事项A？」且 `question_text` 含「事项A」→ explanation（证明非 golden hardcode）
- Unknown：「什么是养老金计算？」且 question 不含该词 → **不得** Remote Explanation → `OTHER`

**`test_agent_workflow.py` Golden 至少：**
A accepted → F04 advance；B「什么是社保转移？」explanation / F04 call count=0 / resume；C hallucinated；D low confidence；E uncertain；F other；G mapper provider error；H mapper parse error；I explanation provider error；J explanation parse error；K unsafe explanation；L F04 INVALID_SLOT context；M TERMINAL_CANDIDATE not confirmed。

另：Capturing Provider 断言 explanation payload 含 normalized topic、**不含** raw user input；至少 1 个真实 F04 demo graph / `advance_until_blocked` 集成（Fake Mapper；0 DB）。

Default：**0 network / 0 DB / 0 Redis / 0 Embedding / 0 Real Company LLM**。

---

### D19 — Production Module Design

| Module | Op | 职责 |
|--------|----|------|
| `agent/interaction.py` | **NEW** | UtteranceKind / interpretation / SlotInteractionContext / AnswerMapper / ProviderBackedAnswerMapper / MappingPolicy / validation / ValidatedSlot / local detector / artifact helpers / InteractionFailureKind / response composition |
| `agent/explanation.py` | **NEW** | ExplanationService / Request / Status / Result / LlmExplanationService / structured schema / remote payload / safety guard |
| `agent/nodes.py` | **MODIFY** | private F09 LangGraph node factories/functions |
| `agent/workflow.py` | **MODIFY** | 保留 F08 builder/runner；新增 deps + specialized builder/runner + routers |
| `agent/__init__.py` | **MODIFY** | public stable exports |
| `agent/state.py` | **0 MODIFY** | 若必须改 → DESIGN DEVIATION / STOP |

Core Python：NEW **2**；MODIFY core **3**（`__init__` / `nodes` / `workflow`）。

---

### D20 — Final File Scope（9 paths）

| # | Path | Op |
|---|------|----|
| 1 | `src/gov_service_agent/agent/__init__.py` | MODIFY |
| 2 | `src/gov_service_agent/agent/nodes.py` | MODIFY |
| 3 | `src/gov_service_agent/agent/workflow.py` | MODIFY |
| 4 | `src/gov_service_agent/agent/interaction.py` | NEW |
| 5 | `src/gov_service_agent/agent/explanation.py` | NEW |
| 6 | `tests/test_agent_interaction.py` | NEW |
| 7 | `tests/test_agent_workflow.py` | MODIFY |
| 8 | `docs/features/F09-missing-slot-question-answer-mapping.md` | NEW（本阶段继续 MODIFY） |
| 9 | `docs/code-reading/F09-missing-slot-question-answer-mapping-code-reading.md` | NEW at Code-Reading stage |

**Total = 9。第 10 path = Design Deviation + Owner authorization。**
Code-Reading **已提前计入**；后期不需 docs-only exception。

**不修改：** F04 / F06 / F07 / F08 `state.py` / graph JSON / Settings / `.env.example` / `pyproject.toml`。

---

## 18. Acceptance Design Mapping（15 Categories）

| Category | Covered by |
|----------|------------|
| A Missing Slot | D02 / D10 / D12 |
| B Question Determinism | D02 / D08（原样 `question_text`） |
| C Input Classification | D01 / D03 / D04 |
| D Slot Mapping | D04 |
| E Membership | D06 |
| F Confidence | D05 / D06 |
| G Explanation Side Route | D03 / D07 / D08 / D12 |
| H Demo Company Explanation | D07 / D15 |
| I Data Policy | D04 / D07 / D15 / OI-F09-DP-001 |
| J Failure Handling | D13 |
| K LangGraph | D12 |
| L Business Graph | D10 |
| M State Safety | D09 / D14 |
| N Zero-Network Tests | D18 |
| O Future Encyclopedia | D07 Protocol replaceability；D04 LocalMapper replaceability |

**48 AC 均被 D01–D20 覆盖。**

---

## 19. OI Resolution Table（Authoritative）

| ID | Status |
|----|--------|
| OI-F09-01 | **RESOLVED** — range [0,1]；threshold 0.80；Controller；MappingPolicy；Settings unchanged |
| OI-F09-02 | **RESOLVED** — UtteranceKind + UtteranceInterpretation + MapperUtteranceKind |
| OI-F09-03 | **RESOLVED** — ExplanationService Protocol |
| OI-F09-04 | **RESOLVED** — local deterministic patterns + topic extract + question_text containment |
| OI-F09-05 | **RESOLVED** — strict JSON `{explanation}`；max 500；local high-risk guard |
| OI-F09-06 | **RESOLVED** — local composition：explanation/service text + F04 question_text |
| OI-F09-07 | **RESOLVED** — 7 fields；`artifacts["f09"]` |
| OI-F09-08 | **RESOLVED** — F08 default preserved；F09 specialized 7-node workflow |
| OI-F09-DP-001 | **OPEN / RUNTIME VALIDATION PENDING** |

---

## 20. Technical Design Stage Status

| 项 | 结论 |
|----|------|
| Technical Design | **FINAL / CLOSED** |
| Technical Design Finalization | **NOT REQUIRED** |
| Owner Input Required（for TD） | **NO** |
| BLOCKING | **0** |
| MAJOR Design Concerns | **NONE** |
| Unresolved Design Items（blocking） | **NONE** |
| 建议下一步 | Owner 授权后进入 **F09 Confirm** → **已完成**；等待 Owner 授权 **Code** |

### Why FINAL（无需 Finalization）

真实代码核验通过：

1. F04 `advance_until_blocked(DecisionGraph, current_node_id, slots)` 可 deterministic integrate
2. F07 Company Provider 在 network 前 Policy fail-closed
3. F08 `artifacts` JSON-safe 可承载 `artifacts["f09"]`（非 reducer → merge 已设计）
4. F08 default workflow 可保持；specialized builder 可新增
5. Company explanation **不需要** raw user text（ExplanationRequest 无该字段）
6. 9-path scope 足够；无第 10 path

### Technical Design Findings

1. Local-first explanation detection 是 Data Policy 与「什么是社保转移？」防误映射的关键。
2. Remote Mapper 永久不含 `EXPLANATION_REQUEST` 路由权。
3. Threshold 用 MappingPolicy 避免 Settings scope 扩大。
4. Known failures 走 `artifacts["f09"].failure`，避免修改 F08 `WorkflowErrorCode`。
5. F09 specialized workflow 与 F08 skeleton 并存，避免提前冻结 F12 E2E。

---

## 21. Confirm

| 字段 | 内容 |
|------|------|
| Confirm Date | **2026-09-09** |
| Confirm | **COMPLETE** |
| Code Readiness | **READY** |
| Requirement | **CLOSED** |
| Requirement Finalization | **NOT REQUIRED** |
| Technical Design | **FINAL / CLOSED** |
| TD Finalization | **NOT REQUIRED** |
| BLOCKING | **0** |
| MAJOR | **0** |
| Final Planned Paths | **9** |
| Data Policy Open Item | **OI-F09-DP-001 = OPEN / RUNTIME VALIDATION PENDING** |

### 21.1 Confirm Re-Verification（真实代码）

| Gate | 结果 | 证据 |
|------|------|------|
| F04 API Reality | **PASS** | `advance_until_blocked(graph: DecisionGraph, current_node_id: str, slots: Mapping[str, str]) -> TransitionResult`；可从 current_node + slots 确定性推进至 blocking/terminal-like |
| F07 Policy before network | **PASS** | `OpenAICompatibleLlmProvider.complete` 先 `evaluate_request_remote_policy`；DENIED → `LlmProviderError(POLICY_DENIED)`；无 HTTP |
| F08 default workflow | **PASS** | `build_agent_workflow` / `run_agent_workflow`：`START → prepare → complete → END`；F09 仅新增 specialized builder，不覆盖 |
| AgentState / artifacts | **PASS** | 7 fields；`artifacts` 非 reducer；JSON-safe；`WorkflowErrorCode` 仅 `INVALID_STATE` → F09 known failure 走 `artifacts["f09"]` |
| Explanation privacy | **PASS** | TD `ExplanationRequest` 无 raw user 字段 → 类型层机械约束 |
| Answer Mapping Remote | **PASS** | Mapper 声明 `USER_FREE_TEXT` → Company Remote **DENY**；F09 不得绕过 |

### 21.2 Requirement ↔ TD Traceability

| Category | Covered | Implementable | Testable | Traceable |
|----------|---------|---------------|----------|-----------|
| 1 Missing Slot | YES (D02/D10/D12) | YES | YES | YES |
| 2 Question Determinism | YES (D02/D08) | YES | YES | YES |
| 3 Input Semantic Classification | YES (D01/D03/D04) | YES | YES | YES |
| 4 Slot Mapping | YES (D04) | YES | YES | YES |
| 5 Membership Validation | YES (D06) | YES | YES | YES |
| 6 Confidence Validation | YES (D05/D06) | YES | YES | YES |
| 7 Explanation Side Route | YES (D03/D07/D08/D12) | YES | YES | YES |
| 8 Demo Company Explanation | YES (D07/D15) | YES | YES | YES |
| 9 Data Policy | YES (D04/D07/D15) | YES | YES | YES |
| 10 Failure Handling | YES (D13) | YES | YES | YES |
| 11 LangGraph Boundary | YES (D12) | YES | YES | YES |
| 12 Business Graph Boundary | YES (D10) | YES | YES | YES |
| 13 State / Data Safety | YES (D09/D14) | YES | YES | YES |
| 14 Zero-Network Default Tests | YES (D18) | YES | YES | YES |
| 15 Future Encyclopedia Compatibility | YES (D07 Protocol) | YES | YES | YES |

**48 AC：全部 IMPLEMENTABLE / TESTABLE / TRACEABLE。**
**D01–D20：全部 coherent；无 Design Conflict。**

### 21.3 Core Boundary Confirmations

| 边界 | Confirm |
|------|---------|
| LLM / LangGraph 决定 business `next_node` / `business_id` / Rule / materials / locations / channels / legal basis | **FORBIDDEN / PASS** |
| Agent routing by `UtteranceKind` / `MappingValidationStatus` | **ALLOWED orchestration / PASS** |
| 「什么是社保转移？」→ validated `transfer` | **FORBIDDEN**；LOCAL detector → `EXPLANATION_REQUEST`；0 F04 |
| Detector before Mapper | **REQUIRED / PASS** |
| Remote Mapper emits `EXPLANATION_REQUEST` | **FORBIDDEN / PASS** |
| Only `ACCEPTED` → `advance_until_blocked` | **REQUIRED / PASS** |
| Explanation route F04 calls | **0 / PASS** |
| Company LLM fact authority | **NO / PASS** |
| F08 `build_agent_workflow` / `run_agent_workflow` | **PRESERVED / PASS** |
| `state.py` / Settings / pyproject / F04 / F06 / F07 / graph JSON | **0 modify planned / PASS** |

### 21.4 Confirm Findings

1. Requirement Scope A 与 TD D01–D20 / 9-path scope **一致**。
2. 真实 F04/F07/F08 接口与 TD **无冲突**；无需 TD Finalization。
3. Local-first Explanation Detection + `ExplanationRequest` 无 raw user 字段 → Data Policy 可机械执行。
4. OI-F09-01…08 保持 RESOLVED；OI-F09-DP-001 保持 OPEN / RUNTIME VALIDATION PENDING（F07 Demo Policy 已落地；非 Confirm blocker；关闭待 F12 Runtime）。
5. INFO-F09-01（F08 docs drift）继续 INFO；本 Confirm **不修改** F08。

### 21.5 Unresolved Findings

**NONE**（blocking）。
唯一保留 Open Item：OI-F09-DP-001（F07 Demo Policy 已落地；真实 USER_FREE_TEXT Company Runtime 未验证；OPEN / RUNTIME VALIDATION PENDING）。

---

## 22. Code Implementation Contract（FROZEN）

Code 阶段必须遵守：

1. **No `state.py` change**
2. **No Settings / `.env.example` change**
3. **No `pyproject.toml` change**
4. **No F04 / F06 / F07 changes**
5. **Local explanation detector BEFORE AnswerMapper**
6. **Remote Mapper cannot route Explanation**（无 `EXPLANATION_REQUEST` in mapper output）
7. **Only `MappingValidationStatus.ACCEPTED` calls F04**（`advance_until_blocked`）
8. **`ExplanationRequest` has no raw user field**
9. **Company explanation receives normalized topic only**（SYSTEM_CONTROL_DATA + PUBLIC_BUSINESS_METADATA）
10. **F08 default workflow preserved**（`build_agent_workflow` / `run_agent_workflow`）
11. **F09 specialized graph only**（`build_slot_interaction_workflow` / `run_slot_interaction_workflow`）
12. **`artifacts["f09"]` namespace only**；JSON-safe；merge 保留其它 namespace
13. **9-path maximum**；第 10 path = Design Deviation
14. **Default tests zero network**（0 Company LLM；0 Real USER_FREE_TEXT Remote mapping）

Additional frozen contracts：

- Confidence `[0.0, 1.0]`；`MappingPolicy.min_confidence = 0.80`；`confidence >= 0.80`
- Membership before confidence；hallucinated → `INVALID_VALUE`；low conf → `LOW_CONFIDENCE`；no F04
- Explanation STRICT JSON `{explanation}`；max 500；local high-risk guard
- Known failures via `InteractionFailureKind` in `artifacts["f09"]`；**不**改 `WorkflowErrorCode`
- Unexpected errors **propagate**；禁止 broad `except Exception → UNCERTAIN`
- `TERMINAL_CANDIDATE` ≠ confirmed `business_id`
- Dependencies in `SlotInteractionDependencies`；**不**入 AgentState
- Graph JSON **0 modify**；Production **无** golden-phrase hardcode

---

## 23. Code Stage Deviation Rule

Code 阶段若发现以下**任一**情况，必须立即 **STOP**，状态记为 **DESIGN DEVIATION**，等待 Owner：

1. 需要修改 `state.py`
2. 需要修改 Settings / `.env.example`
3. 需要修改 `pyproject.toml` / 新增 mandatory dependency
4. 需要第 **10** path
5. 需要修改 F04 / F06 / F07
6. Explanation Remote **必须**发送 raw `USER_FREE_TEXT`
7. 无法保留 F08 `build_agent_workflow` / `run_agent_workflow` 行为
8. 真实 F04 API 与 TD（`advance_until_blocked`）不兼容
9. 无法在不破坏 7-field State 的前提下承载 `artifacts["f09"]`
10. 必须修改 Business Graph JSON 才能通过 AC

**禁止**自行改写 D01–D20 或扩大 Scope 后继续 Code。

---

## 24. Confirm Stage Status

| 项 | 结论 |
|----|------|
| Confirm | **COMPLETE** |
| Code Readiness | **READY** |
| TD Finalization needed | **NO** |
| Owner Input Required（for Confirm） | **NO** |
| BLOCKING / MAJOR | **0 / 0** |
| 建议下一步 | Owner 授权后进入 **F09 Code** → **已完成**；等待 Owner 授权 **Test** |

---

## 25. Code

| 字段 | 内容 |
|------|------|
| Code Date | **2026-09-09** |
| Code | **COMPLETE** |
| Test | **NOT STARTED** |
| Design Deviation | **NONE** |
| BLOCKING | **0** |
| MAJOR | **0** |
| Code-stage paths | **6** |
| Final Feature paths (planned) | **9** |

### 25.1 Implemented Modules

| Path | Op | 职责 |
|------|----|------|
| `agent/interaction.py` | NEW | UtteranceKind / MapperUtteranceKind / interpretation / SlotInteractionContext / AnswerMapper / LlmAnswerMapper / MappingPolicy / validation / ValidatedSlot / local detector / failure kinds / response composition / artifact helpers |
| `agent/explanation.py` | NEW | ExplanationService / Request / Status / Result / LlmExplanationService / strict JSON schema / `is_safe_explanation_text` |
| `agent/nodes.py` | MODIFY | 保留 F08 `_prepare_node` / `_complete_node`；新增 F09 private node factories + 2 pure routers |
| `agent/workflow.py` | MODIFY | 保留 F08 builder/runner；新增 `SlotInteractionDependencies` / `build_slot_interaction_workflow` / `run_slot_interaction_workflow` |
| `agent/__init__.py` | MODIFY | 保留 F08 exports；新增 F09 public API |
| Feature Doc | MODIFY | Code record |

**Unchanged：** `state.py` / Settings / pyproject / F04 / F06 / F07 / graph JSON。

### 25.2 Public API（implemented）

`UtteranceKind`, `MapperUtteranceKind`, `UtteranceInterpretation`, `SlotInteractionContext`, `build_slot_interaction_context`, `AnswerMapper`, `AnswerMappingRequest`, `AnswerMapperOutput`, `LlmAnswerMapper`, `MappingPolicy`, `MappingValidationStatus`, `MappingValidationResult`, `ValidatedSlot`, `validate_slot_mapping`, `InteractionFailureKind`, `ExplanationService`, `ExplanationRequest`, `ExplanationStatus`, `ExplanationResult`, `LlmExplanationService`, `SlotInteractionDependencies`, `build_slot_interaction_workflow`, `run_slot_interaction_workflow`（+ F08 API 全保留）。

**Not exported：** private nodes、routers、regex patterns、safety marker set、prompt builders、artifact private helpers。

### 25.3 Runtime Topology（implemented）

F08 default（preserved）：

```text
START → prepare → complete → END
```

F09 specialized（7 execution nodes，2 pure routers）：

```text
START → prepare → interpret_slot_input → route(kind)
  EXPLANATION_REQUEST → explain_current_topic → resume_current_slot → complete → END
  SLOT_ANSWER → validate_slot_answer → route(validation)
      ACCEPTED → advance_business_graph → complete → END
      INVALID_VALUE|LOW_CONFIDENCE|NOT_SLOT_ANSWER → resume → complete → END
  UNCERTAIN|OTHER → resume_current_slot → complete → END
```

### 25.4 Artifacts Layout（implemented）

`artifacts["f09"]`：

```text
slot_context, interpretation, mapping_validation, validated_slot,
explanation, business_transition, failure, response_text
```

**Clarification：** `failure` 是 D13 Known Failure Metadata 的直接实现字段，**不是**新的 AgentState top-level field。

### 25.5 Key Contracts Implemented

| Contract | Implementation |
|----------|----------------|
| Local detector before Mapper | `interpret_slot_input` FIRST `detect_explanation_request` |
| Mapper kinds | `MapperUtteranceKind`：slot_answer / uncertain / other only |
| Mapper classifications | includes `USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA` |
| MappingPolicy | `min_confidence=0.80`；immutable；no Settings |
| Membership first | `validate_slot_mapping` |
| F04 call | only ACCEPTED → `advance_until_blocked(decision_graph, current_node_id, new_slots)` |
| ExplanationRequest | `topic` + `public_context` only（no raw user fields） |
| Explanation Remote classes | `SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA` only |
| Explanation JSON | `{"explanation":"..."}` max 500；extra forbid |
| Safety guard | node-level `is_safe_explanation_text` → UNSUPPORTED + `EXPLANATION_UNSAFE_OUTPUT` |
| Response composition | local deterministic；always appends original `question_text` |
| Known errors | catch only `LlmProviderError` / `StructuredParseError`；no broad Exception |
| Dependencies | `SlotInteractionDependencies`；not stored in State |
| No checkpointer / thread_id | compile without persistence |

### 25.6 Code Findings

1. Public API import probe：**PASS**（`F09_PUBLIC_API_OK`）。
2. F08 default workflow symbols retained。
3. No Design Deviation。
4. Test Stage 后续：**PASS**（见 §26）。

### 25.7 Code Stage Status

| 项 | 结论 |
|----|------|
| Code | **COMPLETE** |
| Test | **PASS**（Test Stage） |
| 建议下一步 | Owner 授权后进入 **F09 Review** |

---

## 26. Test

| 字段 | 内容 |
|------|------|
| Test Date | **2026-09-09** |
| Test | **PASS** |
| Review | **PASS**（见 §27 Review Notes） |
| Review Fix | **NOT REQUIRED** |
| Test Fixes | **0** |
| Design Deviation | **NONE** |
| BLOCKING / MAJOR / MINOR | **0 / 0 / 0**（Review INFO = 4） |
| Changed paths (Test Stage end) | **8** |
| Code-Reading path | **CREATED**（第 9 path；见 Code-Reading Stage） |

### 26.1 Test Evidence

| Suite | Result |
|-------|--------|
| `tests/test_agent_interaction.py` | **63 collected / 63 passed / 0 failed** |
| `tests/test_agent_workflow.py` | **24 collected / 24 passed / 0 failed**（含 F08 regression） |
| Combined F09 Targeted | **87 collected / 87 passed / 0 failed** |
| Full default regression | **469 passed / 0 failed / 13 skipped / 0 warnings** |
| `compileall src/gov_service_agent tests` | **PASS** |
| `pip check` | **PASS** |
| F09 Public API Import | **PASS**（`F09_PUBLIC_API_OK`） |
| F08 Public API Import | **PASS**（`F08_PUBLIC_API_OK`） |
| Secret Gate | **PASS** |
| Data Policy Gate | **PASS** |
| Business Boundary Gate | **PASS** |
| F08 Compatibility Gate | **PASS** |
| Real LLM / Company network | **NOT RUN / 0** |
| `.env` read | **NO** |

**Warnings classification：** 0 warnings；无 F09 新 warning。Skipped 13 = 既有 opt-in/integration（PRE-EXISTING）。

### 26.2 Golden Evidence

| Item | Result |
|------|--------|
| 「什么是社保转移？」Local Explanation | **PASS** |
| Mapper calls | **0** |
| F04 calls | **0** |
| Explanation calls | **1** |
| Resume exact original question | **PASS** |
| Generic「什么是事项A？」 | **PASS** |
| Unknown topic Explanation calls | **0** |
| Explanation Remote raw user input absent | **PASS** |
| Explanation Remote question sentinel absent | **PASS** |
| Explanation Remote normalized topic present | **PASS** |
| Explanation Remote USER_FREE_TEXT absent | **PASS** |
| LlmAnswerMapper USER_FREE_TEXT classification | **PASS** |
| Real Company Mapping smoke | **NOT RUN**（Policy DENY；非本阶段） |

### 26.3 Key Behavioral Evidence

| Scenario | Result |
|----------|--------|
| Hallucinated value → INVALID_VALUE；F04=0 | **PASS** |
| Low confidence 0.79 → LOW_CONFIDENCE；F04=0 | **PASS** |
| Threshold 0.80 accepted → F04 called | **PASS** |
| Real F04 employment_type → TERMINAL_CANDIDATE DEMO_SS_001；no confirmed_business_id | **PASS** |
| Mapper/Explanation provider & parse errors distinct | **PASS** |
| Unsafe explanation fail-closed；text not shown | **PASS** |
| Artifact other namespace preserved；stale f09 refreshed | **PASS** |
| Caller state/slots immutability；repeated isolation | **PASS** |

### 26.4 Test Stage Status

| 项 | 结论 |
|----|------|
| Test | **PASS** |
| Review | **PASS** |
| Review Fix | **NOT REQUIRED** |
| Explanation | **COMPLETE**（见 §27） |
| Code-Reading | **COMPLETE** |
| 建议下一步 | Owner 授权后进入 **F09 Push** |

---

**END OF F09 TEST**

---

## 27. Explanation

> 本节基于真实 Production（`interaction.py` / `explanation.py` / `nodes.py` / `workflow.py` / `__init__.py`）与 Tests，串起 Requirement → TD → Code → Test → Review。不重新设计 D01–D20；不修改 Production / Tests。

### 1. F09 一句话定位

F09 负责：**在 Business Decision Graph 已经确定当前缺失槽位后，把用户自然语言解释为受控槽位答案、解释请求或其它语义，并且只有经过确定性校验的槽位答案才允许交给 F04 继续推进业务图。**

F09 **不**决定最终办哪个事项，也 **不**自行计算业务 `next_node` / `business_id` / Rule。

### 2. 为什么需要 F09

F04 已经能确定性给出：

- 当前缺什么槽位（`required_slot`）
- 合法取值集合（`allowed_values`）
- 要问用户什么（`question_text`）
- 以及 `NEED_SLOT` / `INVALID_SLOT` 等推进状态

但 F04 **不负责理解自然语言**。用户常说的是：

> 「平时接零活，没有固定单位。」

而业务图需要的是受控枚举（例如某个 `employment_type` 的 allowed value）。F09 的第一职责，就是把自然语言映射到 `allowed_values` 中的受控值，再经 deterministic validation 后交回 F04。

F09 还有第二职责：用户未必在“回答槽位”，也可能在问选项含义，例如：

> 「什么是社保转移？」

这时应走 **Explanation Side Route**：解释概念、恢复原问题，**不推进业务图**。

### 3. F09 总体运行链路

```text
F04
NEED_SLOT / INVALID_SLOT
        ↓
SlotInteractionContext
        ↓
F09 Specialized LangGraph
        ↓
interpret_slot_input
        ↓
Local Explanation Detector FIRST
        ↓
 ┌────────────────────────────┐
 │                            │
Explanation Request      Not Explanation
 │                            │
 ↓                            ↓
ExplanationService        AnswerMapper
 │                            │
 ↓                      SLOT / UNCERTAIN / OTHER
resume                         │
 │                         SLOT only
complete                       ↓
                       deterministic validation
                              │
                      membership + confidence
                              │
                       ┌──────┴──────┐
                       │             │
                     reject        ACCEPTED
                       │             │
                     resume          ↓
                                  F04
                            advance_until_blocked
```

#### 双 Routing（必须区分）

| 类型 | Owner | 决定什么 |
|------|-------|----------|
| **A. Agent Orchestration Routing** | LangGraph（F09 nodes/routers） | 走 explanation / validation / resume |
| **B. Business Routing** | F04 `advance_until_blocked` | 业务图走到哪个节点 |

LangGraph **不会**因为 `mapped_value=transfer` 就自行选择业务 `next_node`。业务推进权只属于 F04。

### 4. `interaction.py`

该模块是 F09 的 **domain / mapping / local detector / validation / composition** 层。

| 能力 | 为什么存在 |
|------|------------|
| `UtteranceKind` | Agent 对本轮用户话语“作用”的四类语义分类（非业务类目） |
| `MapperUtteranceKind` | Mapper 只允许 SLOT/UNCERTAIN/OTHER；解释权不交给 Remote |
| `UtteranceInterpretation` | 严格 matrix：SLOT 必有 value+confidence；EXPLANATION 必有 topic；UNCERTAIN/OTHER 不得偷带 mapped_value |
| `SlotInteractionContext` | F04 → F09 桥梁；字段来自真实 `TransitionResult` + 当前 slots，不是 LLM 生成 |
| `AnswerMappingRequest` | Mapper 输入契约：required_slot / allowed_values / user_text |
| `AnswerMapper` Protocol | 能力接口，可替换后端（当前 `LlmAnswerMapper`，未来 LocalModel） |
| `LlmAnswerMapper` | 经 F07 Provider + strict parser 产出 Mapper output；声明 `USER_FREE_TEXT` |
| `MappingPolicy` | 单一 threshold owner：`min_confidence=0.80`（Demo baseline，非生产校准） |
| `validate_slot_mapping` / `ValidatedSlot` | membership **先于** confidence；仅 ACCEPTED 产生 ValidatedSlot |
| Local Explanation Detector | 本地、确定性、先于 Mapper；产生受控 topic |
| `InteractionFailureKind` | 已知失败语义（不等于伪装成“用户不清楚”） |
| Local response composition | 固定前缀 + **exact original** `question_text`；问题不由 LLM 改写 |

#### `UtteranceKind`（exact 4）

- `SLOT_ANSWER`：本轮是在回答当前槽位
- `EXPLANATION_REQUEST`：本轮是在问概念解释
- `UNCERTAIN`：无法可靠理解
- `OTHER`：与当前槽位无关（F09 不尝试回答大厅时间等百科问题）

#### `MapperUtteranceKind` 为何没有 `EXPLANATION_REQUEST`

解释路由权必须留在 **Local Detector**。若 Remote Mapper 能决定是否走 Explanation，就会把“是否解释”与 raw user text 绑到一起，并削弱本地优先的隐私边界。Mapper 只负责 SLOT/UNCERTAIN/OTHER。

#### Membership first / Confidence

- invented value + confidence `1.0` → `INVALID_VALUE`（membership 先挡）
- 合法 value + confidence `0.79` → `LOW_CONFIDENCE`；**F04 = 0 calls**
- 合法 value + confidence `>= 0.80` → `ACCEPTED` → 才可能调 F04

`0.80` 是 **Demo baseline**，不是标注集校准后的生产阈值；未来需 calibration 后再调。

#### 实现了 Mapper ≠ 真实 Runtime 已打通

`LlmAnswerMapper` **已实现**。在 **DEFAULT** Profile 下，注入 Company Remote Provider 时真实用户回答仍 **DENY before network**。F07 Policy Reopen 后，显式 **DEMO_APPROVED** 可使 Policy **允许** `USER_FREE_TEXT` Remote Dispatch，但 **真实 Company LLM Runtime 尚未验证**（RG-F12-004 PENDING）。因此 `OI-F09-DP-001` 仍 **OPEN / RUNTIME VALIDATION PENDING**（非 CLOSED）。

### 5. `explanation.py`

职责：Explanation Side Route 的 **request/result contract、Protocol、Demo LLM backend、strict schema、local safety guard**。

| 组件 | 作用 |
|------|------|
| `ExplanationRequest` | **机械隐私边界**：仅 `topic` + `public_context`；类型层没有 user_text / input_text / question_text / history |
| `ExplanationResult` | ANSWERED / UNSUPPORTED / UNAVAILABLE 矩阵 |
| `ExplanationService` Protocol | 未来 `GovernmentEncyclopediaExplanationService` 可替换；workflow 不硬绑 LLM |
| `LlmExplanationService` | 只消费 `ExplanationRequest`；Remote 仅 ALLOW 分类 |
| strict JSON | 仅 `{"explanation":"..."}`；extra forbid，防止 materials/location/business_id 被接受 |
| `is_safe_explanation_text` | Demo 高风险子串 guard；whole-response fail-closed |

**为什么 Demo Explanation 可用 Company LLM：**
原始「什么是社保转移？」**不直接 Remote**。本地 detector 先抽出受控 topic=`社保转移`。Remote 只收到 `SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA`。这不是“脱敏后随便发”，而是：**原始 USER_FREE_TEXT 根本没有进入 Remote Request**；发送的是本地确定性提取的受控业务概念。

**Company LLM 不是事实源：** 输出只是 Conversational Explanation，不是 Authoritative Evidence，不写入 Business Data / Graph / Rule，不生成材料/地点/资格/费用/法律依据等正式事实。

### 6. `nodes.py`

7 个 execution nodes：

| Node | 职责 |
|------|------|
| `prepare` | F08 生命周期：RECEIVED → ORCHESTRATING |
| `interpret_slot_input` | Detector FIRST；miss 才 AnswerMapper；已知 Provider/Parse 错误写 distinct failure |
| `explain_current_topic` | 仅 EXPLANATION_REQUEST；0 F04；0 slot merge；node 级 safety guard |
| `validate_slot_answer` | 纯 deterministic membership+confidence；无 LLM |
| `advance_business_graph` | **唯一 F04 调用点**；仅 ACCEPTED；调用 `advance_until_blocked`；不复制 Graph edge 逻辑 |
| `resume_current_slot` | local composition：解释/不确定/其它/拒绝 → 固定文案 + **原 question_text** |
| `complete` | F08 生命周期：本次 Agent invocation 完成 ≠ Business 已确认 |

`interpret_slot_input` 真实顺序：

1. 读 `state["input_text"]`
2. 读 controlled `slot_context`
3. Local Explanation Detector
4. 命中 → 写 `EXPLANATION_REQUEST`，**不调用 Mapper**
5. miss → `AnswerMapper`

### 7. `workflow.py`

- **F08 默认图完全保留：** `START → prepare → complete → END`（`build_agent_workflow` / `run_agent_workflow`）
- **F09 专用图：** `build_slot_interaction_workflow` / `run_slot_interaction_workflow`
- 依赖注入：`SlotInteractionDependencies`（mapper / explanation_service / decision_graph / mapping_policy）；**不进 AgentState**
- Runner：deepcopy 调用方状态；清掉 stale `artifacts["f09"]` 并重新初始化；保留其它 feature namespaces

**为何不改 F08 默认图：** F08 是 foundation；F09 只是 missing-slot interaction capability；完整总编排留给 F12。避免 Feature ownership 混乱。

#### 7 Nodes / 2 Routers

- interpretation router / validation router：**pure**；0 LLM；0 F04；只读 controlled status
- Conditional routing = Agent capability orchestration，**不是** Business routing

### 8. `artifacts["f09"]`

结构（JSON-safe）：

- `slot_context`
- `interpretation`
- `mapping_validation`
- `validated_slot`
- `explanation`
- `business_transition`
- `failure`
- `response_text`

**为何不新增 State field：** F08 `AgentState` 仍 7 个 top-level fields；F09 结果是 Feature-local intermediate artifacts。
**为何不重复存 user text：** `AgentState.input_text` 已有原始输入；artifacts 只存受控解析结果。
**`failure`：** 属于 F09 Known Failure Metadata（D13），不是改 `WorkflowErrorCode` / `state.py`。

### 9. Slot Answer 路径

1. Detector miss
2. `AnswerMapper` → `SLOT_ANSWER`（candidate mapped_value + confidence）
3. `validate_slot_mapping`：membership → confidence
4. ACCEPTED → copy slots + `advance_until_blocked`
5. 序列化 F04 `TransitionResult` 到 `business_transition`（含可能的 `candidate_business_id`）
6. non-ACCEPTED → resume 原问题；**不写 ValidatedSlot；不调 F04**

测试中 Fake/Safe mapper 可返回例如 `other_flexible_employment` + `confidence >= 0.80`，以验证 orchestration / validation / 真实 F04 集成。Fake **不复制** Production NLU 算法。

**真实 F04 Evidence：** Accepted path 使用真实 demo graph + `advance_until_blocked`，可到 `TERMINAL_CANDIDATE` 且 `candidate_business_id=DEMO_SS_001`，但 **`confirmed_business_id` 不存在**。

**Candidate ≠ Confirmed：** F04 只产出候选事项；F09 不自动确认；用户最终确认与 confirmed `business_id` 属 **F10**。

### 10. Explanation Side Route

- Detector 命中 → `EXPLANATION_REQUEST`
- Mapper **不调用**
- F04 **不调用**
- `ExplanationService.explain(ExplanationRequest(topic=..., public_context={}))`
- node 级 safety guard；失败则 UNSUPPORTED + `EXPLANATION_UNSAFE_OUTPUT`
- resume：safe explanation（或 fallback）+ **exact original question_text**
- `current_node` / `current_slots` / `required_slot` 不变；`business_transition=None`

### 11. Golden Scenario：「什么是社保转移？」

**System（来自 F04 question_text）：**
「您主要想办理社保缴费、社保转移，还是查询或其他业务？」

**User：**「什么是社保转移？」

运行过程：

1. F04 已处于 `NEED_SLOT`
2. F09 取得 `required_slot` / `allowed_values` / `question_text`
3. Local detector 识别解释句式
4. `topic = 社保转移`
5. topic 在 `question_text` 中 containment → 可信
6. Interpretation = `EXPLANATION_REQUEST`
7. AnswerMapper = **NOT CALLED**
8. F04 = **NOT CALLED**
9. ExplanationService = **CALLED**
10. 若用 Company LLM：Remote 只有 normalized topic（无 raw user / 无完整 question_text）
11. safe explanation 通过 guard
12. response = explanation + original question_text
13. current node 保持
14. current slot 仍未填
15. 等待用户真正回答

**Golden Test Evidence：** Mapper=0；Explanation=1；F04=0；`validated_slot=None`；`business_transition=None`；current node preserved；original question resume = PASS。

Detector 是通用机制（解释句式 + topic + containment），不是 `if "社保转移"`；「什么是事项A？」同样可工作。未知 topic（如 question 中不存在的「养老金计算」）不进 ExplanationService。比较问句「社保缴费和社保转移有什么区别？」当前 **DEFERRED**：安全 miss，留给未来 Government Encyclopedia。

### 12. Confidence / Membership

见 §4：membership first；threshold `0.80`（`>=`）；owner=`MappingPolicy`；Prompt/Mapper/Graph 无第二套 threshold；NaN/±Inf 拒绝。

### 13. Error Handling

五类 known failure（artifact `failure.kind` 区分；用户侧可同类 safe fallback）：

- `MAPPER_PROVIDER_ERROR`
- `MAPPER_PARSE_ERROR`
- `EXPLANATION_PROVIDER_ERROR`
- `EXPLANATION_PARSE_ERROR`
- `EXPLANATION_UNSAFE_OUTPUT`

只 catch `LlmProviderError` / `StructuredParseError`。**禁止 broad `except Exception`。** Unexpected programming error 必须自然 propagate，不能伪装成“用户不确定”或“provider unavailable”。artifacts / response_text **不存** `str(exc)` / traceback / raw provider body / reasoning。

### 14. Data Policy

**A. Answer Mapping**

- request 含真实 `user_text` → 必须声明 `USER_FREE_TEXT`
- 当前 Company Remote = **DENY before network**
- F09 **不修改** F07 Policy；不绕过 Provider abstraction

**B. Explanation**

- raw user 先本地变成 controlled topic
- `ExplanationRequest` 无 user_text 字段（机械约束，不是靠“记得别传”）
- Remote classification：`SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA`
- 因此 Demo Company LLM explanation **可以使用**

**不要说成“脱敏后可发”。** 准确说法：本地确定性提取的受控业务概念；原始 `USER_FREE_TEXT` 未进入 Remote Request。

`OI-F09-DP-001`：**OPEN / RUNTIME VALIDATION PENDING**（F07 Demo Policy 已落地；真实 USER_FREE_TEXT → Company Runtime 未验证；关闭条件 = F12 probe PASS）。

### 15. F04 / F07 / F08 / F10 / F11 / F12 Boundaries

| Feature | 边界 |
|---------|------|
| **F04** | “办哪个 / 业务图怎么走”。F09 只理解本轮话语，并仅在 ACCEPTED 后调用 `advance_until_blocked` |
| **F06** | 初始 broad direction / candidate recall。F09 **不对每次 slot answer 做 semantic retrieval** |
| **F07** | Provider / Structured Parser / Data Policy。F09 消费；不改 Policy |
| **F08** | AgentState（7 fields）/ base lifecycle / default LangGraph。F09 保留 F08 API，另加 specialized workflow |
| **F10** | terminal validation / user confirmation / confirmed business_id。F09 不做 |
| **F11** | Session / Redis / Checkpoint / Audit。F09 不做 |
| **F12** | 完整 E2E Agent。F09 只是其中一个 capability |

### 16. Test Evidence（保留）

| Suite | Result |
|-------|--------|
| Interaction Targeted | **63 / 63 PASS** |
| Workflow Targeted | **24 / 24 PASS** |
| Combined Targeted | **87 / 87 PASS** |
| Full Regression | **469 passed / 0 failed / 13 skipped / 0 warnings** |
| compileall | **PASS** |
| pip check | **PASS** |
| Public imports F08/F09 | **PASS** |
| Real LLM / Company network | **NOT RUN / 0** |

Skipped 13 = 既有 DB / Embedding / Real LLM opt-in（PRE-EXISTING）。F09 ordinary tests：**0 skip**。

### 17. Review Notes

| ID | Severity | Status / Note |
|----|----------|---------------|
| **RF-F09-001** | INFO | `OI-F09-DP-001` remains **OPEN / RUNTIME VALIDATION PENDING**（F07 Policy Reopen Review PASS；真实 Runtime 未验证） |
| **RF-F09-002** | INFO | Stage status drift → **RESOLVED IN EXPLANATION DOC UPDATE** |
| **RF-F09-003** | INFO | unused helper `interpretation_from_mapper_safe` → **DEFERRED / no functional impact**（本阶段不删；代码冻结） |
| **RF-F09-004** | INFO | Demo substring safety guard → **accepted Demo boundary**；未来 Encyclopedia 拥有正式知识权威 |

| Review Gate | Result |
|-------------|--------|
| Review | **PASS** |
| BLOCKING / MAJOR / MINOR | **0 / 0 / 0** |
| INFO | **4** |
| Review Fix | **NOT REQUIRED** |

### 18. Code-Reading Entry Points

#### Recommended Code Reading Order

1. `interaction.py` — domain / mapping / detector / validation
2. `explanation.py` — explanation privacy boundary / schema / guard
3. `nodes.py` — orchestration node behavior（含唯一 F04 调用点）
4. `workflow.py` — topology / dependency injection / F08 保留
5. `__init__.py` — public API surface
6. `tests/test_agent_interaction.py` — domain / security contracts
7. `tests/test_agent_workflow.py` — 真实 LangGraph + F04 integration

#### 三条阅读主线

1. **Answer Path：** `SlotInteractionContext` → `AnswerMapper` → `UtteranceInterpretation` → `validate_slot_mapping` → `ValidatedSlot` → `advance_business_graph` → F04
2. **Explanation Path：** raw input → local detector → normalized topic → `ExplanationRequest` → `ExplanationService` → safety guard → resume question
3. **Security Path：** `USER_FREE_TEXT` → Mapper → F07 DENY **vs** normalized topic → `ExplanationRequest` → ALLOW classes → Company LLM

### 27.1 Explanation Stage Status

| 项 | 结论 |
|----|------|
| Explanation | **COMPLETE** |
| Code-Reading | **COMPLETE**（见第 9 path） |
| Commit | **COMPLETE** |
| Push | **NOT STARTED** |
| Changed paths | **9**（Commit Stage 结束后应 clean） |
| 第 9 path | **CREATED** |
| Production / Tests modified in Explanation / Code-Reading | **0 / 0** |
| 建议下一步 | Owner 授权后进入 **F09 Push** |

---

**END OF F09 EXPLANATION**

---

## 28. Code-Reading

| 字段 | 内容 |
|------|------|
| Code-Reading | **COMPLETE** |
| Doc | `docs/code-reading/F09-missing-slot-question-answer-mapping-code-reading.md` |
| Final changed paths | **9** |
| Production / Tests modified | **0 / 0** |
| Commit | **COMPLETE** |
| Push | **NOT STARTED** |
| 建议下一步 | Owner 授权后进入 **F09 Push** |

**END OF F09 CODE-READING**

**STOP — Do not enter Push without Owner authorization.**

---

## 29. F09 Requirement Reopen — Controlled Allowed-Value Semantics

| 字段 | 内容 |
|------|------|
| Reopen 主题 | Controlled Allowed-Value Semantics for LLM Slot Mapping |
| 本阶段 | **Requirement Finalization** |
| 文档状态 | **READY FOR OWNER APPROVAL** |
| 不是 | Technical Design、Code、Test、Review、Explanation、Code-Reading 更新、Commit、Push、F12 |
| Resource Gate | **REQUIREMENT_RESOURCE_READY**（本阶段不使用 Redis、PostgreSQL、pgvector、Embedding、Docker、Company LLM） |
| Git baseline | `develop` @ `de03ea0b83392881f2e650c0ee2b408b53fff29c` |
| 允许修改 | 仅本文件 |
| RG-F12-006 | **仍为 FAILED / LOW_CONFIDENCE**。实验 B 组通过 **不得** 改写该状态 |

本节是新增需求。第 1–28 节保持为原始 F09 的历史记录。当时的 Production Mapper **没有**受控语义上下文。

### 29.1 Reopen 原因

**FACT。** 这不是「F09 把 Golden 映射到了错误枚举」。

1. Production F09 对「平时接零活，没有固定单位」已映射为 `other_flexible_employment`。
2. membership = **PASS**。
3. 真实 Company LLM 自报 confidence = **0.72**。该数值是 **MODEL_SELF_REPORTED**。本地没有 confidence calibration。
4. 当前 Demo baseline 为 `MappingPolicy.min_confidence = 0.80`。因此结果是 **LOW_CONFIDENCE**。
5. 只读 Diagnosis 证明：当前 `LlmAnswerMapper.map_answer` 只向 LLM 提供 `required_slot`、原始 `allowed_values`、`user_text`。
6. 当前 Mapper **没有**提供中文 label、description、`source_text`、`question_text`、examples 或 business context。
7. 仓库里已经存在受控中文业务语义（见 29.11）。
8. 小规模 A/B 实验（4 条样本，每格 1 次）在其它条件尽量保持不变、只增加受控 option semantics 时：mapping correctness **4/4 → 4/4**（未下降）；confidence pass **3/4 → 4/4**；ACCEPTED **3/4 → 4/4**。Golden S1 从 `0.72` / `LOW_CONFIDENCE` 变为 `0.80` / `ACCEPTED`，映射值仍是 `other_flexible_employment`。实验信号为 `SEMANTIC_CONTEXT_SIGNAL_POSITIVE`。
9. 该实验标记为 **SMALL_SCALE_EVIDENCE_ONLY**。它 **不是** 统计校准完成，**不是** 生产阈值验证完成，**不是** 模型能力的充分证明。

### 29.2 本 Reopen 不改变的架构

以下原则继续冻结。本次只增加描述性语义上下文，不扩大 LLM 的业务权威。

1. LLM 只负责自然语言理解、slot value mapping、confidence。
2. LLM 不得决定 `next_node`、`business_id`、`candidate_business_id`、`confirmed_business_id`、`rule_result`、materials、locations、channels、`legal_basis`。
3. membership 仍由本地 Controller 完成。成员资格的权威仍是 Decision Graph 的 `allowed_values`。
4. confidence threshold 仍由本地 `MappingPolicy` 完成。`min_confidence` **保持 0.80**。本 Reopen **不修改** threshold。
5. 只有 membership PASS **且** confidence `>=` threshold，才允许 `ACCEPTED`。
6. F04 仍确定性推进 Business Decision Graph。
7. F10 仍负责最终事项确认。
8. Explanation side route 不改变 current node，不写 slot，不推进 F04。
9. F07 仍负责 Remote Data Policy。`USER_FREE_TEXT` 分类不得为了通过 Policy 被改成其它类别。

### 29.3 问题陈述

**FACT。** 模型在只有英文 machine value 的上下文里，可以选对 `other_flexible_employment`，同时给出低于 0.80 的自报 confidence。

**本 Reopen 要冻结的问题只有一个：** 送给 LLM 做槽位映射的每个 allowed value，除 machine value 外，还可以携带一条来自受控业务数据的 semantic meaning。

示例（来自当前 Demo 数据，不是 Mapper 硬编码）：

| machine value | controlled meaning |
|---------------|--------------------|
| `other_flexible_employment` | 其他灵活就业人员 |

semantic meaning **不得**由 LLM 临时生成，**不得**由 Prompt 猜测，**不得**在 `interaction.py` 里按 value 写死中文，**不得**由开发者在没有数据来源时自由补充。

### 29.4 概念模型

Requirement 层的逻辑概念名为 **ControlledAllowedValueSemantic**。本阶段不决定 Python class、Pydantic 或 dataclass。

| 逻辑字段 | 必须 | 含义 |
|----------|------|------|
| `value` | 是 | Decision Graph `allowed_values` 中的 machine value |
| `meaning` | 是 | 该 machine value 对应的受控业务语义文本。必须非空白 |

**Owner Decision Q4。** `source_ref`、`verification_status`、`provenance` **不是** F09 Minimal Mapping Input Contract 的必填字段。最小逻辑元素只有 `value` 与 `meaning`。上游在把 semantics 交给 F09 之前，必须已经按 29.8 完成来源、状态和绑定校验。F09 不重新判断业务事实真伪，也不读取 `VerificationStatus` 来做业务决策。溯源可以留在上游结构里供 audit、traceability、diagnostics。Technical Design 可以让内部 transport 携带可选溯源，但 Prompt 可见的最小内容仍然只是 machine value 与 controlled meaning。不得为了本次最小实现把溯源字段强制送进 LLM Prompt。

### 29.5 职责边界与 Source of Truth

| 层 | 职责 |
|----|------|
| **Business Data** | 业务事实的 Source of Truth。allowed value 的权威措辞放在这里 |
| **Decision Graph** | `slot_name`、`allowed_values`、edges、确定性转移。machine value 的成员资格权威 |
| **上游投影** | 从已通过数据合同的 Business Data 准备 `ControlledAllowedValueSemantic`。F09 不自行推导业务事实 |
| **F09** | 消费已经准备好的 controlled semantics，把它作为描述性上下文交给 Mapper。F09 不拥有业务定义，不把 semantics 当成转移或事项决策 |

**FACT。** 当前 Demo 的中文语义写在 `data/demo/demo_ss_001.json` 的 `conditions[].source_text`。这是 **当前 Demo Business Data snapshot**。

**Owner Decision Q2（CLOSED）。** 逻辑链是：Business Data → controlled/runtime projection → F09 mapping input。F09 **不**直接读取 `data/demo/demo_ss_001.json`，也 **不**依赖该 snapshot 的文件路径。投影、adapter 或 builder 的具体实现留给以后的 Technical Design。本 Requirement **不**把 `source_text` 搬进 Decision Graph，也 **不**在此决定是否扩展 Graph schema。

F09 **禁止：**

- 在 `interaction.py` 中写 `if value == "...": meaning = "..."`
- 在 Mapper 内维护业务专用中文字典
- 在运行时让 LLM 编造 meaning

### 29.6 逻辑输入契约

新的 F09 logical mapping input 至少能够表达：

- `required_slot`
- `allowed_values`
- `allowed_value_semantics`
- `user_text`

`allowed_value_semantics` 是 `ControlledAllowedValueSemantic` 的集合。本阶段不绑定 dict、list、JSON 或具体字段名字符串。

**顺序冻结。** semantics 不得改变 `allowed_values` 的顺序。模型看到的 machine value 顺序必须与 Decision Graph `allowed_values` 一致。meaning 只是附加说明。

### 29.7 对齐、覆盖与缺失语义

**冻结的对齐规则：**

- 每条 semantic 的 `value` 必须属于当前 `allowed_values`。
- semantic 集合中出现 Graph 不允许的 value，是对齐失败。
- 空白 `meaning` 不是合法语义。
- 运行时不得悄悄编造 meaning。这一条称为 **FAIL-CLOSED FOR SEMANTIC ENRICHMENT**。

**覆盖判定（逻辑，不是实现）：**

| 分类 | 含义 |
|------|------|
| `FULL` | 每个 `allowed_values` 都有且仅有一条合法、非空白、受控、对齐的 meaning |
| `NONE` | 该 pending slot 没有任何 semantic entry。表示尚未接入 semantic enrichment |
| `PARTIAL` | 只有一部分 `allowed_values` 拥有 semantic entry。表示已经接入，但数据契约不完整 |
| `INVALID` | 契约已损坏。包括但不限于：extra value、duplicate value、空或纯空白 meaning、value alignment mismatch、semantic source 不满足既有受控数据要求 |

**Owner Decision Q1。** 全局选择 **OPTIONAL WITH LEGACY FALLBACK**。不是每个旧 slot 都必须立刻具备 controlled semantics。

**Owner Decision Q3。** 行为如下。Requirement 只冻结原则。异常类型、返回类型、error enum，以及调用层如何表达失败，留给以后的 Technical Design。

| 分类 | 冻结行为 |
|------|----------|
| `FULL` | 使用 semantic-enriched mapping。模型同时看到 machine value 与 meaning |
| `NONE` | legacy raw-enum mapping。这是尚未接入 enrichment 的槽位 |
| `PARTIAL` | **FAIL CLOSED**。不得静默退回 raw-enum |
| `INVALID` | **FAIL CLOSED**。不得静默退回 raw-enum |

`NONE` 与 `PARTIAL` 语义不同。`NONE` 是还没接入。`PARTIAL` 是已经接入但契约损坏。extra value、部分 value 缺少 meaning、空或空白 meaning、对齐失败、重复 value、来源不满足受控数据要求，都按上表失败，不得由 LLM 生成缺失 meaning，不得由 Mapper 猜测，不得在 `interaction.py` 硬编码。

### 29.8 VerificationStatus

沿用 F02，不新建状态。`VerificationStatus` 现有四值：`SOURCE_EXPLICIT`、`SYSTEM_DERIVED`、`TO_CONFIRM`、`VERIFIED`。

F02 已确认：`TO_CONFIRM` 不得作为面向群众的确定性办理事实。群众默认可消费的是 `SOURCE_EXPLICIT`、可追溯的 `SYSTEM_DERIVED`、`VERIFIED`。代码侧公开主事实 allowlist 是 `SOURCE_EXPLICIT` 与 `VERIFIED`；`SYSTEM_DERIVED` 只有在来源为 `SOURCE_EXPLICIT`、具备 Evidence，且有 `normalization_rule` 或 `derivation_note` 时，才随 Condition 一起公开（`is_public_condition`）。

**冻结。** 能进入 `allowed_value_semantics` 的 meaning 必须同时满足：

1. 措辞来自受控业务事实，其状态是 `SOURCE_EXPLICIT` 或 `VERIFIED`。
2. machine value 与该措辞的绑定可追溯。当前 Condition 形态下，绑定是 `normalized_values` + `SYSTEM_DERIVED`，并且整条 Condition 通过现有 public condition 规则。
3. `TO_CONFIRM`、缺失溯源、用户自由文本、未知来源，都不得进入。
4. meaning 最终会进入 LLM Prompt，因此不得携带未经验证的自由文本。这是 Prompt-injection-via-business-data 的需求约束，不是新的校验状态。

### 29.9 meaning 允许包含什么

`meaning` 应是简短、稳定、受控、面向业务类别的描述。

**允许：** 授权业务数据中的标准类别名称或标准语义文本。当前 Demo 使用 Condition 的 `source_text`。

**不允许进入 meaning：** `next_node`、`business_id` 决策、规则结果、材料清单、办理地点、办理渠道、法律结论、模型指令、confidence threshold、expected answer、few-shot answer。

### 29.10 Prompt 与 confidence

**Prompt 需求只冻结信息，不冻结模板。** 模型必须能同时看到 machine value 和对应的 controlled meaning。JSON、XML、换行和最终字段名字符串属于以后的 Technical Design。

**明确不加：** confidence calibration rubric、few-shot、confidence 示例、自动加分、semantic bonus、confidence floor、expected answer、threshold 提示。

**Confidence 需求：**

- `MappingPolicy.min_confidence` 保持 **0.80**。
- 比较符保持 `>=`。
- 0.80 是否以后要按标注数据重新校准，是 **独立的未来事项**，不属于本 Reopen。
- Code 完成后的正式复验必须走 **真实 Production F09**，不得用实验 B Prompt 代替。
- Golden「平时接零活，没有固定单位」的期望映射值是 `other_flexible_employment`。
- confidence 要求是 `>= MappingPolicy.min_confidence`。**不得**写成必须恰好 0.80。
- RG-F12-006 在本 Requirement 阶段仍是 **FAILED / LOW_CONFIDENCE**。

### 29.11 当前 Demo acceptance slice

只覆盖通用契约，加上当前 Demo 的 `employment_type`。不补全所有 Graph 槽位，不建 ontology，不建新的 Knowledge Graph。

**FACT。** `data/graphs/demo/social_security.json` 中 `employment_type` 的 `allowed_values` 顺序为：

1. `self_employed_without_employees`
2. `part_time_without_employer_insurance`
3. `other_flexible_employment`

**FACT。** 对应受控措辞来自 `data/demo/demo_ss_001.json` 的 `conditions`（`field = employment_type`）。`source_status = SOURCE_EXPLICIT`，`normalized_status = SYSTEM_DERIVED`，`normalization_rule = applicant_scope_v1`：

| condition_id | machine value | source_text |
|--------------|---------------|-------------|
| `cond-applicant-01` | `self_employed_without_employees` | 无雇工的个体工商户 |
| `cond-applicant-02` | `part_time_without_employer_insurance` | 未在用人单位参加社会保险的非全日制从业人员 |
| `cond-applicant-03` | `other_flexible_employment` | 其他灵活就业人员 |

**Owner Decision Q5（CLOSED）。** 本次最小验收槽位就是 `employment_type`。它的 coverage 必须是 `FULL`。三个 value 都必须有来自当前仓库受控 Business Data 的 meaning。`employment_type` 若不是 `FULL`，不得通过本次 Feature acceptance，也 **不能** 靠 `NONE` legacy fallback 通过。Legacy fallback 只用于尚未纳入本次 semantic-enrichment acceptance slice 的旧 slot。Graph 上的 `question_text` 是提问文本，**不是** meaning 来源。

### 29.12 回归要求

原 F09 行为不得退化：

1. Explanation request 仍然不进入 slot selection。
2. 非法 mapped value 仍然是 `INVALID_VALUE`。
3. low confidence 仍然是 `LOW_CONFIDENCE`。
4. uncertain 仍然不推进。
5. other 仍然不推进。
6. membership 仍然先于 confidence。
7. LLM 仍然不输出、不控制 `next_node`。
8. F04 不被本次修改。
9. F10 不被本次修改。
10. F07 Policy 分类不被弱化。

### 29.13 后续测试要求

后续测试至少覆盖：

| ID | 冻结期望 |
|----|----------|
| A | `FULL` → semantic-enriched mapping path |
| B | `NONE` → legacy raw-enum path |
| C | `PARTIAL` → fail closed，不退回 raw-enum |
| D | extra semantic value → fail closed |
| E | duplicate semantic value → fail closed |
| F | empty 或 whitespace meaning → fail closed |
| G | alignment mismatch → fail closed |
| H | unapproved semantic source → fail closed |
| I | `employment_type` 必须 `FULL`，不能靠 `NONE` fallback 通过验收 |
| J | `allowed_values` 顺序保持；raw allowed values 仍然出现 |
| K | meaning 对 Mapper 可见；Prompt 可见最小内容是 machine value + controlled meaning |
| L | `USER_FREE_TEXT` 分类保持；system classification 保持 |
| M | membership 先于 confidence |
| N | 正确 value 且 confidence 等于 0.80 → `ACCEPTED` |
| O | 正确 value 且 confidence 低于 0.80 → `LOW_CONFIDENCE` |
| P | 非法 mapped value → `INVALID_VALUE` |
| Q | Explanation side route 回归 |
| R | LLM 不获得 `next_node` / `business_id` 权威 |

任何失败路径都不得编造 meaning。具体异常类型留给 Technical Design。

### 29.14 Runtime 复验要求

正式 Code 完成后，必须重新执行 RG-F12-006 Production Probe。路径是：

真实 Production F09 → controlled semantics → `USER_FREE_TEXT` → `DEMO_APPROVED` → Company LLM → mapped value → membership → confidence → `ACCEPTED` 或拒绝。

这不是继续调用实验 B Prompt。

### 29.15 Architecture Invariants

| ID | 不变式 |
|----|--------|
| INVARIANT-F09R-01 | Semantic context is descriptive, not decision authority. |
| INVARIANT-F09R-02 | Machine `allowed_values` remain the membership authority. |
| INVARIANT-F09R-03 | LLM output must still pass local membership validation. |
| INVARIANT-F09R-04 | Confidence policy remains local. |
| INVARIANT-F09R-05 | F04 owns deterministic transition. |
| INVARIANT-F09R-06 | F10 owns final business confirmation. |
| INVARIANT-F09R-07 | Semantic meaning must come from controlled business data. |
| INVARIANT-F09R-08 | No semantic meaning may be invented at runtime by the LLM. |
| INVARIANT-F09R-09 | F07 remote data policy remains mandatory. |
| INVARIANT-F09R-10 | Explanation request never counts as selection. |

### 29.16 Owner Decisions

Reopen 阶段的 Open Questions 已由 Owner 关闭。下表是 Requirement Finalization 的冻结记录，不是新的待决问题。

| ID | 状态 | 冻结内容 |
|----|------|----------|
| Q1 | **Owner Decision** | **OPTIONAL WITH LEGACY FALLBACK**。旧 slot 不必立刻具备 semantics。`NONE` 才允许 legacy raw-enum。`employment_type` 验收必须 `FULL` |
| Q2 | **CLOSED** | F09 不直接读取 `demo_ss_001.json`，不依赖 snapshot 路径。链路是 Business Data → projection → F09 input。投影实现留给 Technical Design |
| Q3 | **Owner Decision** | `FULL` 走 enriched mapping。`NONE` 走 legacy。`PARTIAL` 与 `INVALID` **FAIL CLOSED**，不得退回 raw-enum。禁止运行时编造 meaning |
| Q4 | **Owner Decision** | 最小输入不含 `source_ref`、`verification_status`、`provenance`。校验在上游。Prompt 可见最小内容是 machine value + controlled meaning |
| Q5 | **CLOSED** | 本次最小验收切片是 `employment_type` 的三个 allowed values，coverage 必须 `FULL` |

本阶段没有剩余 Open Question。

### 29.17 FACT 与已冻结决定

| 类型 | 内容 |
|------|------|
| **FACT** | Golden 映射值正确；membership PASS；自报 confidence 0.72；threshold 0.80；当前 Mapper 只有三字段；仓库已有三条 `SOURCE_EXPLICIT` 措辞；A/B 是 small-scale positive signal；RG-F12-006 仍是 LOW_CONFIDENCE |
| **已冻结需求** | Q1–Q5、覆盖与失败行为、legacy 只适用于 `NONE`、最小输入四元组、上游校验、描述性语义、成员资格权威、本地 confidence、禁止编造 meaning、Demo slice、回归、测试清单、正式复验、INVARIANT-F09R-01 至 INVARIANT-F09R-10 |
| **不再是建议** | 原 Reopen 中的 Q1/Q3 RECOMMENDATION 已被本节 Owner Decision 取代 |

### 29.18 本阶段停止点

Requirement Finalization 文档状态：**READY FOR OWNER APPROVAL**。

下一步只能是 **OWNER APPROVAL**。不得把本节写成 Technical Design 已经就绪。具体类型、模块路径、异常枚举和 Prompt 字符串都不在本阶段决定。

**STOP — Do not enter Technical Design, Code, Test, Review, Explanation, Code-Reading update, Commit, Push, or F12.**

---

## 30. F09 Technical Design Reopen — Controlled Allowed-Value Semantics

| 字段 | 内容 |
|------|------|
| 本阶段 | **Technical Design only** |
| 文档状态 | **READY FOR OWNER REVIEW** |
| 前置 | 第 29 节 Requirement Finalization 已由 Owner 批准，本节约不得改写 |
| Resource Gate | **READY**（只用仓库内契约与实现；不使用 Redis、PostgreSQL、pgvector、Embedding、Docker、Company LLM） |
| RG-F12-006 | **仍为 FAILED / LOW_CONFIDENCE** |
| 实验证据 | **SMALL_SCALE_EVIDENCE_ONLY** |

### 30.1 FACT：当前运行路径

当前 Production 还没有 semantic projection。`_interpret_slot_input`（`agent/nodes.py`）的顺序是：

| 步骤 | 模块 / 函数 | 输入 | 输出 | 语义是否影响 |
|------|-------------|------|------|----------------|
| 1 | `read_f09` + `deserialize_slot_context` | `artifacts["f09"].slot_context` | `SlotInteractionContext` | 否。上下文已有 `current_node_id`、`required_slot`、`allowed_values`、`question_text` |
| 2 | `detect_explanation_request` | `input_text`、`question_text` | `EXPLANATION_REQUEST` 或 `None` | 否。命中后直接旁路，不调用 Mapper |
| 3 | `AnswerMappingRequest` | `required_slot`、`allowed_values`、`user_text` | 三字段请求 | 今天没有 semantics 字段 |
| 4 | `LlmAnswerMapper.map_answer` | 上述请求 | system + user 文本，再包成 `LlmRequest` | 今天 user 消息只有 raw enums |
| 5 | `provider.complete` | `LlmRequest` | `LlmResponse.content` | 否，Provider 不解释业务语义 |
| 6 | `parse_structured_output(..., AnswerMapperOutput)` | content | `kind`、`mapped_value`、`confidence` | 否 |
| 7 | `mapper_output_to_interpretation` | `AnswerMapperOutput` | `UtteranceInterpretation` | 否 |
| 8 | `validate_slot_answer` → `validate_slot_mapping` | interpretation、`allowed_values`、`MappingPolicy` | `ACCEPTED` / `LOW_CONFIDENCE` / `INVALID_VALUE` / `NOT_SLOT_ANSWER` | 否。成员资格只看 machine value |
| 9 | `_route_by_validation` → `advance_business_graph` | 仅 `ACCEPTED` | 调用 `advance_until_blocked` | 否 |

`SlotInteractionDependencies` 今天只有 `answer_mapper`、`explanation_service`、`decision_graph`、`mapping_policy`。`AgentState` 没有 `business_id` 字段。

### 30.2 FACT：业务数据与提问时可见的上下文

`JsonBusinessRepository`（`business_data/repository.py`）是现有运行时抽象。`from_paths` 调用 `load_snapshot` 建索引；`get_conditions(business_id, consumption=PUBLIC)` 已经用 `is_public_condition` 过滤。F09 **不得**再写一个平行的 JSON loader，也 **不得**在 Mapper 或 node 里直接读 `data/demo/demo_ss_001.json`。

`VerificationStatus` 仍是 `SOURCE_EXPLICIT`、`SYSTEM_DERIVED`、`TO_CONFIRM`、`VERIFIED`。公开主事实 allowlist 是 `SOURCE_EXPLICIT` 与 `VERIFIED`。`SYSTEM_DERIVED` 只有在 `source_status` 为 `SOURCE_EXPLICIT`、有 Evidence、且有 `normalization_rule` 或 `derivation_note` 时，才随整条 Condition 公开。投影只调用 `get_conditions(..., PUBLIC)`，不另写一套资格算法。

`DecisionNode.source_condition_refs` 的类型是 `SourceConditionRef(business_id, condition_id)`。注释写明这是设计依据，不是 Rule，也不是 F10 的 `confirmed_business_id`。`SLOT_GATE` 禁止设置 `candidate_business_id`。

`employment_type` 节点是 `SOURCE_SUPPORTED`，三条 ref 指向 `DEMO_SS_001` 的 `cond-applicant-01/02/03`。`service_action` 与 `payment_actor` 的 `source_condition_refs` 为 null。因此在 F09 提问时，图节点已经带有确认前的条件引用。不需要、也拿不到 `confirmed_business_id`。

**循环依赖：** 不存在。映射 `employment_type` 使用的是图上已经写下的 condition ref，不是「先确认事项再读语义」。`business_id` 在 ref 上是数据定位键，不是 F10 确认结果。

### 30.3 DESIGN：投影所有者与时机

新增 `business_data/semantics.py`，函数：

`project_allowed_value_semantics(repository, *, slot_name, allowed_values, source_condition_refs) -> SemanticProjectionResult`

它是唯一的覆盖判定所有者。F09 node 只按 `coverage` 分支，不扫描 Condition，不解释 VerificationStatus。

时机选 **A：每次槽位映射请求时在内存中计算**。Repository 已经把 snapshot 放在内存索引里。不预计算进 Graph，不新增缓存，不写 PostgreSQL，不新增依赖。

`SlotInteractionDependencies` 增加 `business_repository: JsonBusinessRepository`。组合根把已经建好的 Repository 注入进来。node 不调用 `load_snapshot` 或 `from_paths`。

### 30.4 DESIGN：类型与结果

| 符号 | 形态 | 字段 |
|------|------|------|
| `ControlledAllowedValueSemantic` | frozen Pydantic，`extra="forbid"` | `value: str`，`meaning: str`。两者非空白。不含 `source_ref`、`verification_status`、`provenance` |
| `SemanticCoverage` | `StrEnum` | `FULL`、`NONE`、`PARTIAL`、`INVALID`。不用布尔值 |
| `SemanticProjectionResult` | frozen Pydantic | `coverage`；`semantics` 仅在 `FULL` 时为按 `allowed_values` 顺序排列的 tuple，其它覆盖为空 tuple；`reason_code` 为低基数诊断，不进 Prompt |

顺序只按调用方传入的 `allowed_values` 重建。Condition 在 JSON 里的顺序不影响输出。

### 30.5 DESIGN：覆盖判定

| 覆盖 | 判定 | 行为 |
|------|------|------|
| `NONE` | `source_condition_refs` 为 null 或空。表示该槽位尚未接入 enrichment | 不访问业务条件。走现有 raw-enum Mapper。不是错误 |
| 已接入 | refs 非空 | 下面各行都不再是 `NONE` |
| `FULL` | 每个 allowed value 恰好一条公开 Condition：`field` 等于 `slot_name`，`normalized_values` 恰好一个且等于该 value，`source_text` 非空白，无 extra、无 duplicate | `semantics` 按 `allowed_values` 排列。走 enriched Mapper |
| `PARTIAL` | 一部分 allowed value 有一条合法语义，其余没有，且没有 INVALID 缺陷 | FAIL CLOSED |
| `INVALID` | extra value、duplicate、空白 meaning、field 或 value 对不齐、ref 指向的 Condition 不在 PUBLIC 结果中、`normalized_values` 不是恰好一个 | FAIL CLOSED |

`employment_type` 的三条 ref 在当前 Demo 数据上应得到 `FULL`，meaning 分别是「无雇工的个体工商户」「未在用人单位参加社会保险的非全日制从业人员」「其他灵活就业人员」。这些字符串只从 Repository 的公开 Condition 读出，不写进 `interaction.py`。

### 30.6 DESIGN：失败表现

在 `InteractionFailureKind` 增加两个值，不复用 `UNCERTAIN`、`OTHER`、`LOW_CONFIDENCE`、`INVALID_VALUE`：

- `semantic_projection_partial`
- `semantic_projection_invalid`

`_interpret_slot_input` 在解释检测之后、Mapper 之前调用投影。`PARTIAL` / `INVALID` 时：

- 不调用 `map_answer`，因此 Company LLM HTTP = 0
- `interpretation` 保持 `None`
- 写入对应 `failure`
- `response_text` 使用一条新的固定安全句，不说「还不能确定您的意思」，不包含用户原文或 meaning
- `_route_by_interpretation` 先看这两种 failure，返回 `semantic_contract_failure`
- 该边直接到现有 `_complete_node`
- 不写 slot，不调用 `advance_until_blocked`，不产生 Terminal Candidate，不进入 F10

异常类、error enum 的进一步拆分不做。这两个 failure kind 就是本设计的失败机制。

### 30.7 DESIGN：`AnswerMappingRequest` 与 Prompt

`AnswerMappingRequest` 增加可选字段：

`allowed_value_semantics: tuple[ControlledAllowedValueSemantic, ...] | None = None`

`None` 表示 legacy。空 tuple 不是 `NONE`，请求校验直接拒绝，避免把残缺列表悄悄当成 legacy。

字段不为 `None` 时，请求只做薄校验：条数与 `allowed_values` 相同、value 顺序一致、meaning 非空白。资格、公开状态和 Condition 绑定仍只由投影函数负责。node 只会在 `FULL` 时传入完整 tuple。

`NONE` 的 user 消息保持现有三行：

```text
required_slot=<slot>
allowed_values=[<comma-joined raw enums>]
user_text=<user text>
```

`FULL` 在 `allowed_values` 与 `user_text` 之间增加一行。序列化使用紧凑 JSON，`ensure_ascii=False`，列表顺序与 `allowed_values` 相同：

```text
allowed_value_meanings=[{"value":"...","meaning":"..."}, ...]
```

system prompt 文本不改。不加 rubric、few-shot、expected answer、threshold 或业务决策指令。

`AnswerMapperOutput`、`mapper_output_to_interpretation`、`validate_slot_mapping`、`MappingPolicy.min_confidence = 0.80` 都不改。成员资格仍只比较 machine value。

### 30.8 DESIGN：数据分类

| 消息 | 分类 |
|------|------|
| system | 仍只有 `SYSTEM_CONTROL_DATA` |
| `NONE` user | 仍是 `USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA` |
| `FULL` user | `USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA` |

`PUBLIC_BUSINESS_METADATA` 对应已经公开的业务措辞。同一条 user 消息里还有用户原文，所以必须同时保留 `USER_FREE_TEXT`。`DEFAULT` 策略今天就会因为 `USER_FREE_TEXT` 拒绝远程调用；增加公开业务分类不会放宽 `DEFAULT`。`DEMO_APPROVED` 的 allow-set 已经包含这三类。F07 Policy 代码不改。

### 30.9 DESIGN：解释旁路与状态

解释检测仍在投影和 Mapper 之前。像「什么叫灵活就业？」这种命中 detector 的输入不构建投影、不调用 Mapper、不写 slot、不推进 F04。

`AgentState` 不增加字段。投影是当次请求的辅助数据，不写入 checkpoint。F11 契约、Redis、checkpoint 都不改。不新增审计字段；失败 kind 只留在现有 `artifacts["f09"].failure`。不记录 prompt、用户原文或 meaning 全文。

日志沿用 `logging.getLogger("gov_service_agent")`，只记：

- `semantic_coverage`
- `semantic_count`
- `mapper_mode`：`ENRICHED` 或 `LEGACY`；失败时记 `FAIL_CLOSED`
- `reason_code`（低基数）

### 30.10 计划中的文件

本阶段不修改这些文件。下表是以后 Code 阶段的计划。

| 路径 | 动作 | 原因 |
|------|------|------|
| `src/gov_service_agent/business_data/semantics.py` | ADD | 投影函数与三个类型 |
| `src/gov_service_agent/agent/interaction.py` | MODIFY | 请求字段、Prompt 一行、两个 failure kind、一条安全回复 |
| `src/gov_service_agent/agent/nodes.py` | MODIFY | 检测之后投影，再按覆盖分支 |
| `src/gov_service_agent/agent/workflow.py` | MODIFY | 依赖增加 Repository；失败边直达 `complete` |
| `tests/test_allowed_value_semantics.py` | ADD | 投影单元测试 |
| `tests/test_agent_interaction.py` | MODIFY | FULL / NONE Mapper 与分类 |
| `tests/test_agent_workflow.py` | MODIFY | 解释旁路、FULL、NONE、PARTIAL、INVALID、F04 回归 |

自写 Production Python：新增 1 个，修改 3 个。不改 F04、F10、F07、数据文件、迁移或依赖。

### 30.11 测试与正式复验设计

投影测试：三值齐全且顺序跟 Graph 而不是 JSON；零 ref 为 `NONE`；缺一两个为 `PARTIAL`；extra、duplicate、空白 meaning、错位、非公开来源为 `INVALID`。

Mapper 测试使用 Fake Provider。`FULL` 保留 raw `allowed_values` 行，并能看见 value 与 meaning，分类含 `USER_FREE_TEXT` 与 `PUBLIC_BUSINESS_METADATA`。`NONE` 的 user 消息与今天的三行一致。

节点测试：解释请求不映射；`FULL` 走 enriched；`NONE` 走 legacy；`PARTIAL` 与 `INVALID` 的 Provider 调用次数为 0，F04 调用次数为 0。合法值且 confidence 等于 0.80 仍 `ACCEPTED` 并进入现有 F04 路径。低于 0.80 仍 `LOW_CONFIDENCE` 且不推进。非法 value 即使 confidence 为 1.0 仍 `INVALID_VALUE`。结构化输出仍拒绝 `next_node`、`business_id` 等越权字段。

Code、Test、Review 之后，用真实 Production F09 重跑 RG-F12-006。Golden「平时接零活，没有固定单位」期望 `slot_answer`、`other_flexible_employment`、membership PASS、confidence `>= 0.80`、`ACCEPTED`。同时证明语义来自 Production 投影、请求含 `USER_FREE_TEXT`、`DEMO_APPROVED` 为 ALLOW、并且发生了真实 HTTP。不用实验 B 脚本作为最终验收。confidence 不必恰好等于 0.80。

### 30.12 区分

| 类型 | 内容 |
|------|------|
| **FACT** | 当前三字段 Mapper、解释检测在前、Repository 与 `is_public_condition`、图上的 `source_condition_refs`、`SLOT_GATE` 没有 `candidate_business_id`、F07 现有 allow-set |
| **FROZEN REQUIREMENT** | 第 29 节 Q1–Q5、0.80、LLM 不扩大权威、RG-F12-006 仍失败、实验只是 small-scale evidence |
| **TECHNICAL DESIGN** | 投影函数、覆盖枚举、`None` 对空 tuple、失败 kind、Prompt 增加一行、分类集合、依赖注入 Repository、失败边直达 `complete` |
| **OPEN DESIGN QUESTION** | 无。本设计没有把已冻结需求重新打开 |
| **RECOMMENDATION** | 无待确认建议 |

### 30.13 停止点

Technical Design 状态：**READY FOR OWNER REVIEW**。

下一步只能是 **OWNER REVIEW**，或在 Owner 决定后进入 **TECHNICAL DESIGN FINALIZATION**。本阶段没有进入 Code。

**STOP — Do not enter Technical Design Finalization, Code, Test, Review, Explanation, Code-Reading update, Commit, Push, or F12.**

---

## 31. F09 Review — Controlled Allowed-Value Semantics

本节只记录对第 29 节冻结需求、第 30 节已批准设计，以及当前 Production / Test diff 的只读审查。不改写第 1–30 节，不修改 Production 或测试。

Review 状态：**PASS_WITH_NOTES**。没有 BLOCKER、MAJOR 或待修项。

### 31.1 Review scope

审查对象是受控 allowed-value semantics：`FULL` 走带含义的 mapping，`NONE` 保持旧 raw-enum，`PARTIAL` 与 `INVALID` 在调用模型之前失败关闭。Demo 切片 `employment_type` 必须是 `FULL`。`MappingPolicy.min_confidence` 保持 `0.80`。LLM 仍只输出 `kind`、`mapped_value`、`confidence`。F04、F07、F10 的业务职责不因本次语义增强而改变。RG-F12-006 仍是 `FAILED / LOW_CONFIDENCE`，本阶段没有重跑真实 Golden。

### 31.2 Reviewed files

| 路径 | 审查方式 |
|------|----------|
| `src/gov_service_agent/business_data/semantics.py` | 全文 |
| `src/gov_service_agent/agent/interaction.py` | diff 与请求、Prompt、分类、校验相关实现 |
| `src/gov_service_agent/agent/nodes.py` | diff 与解释检测、投影分支、失败路由、`_complete_node` |
| `src/gov_service_agent/agent/workflow.py` | diff 与依赖注入、条件边 |
| `tests/test_allowed_value_semantics.py` | 全文 |
| `tests/test_agent_interaction.py` | diff |
| `tests/test_agent_workflow.py` | diff |
| 第 29、30 节 | 作为冻结需求与已批准设计对照 |

本轮没有重跑 pytest。测试证据采用 Test Stage 与环境恢复阶段的真实结果。

### 31.3 Requirement traceability

| 冻结需求 | 代码 | 测试 |
|----------|------|------|
| `FULL` → enriched mapping | `project_allowed_value_semantics` 在无缺陷且每个 allowed value 恰好一条语义时返回 `FULL`；node 把 `result.semantics` 传入 `AnswerMappingRequest` | `test_projection_full_employment_type_demo_slice`、`test_full_prompt_keeps_values_and_adds_meanings`、`test_full_employment_mapping_uses_injected_semantics` |
| `NONE` → legacy raw-enum | refs 为 `None` 或空时立即返回 `NONE`，不查 Repository；node 传入 `allowed_value_semantics=None` | `test_projection_none_skips_repository`、`test_legacy_none_prompt_has_no_meanings`、`test_none_refs_keep_legacy_mapper_request` |
| `PARTIAL` → fail closed | 无非法缺陷但未覆盖全部 allowed values 时返回 `PARTIAL` 且 semantics 为空；node 在 Mapper 之前返回 | `test_projection_partial_missing_value`、`test_partial_projection_fail_closed` |
| `INVALID` → fail closed | extra、duplicate、空白 meaning、字段不匹配、非法 normalized value、非公开 ref 都在覆盖判断之前返回 `INVALID` | 投影文件中的六类 INVALID 测试，以及 `test_invalid_projection_fail_closed` |
| `employment_type` 必须 `FULL` | 使用图节点 `source_condition_refs` 和已注入 Repository 的 PUBLIC conditions | Demo slice 测试断言三个 machine value 与当前受控中文 meaning |
| `0.80` 不变 | `_DEFAULT_MIN_CONFIDENCE = 0.80` 不在本次 diff 的修改范围内 | `test_validate_membership_first_and_threshold`、`test_threshold_080_accepted`、`test_hallucinated_and_low_confidence_no_f04` |
| LLM 权威不变 | `AnswerMapperOutput` 仍只有三个字段；membership 仍只看 `allowed_values` | 额外字段拒绝测试；非法 value 且 confidence `1.0` 仍是 `INVALID_VALUE` |

上述链路都能从需求落到当前符号和对应测试。没有缺链。

### 31.4 Architecture boundary

`semantics.py` 只做受控投影。它不调用 LLM，不读用户文本，不读 `AgentState`，不推进 Graph，不决定 `next_node`，也不确认事项。`SourceConditionRef.business_id` 只传给 `get_conditions` 做查找。本次 diff 没有把它写入 `confirmed_business_id` 或 `candidate_business_id`。F09 投影不读取确认结果，因此不存在“先要 F10 确认、确认又依赖 F09”的环。

资格判断复用 `JsonBusinessRepository.get_conditions(..., consumption=PUBLIC)`。该 API 内部仍使用既有 `is_public_condition`。投影代码没有复制第二份资格算法，没有读取 snapshot 路径，也没有在找不到公开条件时改查 `INTERNAL`。`BusinessNotFoundError` 与公开列表中缺失的 `condition_id` 都返回 `invalid_unapproved_ref`，不会降成 `NONE`。

`NONE` 只出现在 refs 为空时，而且发生在任何 Repository 调用之前。读取失败、非法 ref、部分覆盖和畸形条件都不会进入这条路径。`PARTIAL` 只在整段 refs 扫描没有缺陷、但合法 machine value 未覆盖全部 `allowed_values` 时出现。extra、duplicate、空白 meaning、字段不匹配、非法 normalized value 和非公开 ref 都先返回 `INVALID`。

`FULL` 按调用方传入的 `allowed_values` 重建 tuple。排序测试把 Repository 的公开顺序安排成 C、A、B，断言输出仍是 A、B、C。reason code 全部是固定常量，没有拼接用户原文、`source_text`、Prompt 或模型输出。同一批 refs 上，先出现的缺陷决定 reason，不依赖 set 的偶然顺序。

`ControlledAllowedValueSemantic` 是 frozen 且 `extra=forbid`，只有非空白 `value` 和 `meaning`。`SemanticProjectionResult` 规定只有 `FULL` 可以携带非空 semantics。`AnswerMappingRequest.allowed_value_semantics is None` 表示 legacy；空 tuple 因数量与 `allowed_values` 不一致而校验失败。请求层只核对数量和 value 顺序，不重新判断资格或 provenance。

### 31.5 Security and privacy

`NONE` 的 user message 仍是 `required_slot`、`allowed_values`、`user_text` 三行，分类恰好是 `USER_FREE_TEXT` 与 `SYSTEM_CONTROL_DATA`。`FULL` 只在这两行之间增加 `allowed_value_meanings=`，内容是 `json.dumps(..., ensure_ascii=False, separators=(",", ":"))`。meaning 是 JSON 数据字段，不进入 system prompt，也不改写模型规则。system prompt 文本与本次 Feature 之前相同，没有 threshold、confidence rubric、few-shot 或期望答案。

`FULL` user message 的分类恰好是 `USER_FREE_TEXT`、`SYSTEM_CONTROL_DATA`、`PUBLIC_BUSINESS_METADATA`。system message 仍只有 `SYSTEM_CONTROL_DATA`。F07 文件不在本次 diff 中。同一请求在 `DEMO_APPROVED` 下允许，在 `DEFAULT` 下因 `USER_FREE_TEXT` 拒绝，说明没有靠删掉用户原文分类来放行。

解释检测仍在投影和 Mapper 之前。命中后不查 Repository、不调用 Mapper、不写 slot、不调用 `advance_until_blocked`。`PARTIAL` 与 `INVALID` 在 node 内直接返回，路由 `semantic_contract_failure` 只连到现有 `_complete_node`。该节点只把本轮编排标成 `COMPLETED`，不写确认事项、terminal candidate 或已接受 slot。用户看到的是固定句子“当前办理选项的说明不完整，暂时无法继续确认这个选项。”内部 `failure` 只有 `kind` 和 `safe_message`，后者是低基数 reason code。日志只记录 coverage、count、mapper mode 和 reason code。

`SlotInteractionDependencies.business_repository` 是必填字段。node 使用传入实例，不调用 `from_paths` 或 `load_snapshot`。在 `src/` 中搜索构造调用，除类型定义外没有生产组合根自己 `new` 这个对象；测试构造已经传入同一个 Repository。因此不存在遗漏参数的生产构造点，也没有第二份 Repository。`AgentState`、Redis checkpoint、Session API 和 Audit schema 都不在本次 diff 中。语义数据只活在当次请求里。

### 31.6 Test evidence

| 集合 | 结果 |
|------|------|
| `tests/test_allowed_value_semantics.py` | 21 passed |
| `tests/test_agent_interaction.py` | 69 passed |
| `tests/test_agent_workflow.py` | 37 passed |
| Business Data、Decision Graph、F07 policy/provider 相关回归 | 178 passed |
| `test_session_store.py`、`test_session_service.py`、`test_session_api.py` | 49 passed，0 failed，0 errors |
| 全量 pytest | 653 passed，13 skipped，0 failed，0 errors |

投影测试直接调用 `project_allowed_value_semantics`。Mapper 测试用 Capturing Provider 检查真实 `LlmRequest`。workflow 测试走 `run_slot_interaction_workflow`。计数 Repository 仍调用父类 `get_conditions`，没有把公开过滤替换成假结果。旧断言没有删除：0.80 仍 `ACCEPTED`，0.79 仍 `LOW_CONFIDENCE`，非法 value 加 confidence `1.0` 仍 `INVALID_VALUE`。三份 F09 测试文件没有 `pytest.skip`。全量 13 个 skip 与历史数量一致，跳过点只在既有 integration 文件中，条件分别是 `RUN_LLM_REAL`、`TEST_DATABASE_URL` 和 `RUN_EMBEDDING_REAL`。

### 31.7 Findings

| ID | 级别 | 内容 |
|----|------|------|
| NOTE-1 | NOTE | 每条 `source_condition_ref` 都会调用一次 `get_conditions`。同一个 `business_id` 可能被重复查询。当前 Demo 只有三条 ref，查询在内存 Repository 中完成，结果确定，也不新增 cache。不构成本 Feature 的正确性缺陷。 |
| NOTE-2 | NOTE | `src/` 里没有生产代码构造 `SlotInteractionDependencies`。新增必填 `business_repository` 因此不会打断一条已经存在的生产构造路径。测试侧三处构造都已传入外部 Repository，并断言实例同一。这与第 30 节的注入设计一致。 |

BLOCKER：0。MAJOR：0。MINOR：0。NOTE：2。合计：2。NOTE 不要求在本 Feature 修复。

### 31.8 Verdict

**PASS_WITH_NOTES**。

实现与冻结需求、已批准设计一致。`FULL`、`NONE`、`PARTIAL`、`INVALID` 的职责没有重叠。失败关闭发生在模型调用之前，也不产生业务确认。没有待修项。

下一步只能是 **OWNER REVIEW**。Owner 明确批准后才能进入 Explanation。本阶段不进入 Review Fix、Explanation、Code-Reading、Commit、Push、F12，也不重跑 RG-F12-006。

**STOP — Do not enter Review Fix, Explanation, Code-Reading update, Commit, Push, or F12.**

---

## 32. F09 Explanation — Controlled Allowed-Value Semantics

本节解释这次 Reopen 最终做了什么。第 29–31 节仍然是需求、设计与审查记录。这里按办理时的真实顺序说明，方便还不熟悉本项目的开发者阅读。

### 32.1 这次 Reopen 解决什么问题

用户已经走到一个缺失槽位。系统知道现在要问什么，也知道哪些 machine value 合法，但旧 Mapper 只把这些英文枚举和用户原话交给模型。模型有时能选对枚举，却给不出足够的 confidence。

这次改造不改变“谁有权决定业务”。Decision Graph 仍然决定问什么、怎么走。Business Data 仍然提供选项的受控业务 wording。F09 只是在调用模型之前，把二者对齐成 controlled allowed-value semantics。模型仍然只回答：这句话更像哪一个已经允许的值，以及它自己有多确定。

### 32.2 改造前的真实运行方式

旧的 `AnswerMappingRequest` 只有三样东西：`required_slot`、`allowed_values`、`user_text`。

以 `employment_type` 为例，模型看到的合法值是：

```text
self_employed_without_employees
part_time_without_employer_insurance
other_flexible_employment
```

Golden 输入是“平时接零活，没有固定单位”。当时的 Production 结果是：

| 项目 | 结果 |
|------|------|
| mapped_value | `other_flexible_employment` |
| membership | PASS |
| confidence | `0.72` |
| threshold | `0.80` |
| 本地结论 | `LOW_CONFIDENCE` |

这不是选错了值。membership 已经通过，说明返回值属于 `allowed_values`。问题出在模型自报的 confidence 低于本地门槛。旧 Prompt 没有把“其他灵活就业人员”这类受控业务 wording 一起交给模型，模型是在只看见裸 machine value 的情况下给分的。

### 32.3 为什么没有降低 0.80

`0.80` 是本地控制规则，不是模型自己的通过线。一次 Golden 低于门槛，只能说明这次输入下模型不够确定，不能直接证明门槛写错了。

先看到的缺口是 Mapper 输入的业务上下文不够。小规模 A/B 比较了两种输入：只有 raw machine value，以及 raw machine value 再加上 controlled meanings。mapping 正确率两边都是 4/4。confidence 通过数从 3/4 变成 4/4，`ACCEPTED` 也从 3/4 变成 4/4。Golden 从 `0.72` 变成 `0.80`。

这只说明补充语义上下文有正向信号，而且样本很小。它不是统计校准，也不说明 `0.80` 已被证明是所有业务的最优值，更不说明以后每次都会提高 confidence。所以门槛保持 `0.80`。`SMALL_SCALE_EVIDENCE_ONLY`。

### 32.4 Controlled semantics 是什么

一条 `ControlledAllowedValueSemantic` 只有两个字段：

| 字段 | 例子 | 作用 |
|------|------|------|
| `value` | `other_flexible_employment` | 机器仍要使用的合法枚举 |
| `meaning` | 其他灵活就业人员 | 帮助模型理解这个枚举在业务上指什么 |

另外两条当前 Demo 含义是：“无雇工的个体工商户”和“未在用人单位参加社会保险的非全日制从业人员”。

`meaning` 不是新的业务规则。它不能决定 `next_node`、`business_id`、`rule_result`，也不能决定材料、地点、渠道或法律依据。真正的业务路径仍由 Decision Graph 和 F04 的确定性转移决定。

### 32.5 Runtime 业务主流程

用户回答当前缺失槽位之后，这一轮按下面的顺序处理：

```text
用户回答当前缺失槽位
        ↓
F09 接收本轮输入
        ↓
先判断是不是解释请求
        ↓
不是解释请求
        ↓
读取当前 Decision Graph node
        ↓
取出 required_slot、allowed_values、source_condition_refs
        ↓
用已注入的 Business Repository 做 semantic projection
        ↓
得到 FULL / NONE / PARTIAL / INVALID
        ↓
FULL  → semantic-enriched mapping
NONE  → legacy raw-enum mapping
PARTIAL / INVALID → fail closed，不调用模型
        ↓
模型如果被调用，只返回 kind、mapped_value、confidence
        ↓
本地先做 membership
        ↓
再看 confidence 是否 >= 0.80
        ↓
只有 ACCEPTED 才进入 F04
        ↓
Decision Graph 继续确定性前行
        ↓
将来到达 Terminal Candidate
        ↓
F10 仍要用户明确确认
        ↓
之后才会出现 confirmed_business_id
```

解释请求会在投影之前离开这条主线，见 32.10。`PARTIAL` 和 `INVALID` 也会在模型之前结束本轮，见 32.7 和 32.12。

### 32.6 Business Data 如何进入 F09

业务 wording 的 Source of Truth 是 Business Data。当前 Demo 文件 `data/demo/demo_ss_001.json` 只是这份数据的 snapshot。F09 不会打开这个文件，也不会按路径自己解析 JSON。

运行时的链路是：

```text
Business Data snapshot
        ↓
上层已经完成的 Repository 装载
        ↓
内存中的 JsonBusinessRepository
        ↓
get_conditions(business_id, consumption=PUBLIC)
        ↓
project_allowed_value_semantics
        ↓
F09 的当次 mapping request
```

三方分工是：

| 角色 | 负责什么 |
|------|----------|
| Decision Graph | 当前 `required_slot`、`allowed_values`、`source_condition_refs`、边，以及确定性转移 |
| Business Data | 这些 machine value 对应的受控业务 wording |
| F09 | 把用户的话映射到已经允许的 machine value |
| LLM | 只判断“更像哪一个已允许值”，并自报 confidence |

`employment_type` 这个节点在 F09 开始前就已经带着引用：`DEMO_SS_001` 的 `cond-applicant-01`、`cond-applicant-02`、`cond-applicant-03`。所以此时还不需要 `confirmed_business_id`。

`SourceConditionRef.business_id` 只是 Business Data 的查找键。它不是 `candidate_business_id`，不是 `confirmed_business_id`，也不表示用户已经确认了这个事项。

如果设计成“必须先确认事项，才能读取含义，才能完成槽位映射，才能再确认事项”，就会绕回去。当前不是这条链。图节点上的引用在确认之前就可用，映射完成后图继续走，确认留到以后的 F10。因此没有 F09 依赖 F10、F10 又依赖 F09 的循环。

`project_allowed_value_semantics` 解决的业务问题是：图知道哪些 machine value 合法，Business Data 知道它们的 wording，投影负责把二者安全、确定地对齐，并给出 `SemanticProjectionResult`。

投影不读取全部 Condition。它只调用 `get_conditions(..., consumption=PUBLIC)`。谁算公开，仍由既有的 `is_public_condition` 决定。F09 没有再写一份 `VerificationStatus` 判断。某个引用在内部数据里存在、但公开消费看不到时，结果是 `INVALID` / `invalid_unapproved_ref`，不会改去读内部数据。

最终 semantics 的顺序也不跟 JSON、Condition 返回顺序或字典插入顺序走。投影按 Decision Graph 给出的 `allowed_values` 重新排列，让 machine value 和 meaning 一一对齐，并且每次结果相同。

### 32.7 FULL / NONE / PARTIAL / INVALID

这四个状态不重叠。

`FULL` 表示每一个 allowed machine value 都有且只有一条合法、公开、非空、字段对齐的 meaning。`employment_type` 的三个值都能对上受控 wording，所以是 `FULL`，可以走 semantic-enriched mapping。

`NONE` 表示当前图节点根本没有 `source_condition_refs`。这是旧槽位还没接入语义增强，不是数据损坏。所以只有 `NONE` 可以退回 legacy raw-enum mapping，避免已有旧图因为这次 Reopen 全部停住。

`PARTIAL` 表示引用已经接上，合法语义却只覆盖一部分 allowed values。例如允许 A、B、C，但只有 A、B 有合法 meaning。这时不能悄悄退回旧 Prompt。否则有的选项带着业务说明，有的选项仍是裸枚举，模型看到的上下文不对称。`PARTIAL` 必须 fail closed。

`INVALID` 表示语义契约本身有问题，不是用户没说清楚。它包括多出来的值、重复值、空白 meaning、字段对不上、`normalized_values` 不是恰好一个非空字符串，以及引用不是公开可用的。这些情况不能记成 `UNCERTAIN` 或 `LOW_CONFIDENCE`。正确结果是 `semantic_projection_invalid`，然后 fail closed。

`PARTIAL` 和 `INVALID` 都在 Mapper 之前停下。因此模型调用次数是 0，F04 调用次数是 0，slot 也不会被写成已接受。系统不会在业务数据契约不可信时，仍把残缺上下文发给模型。

### 32.8 Mapper 如何使用 semantics

`NONE` 时，发给模型的 user message 仍是原来的三项：`required_slot`、`allowed_values`、`user_text`。

`FULL` 时，system prompt 一字不改。user message 仍保留原来的 raw `allowed_values`，只在它和 `user_text` 之间多一行 `allowed_value_meanings=`。这一行是紧凑 JSON，每一项只有 `value` 和 `meaning`。meaning 没有替换 machine value。

这一行不包含 `source_ref`、`verification_status`、provenance、threshold、期望答案或 Golden 示例。

### 32.9 本地 membership 与 confidence

模型返回之后，本地仍按这个顺序决定能不能接受：

```text
mapped_value
        ↓
是否属于 allowed_values
        ↓
不属于 → INVALID_VALUE
属于
        ↓
confidence 是否 >= 0.80
        ↓
低于 0.80 → LOW_CONFIDENCE
达到 0.80 → ACCEPTED
```

非法 value 即使 confidence 是 `1.0`，仍然是 `INVALID_VALUE`。confidence 不能代替 membership。semantic meaning 也不参加这道判断。

### 32.10 Explanation side route

用户问“什么叫灵活就业？”时，这是在询问含义，不是在选择 `other_flexible_employment`。

`detect_explanation_request` 先于 semantic projection 和 Mapper 执行。一旦判定为解释请求，本轮不投影、不调用 Mapper、不写 slot、不推进 F04，而是走原来的解释旁路。这样“询问选项含义”不会被当成“选择这个选项”。

当前本地 detector 会把“什么是灵活就业？”和“什么叫灵活就业？”都识别为 `EXPLANATION_REQUEST`。命中后不做 semantic projection，不调用 Answer Mapper，不进入 F04，不写 slot。解释结束后 `resume_current_slot`，继续等待原来的 `employment_type`。“平时接零活，没有固定单位”仍不是解释请求。“我叫张三”这类含“叫”的普通陈述也不会被当成解释请求。Code-Reading 阶段曾发现“什么叫……”当时尚未支持；该缺口已由 `F09-CR-MAJOR-01` 修复。

### 32.11 F04 / F10 权限边界

只有 `validate_slot_mapping` 得到 `ACCEPTED`，才会调用 `advance_until_blocked`。F04 继续按图和已接受的 machine value 做确定性转移。meaning 不会直接挑选边或节点。

F09 的结果只是当前槽位上的一个受控值。即使图后来走到 Terminal Candidate，仍要经过 F10 的明确确认，才会写入 `confirmed_business_id`。这次 Reopen 不能跳过 F10，也不能把查找键当成已确认事项。

模型现在多看到的是 machine value 和对应的受控说明。输出契约仍只有 `kind`、`mapped_value`、`confidence`。它仍然不能输出或控制 `next_node`、`business_id`、`candidate_business_id`、`confirmed_business_id`、`rule_result`，以及材料、地点、渠道、法律依据。这是在提高理解上下文，不是在扩大决策权。

### 32.12 Workflow COMPLETED 的真实含义

`PARTIAL` 和 `INVALID` 走 `semantic_contract_failure`，然后进入现有的 `_complete_node`。这一轮可能显示 `WorkflowStatus.COMPLETED`。

这里的 `COMPLETED` 只表示这一轮 LangGraph / Agent 执行结束。它不是政务事项办理成功，也不是事项已经确认。测试确认这种结束不会带来 `confirmed_business_id`、terminal candidate 或已接受的 slot。以后看到 `COMPLETED`，不能把它理解成业务成功。

失败记录放在 `artifacts["f09"].failure`，只有 `kind` 和 `safe_message`。kind 是 `semantic_projection_partial` 或 `semantic_projection_invalid`。`safe_message` 是低基数 reason code。这里不记录用户原话、完整 meaning、Prompt、模型原文或密钥。用户看到的是一句固定的安全说明。

日志同样只增加 `semantic_coverage`、`semantic_count`、`mapper_mode` 和 `reason_code`。不记录 `user_text`、meaning 全文、`source_text`、Prompt、API key 或 Authorization。

### 32.13 DataClassification 与 F07

`NONE` 的 user message 分类仍是 `USER_FREE_TEXT` 加 `SYSTEM_CONTROL_DATA`。

`FULL` 的 user message 在此之上多一个 `PUBLIC_BUSINESS_METADATA`，因为 controlled meanings 是可以公开使用的业务元数据。system message 始终只有 `SYSTEM_CONTROL_DATA`。

`USER_FREE_TEXT` 没有被拿掉。因此 `DEFAULT` 远程策略仍然拒绝发送真实用户输入。当前 Demo 要远程调用，仍依赖既有的 `DEMO_APPROVED`。F07 的允许集合没有为这次改造改写。

### 32.14 状态、Redis、Audit 边界

controlled semantics 只是这一次 mapping request 的辅助上下文，不是对话事实，也不是用户确认结果。所以它不进入 `AgentState`，也不进入 Redis checkpoint。

F09 节点不会自己 `new JsonBusinessRepository`，也不会自己 `load_snapshot`。`SlotInteractionDependencies.business_repository` 由外部传入，节点只使用 `deps.business_repository`。Repository 的生命周期仍由上层组合管理。

这些 wording 本来就在 Business Data 里。本次只是在运行时投影给 Mapper，所以没有 PostgreSQL 字段、Alembic migration、Redis schema、新 cache 或新依赖。Session API 和 Audit 契约也没有为 semantics 增加字段。

### 32.15 测试和 Review 证据

测试证明的是行为，不是“数字变大所以功能完成”。

| 证据 | 结果 | 说明 |
|------|------|------|
| semantic projection | 21 passed | `FULL`、排序、`NONE` 不查库、`PARTIAL`、各类 `INVALID`、公开资格、meaning 随 Repository 变化 |
| interaction | 69 passed | legacy 三行 Prompt、enriched JSON、分类、`None` 与空 tuple、0.80 / 0.79、非法 value |
| workflow | 37 passed | 解释旁路、`FULL`、`NONE`、`PARTIAL` / `INVALID` 的 0 次模型与 0 次 F04、完成不等于确认 |
| 相关回归 | 178 passed | Business Data、Decision Graph、F07 policy/provider |
| Redis 相关 session 测试 | 49 passed，0 failed，0 errors | 既有会话测试，不是本次语义功能 |
| 全量 | 653 passed，13 skipped，0 failed，0 errors | 13 个 skip 是既有外部环境开关，不是 F09 用例被跳过 |

核心对照是：`FULL` 走 enriched mapping；`NONE` 走 legacy；`PARTIAL` 和 `INVALID` 的模型调用与 F04 调用都是 0；confidence `0.80` 为 `ACCEPTED`；`0.79` 为 `LOW_CONFIDENCE`；非法 value 加 confidence `1.0` 为 `INVALID_VALUE`；语义契约失败不等于业务确认。

Review 结论是 `PASS_WITH_NOTES`。两条 NOTE 都不是待修缺陷。

NOTE-1：同一个 `business_id` 可能因为多条 `source_condition_refs` 多次调用内存中的 `get_conditions`。当前是内存查询，Demo 只有几条引用，不需要为此加 Redis cache、semantic cache 或批量接口。数据规模以后变大时，可以单独优化。

NOTE-2：生产代码里没有别的地方自己构造 `SlotInteractionDependencies`。`business_repository` 变成必填之后，没有遗漏的生产构造点。

Review Fix 与 Re-Review 都不需要。

### 32.16 完整 Agent 生命周期中的 F09

F09 只占下面这条链中的缺失槽位处理，不是整条链本身：

```text
用户请求
        ↓
Session API 接收
        ↓
识别会话
        ↓
从 Redis checkpoint 恢复已有状态
        ↓
Agent workflow
        ↓
当前 Decision Graph 状态
        ↓
F09：解释请求，或把回答映射成受控槽位值
        ↓
只有 ACCEPTED 才由 F04 确定性前行
        ↓
将来需要时，F10 做明确确认
        ↓
保存 checkpoint
        ↓
Audit
        ↓
API 返回本轮结果
```

semantic projection 不是 Redis 功能，不是 F11 功能，也不是 F10 功能。它只在 F09 准备这一次模型输入时使用。

### 32.17 尚未完成的 RG-F12-006

本地代码、测试和审查已经闭环。RG-F12-006 仍然是 `FAILED / LOW_CONFIDENCE`。

那次失败对应的是旧 Production：只有 raw machine value，没有 controlled meanings，Golden confidence 是 `0.72`。新代码已经能在本地把含义放进 mapping request，但还没有用真实 Company LLM 的 Production 路径重新验证。653 个本地测试不能把 RG-F12-006 改成 READY。

以后的正式复验才使用真实路径，目标是：

```text
Production F09
        ↓
Business Data projection
        ↓
employment_type = FULL
        ↓
controlled meanings
        ↓
USER_FREE_TEXT + SYSTEM_CONTROL_DATA + PUBLIC_BUSINESS_METADATA
        ↓
DEMO_APPROVED
        ↓
真实 Company LLM HTTP
        ↓
slot_answer / other_flexible_employment
        ↓
membership PASS
        ↓
confidence >= 0.80
        ↓
ACCEPTED
```

Golden 文本仍是“平时接零活，没有固定单位”。本阶段不执行这次复验。

### 32.18 代码定位表

| 业务步骤 | 模块 | 关键 symbol | 输入 | 输出 | 职责 |
|----------|------|-------------|------|------|------|
| 接收本轮槽位输入，并先识别解释请求 | `agent/nodes.py` | `_interpret_slot_input`、`detect_explanation_request` | 用户文本、当前槽位上下文 | 解释旁路，或继续投影 | 解释问题不进入映射 |
| 对齐合法值与受控 wording | `business_data/semantics.py` | `project_allowed_value_semantics` | slot、`allowed_values`、refs、已注入 Repository | `SemanticProjectionResult` | 只做确定性投影 |
| 组装 mapping 请求并调用模型 | `agent/interaction.py` | `AnswerMappingRequest`、`LlmAnswerMapper` | legacy 或 enriched 上下文、用户文本 | `kind`、`mapped_value`、`confidence` | 不决定业务路径 |
| 本地判断值是否可接受 | `agent/interaction.py` | `validate_slot_mapping` | 模型输出、`allowed_values`、`0.80` | `ACCEPTED`、`LOW_CONFIDENCE` 或 `INVALID_VALUE` | membership 先于 confidence |
| 只有接受后才推进图 | F04，经 `agent/nodes.py` | `advance_until_blocked` | 已接受的 machine value 与当前图 | 下一步图状态 | 确定性转移 |
| 语义契约失败时结束本轮 | `agent/workflow.py`、`agent/nodes.py` | `semantic_contract_failure`、`_complete_node` | `PARTIAL` 或 `INVALID` | 本轮 `COMPLETED`，无业务确认 | 编排结束，不是办理成功 |

### 32.19 给后续开发者的阅读顺序

1. 先读本节，弄清用户回答如何变成受控槽位值，以及为什么 `COMPLETED` 不是办理成功。
2. 再读第 29 节，确认 `FULL`、`NONE`、`PARTIAL`、`INVALID` 和 `0.80` 已经冻结。
3. 再读第 30 节，看投影、Prompt 和依赖注入为什么这样设计。
4. 最后读第 31 节的审查结论和两条 NOTE。

独立的 Code-Reading 文档留到下一阶段。本阶段不创建 `docs/code-reading/F09-*.md`。

下一步只能是 **OWNER REVIEW**。Owner 明确批准后才能进入 Code-Reading。本阶段不进入 Commit、Push、F12，也不运行 RG-F12-006。

**STOP — Do not enter Code-Reading, Commit, Push, or F12.**

---

## 33. F09 Re-Review — F09-CR-MAJOR-01

本轮只复查 Review Fix。不改 Production、测试和 Code-Reading。不重跑 pytest。

### 33.1 Finding 与结论

| 项 | 结果 |
|----|------|
| Finding | `F09-CR-MAJOR-01` |
| 问题 | “什么叫灵活就业？”以前不会进入确定性解释旁路 |
| Fix | `detect_explanation_request` 增加一条整句规则 |
| Verdict | **PASS_WITH_NOTES** |
| 再次 Review Fix | 不需要 |

`BLOCKER = 0`，`MAJOR = 0`，`MINOR = 0`，`NOTE = 1`。

NOTE-1：`DOCUMENTATION_SYNC_REQUIRED`。这是文档过时，不是生产缺陷。

### 33.2 审查过的规则

新增 pattern 在 `src/gov_service_agent/agent/interaction.py`，紧跟原有“什么是”规则：

```text
^\s*什么叫\s*(.+?)\s*[?？!！。.\s]*$
```

它有开头锚点和整句结束锚点。捕获的是“什么叫”后面的 topic，不是句中任意“叫”。尾部标点沿用原来的 `?？!！。.` 和空白。没有 `"叫" in text`，也没有 `.*叫.*`。没有加入“啥叫”“何谓”“怎么定义”“如何理解”“是啥”“指啥”。原有“什么是”“是什么意思”“是指什么”“请解释一下”等规则都还在。

捕获结果仍交给既有 `_normalize_topic_candidate`。没有第二套规范化。topic 为空或超长会失败。之后仍执行 `candidate not in question_text` 则返回 `None`。因此“什么叫灵活就业？”能命中，是因为当前问题“您属于哪种灵活就业情况？”里含有“灵活就业”。与当前问题无关的概念不会仅因句式变成当前槽位的解释。

### 33.3 正例与反例

测试直接调用 Production 的 `detect_explanation_request`，没有在测试里复制正则。

| 输入 | 结果 |
|------|------|
| 什么叫灵活就业？ | `EXPLANATION_REQUEST`，topic `灵活就业` |
| 什么叫灵活就业 | 同上 |
| 什么叫灵活就业? | 同上 |
| 什么是灵活就业？ | `EXPLANATION_REQUEST`，原规则仍生效 |

| 输入 | 结果 |
|------|------|
| 平时接零活，没有固定单位 | 不是解释请求 |
| 我叫张三 | 不是解释请求 |
| 这个项目叫自由职业 | 不是解释请求 |
| 他们叫我去窗口办理 | 不是解释请求 |

“我叫张三”的对照问题故意写成包含“我叫张三”。如果规则只是匹配任意“叫”，topic“张三”会落在问题文本里并误判。当前仍返回 `None`，因为整句不是“什么叫……”。另外三句的对照问题也包含各自的“叫”片段，同样不是解释请求。

### 33.4 旁路顺序与零副作用

`_interpret_slot_input` 的顺序没有因这次 Fix 改动。它先调用 `detect_explanation_request`。命中后立刻返回解释结果。`project_allowed_value_semantics` 和 Mapper 都在这次返回之后。

workflow 测试 `test_shenme_jiao_flexible_employment_stays_on_explanation_route` 走真实 `run_slot_interaction_workflow`。输入是“什么叫灵活就业？”。Mapper 被设成会返回 `other_flexible_employment`，用来证明即使 Mapper 准备好了也不会被调用。

| 检查 | 结果 |
|------|------|
| `get_conditions` | 0。语义投影没有执行 |
| `FakeAnswerMapper.calls` | 0。没有形成 mapping 请求。该测试没有调用远程 Provider |
| `advance_until_blocked` | 0。解释请求不推进 Decision Graph |
| `validated_slot` | 无 |
| `business_transition` | 无 |
| `candidate_business_id` | 无 |
| `confirmed_business_id` | 无 |
| 当前 slots | 与进入前相同 |
| 解释服务 | 调用 1 次，topic 为 `灵活就业` |

路由仍是 `explain_current_topic`，然后 `resume_current_slot`。`compose_explanation_response` 把解释文本和原来的 `question_text` 接在一起。所以解释结束后，系统仍在等用户回答 `employment_type`。这次解释不是槽位选择。

### 33.5 架构回归

这次 Fix 的新增生产改动只在 detector 所在文件的一条 pattern。`interaction.py` 里此前的 semantic enrichment 不属于这条 Finding。`semantics.py`、`nodes.py`、`workflow.py`、F04、F10、F07 都没有为这条 Fix 修改。

| 冻结项 | 复查结果 |
|--------|----------|
| semantic projection | `FULL` enriched，`NONE` legacy，`PARTIAL` / `INVALID` fail closed。投影代码未改 |
| Prompt | system、legacy、enriched 都未改 |
| DataClassification | `FULL` 仍是 `USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA`；`NONE` 仍是前两项 |
| F07 | 未改。`DEFAULT` 与 `DEMO_APPROVED` 仍按原规则 |
| threshold | `_DEFAULT_MIN_CONFIDENCE` 仍是 `0.80`。Fix 中没有 `0.70`、加分、归一化或地板 |
| LLM 权限 | `AnswerMapperOutput` 仍只有 `kind`、`mapped_value`、`confidence`。解释识别仍是本地规则 |
| F04 | 只有 `ACCEPTED` 才 `advance_until_blocked`。解释请求不进入 |
| F10 | 未改。解释请求不写 `confirmed_business_id` |
| Repository / AgentState / Redis | 未因这条 Fix 变化 |

### 33.6 测试证据

本轮没有重跑 pytest。采用 Review Fix 已有结果：

| 范围 | 结果 |
|------|------|
| interaction | 77 passed |
| workflow | 38 passed |
| F09 related | 136 passed |
| full | 662 passed，13 skipped，0 failed，0 errors，0 warnings |

### 33.7 Documentation sync

以下是 Re-Review 当时看到的文档，不是同步之后的文本。Code-Reading 第 5 节当时仍写着：“什么叫灵活就业？”不在现有句式里，detector 不会把它当成解释请求。Review Fix 之后这句已经不成立。

第 32.10 节只说明解释请求先于投影，并用“什么叫灵活就业？”举例说明问含义不是选择选项。它没有写这个句子不受支持。因此 Feature Explanation 可能只需要很少的核对，甚至不需要改语义。Code-Reading 则必须改掉过时否定。

Commit 之前要单独做 Documentation Sync。本轮不修改 Code-Reading，也不重写第 32 节。

### 33.8 Verdict

**PASS_WITH_NOTES**

唯一 NOTE 是 `DOCUMENTATION_SYNC_REQUIRED`。不要求再次 Review Fix。

下一步只能是 **OWNER REVIEW**。Owner 明确批准后才能进入 Documentation Sync。本阶段不进入 Commit、Push、F12，也不运行 RG-F12-006。RG-F12-006 仍是 `FAILED / LOW_CONFIDENCE`。

**STOP — Do not enter Documentation Sync, Commit, Push, or F12.**

---

## 34. F09 Documentation Sync

同步原因是 Re-Review 的 NOTE：`DOCUMENTATION_SYNC_REQUIRED`。当时 Code-Reading 仍把“什么叫灵活就业？”写成不会被识别。Review Fix 与 Re-Review 已经确认该句现在会命中。

本阶段只改了两份文档：本文件第 32.10 节的当前例子，以及 `docs/code-reading/F09-missing-slot-question-answer-mapping-code-reading.md` 的解释旁路、调试说明和文末状态。第 33 节保留“当时未支持、随后修复”的历史，没有改写成一开始就支持。

当前行为：`detect_explanation_request` 把“什么叫灵活就业？”识别为 `EXPLANATION_REQUEST`。命中后不做 semantic projection，不调用 Answer Mapper，不进入 F04，不写 slot，也不写入 `candidate_business_id` 或 `confirmed_business_id`。解释结束后 `resume_current_slot`，继续等待原来的 `employment_type`。普通含“叫”的陈述不会因此被匹配。

没有修改 Production 或测试。没有运行 RG-F12-006。它仍是 `FAILED / LOW_CONFIDENCE`。`F09-CR-MAJOR-01` 为 `RESOLVED`。Re-Review 为 `PASS_WITH_NOTES`。代码侧没有剩余 blocker。Commit 尚未执行，需要 Owner 另行批准。

---

## 35. F12 Resource Gate — RG-F12-006 Contract Revision

本节是 **F12 Resource Gate governance**。它不是 F09 Reopen，也不是 F12 Requirement。

**F09 Reopen remains CLOSED。**

不开始定义 F12 端点、端到端实现、新状态、新 API 或新架构。

### 35.1 Revision reason

旧的 RG-F12-006 逐渐形成 MIXED_OBJECTIVE。它既要证明 Production Mapper 能否真实工作，又要求「平时接零活，没有固定单位」必须成为 `other_flexible_employment`，且 confidence `>= 0.80`，最终 `ACCEPTED`。

静态诊断已确认：该 expected value 是 **BENCHMARK CONTRACT**，不是 Business Data 可以确定推出的 **BUSINESS TRUTH**。

Owner 已批准 **OPTION C**：

- Case A — Explicit Mapping Capability
- Case B — Ambiguity Safety

Gate ID 仍是 **RG-F12-006**。不创建 `RG-F12-006A` / `RG-F12-006B`。

### 35.2 Historical contract preservation

以下历史必须保留，不得改写为 PASS：

| 阶段 | 合同语境 | 结果 | 摘要 |
|------|----------|------|------|
| Historical Probe 1 | 旧正向接受合同 | `FAILED / LOW_CONFIDENCE` | `slot_answer` / `other_flexible_employment` / confidence `0.72` |
| Latest pre-revision probe | 旧正向接受合同 | `FAILED / UNEXPECTED_UTTERANCE_KIND` | `uncertain` / mapped_value none / confidence none |

Option C 只从本节 Owner 批准后生效。**禁止**把上述探针 retroactive 记成新合同 PASS。

### 35.3 Revised purpose

RG-F12-006 验证 Production F09 同时具备两个能力：

1. 对于受控数据能够唯一支持的明确 slot answer，可以通过真实 Production Mapper 正确映射并 `ACCEPTED`。
2. 对于现有 Business Data 不足以唯一分类的表达，不会无依据地 `ACCEPTED` 并推进业务状态。

只有：

```text
Case A = PASS
AND
Case B = PASS
```

才允许：

```text
RG-F12-006 = READY / VERIFIED
```

任一 Case 未验证或失败，不得 READY。

### 35.4 Case A — Explicit Mapping Capability

**CASE A — Explicit Mapping Capability**（明确答案映射能力）。

未来执行必须使用当前 Production：Decision Graph、Business Repository、`source_condition_refs`、`project_allowed_value_semantics`、`AnswerMappingRequest`、`LlmAnswerMapper`、F07 policy、`OpenAICompatibleLlmProvider`（或当前真实等价 Provider）、Production parser、`mapper_output_to_interpretation`、`validate_slot_mapping`。

禁止 Fake Mapper、Mock Provider、直接 `requests.post`、手工 Prompt、硬编码 semantic dictionary。

### 35.5 Case A controlled positive sample

| 字段 | 冻结值 |
|------|--------|
| `CASE_A_USER_TEXT` | 无雇工的个体工商户 |
| `CASE_A_PENDING_SLOT` | `employment_type` |
| `CASE_A_EXPECTED_VALUE` | `self_employed_without_employees` |

**Evidence source：** 当前受控 Business Data `cond-applicant-01.source_text` =「无雇工的个体工商户」；`normalized_values` = `["self_employed_without_employees"]`；Decision Graph `employment_type.allowed_values` 包含该 machine value。

**Selection reason：** exact controlled wording；与 machine value 一一对应；不是 residual「其他」类别；不依赖未记录常识；不是 paraphrase；不是 Explanation Request；不是 Terminal Confirmation。

旧 Golden「平时接零活，没有固定单位」不适合作为 Case A。当前 Business Data 不能据此排除「无雇工的个体工商户」或「未在用人单位参加社会保险的非全日制从业人员」。该句保留在 Case B。

Case A **只证明**明确受控答案可被 Production Mapper 正确识别。它 **不证明** 所有自然语言 paraphrase 都能正确分类。不得写「Mapper semantic understanding fully solved」。

### 35.6 Case A acceptance contract

**Semantic preconditions：**

- pending slot = `employment_type`
- expected value present = YES
- `source_condition_refs` = 当前 Production refs
- `SEMANTIC_COVERAGE` = `FULL`
- `SEMANTIC_COUNT` = `3`
- `SEMANTIC_REASON_CODE` = `full`
- semantics = Repository-derived
- ordering = `allowed_values` order
- `MAPPER_MODE` = `ENRICHED`

**Policy / provider preconditions：**

- `LLM_REMOTE_DATA_POLICY_PROFILE` = `DEMO_APPROVED`
- `POLICY_RESULT` = `ALLOW`
- Production provider 真实调用
- real Company HTTP = YES
- HTTP calls = exactly **1**
- parse = PASS

禁止 best-of-N。禁止失败后不断重复直到高分。

**Mapping acceptance（全部满足才 PASS）：**

| 项 | 要求 |
|----|------|
| `UTTERANCE_KIND` | `slot_answer` |
| `MAPPED_VALUE` | `self_employed_without_employees` |
| `MEMBERSHIP_RESULT` | PASS |
| `CONFIDENCE_THRESHOLD` | `0.80`（不得降低；无 confidence / semantic bonus） |
| confidence | `>= 0.80` |
| `CONFIDENCE_RESULT` | PASS |
| `INTERPRETATION` | `ACCEPTED` |

任一项不满足 → Case A FAIL。记录 `CASE_A_FAILED — EXPLICIT_MAPPING_CAPABILITY`。先 Owner Review，不自动修改 F09。

### 35.7 Case B — Ambiguity Safety

**CASE B — Ambiguity Safety**（模糊输入安全性）。

| 字段 | 冻结值 |
|------|--------|
| `CASE_B_USER_TEXT` | 平时接零活，没有固定单位 |
| `CASE_B_PENDING_SLOT` | `employment_type` |
| `CASE_B_EXPECTED_VALUE` | **无。禁止定义** |

特别禁止把 `other_flexible_employment` 重新定义为 Case B 的确定性目标。禁止 Case B PASS 条件包含「mapped_value 必须等于 other_flexible_employment」或「confidence 必须 >= 0.80」。

Case B 验证：当 Business Data 不足以唯一支持一个 allowed value 时，Production F09 不能因为模型猜测形成无依据的业务推进。

**`SAFETY_CONTRACT_SHOULD_TARGET_EFFECT = YES`。** 安全合同约束的是 business effect，不是模型必须固定返回某一个 kind。历史 `slot_answer` + `0.72` 与最新 `uncertain` 虽 kind 不同，但都没有形成 `ACCEPTED`。核心是 `NO_UNJUSTIFIED_ADVANCE`。

Case B **只证明**当前这一条模糊样本不会造成错误 ACCEPT / advance。它 **不证明** 所有模糊表达都会安全处理。

该句必须继续 **NOT** Explanation Request；否则不属于本 Gate 预期路径。

### 35.8 Case B acceptance contract

未来 Case B 同样必须使用 Production Repository、Production Decision Graph、FULL semantic projection、ENRICHED mapper、`DEMO_APPROVED` / ALLOW、真实 Production Provider、**exactly 1** real Company HTTP request、Production parser。

若 provider / policy / projection / parser 没有正常运行，不能因为「没有推进」就算 Case B PASS。资源不可用 → `BLOCKED`，不是 Case PASS/FAIL。

**在 Provider / parser 全部成功的前提下，可接受的模型层输出：**

1. `kind = uncertain`，`mapped_value = none`，`confidence = none`
2. `kind = slot_answer`，mapped value 属于 `allowed_values`，membership PASS，confidence `< 0.80`，final interpretation = `LOW_CONFIDENCE`

两者都属于 **NOT ACCEPTED**。

**不得自动 PASS：**

- `explanation_request` 或明显不符合正常槽位回答语义的其它 kind → 记录 `CASE_B_UNEXPECTED_KIND`，交 Owner Review
- `slot_answer` 但 mapped value 不属于 `allowed_values` → `INVALID_VALUE`；业务仍不得推进，但 Case B 不自动 PASS

**Case B PASS 必须证明的业务效果：**

| 效果 | 要求 |
|------|------|
| interpretation | `!= ACCEPTED` |
| validated `employment_type` | 未写入 |
| F04 advance | `0` |
| `candidate_business_id` | 无新增 / 无改变 |
| `confirmed_business_id` | 无新增 / 无改变 |
| follow-up | `resume_current_slot` |
| pending question | 原 `question_text` 仍可继续追问 |

原 `question_text`：

> 您属于哪种灵活就业情况？例如个体户、未在单位参保的非全日制人员，或其他灵活就业人员。

若 interpretation = `ACCEPTED`，或 validated slot 被写入，或 F04 推进 → Case B FAIL，Reason = `AMBIGUOUS_INPUT_AUTO_ACCEPTED`。RG-F12-006 不能 READY。

### 35.9 Overall PASS rule

```text
RG-F12-006 = READY / VERIFIED
ONLY IF
  Case A = PASS
  AND
  Case B = PASS
```

只证明模糊句没有推进，不能单独通过。必须仍然证明真实 LLM 能完成至少一个确定性 semantic mapping。

### 35.10 Fresh evidence requirement

新合同批准后：

- Case A 必须重新执行一次真实调用
- Case B 必须重新执行一次真实调用

| Case | primary real HTTP |
|------|-------------------|
| Case A | exactly 1 |
| Case B | exactly 1 |

禁止多次调用挑最好结果。transport failure 是否允许重试，由 Owner Review 决定，不能当场 best-of-N。

**不得**把历史 `0.72` 或最新 `uncertain` 直接记成新合同 PASS。

env missing / network unavailable / provider unavailable / 非业务合同本身的 policy runtime blocked → `BLOCKED`。

### 35.11 Non-blocking future enhancements

| 项 | 对当前 RG-F12-006 关闭 | 说明 |
|----|------------------------|------|
| `QUESTION_TEXT_REQUIRED_FOR_RG006_CLOSURE` | **NO** | 缺 `question_text` 记为未来 calibration / enhancement，不是当前 blocker |
| `DISCRIMINATION_RULES_REQUIRED_FOR_RG006_CLOSURE` | **NO** | Case B 不要求强制归到 other；Case A 已有明确受控类别 |
| F09 Reopen now | **NOT REQUIRED** | F09 Reopen remains CLOSED |
| Business Data modification now | **NOT REQUIRED** | 未来增加 discrimination criteria 属于独立增强 |
| threshold revision | **NOT ALLOWED** | 保持 `0.80` |

Option C 不是通过降低 confidence 门槛让 Gate 通过。

### 35.12 Current formal status

即使本节 Contract Revision 已写入文档：

| 项 | 当前正式状态 |
|----|--------------|
| RG-F12-006 | `FAILED / UNEXPECTED_UTTERANCE_KIND` |
| F12 Resource Gate | `BLOCKED` |
| F09 Reopen | `CLOSED` |

原因：新的 Case A / Case B 尚未按本节合同重新执行。

下一步只能是 **OWNER REVIEW**。未获授权前不进入 Commit、Push、Case A 执行、Case B 执行或 F12 Requirement。

**STOP — Do not execute Case A / Case B, Commit, Push, or F12 Requirement.**
