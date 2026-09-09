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
| **OI-F09-DP-001** | 真实 `USER_FREE_TEXT` → Remote Company LLM 仍 DENY；未来 Remote NLU 须 Owner Policy 授权 | **OPEN / NON-BLOCKING** | **NO** | D15（保持；不修改 F07 Policy） |

**禁止（OI-F09-04）：** 仅为单个 Demo 句子做 `if "什么是社保转移"` 特例 hardcode。

**INFO-F09-01：** F08 Feature Doc stage wording drift — **INFO only**；F09 **不修改** F08。

---

## 14. Deferred Items

| 项 | 归属 |
|----|------|
| Real Remote NLU（真实 USER_FREE_TEXT → Company Provider） | 未来 Owner Policy authorization（OI-F09-DP-001） |
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
| OI-F09-DP-001 | **OPEN / NON-BLOCKING** |
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
- 真实 `USER_FREE_TEXT` → Company Remote = **DENY**（OI-F09-DP-001）

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

### D15 — Data Policy（OI-F09-DP-001 保持 OPEN / NON-BLOCKING）

| Path | Classification | Company Remote |
|------|----------------|----------------|
| Answer Mapper request | **含** `USER_FREE_TEXT` | **DENY before network** |
| Explanation request | **仅** `SYSTEM_CONTROL_DATA` + `PUBLIC_BUSINESS_METADATA` | Demo **可行**（因无 raw user text） |

**为什么 Demo Explanation 可行：** Local detector 已 normalize；`ExplanationRequest` 类型无 raw user field；Remote 仅 ALLOW 分类。**不是**放宽 `USER_FREE_TEXT` Policy。

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
| OI-F09-DP-001 | **OPEN / NON-BLOCKING** |

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
| Data Policy Open Item | **OI-F09-DP-001 = OPEN / NON-BLOCKING** |

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
4. OI-F09-01…08 保持 RESOLVED；OI-F09-DP-001 保持 OPEN / NON-BLOCKING（非 Confirm blocker）。
5. INFO-F09-01（F08 docs drift）继续 INFO；本 Confirm **不修改** F08。

### 21.5 Unresolved Findings

**NONE**（blocking）。
唯一保留 Open Item：OI-F09-DP-001（Real USER_FREE_TEXT → Company Remote = DENY）。

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

#### 实现了 Mapper ≠ 当前可 Remote

`LlmAnswerMapper` **已实现**，但注入 Company Remote Provider 时，真实用户回答仍 **DENY before network**。这不是功能没做完，而是 F07 Data Policy 明确禁止真实 `USER_FREE_TEXT` 远程发送（`OI-F09-DP-001` 仍 OPEN / NON-BLOCKING）。

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

`OI-F09-DP-001`：**OPEN / NON-BLOCKING**（真实 USER_FREE_TEXT → Company Remote 仍 DENY）。

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
| **RF-F09-001** | INFO | `OI-F09-DP-001` remains **OPEN / NON-BLOCKING** |
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
