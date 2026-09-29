# F07 — LLM Abstraction + Demo Provider + Real Company Provider + Data Policy

## 1. Feature Status

| 字段 | 内容 |
|------|------|
| Feature ID | F07 |
| Feature Name | LLM Abstraction + Demo Provider + Real Company Provider + Data Policy |
| Original F07 | **CLOSED** @ `3b6872657fc4c6a74f74a1432fa2818707476a89`（`feat(F07): 建立LLM提供方与远程数据安全边界`） |
| Current Stage | **POLICY REOPEN — CODE-READING COMPLETE / AWAITING COMMIT AUTHORIZATION** |
| Policy Reopen Resource Gate | **READY**（Owner Demo Policy Decision Integrated） |
| 前置 Feature | F06 — Embedding + Semantic Retrieval（CLOSED @ `4a8bb61`） |
| Git Baseline（本 Reopen Requirement） | `develop` @ `894e39426d5e8b9b3bd2dc81e3b4ac40569c42c5` |
| Original Git Baseline（历史） | `develop` @ `4a8bb61c1a9618e010352ece36ac72d5be0aabfc`（见下方 Original Stage Status） |
| External Resource Gate（原） | **CLOSED** |
| Real Provider Scope | **B**（Abstraction + Demo + Real Company Provider + Data Policy + Real Connectivity Smoke） |
| Requirement Document | `docs/features/F07-llm-provider-data-policy.md` |
| Code-Reading Document | `docs/code-reading/F07-llm-provider-data-policy-code-reading.md` |

### Current Stage Status（Policy Reopen）

| 阶段 | 状态 |
|------|------|
| Original F07 | **CLOSED** |
| Policy Reopen Resource Gate | **READY** |
| Policy Reopen Requirement | **COMPLETE** |
| Policy Reopen Requirement Finalization | **NOT REQUIRED** |
| Policy Reopen Technical Design | **COMPLETE** |
| Policy Reopen Technical Design Finalization | **NOT REQUIRED** |
| Policy Reopen Confirm | **COMPLETE** |
| Policy Reopen Code | **COMPLETE** |
| Policy Reopen Test | **PASS**（620 passed / 13 skipped / 0 failed / 0 warnings） |
| Policy Reopen Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 3） |
| Policy Reopen Review Fix | **NOT REQUIRED** |
| Policy Reopen Explanation | **COMPLETE** |
| Policy Reopen Code-Reading Update | **COMPLETE** |
| Policy Reopen Commit | **AWAITING OWNER AUTHORIZATION** |
| F12 Resource Gate | **仍 BLOCKED**（RG-F12-004 PENDING；RG-F12-006 = POLICY IMPLEMENTATION REVIEW PASS / RUNTIME VALIDATION PENDING） |

**本阶段范围：** Code-Reading Update 已完成。**禁止**自动 Commit / Push / 进入 F12。

> **RI-F07R-001 disposition：** Feature Doc stage 已同步至 Confirm→Code-Reading COMPLETE / AWAITING COMMIT。Original F07 CLOSED 历史保留不删。### Original Stage Status（历史快照 — 原 F07 CLOSED；保留不删）

> 说明：原文档表头曾长期残留「Commit — AWAITING COMMIT / Push NOT STARTED」字样（后续 Feature 已记录为 docs drift）。实际 Original F07 已于 commit `3b68726…` **CLOSED**（含 Push）。下表保留原阶段完成事实，不改写为「从未完成」。

| 阶段 | 状态 |
|------|------|
| Resource Gate | **CLOSED** |
| Requirement | **CLOSED** |
| Requirement Finalization | **N/A（Owner CLOSED，无 Finalization）** |
| Technical Design | **FINAL / CLOSED** |
| Technical Design Finalization | **PASS**（TD-F07-01 / 02 / 03） |
| Confirm | **DONE**（Owner 授权 Code） |
| Code | **COMPLETE** |
| Test | **PASS** |
| Review | **PASS** |
| Review Fix | **NOT REQUIRED** |
| Explanation | **COMPLETE** |
| Code-Reading | **COMPLETE**（Owner-approved 第 18 path） |
| Commit | **COMPLETE** @ `3b6872657fc4c6a74f74a1432fa2818707476a89` |
| Push | **COMPLETE** |

**原 Feature Scope：** **18 paths**（原 17 + 1 Code-Reading；非 Production/Test/Design Deviation）。

**原 Review：** PASS；BLOCKING/MAJOR/MINOR = 0；INFO = 3；Review Fix = NOT REQUIRED。

### Final F07 Paths（18）

| # | Path | 操作 |
|---|------|------|
| 1 | `src/gov_service_agent/llm/__init__.py` | NEW |
| 2 | `src/gov_service_agent/llm/types.py` | NEW |
| 3 | `src/gov_service_agent/llm/policy.py` | NEW |
| 4 | `src/gov_service_agent/llm/structured.py` | NEW |
| 5 | `src/gov_service_agent/llm/provider.py` | NEW |
| 6 | `src/gov_service_agent/llm/demo.py` | NEW |
| 7 | `src/gov_service_agent/llm/openai_compatible.py` | NEW |
| 8 | `src/gov_service_agent/settings.py` | MODIFY |
| 9 | `.env.example` | MODIFY |
| 10 | `pyproject.toml` | MODIFY |
| 11 | `tests/test_llm_policy.py` | NEW |
| 12 | `tests/test_llm_structured.py` | NEW |
| 13 | `tests/test_llm_demo.py` | NEW |
| 14 | `tests/test_llm_openai_compatible.py` | NEW |
| 15 | `tests/integration/test_llm_real.py` | NEW |
| 16 | `tests/test_settings.py` | MODIFY |
| 17 | `docs/features/F07-llm-provider-data-policy.md` | MODIFY |
| 18 | `docs/code-reading/F07-llm-provider-data-policy-code-reading.md` | NEW |

---

## 2. Background and Goals

F00–F06 已提供：最小 FastAPI 与 Settings/Logging、DEMO 业务数据契约、Business Decision Graph、确定性 Transition / Rule Selection、PostgreSQL+pgvector、本地 Embedding + Semantic Retrieval。

尚缺：**可替换的 LLM Capability 层**——在不夺取 Graph / Rule / 用户确认决定权的前提下，提供自然语言理解与受控结构化输出能力，并为远程调用建立可执行 Data Policy。

Canonical Flow（F07 仅负责加粗段中的 **LLM Capability**，不负责编排整条链路）：

```
用户自然语言
→ NLU / Slot Mapping（LLM Capability）          ← F07 provides capability
→ Semantic Retrieval（F06）
→ graph_entry
→ Business Decision Graph（deterministic）
→ missing slots / questions（F08/F09 编排集成）
→ Terminal Candidate
→ Verified Rule Layer
→ 用户确认 → confirmed business_id
→ Knowledge facts / Agent expression
```

### Goals

1. **LLM Provider Abstraction**：上层依赖中立抽象，不直接绑定公司 HTTP/SDK/具体模型实现。
2. **Deterministic Demo Provider**：无网络、无 API Key、确定性、可测；支撑普通 unit tests。
3. **Real Company Provider**：基于已验证的 OpenAI-compatible Chat Completion，完成受控调用与结构化输出。
4. **Structured Output Contract**：`DIRECT_JSON` 与严格唯一 JSON code fence + typed schema validation + Fail Closed。
5. **Data Policy / Remote Dispatch Guard**：远程发送前可执行分类与放行/拒绝；未知默认拒绝。
6. **Local-First Continuity**：基础 app import / `/health` / 普通测试不依赖公司 LLM 配置或网络。
7. **Safe Observability**：默认不记 raw prompt/response/reasoning/credential；失败受控、不伪装成功。

---

## 3. Resource Gate Conclusion

F07 Resource Gate：**CLOSED**。以下作为 Requirement 输入证据（不含 secret / 内部地址）：

| 项 | 冻结结论 |
|----|----------|
| Real Provider Scope | **B** |
| Protocol | **OPENAI_COMPATIBLE** |
| Authentication | **BEARER TOKEN SUPPORTED** |
| Endpoint / Credential / Model | **CONFIGURED / ACCEPTED**（运行时配置；文档不记录真实值） |
| Chat Completion | **PASS** |
| Temperature Control | **SUPPORTED** |
| Reasoning Field | **PRESENT**（不得作为业务结果） |
| Structured Output | **DIRECT_JSON PASS**（严格 normalization + Pydantic + Fail Closed） |
| Strict Single JSON Code Fence | Resource 基线允许作为第二 Parsing Tier |
| Native JSON Mode | **NOT REQUIRED**（未稳定证明） |
| Real Provider Resource | **READY** |
| Demo Provider Resource | **READY**（技术可行；本 Feature 必须实现） |
| Data Policy Minimum | **READY** |
| Mandatory Resources | **13 / 13 READY** |
| BLOCKING / Owner Input | **0 / 0** |

**禁止写入 Requirement 的 Probe 细节：** 固定 content length、固定 confidence 数值、真实 Base URL、API Key、Authorization Header。

---

## 4. Scope

### In Scope（必须）

| 部分 | 内容 |
|------|------|
| A | LLM Provider Abstraction（provider-neutral） |
| B | Deterministic Demo Provider |
| C | Real Company Provider（OpenAI-compatible chat completion） |
| D | Data Policy / Remote Dispatch Guard（可执行边界） |
| E | Structured Output：`DIRECT_JSON` + `STRICT_SINGLE_JSON_CODE_FENCE` + typed validation + Fail Closed |
| F | Reasoning/thinking 忽略策略（不进业务结果 / 默认日志） |
| G | Provider failure 受控分类表达 |
| H | Finite timeout + bounded retry（能力要求；具体数值 Design later） |
| I | Real Company Provider Integration Smoke（explicit opt-in；synthetic-only） |
| J | 配置化 endpoint / credential / model identity；未知 provider Fail Closed |
| K | 禁止隐式 Provider fallback；Policy 缺失则 Remote BLOCK |

### Out of Scope（本 Feature 不实现）

见 §17 Non-Goals。特别强调：

- **不**实现 Graph transition / Agent 编排 / 具体业务 slot flow（属 F08/F09）。
- **不**新增公共 HTTP LLM proxy endpoint。
- **不**引入 LangGraph、Redis、ASR、Embedding 调用、PostgreSQL migration。
- **不**默认允许真实生产 `USER_FREE_TEXT` 远程发送。

---

## 5. Architecture Boundary

### 5.1 LLM 可以做什么

- 自然语言理解（NLU）
- Slot extraction
- 将用户回答映射到**预定义** `allowed_values`（作为模型输出候选；是否接受由上层决定）
- 返回 **application-level confidence**（非校准统计概率、非政策置信度）
- 基于**受控业务事实**组织自然语言表达

### 5.2 LLM 不可以做什么（最高优先级）

无论 Demo 还是 Real Company Provider，均**不得**决定或直接产出为流程真值：

- `next_node` / Graph edge 创建或选择
- final / confirmed `business_id`
- candidate finalization
- Rule PASS / FAIL
- materials / locations / channels / legal basis
- 修改 Business Decision Graph
- 将 similarity 或 LLM 输出直接当作业务真值

**Graph Controller** 仍为：`current_node` + validated slots + predefined edges → **deterministic transition**。
**F07 只提供 LLM capability，不实现 Graph transition。**

### 5.3 与相邻 Feature 边界

| Feature | F07 关系 |
|---------|----------|
| **F06 Embedding** | 完全独立；不得复用 `EmbeddingProvider` 作为 LLM interface；F07 不调用 Embedding |
| **F08 Agent State + LangGraph** | F07 Provider 可被未来调用，但 F07 不引入 LangGraph / Agent State / checkpoint / workflow node |
| **F09 Missing Slot / Question / Answer mapping** | F09 做业务级集成；F07 不得提前绑定具体业务节点/事项/slot flow；可用 synthetic slot/value/confidence 作测试契约，但不得把例如 `payment_mode` 写成 F07 生产业务逻辑 |

### 5.4 Schema Validation ≠ Business Validation

| 层 | 责任 | F07 |
|----|------|-----|
| **A 结构 Validation** | JSON shape、字段类型、required、unknown extra reject | Provider/结构化处理可参与 |
| **B 业务 Validation** | value ∈ allowed_values、slot 是否当前所需、confidence 阈值等 | **上层 Agent/Controller**；Provider 不得自行推进流程 |

Provider structured call 必须允许上层提供明确 output contract / 等价约束（如未来 allowed_values 描述）。是否接受模型结果仍由上层决定。

---

## 6. LLM Provider Abstraction Requirements

1. 必须存在 **provider-neutral abstraction**。
2. 上层业务代码**不得**直接依赖：公司 HTTP endpoint、OpenAI-compatible 具体 payload 细节、某一 SDK、某一模型实现类。
3. Abstraction 必须能够：接收受控输入、返回受控结果、表达 provider failure。
4. Provider 可替换：从 Demo 切换到 Company Provider **不得**迫使修改业务流程代码；选择属于配置，实现属于 infrastructure boundary。
5. 非法 / unknown provider 配置：**Fail Closed**。
6. **禁止隐式 fallback**：Demo 失败不得自动切 Real；Real 失败不得悄悄切其它 Remote Provider。切换必须由明确配置或上层控制。
7. Provider **不访问** PostgreSQL / Business DB write / Graph repository write / Redis；不得自行查材料、地点、Rule。
8. **不新增**公共 HTTP API（如 `/llm`、`/chat`、completions proxy）。F07 为内部 capability。
9. **不要求**修改 `main.py`；`/health` 继续不依赖 Company LLM。
10. 具体接口签名、模块路径、类型名：**DESIGN LATER**。

---

## 7. Demo Provider Requirements

1. F07 **必须**实现 Deterministic Demo Provider。
2. 必须满足：**No Network / No API Key / No External Model / Deterministic / Fast / Testable**。
3. 普通 unit tests **默认**使用 Demo/Fake capability（或 Design 需要的 fake transport）。
4. 用途：abstraction 校验、structured result 校验、error-path 校验、后续 F08/F09 integration scaffold。
5. **不得**声称真实 LLM accuracy；不得用它证明真实模型效果。
6. 即使返回 slot/value/confidence，也只是模拟 LLM result；**不得**返回 `next_node` / final_business_id / Rule result / materials / locations / channels / legal basis。
7. Demo 测试数据仅 synthetic；不得因 Demo 本地而把真实生产 PII 写入 fixtures。

---

## 8. Real Company Provider Requirements

1. F07 **必须**实现 Real Company Provider。
2. Protocol 冻结为：**OpenAI-compatible chat completion capability**（Resource Gate 已证明）。是否 raw HTTP client 或 SDK：**DESIGN LATER**（Requirement **不**冻结 OpenAI SDK）。
3. Endpoint、credential、model identity 必须来自 **runtime configuration**；禁止硬编码 Base URL / API Key / Model ID 进入 production Python。
4. API Key **不得**进入：源码、tracked JSON、测试 fixture、文档、Git。
5. Credential 来源：runtime environment、ignored local configuration、或未来 secret manager。
6. **Optional startup**：基础 app import / `/health` / 普通 tests **不得**因未配置 Real LLM 而失败；仅在实际选择/调用 Real Provider 时要求完整配置。
7. **No startup network call**：启动阶段不得自动请求 `/models`、`/chat/completions` 或其它公司 API。
8. 实际调用时：**NETWORK REQUIRED**；Ordinary unit tests / Demo：**NETWORK NOT REQUIRED**。
9. 所有真实网络调用必须有 **finite timeout**；禁止无限等待。具体秒数：**DESIGN LATER**。
10. 允许 **bounded retry**；禁止无限 retry；对明显 schema invalid、业务 validation failure、authentication failure 不得无意义反复请求。具体次数/可重试状态/backoff：**DESIGN LATER**。
11. 必须有 **bounded behavior**（避免无限制处理异常巨大响应）；max tokens/bytes 是否引入：**DESIGN LATER**。
12. Company LLM down：不得导致基础应用无法启动；调用时返回受控 Provider Failure；不得包装成正常 structured success。
13. 错误不得泄露：API Key、Authorization、含 credential 的 URL、完整 prompt/response、真实 PII。
14. Provider failure **不得**伪装成「无 slot」或「低 confidence」等业务语义（Error ≠ Empty Candidate）。

### Real Smoke

1. 必须包含 Real Company Provider Integration Smoke。
2. 默认 test run **不执行**；必须 **explicit opt-in**。
3. Opt-in 但 endpoint / credential / model 缺失 → **FAIL**，不得 **SKIP** 假绿色（延续 F06 Review Fix 原则）。
4. Smoke 数据：仅 `SYNTHETIC_TEST_DATA` 以及明确允许的 `PUBLIC_BUSINESS_METADATA` / `SYSTEM_CONTROL_DATA`；禁止真实用户数据。
5. Smoke 至少验证：配置可用、鉴权、model accepted、chat completion、structured output、strict normalization、schema validation、reasoning ignored、Data Policy 允许的输入。是否每次 `GET /models`：**DESIGN LATER**。
6. Opt-in 环境变量最终名称：**DESIGN LATER**。

---

## 9. Structured Output Requirements

### 9.1 Supported Parsing Tiers（最低）

| Tier | 规则 |
|------|------|
| **DIRECT_JSON** | `trimmed message.content` 可直接 `json.loads` 成功 → 进入 schema validation |
| **STRICT_SINGLE_JSON_CODE_FENCE** | 整个 trimmed content **完全**由唯一 Markdown code fence 包裹一个 JSON payload；允许 language=`json` 或 empty；去除 fence 后再 `json.loads` |

**NOT REQUIRED：** Native JSON Mode、Tool Calling、Function Calling、Logprob、Streaming。

### 9.2 Forbidden Extraction（OUT OF SCOPE）

明确禁止：

- 从 prose 中 regex 抽 JSON / 寻找第一个 `{...}`
- 忽略前缀/后缀自然语言
- 多 JSON 择一
- 自动补引号/括号/修 malformed JSON
- yaml parse / `ast.literal_eval` / `eval`
- 二次调用 LLM 修 JSON

原则：**只要输出存在歧义 → FAIL CLOSED**。

### 9.3 Fail Closed Triggers（STRUCTURED OUTPUT FAILURE）

至少包括：empty content；malformed JSON；prose+JSON；JSON+prose；multiple JSON objects；invalid code fence envelope；schema validation failure；unknown extra fields；invalid confidence（结构层范围）；违反 caller constraints（结构层可检查部分）。

不得「尽量猜」。

### 9.4 Typed Schema Validation

- Structured JSON 必须经 typed schema validation（项目已具备 Pydantic v2 资源）。
- **Unknown extra fields 必须可 reject**（例如 `extra=forbid` 或等价）。
- 特别禁止越权字段成为合法结果：`next_node`、`business_id`、`candidate_business_id`、`rule_result`、`materials`、`locations`、`channels`、`legal_basis`、以及把 reasoning 塞进业务 schema 等。
- 具体 schema/class 名：**DESIGN LATER**。

### 9.5 Content Source

最终 response content **只允许**来自 `message.content`。不得拼接/解析 reasoning 字段。

---

## 10. Reasoning Handling

Resource Gate 已验证 Company Provider 响应可能含 `reasoning` / thinking 类字段。

冻结：

1. reasoning **不能**作为业务结果。
2. **不能**拼入 `message.content`。
3. **不能**进入 structured parser。
4. **不能**用于决定 slot/value。
5. **不能**写默认日志；完整 reasoning 默认禁止记录（即使未来 debug，也不得成为 F07 默认行为）。

---

## 11. Data Classification

Requirement 至少包含以下分类概念（具体 Enum 名 Design 可调整）：

| 分类 | 含义（示例） |
|------|----------------|
| `PUBLIC_BUSINESS_METADATA` | 已确认公开的事项名称、category、公开 allowed_values 等 |
| `SYSTEM_CONTROL_DATA` | slot name、allowed_values、output schema description、抽象 operation type（不含隐私/内部敏感） |
| `SYNTHETIC_TEST_DATA` | 明显构造的测试数据 / fake identifiers / 合成用户表达 |
| `USER_FREE_TEXT` | 真实用户自然语言 |
| `USER_PII` | 真实姓名、手机号、邮箱、详细住址、个人账户等 |
| `HIGH_SENSITIVE_IDENTITY` | 身份证号、证件号、银行卡号等 |
| `TO_CONFIRM_OR_INTERNAL` | TO_CONFIRM、internal-only、内部备注、未确认映射、内部系统字段、非公开业务数据 |
| `UNKNOWN` | 无法明确分类 |

不得仅因字段名「看起来公开」就自动认定 `PUBLIC_BUSINESS_METADATA`。

---

## 12. Remote Data Policy

Data Policy 是 F07 **正式可执行能力**，不是仅文档说明。远程 Provider 调用前必须能判断 payload 是否允许发送；实现方式：**DESIGN LATER**。

### 12.1 Remote Allow / Deny Matrix

| 分类 | Remote Company Provider |
|------|-------------------------|
| `PUBLIC_BUSINESS_METADATA` | **ALLOW**（确认为公开业务数据时） |
| `SYSTEM_CONTROL_DATA` | **ALLOW**（不含隐私/内部敏感时） |
| `SYNTHETIC_TEST_DATA` | **ALLOW**（含 real smoke） |
| `USER_FREE_TEXT`（真实生产） | **DENY**（当前） |
| `USER_PII` | **DENY** |
| `HIGH_SENSITIVE_IDENTITY` | **DENY**（F07 不设计「简单 mask 后自动允许」） |
| `TO_CONFIRM_OR_INTERNAL` | **DENY** |
| `UNKNOWN` | **DENY**（Fail Closed） |

### 12.2 Mixed Payload

payload 含多个分类时：任一 **DENY** → 整个 Remote Request **DENY**。不得只发送「看起来 ALLOW」的部分而夹带 DENY 内容。

### 12.3 Ordering

必须：**Data Policy Check → 然后 network dispatch**。禁止先调模型再事后认定不该发。

### 12.4 Missing Policy

Data Policy metadata 缺失、classification unknown、policy evaluator unavailable → Real Remote Request **BLOCK**。不得为可用性绕过 Policy。

### 12.5 Future Re-open

若未来允许真实生产 `USER_FREE_TEXT` 进入 Real Company Provider，必须有**新的明确数据策略确认**，并更新 Data Policy 与相应 Review。
**不得**仅因「公司模型在内网」自动 ALLOW。

---

## 13. Logging / Secret Policy

| 项 | 策略 |
|----|------|
| Raw prompt logging | **DEFAULT OFF**；默认不得记完整 prompt / 完整真实用户输入 / PII |
| Raw response logging | **DEFAULT OFF**；默认不得记完整模型 output / 完整 reasoning |
| Credential logging | **禁止**：API Key、Authorization Header、完整 credential |
| Safe operational logging（允许） | request id、provider identifier、非敏感 model identifier、operation、status、latency、retry count、parse/schema result、response length、error category |
| Error dump | 不得未经处理整对象 dump 导致 secret / path / prompt 泄漏 |
| Requirement / docs | 不得记录真实内部 endpoint / API Key；可用 placeholder 或 CONFIGURED |

后续可更新 `.env.example` 安全 placeholder；**永远不得** tracked real `.env`。具体 config field 名：**DESIGN LATER**。

---

## 14. Failure Semantics

F07 必须能区分至少以下失败类型（具体 Error Enum：**DESIGN LATER**）：

1. Provider not configured
2. Authentication failure
3. Network unavailable
4. Timeout
5. Provider/server error
6. Invalid response shape
7. Empty content
8. Structured parse failure
9. Schema validation failure

附加规则：

- Provider failure **受控表达**，不得伪装成功 structured result。
- 上层必须能区分：Provider failure vs 模型正常返回但业务不被接受。
- 安全：错误信息不得泄露 credential / 完整 prompt/response / PII。

---

## 15. Testing Requirements

### 15.1 Ordinary Unit Tests

- **0 real network**；不需要公司网、endpoint、API Key、真实模型。
- 默认 Demo Provider（及 Design 需要的 fake transport）。

### 15.2 Structured Parser Tests（必须覆盖）

- DIRECT_JSON pass
- single JSON fence pass
- empty / malformed reject
- prose + JSON reject
- JSON + prose reject
- multiple JSON reject
- unknown extra field reject

### 15.3 Data Policy Tests（必须覆盖）

- PUBLIC / SYSTEM_CONTROL / SYNTHETIC allow
- USER_FREE_TEXT / USER_PII / HIGH_SENSITIVE / TO_CONFIRM-internal / UNKNOWN deny
- mixed allow+deny → deny

### 15.4 Provider Boundary Tests

证明 Provider output 不能产生 `next_node` / final `business_id` / Rule result（至少 via schema extra-forbid 或等价边界）。

### 15.5 Reasoning Tests

若响应含 reasoning：最终业务 content 不得包含 reasoning；默认日志不得包含 reasoning。

### 15.6 Real Smoke

见 §8 Real Smoke；explicit opt-in；缺配置 FAIL；synthetic-only。

### 15.7 Non-requirements for Test Phase

不做 QPS / load / concurrency benchmark；不做 LLM accuracy benchmark。

---

## 16. Acceptance Criteria

| ID | Criteria |
|----|----------|
| **AC-F07-01** | 存在 provider-neutral LLM abstraction |
| **AC-F07-02** | 存在 deterministic Demo Provider（无网络、无 API Key） |
| **AC-F07-03** | 存在 Real Company Provider，能经已验证 OpenAI-compatible interface 完成 chat completion |
| **AC-F07-04** | Real Provider configuration 不硬编码 endpoint / key / model |
| **AC-F07-05** | 基础 app/import/health 不依赖 Real Provider 配置或网络 |
| **AC-F07-06** | Structured output 支持 DIRECT_JSON |
| **AC-F07-07** | Structured output 支持 strict single JSON code fence |
| **AC-F07-08** | prose+JSON、multiple JSON、malformed JSON Fail Closed |
| **AC-F07-09** | Structured data 经 typed schema validation；未知字段拒绝 |
| **AC-F07-10** | reasoning/thinking 不作为业务结果 |
| **AC-F07-11** | reasoning 不进入默认日志 |
| **AC-F07-12** | LLM Provider 无法决定 `next_node` |
| **AC-F07-13** | LLM Provider 无法决定 final `business_id` |
| **AC-F07-14** | LLM Provider 无法决定 Rule result / materials / locations / channels / legal basis |
| **AC-F07-15** | Remote 调用前执行 Data Policy |
| **AC-F07-16** | PUBLIC_BUSINESS_METADATA 可 Remote Allow |
| **AC-F07-17** | SYSTEM_CONTROL_DATA 可 Remote Allow |
| **AC-F07-18** | SYNTHETIC_TEST_DATA 可 Remote Allow |
| **AC-F07-19** | 真实 USER_FREE_TEXT 当前 Remote Deny |
| **AC-F07-20** | USER_PII Remote Deny |
| **AC-F07-21** | HIGH_SENSITIVE_IDENTITY Remote Deny |
| **AC-F07-22** | TO_CONFIRM/internal Remote Deny |
| **AC-F07-23** | UNKNOWN Remote Deny |
| **AC-F07-24** | Mixed Payload 含任意 Deny class → Remote Deny |
| **AC-F07-25** | Raw prompt logging default off |
| **AC-F07-26** | Raw response logging default off |
| **AC-F07-27** | Credential 不得进入 tracked files / logs |
| **AC-F07-28** | 普通 unit tests：0 real network |
| **AC-F07-29** | Real Company Provider smoke：explicit opt-in |
| **AC-F07-30** | Real smoke opt-in 但配置缺失：FAIL 不是 SKIP |
| **AC-F07-31** | Real smoke：synthetic-only |
| **AC-F07-32** | Provider timeout：finite |
| **AC-F07-33** | Provider retry：bounded |
| **AC-F07-34** | Provider failure 受控表达，不得伪装成功结果 |
| **AC-F07-35** | Unknown provider configuration：Fail Closed |
| **AC-F07-36** | 不新增 LLM public HTTP endpoint |
| **AC-F07-37** | 不新增 PostgreSQL migration / Redis / LangGraph / ASR |
| **AC-F07-38** | EmbeddingProvider 与 LLM Provider 保持独立 |

> **Policy Reopen 注记：** 上表原 AC-F07-01…38 **全部保留**。尤其 **AC-F07-19**（真实 USER_FREE_TEXT 当前 Remote Deny）继续描述 **Default / Non-Demo** 行为。Demo Profile 例外见文末 **Policy Reopen Requirement → AC-F07-39…58**。

---

## 17. Non-Goals

F07 **不负责 / 不实现**：

| 类别 | 排除项 |
|------|--------|
| 生产数据直送 | 真实生产用户对话默认送公司模型；USER_FREE_TEXT Remote Allow（当前） |
| 隐私工程 | PII masking pipeline；PII classifier；完整 DLP 系统 |
| 平台能力 | Prompt management platform；LLM Router；Multiple Real Providers |
| 协议扩展 | Streaming；Tool Calling；Function Calling；Native JSON Mode；Logprob |
| Agent / 流程 | LangGraph；Session memory；Redis checkpoint；Business Graph transition；Rule evaluation；Knowledge Graph querying |
| 输入模态 | ASR |
| 性能评测 | production load testing；LLM accuracy benchmark |
| 其它 | 公共 LLM HTTP proxy；PostgreSQL tables/migrations；调用 EmbeddingProvider |

---

## 18. Requirement Open Items → Technical Design Decisions

Requirement 阶段的 DESIGN LATER 项已在下方 **# Technical Design → TD-20** 逐项关闭。
**Requirement Blockers：0。**

---

## 19. Stage Status (Summary)

| 项 | 值 |
|----|-----|
| Resource Gate | **CLOSED** |
| Requirement | **CLOSED** |
| Technical Design | **FINAL / CLOSED** |
| Code | **COMPLETE** |
| Test / Review / Explanation / Commit / Push | **NOT STARTED** |

等待 Owner **授权 F07 Test**。未经授权不得进入 Test。

---

# Technical Design

## TD-1. Technical Design Status

| 字段 | 内容 |
|------|------|
| Status | **Technical Design FINAL / CLOSED**（Finalization PASS） |
| Code Readiness | Design 已关闭；**进入 Code 仍须 Owner 明确授权**（本阶段不标 Code PASS） |
| Based on | Requirement CLOSED + Resource Gate CLOSED（Scope B）+ Finalization TD-F07-01/02/03 |
| Code | NOT STARTED |
| Scope | LLM Protocol、Demo/Real Providers、Strict Structured Parser、Data Policy、Settings/Secrets、Timeout/Retry、Errors、Factory、Unit/Real Smoke Tests、Exact Paths（**17**） |
| Design Blocking Open Items | **0** |

**冻结原则：** Provider-neutral；Local-First；Policy-before-dispatch；Strict JSON Fail Closed；Demo 可测；Real 可选；无业务流程决策权。
**明确不做：** LangGraph、HTTP `/llm` proxy、DB/Redis/ASR/Embedding 耦合、OpenAI SDK、Streaming/Tool Calling/Native JSON Mode、PII mask pipeline、隐式 Provider fallback。

---

## TD-2. Compatibility Analysis（只读）

| 路径 | 结论 |
|------|------|
| `settings.py` | Two-Stage Dotenv + `KNOWN_DOTENV_KEYS` / `APPLICATION_DOTENV_KEYS`；`hide_input_in_errors=True`；无 `SecretStr` 先例 → F07 引入 `LLM_API_KEY: SecretStr \| None` |
| `embedding/provider.py` | Protocol + 实现同文件风格；错误分层；**LLM 包不得 import Embedding** |
| `pyproject.toml` | `httpx` 仅在 `[dev]`；F07 Real Provider 需升为主依赖 |
| `.env.example` | 无 LLM keys；Code 阶段追加 placeholder |
| `main.py` / `/health` | **不修改**；无 lifespan LLM 初始化 |
| F02–F06 docs | LLM 边界一致；F07 不改其语义 |

---

## TD-3. Architecture

```
Caller (future F08/F09; F07 tests)
        │
        ▼
build_llm_provider(settings)     [provider.py; NO network]
        │
        ├─ None / missing → NOT_CONFIGURED (on use)
        ├─ DEMO → DemoLlmProvider
        └─ OPENAI_COMPATIBLE → OpenAICompatibleLlmProvider
                │
                ▼
        complete(LlmRequest)  [sync]
                │
                ├─ collect classifications → evaluate_remote_policy
                │         DENY → LlmProviderError(POLICY_DENIED); 0 HTTP
                └─ ALLOW → httpx POST {base}/chat/completions
                              │
                              ▼
                         LlmResponse(content, reasoning_present, …)
                                │
                                ▼
                   parse_structured_output(content, model_type)  [structured.py]
                              DIRECT_JSON | STRICT_FENCE → typed object
                              else → STRUCTURED_PARSE_FAILED / SCHEMA_VALIDATION_FAILED
```

Hard boundary：无 `next_node` / `business_id` / Rule / 材料地点渠道；无 Embedding / Graph / DB。

---

## TD-4. Module Layout（冻结）

| 路径 | 职责 |
|------|------|
| `llm/__init__.py` | 最小 public export |
| `llm/types.py` | Request/Response/Message/Classification/Error codes |
| `llm/policy.py` | Remote policy evaluator（纯函数/确定性） |
| `llm/structured.py` | DIRECT_JSON + STRICT_SINGLE_JSON_CODE_FENCE + typed validate |
| `llm/provider.py` | `LlmProvider` Protocol + `build_llm_provider` + 公共错误边界 |
| `llm/demo.py` | Deterministic Demo Provider |
| `llm/openai_compatible.py` | Real OpenAI-compatible HTTP Provider（httpx） |

**核心自写 Python：6**（不计 `__init__.py`）。
**不新增：** `service.py` / `client.py` / `transport.py` / `exceptions.py` / `factory.py` / `config.py`（错误类型放 `types.py`；factory 放 `provider.py`）。

### Public API（`llm/__init__.py`）

导出：`LlmProvider`、`LlmRequest`、`LlmMessage`、`LlmResponse`、`LlmRole`、`DataClassification`、`LlmProviderError`、`LlmErrorCode`、`build_llm_provider`、`evaluate_remote_policy`、`parse_structured_output`、`StructuredParseError`（及必要的 PolicyDecision / ParsingMode）。
**不导出：** fence 内部 helper、HTTP retry helper、raw response mapper。

---

## TD-5. Provider Protocol（sync）

```text
LlmProvider (Protocol, runtime_checkable)
  provider_name: str
  model_id: str | None
  complete(request: LlmRequest) -> LlmResponse
```

- **同步 `complete`**：与当前 Graph/Repository/Rule 同步风格一致；F08 可用 sync LangGraph node 调用。
- **不实现** sync+async 双套。未来若需 async，可另增 `AsyncLlmProvider`（**非 F07**）。
- Protocol **不包含** `close` / `__enter__` / `__exit__`（HTTP 生命周期见 TD-16；Demo 不实现无意义 close）。
- 上层不得依赖 Base URL / Bearer / choices schema / httpx / 公司模型细节。

---

## TD-6. Request / Response Contract

### TD-6.1 Messages & Request

| 类型 | 字段 |
|------|------|
| `LlmRole` | `SYSTEM` \| `USER` \| `ASSISTANT` |
| `LlmMessage` | `role: LlmRole`；`content: str`；`classifications: frozenset[DataClassification]`（可空集合 → 按 UNKNOWN） |
| `LlmRequest` | `messages: list[LlmMessage]`；`operation: str \| None`（可选诊断标记，如 `structured_smoke`；**非业务分支**） |

**禁止字段：** `next_node`、`business_id`、decision/rule 字段。
**分类规则：** 调用方显式提供；缺失/空 → `UNKNOWN` → Remote DENY。多 message / 多分类聚合；**任一 DENY → 整请求 DENY**；不做 DLP/redaction。

### TD-6.2 Response

| 字段 | 说明 |
|------|------|
| `content: str` | 仅来自 `message.content` |
| `provider_name: str` | 如 `DEMO` / `OPENAI_COMPATIBLE` |
| `model_id: str \| None` | 配置/响应中的 model id（非敏感） |
| `reasoning_present: bool` | 仅检测字段是否存在 |
| `finish_reason: str \| None` | 可选安全 metadata |

**禁止暴露：** Authorization、response headers、raw reasoning 文本、完整 provider JSON、Base URL。

---

## TD-7. Data Classification & Policy

### TD-7.0 Trust Boundary

`DataClassification` 是调用方显式提供的 **security metadata**。
F07 Policy Evaluator **不**通过自然语言内容自动判断「这是 PII 还是 PUBLIC」。
调用方无法确定分类时必须标 `UNKNOWN` → Remote **DENY**。
未来 PII classifier / DLP 属独立 Feature，**非 F07**。

### TD-7.1 Enum（冻结名）

`PUBLIC_BUSINESS_METADATA` · `SYSTEM_CONTROL_DATA` · `SYNTHETIC_TEST_DATA` · `USER_FREE_TEXT` · `USER_PII` · `HIGH_SENSITIVE_IDENTITY` · `TO_CONFIRM_OR_INTERNAL` · `UNKNOWN`

### TD-7.2 Matrix

| ALLOW | DENY |
|-------|------|
| PUBLIC_BUSINESS_METADATA | USER_FREE_TEXT |
| SYSTEM_CONTROL_DATA | USER_PII |
| SYNTHETIC_TEST_DATA | HIGH_SENSITIVE_IDENTITY |
| | TO_CONFIRM_OR_INTERNAL |
| | UNKNOWN |

空 classification collection → 视为 `{UNKNOWN}` → DENY。

### TD-7.3 Evaluator

`evaluate_remote_policy(classifications: Iterable[DataClassification]) -> PolicyDecision`

`PolicyDecision`：`allowed: bool`；`denied_categories: frozenset[...]`；`reason_code: str`（如 `POLICY_DENIED`）。
**禁止**携带 raw prompt / PII / secret。

### TD-7.4 Enforcement（defense-in-depth）

`OpenAICompatibleLlmProvider.complete`：**HTTP dispatch 之前必须**调用 evaluator；DENY → `LlmProviderError(POLICY_DENIED)` 且 **0 HTTP calls**、**0 sleep calls**、**0 retry attempts**。
Demo Provider：不访问网络；不强制同一 remote deny 语义，但使用同一 `LlmRequest` 契约。

---

## TD-8. Structured Output Parser（`structured.py`）

### TD-8.1 API

`parse_structured_output(content: str, model_type: type[BaseModel]) -> StructuredParseResult`

Result 含：`value: BaseModel`；`mode: ParsingMode`（`DIRECT_JSON` \| `STRICT_SINGLE_JSON_CODE_FENCE`）。
失败抛 `StructuredParseError`（带 `LlmErrorCode` 等价 code）。

Parser **只解析**；不构建 JSON system prompt（Real Smoke / 调用方自备）。不依赖 Graph/Business/Rule。不硬编码 slot/value/confidence。

### TD-8.2 DIRECT_JSON

1. `text = content.strip()`；空 → `EMPTY_CONTENT`
2. `json.loads(text)`；失败 → 进入 fence 尝试（非立即 malformed，除非 fence 也失败）
3. 结果必须是 `dict`；list/str/number/null → `NON_OBJECT_JSON`

### TD-8.3 STRICT_SINGLE_JSON_CODE_FENCE（line-based）

仅当 DIRECT 失败后：

1. `lines = text.splitlines()`（允许末尾换行已由 strip 处理）
2. 第一行精确：`` ```json `` 或 `` ``` ``
3. 最后一行精确：`` ``` ``
4. 中间行拼接为 payload；中间若再出现 `` ``` `` → `AMBIGUOUS_ENVELOPE`
5. 若存在非 fence 的前后缀行 → `AMBIGUOUS_ENVELOPE`（等价 prose+fence）
6. `json.loads(payload.strip())` 必须得 `dict`，否则 `MALFORMED_JSON` / `NON_OBJECT_JSON`

**禁止：** `re.search` / findall 抽中间 JSON；修 JSON；yaml/`literal_eval`/`eval`；二次 LLM 修复。

### TD-8.4 Extra fields

在 `model_validate` 前：`payload.keys() - model.model_fields.keys()` 非空 → `SCHEMA_VALIDATION_FAILED`（unknown extra）。
F07 仅 field-name contract（不处理复杂 alias）。然后 `model_validate`；业务 allowed_values / threshold → **非** generic parser（F09/Controller）。

### TD-8.5 Fail codes（冻结）

`EMPTY_CONTENT` · `MALFORMED_JSON` · `AMBIGUOUS_ENVELOPE` · `NON_OBJECT_JSON` · `SCHEMA_VALIDATION_FAILED`

---

## TD-9. Demo Provider（`demo.py`）

| 项 | 设计 |
|----|------|
| Network / Key | 无 |
| Deterministic | 是 |
| Constructor | `response_content: str`（默认通用 synthetic JSON 字符串）；可选 `failure: LlmErrorCode \| None` 模拟受控失败 |
| Behavior | `complete` 返回固定 `LlmResponse` 或抛 `LlmProviderError` |
| 禁止 | `payment_mode` / `DEMO_SS_001` / 社保业务分支；禁止返回 next_node/business_id/Rule/材料地点渠道 |

---

## TD-10. Real Provider（`openai_compatible.py`）

| 项 | 冻结 |
|----|------|
| Protocol | OPENAI_COMPATIBLE |
| HTTP | **raw httpx**（不引入 openai/dashscope/litellm/instructor） |
| Endpoint | `base_url.rstrip("/") + "/chat/completions"`；禁止 `/v1/v1/...` |
| Auth | `Authorization: Bearer <api_key>` |
| Payload | `{model, messages[{role,content}], temperature=0}`；messages 由 `LlmRequest` 映射；**不擅自加业务 system prompt** |
| GET /models | **生产 complete 路径不调用**；Real Smoke 亦不要求 |
| Policy | dispatch 前强制 evaluate |
| Response map | 校验 JSON → `choices[0].message.content`；缺字段 → `INVALID_RESPONSE`；空白 content → `EMPTY_CONTENT` |
| Reasoning | 检测 `reasoning` / `reasoning_content` / `thinking` **键是否存在** → `reasoning_present`；**不读内容** |
| Raw body | 不默认保存；异常不嵌完整 body |
| Temperature | 固定请求 `temperature=0`（Resource 已 SUPPORTED）；不暴露为业务 API |

### TD-10.1 Retry

| | |
|--|--|
| `LLM_MAX_RETRIES` 默认 | **1**（额外重试次数） |
| Range | **0–3** |
| `total_attempts` | **`1 + max_retries`**（initial 不算 retry） |
| Retryable | connect/transport error；Timeout；HTTP **429**；HTTP **5xx** |
| Non-retryable | **401/403**（HTTP calls=1，即使 max_retries>0）；其它明确 4xx；`NOT_CONFIGURED`；`POLICY_DENIED`（0 HTTP / 0 sleep）；structured/schema/业务失败（**HTTP 成功后的 parser 失败不进 HTTP retry loop**） |
| Backoff Settings | **不新增** `LLM_RETRY_BACKOFF_SECONDS` |
| Retry-After header | **F07 不实现** |
| Log | attempt + error_code + status；无 prompt/response/Authorization |

**Deterministic bounded backoff（冻结）：**

在第 `retry_index` 次 retry **之前** sleep：

```text
delay_seconds = min(0.25 * (2 ** retry_index), 2.0)
```

| retry_index | 含义 | delay |
|-------------|------|-------|
| 0 | 首次失败后的第 1 次 retry 前 | **0.25s** |
| 1 | 第 2 次 retry 前 | **0.50s** |
| 2 | 第 3 次 retry 前 | **1.00s** |

`max_retries ≤ 3` 时实际 delay 不超过 **1.00s**；`2.0` 为防御上限。

**Sleep testability（冻结）：** `OpenAICompatibleLlmProvider` 接受可选 `sleep_fn: Callable[[float], None] | None = None`；默认 `time.sleep`。Unit tests 注入 zero-delay fake（或等价），**不得**真实等待 0.25/0.5/1.0s。不新增文件。

**Attempt 上限示例：** `max_retries=0` → 最多 1 HTTP；`=1` → 最多 2；`=3` → 最多 4。Tests 必须断言 `call_count` 不超过上限。

**Real Smoke：** 使用 Provider 正式 bounded retry；测试文件外层不再套 retry。

### TD-10.2 HTTP status → error

| Status / 条件 | Code | retryable |
|---------------|------|-----------|
| 401 / 403 | `AUTHENTICATION_FAILED` | false |
| 429 | `RATE_LIMITED` | true |
| 5xx | `SERVER_ERROR` | true |
| 其它 4xx | `INVALID_REQUEST` | false |
| Timeout | `TIMEOUT` | true |
| Connect error | `NETWORK_UNAVAILABLE` | true |
| JSON/shape 坏 | `INVALID_RESPONSE` | false |

禁止笼统 `except Exception → UNKNOWN` 吞掉一切。

---

## TD-11. Error Model（`types.py`）

`LlmProviderError(Exception)`：`code: LlmErrorCode`；`retryable: bool`；`http_status: int \| None`；`message: str`（安全）。
**禁止**字段：raw body、raw request、API Key、Authorization。

`LlmErrorCode`：`NOT_CONFIGURED` · `UNKNOWN_PROVIDER` · `POLICY_DENIED` · `AUTHENTICATION_FAILED` · `NETWORK_UNAVAILABLE` · `TIMEOUT` · `RATE_LIMITED` · `SERVER_ERROR` · `INVALID_REQUEST` · `INVALID_RESPONSE` · `EMPTY_CONTENT` · `STRUCTURED_PARSE_FAILED` · `SCHEMA_VALIDATION_FAILED`
（Parser 细节 code 可映射到 `STRUCTURED_PARSE_FAILED` 子类字段或 `StructuredParseError.code`。）

---

## TD-12. Factory（`provider.py`）

`build_llm_provider(settings: Settings) -> LlmProvider`

| `settings.llm_provider` | 行为 |
|-------------------------|------|
| `None` | 返回内部 `_NotConfiguredProvider`：`complete()` → `NOT_CONFIGURED`；**无网络 / 无 fallback / 不返回 fake success**；**不 public export** |
| `DEMO` | `DemoLlmProvider()`（默认 synthetic content） |
| `OPENAI_COMPATIBLE` | base_url/api_key/model_id 任一缺失 → `_NotConfiguredProvider`（**Settings 不 fail**）；齐全 → `OpenAICompatibleLlmProvider(...)` |

**Unknown provider：**

1. **Primary：** Settings 层 `Literal["DEMO","OPENAI_COMPATIBLE"] | None` validation **fail-fast** 拒绝非法值（常规路径不会把 unknown 交给 factory）。
2. **Defensive：** factory 若仍收到非预期字符串 → raise `LlmProviderError(UNKNOWN_PROVIDER)` Fail Closed（防御性，非常规 happy path）。

- Factory **禁止联网** / load model。
- **禁止** Real↔Demo 隐式 fallback。
- `_NotConfiguredProvider` 仅为 controlled failure object；**不得**列入 `llm/__init__.py` public API。

---

## TD-13. Settings / Secrets

### TD-13.1 Application fields

| Env | Field | Type | Default | Notes |
|-----|-------|------|---------|-------|
| `LLM_PROVIDER` | `llm_provider` | `Literal["DEMO","OPENAI_COMPATIBLE"] \| None` | `None` | blank→None；非法值 Settings fail-fast |
| `LLM_MODEL_ID` | `llm_model_id` | `str \| None` | `None` | blank→None；不猜命名 |
| `LLM_BASE_URL` | `llm_base_url` | `str \| None` | `None` | 见校验 |
| `LLM_API_KEY` | `llm_api_key` | `SecretStr \| None` | `None` | blank→None；`hide_input_in_errors` |
| `LLM_TIMEOUT_SECONDS` | `llm_timeout_seconds` | `float` | **60.0** | **1.0–300.0** |
| `LLM_MAX_RETRIES` | `llm_max_retries` | `int` | **1** | **0–3** |

加入 `KNOWN_DOTENV_KEYS` 与 `APPLICATION_DOTENV_KEYS` / `_APPLICATION_SETTINGS_FIELDS`。不破坏既有 POSTGRES/TEST_DATABASE_URL/EMBEDDING keys。

**不把** `LLM_*` 设为“必须一起出现”的全局约束（与 Embedding 三件套不同）：允许仅配部分字段；Real 完整性在 factory/use 时检查 → Local-First `/health` 不受影响。

### TD-13.2 `LLM_BASE_URL` validation

- strip；empty→None
- scheme ∈ `{http, https}`（**允许内网 http**）
- host required
- **禁止** username/password、query、fragment
- **允许** path（如 `/v1`）
- 不发网络探测

### TD-13.3 `RUN_LLM_REAL`

**仅 test process env**；**不**进入 Settings；**不**写入 `.env.example` 应用配置段。
`== "1"` → 跑 Real Smoke；否则 skip；opt-in 缺配置 → `pytest.fail`。

### TD-13.4 `.env.example`（Code 阶段）

```env
# F07 LLM (Optional — omit for Local-First /health)
# LLM_PROVIDER=
# LLM_MODEL_ID=
# LLM_BASE_URL=
# LLM_API_KEY=
# LLM_TIMEOUT_SECONDS=60
# LLM_MAX_RETRIES=1
```

无真实 endpoint/key/model。

---

## TD-14. Logging

默认：**RAW PROMPT OFF / RAW RESPONSE OFF / REASONING OFF / CREDENTIAL OFF**。
允许：`provider`、`operation`、`status`、`latency_ms`、`attempt`、`error_code`、`reasoning_present`、`response_length`、policy `decision=deny` + denied category names。
最小 logger：`logging.getLogger("gov_service_agent")`；不新建 logging 子系统。

---

## TD-15. Dependencies

| 包 | 决策 |
|----|------|
| `httpx` | **main dependencies**：`httpx>=0.27,<1`（对齐现有 `>=0.24` 风格并收紧下限） |
| `dev` 中 httpx | 可保留或与 main 重复无害；Design：**main 增加后，dev 可去掉重复声明**（Code 执行） |
| openai / dashscope / litellm / instructor | **不添加** |
| langgraph / sentence-transformers | **不添加/不 import** |
| Pydantic v2 | 已有 |

pytest marker 新增：`llm_real: opt-in tests requiring company LLM`。

---

## TD-16. HTTP Client Lifecycle（Finalization TD-F07-02）

`OpenAICompatibleLlmProvider(..., client: httpx.Client | None = None, sleep_fn: ... = None)`

| 情况 | Ownership | Lifetime |
|------|-----------|----------|
| **External** `client` 注入 | **CALLER** | Provider **使用但不 close**；用于 MockTransport / DI / 连接复用 |
| **Internal**（`client is None`） | **PROVIDER CALL SCOPE** | 在单次 `complete()` 内用 `with httpx.Client(...)` **创建并自动 close**；同一次 `complete()` 内所有 retry attempts **复用该同一 Client**；返回或抛异常后必须关闭 |

**冻结要点：**

- Provider Protocol **不含** `close` / context manager。
- **不**长期持有需上层 close 的 owned Client；避免忘记 close 泄漏。
- 不修改 FastAPI lifespan；无 global singleton；无 DI framework；无 connection-pool manager。
- Resource leak risk：**LOW / CONTROLLED**。
- 未来 long-lived pooled client / lifespan / shared transport：**非 F07**（Deferred）。

---

## TD-17. Test Plan

### NEW

| 文件 | 覆盖 |
|------|------|
| `tests/test_llm_policy.py` | ALLOW×3；DENY×5；empty；mixed |
| `tests/test_llm_structured.py` | DIRECT；fence json/empty-lang；prose±JSON；multi；malformed；non-object；empty；extra；schema fail/pass；nested fence fail |
| `tests/test_llm_demo.py` | no network；deterministic；inject content；failure mode；无业务字段；无 key |
| `tests/test_llm_openai_compatible.py` | MockTransport：200；reasoning_present；401/403（**不 retry**）；429/500 retry + **fake sleep**；timeout；connect；invalid JSON；missing choices/message；empty content；**policy deny → call_count=0 且 sleep_count=0**；missing config → 0 calls；retry bound call_count；Bearer（fake key）；repr/error 无 secret |
| `tests/integration/test_llm_real.py` | `RUN_LLM_REAL` gate；Settings 配置；synthetic SYSTEM+SYNTHETIC only；complete+parse test-only schema；**不** GET /models；不外层套 retry |

### MODIFY

| 文件 | 覆盖 |
|------|------|
| `tests/test_settings.py` | 默认无 LLM；provider values；**unknown provider Settings reject**；timeout/retry range；blank→None；invalid URL；URL credentials reject；unknown dotenv key；SecretStr 错误路径不泄漏 |

**普通 pytest：0 company network。** Real smoke：explicit opt-in；缺配置 FAIL。

---

## TD-18. Exact Planned Paths（Finalization TD-F07-01 → **17**）

| # | Path | 类别 |
|---|------|------|
| 1 | `src/gov_service_agent/llm/__init__.py` | Production NEW |
| 2 | `src/gov_service_agent/llm/types.py` | Production NEW |
| 3 | `src/gov_service_agent/llm/policy.py` | Production NEW |
| 4 | `src/gov_service_agent/llm/structured.py` | Production NEW |
| 5 | `src/gov_service_agent/llm/provider.py` | Production NEW |
| 6 | `src/gov_service_agent/llm/demo.py` | Production NEW |
| 7 | `src/gov_service_agent/llm/openai_compatible.py` | Production NEW |
| 8 | `src/gov_service_agent/settings.py` | Production MODIFY |
| 9 | `.env.example` | Production MODIFY |
| 10 | `pyproject.toml` | Production MODIFY |
| 11 | `tests/test_llm_policy.py` | Test NEW |
| 12 | `tests/test_llm_structured.py` | Test NEW |
| 13 | `tests/test_llm_demo.py` | Test NEW |
| 14 | `tests/test_llm_openai_compatible.py` | Test NEW |
| 15 | `tests/integration/test_llm_real.py` | Test NEW |
| 16 | `tests/test_settings.py` | Test MODIFY |
| 17 | `docs/features/F07-llm-provider-data-policy.md` | Feature Doc |

**计算式：** `7 NEW prod + 3 MODIFY prod/config + 5 NEW tests + 1 MODIFY test + 1 Feature = 17`
**第 18 个 planned path：NO。** 禁止为凑数新增文件。Code 若需第 18+ path → **STOP** + `F07 DESIGN DEVIATION REQUIRED`。
**核心 Python：6**（不计 `__init__.py`）。禁止自行新增 `factory.py` / `exceptions.py` / `client.py` / `transport.py` / `config.py` / `service.py`。

**不修改：** `main.py`、DB、alembic、compose、其它 Feature docs、Embedding 包。

---

## TD-19. Non-Goals（Design 再确认）

不修改 `main.py`；无 `/llm` HTTP；无 migration/Redis/LangGraph/ASR；不调用 Embedding；不默认 ALLOW 生产 USER_FREE_TEXT；不记录真实 `<company-llm-base-url>` / key / model 于文档。
Generic parser **不**含 allowed_values / confidence threshold；**不** hardcode `payment_mode` / `self_payment` 于生产模块。

---

## TD-20. OI-F07-D01 … D11 Decisions

| ID | Decision | Reason | Impact |
|----|----------|--------|--------|
| **D01** | **raw httpx**；不引入 OpenAI SDK | 仅需 POST chat/completions + Bearer + timeout/retry | Real Provider = httpx |
| **D02** | **sync `complete` only** | 对齐现有同步业务栈；F08 sync node 可调用；避免双 API | 无 async Provider |
| **D03** | default **60.0s**；range **1–300** | Resource Gate 曾 ReadTimeout；thinking 模型需余量 | Settings field |
| **D04** | max_retries default **1**；range **0–3**；retry 429/5xx/timeout/connect；**deterministic backoff** `min(0.25*(2**retry_index), 2.0)`；可选 `sleep_fn` | 有界、可测、无新 Settings | Mock 断言 call_count + zero-delay sleep |
| **D05** | Settings：`LLM_*` 六键；smoke：`RUN_LLM_REAL` process-only | 与 F06 `RUN_EMBEDDING_REAL` 同模式 | `.env.example` 无 RUN_ |
| **D06** | 模块/类型名见 TD-4/5/6/11；**17 paths** | 清晰且不碎文件 | 6 核心文件 |
| **D07** | `policy.py` 纯函数 `evaluate_remote_policy`；Real Provider 强制调用 | defense-in-depth | 0-call / 0-sleep tests |
| **D08** | **F07 不引入** max_tokens / max response bytes 硬限制 | Demo 阶段足够 | **DEFERRED** 非 blocker |
| **D09** | httpx → **main dependencies** `>=0.27,<1` | 生产 Real Provider 不可仅靠 dev extra | pyproject Code 改 |
| **D10** | Real smoke / production **不** GET /models | Resource 已验证；避免每请求双 RTT | 少网络 |
| **D11** | `.env.example` 六键 placeholder；无真实值 | 安全 | Code 更新 |

**Design Blocking Open Items：0**
**Deferred（非阻塞）：** D08 max bytes/tokens；未来 Async Provider；未来 USER_FREE_TEXT 政策重开；long-lived pooled httpx client；Retry-After parsing。

---

## TD-21. Finalization Record（TD-F07-01 / 02 / 03）

| ID | Decision |
|----|----------|
| **TD-F07-01** | Final Scope **17 paths**；无第 18 planned path |
| **TD-F07-02** | External client = CALLER ownership；Internal client = per-`complete()` context manager；Protocol 无 close；retry 复用同 call Client；leak risk LOW/CONTROLLED |
| **TD-F07-03** | Backoff `min(0.25*(2**retry_index), 2.0)`；无 backoff Settings；无 Retry-After；`sleep_fn` 默认可测 |

---

## TD-22. Design Acceptance Checklist

| 项 | 状态 |
|----|------|
| Module Layout / Protocol / Request-Response | **FROZEN** |
| Classification trust boundary + Remote Policy + policy-before-dispatch | **FROZEN** |
| Demo + Real + httpx + Settings/Secrets | **FROZEN** |
| Timeout/Retry+Backoff/Error/Reasoning/Parser/Extra reject | **FROZEN** |
| Factory / NotConfigured / Unknown Settings+defensive / No fallback | **FROZEN** |
| Client lifecycle（per-call internal / inject external） | **FROZEN** |
| Unit + Mock + Real smoke + Security tests | **FROZEN** |
| Exact paths | **FROZEN（17）** |
| Blocking Open Items | **0** |

---

## TD-23. Code Entry Gate

Technical Design = **FINAL / CLOSED**。

**进入 Code 仍须 Owner 明确授权。**

Code 阶段严格按 TD-18 的 **17 paths** 实施；需要第 18+ path → STOP + Design Deviation；不得调用真实 LLM（直至 Test 授权 Real Smoke）。

---

## TE-1. Test Status

| 字段 | 内容 |
|------|------|
| Test | **PASS** |
| Code | **COMPLETE** |
| Design Deviations | **NONE** |
| Production Test Fixes（TF-F07-*） | **0** |
| Unresolved BLOCKING | **0** |
| Unresolved MAJOR | **0** |
| Unresolved MINOR | **0** |

## TE-2. Test Environment

| 项 | 值 |
|----|-----|
| Branch | `develop` |
| HEAD | `4a8bb61c1a9618e010352ece36ac72d5be0aabfc` |
| Python env | conda `govagent` |
| `httpx` | `0.28.1`（main dependency） |
| `pydantic` | `2.13.4` |
| `pip install -e ".[dev]"` | PASS |
| Import Gate（无 network / 无 Key） | PASS |
| `RUN_LLM_REAL` in Settings / dotenv keys / `.env.example` | **NO** |

## TE-3. Unit Evidence（Phase A）

```text
pytest tests/test_settings.py tests/test_llm_policy.py
      tests/test_llm_structured.py tests/test_llm_demo.py
      tests/test_llm_openai_compatible.py -v
→ 160 passed（0 company network）
```

覆盖：Settings LLM_*、Remote Data Policy、Strict Structured Parser、Demo Provider、Fake HTTP Real Provider（policy-before-dispatch、retry/backoff、reasoning isolation、secret safety、client lifecycle）。

## TE-4. No-Network Full Evidence

```text
RUN_LLM_REAL unset
pytest -v
→ 319 passed, 13 skipped, 1 warning
```

Warning：Starlette `TestClient` + `httpx` deprecation（既有依赖告警，非 F07 回归）。
`tests/integration/test_llm_real.py` 真实请求用例默认 **SKIP**。
默认 full suite **0** 公司 LLM 网络。

## TE-5. Real Provider Smoke Evidence

| 项 | 结果 |
|----|------|
| Formal config | `LLM_*` **CONFIGURED**（Test Stage process mapping from gate vars if needed；未写文件） |
| Opt-in | `RUN_LLM_REAL=1` |
| Command | `pytest tests/integration/test_llm_real.py -v` → **2 passed** |
| Missing-config semantics | opt-in 缺配置 → **FAIL**（非 SKIP） |
| Endpoint / Credential / Model | CONFIGURED / CONFIGURED / CONFIGURED·ACCEPTED |
| Data Policy | PASS（仅 `SYSTEM_CONTROL_DATA` + `SYNTHETIC_TEST_DATA`） |
| USER_FREE_TEXT / USER_PII / HIGH_SENSITIVE / TO_CONFIRM | **未发送** |
| HTTP completion | PASS |
| Content non-empty | YES；length **78** |
| Parsing mode | **DIRECT_JSON** |
| Structured parse + Pydantic | PASS |
| `reasoning_present` | **True**（未读取 reasoning content） |
| Extra GET `/models` | **NO** |
| Extra manual retry loop | **NO** |
| Post-smoke | `RUN_LLM_REAL` cleared |

## TE-6. Gates

| Gate | 结果 |
|------|------|
| `python -m compileall src/gov_service_agent tests` | PASS |
| `pip check` | PASS |
| `git diff --check` | PASS |
| UTF-8 / trailing whitespace（F07 paths） | PASS |
| Security Gate（无真实 endpoint/key/model/F07_GATE_* in production） | PASS |
| Final path count | **17**（无第 18 path） |
| git add / commit / push | **NO** |

## TE-7. Test Findings

| ID | Severity | Notes |
|----|----------|-------|
| — | — | **无 TF-F07 Production Fix**；Unit / Fake / Real Smoke / Gates 全部满足 Test PASS 条件。 |

---

## F07 Code Explanation

面向后续开发者的代码阅读说明：解释 **代码实际如何运行**，而不是重复 Requirement 条文。

### EX-1. 一句话定位

F07 解决的是：**如何让 Agent 以统一、安全、可测试的方式调用 LLM**。

F07 **不是**：“让 LLM 决定政务事项”。

核心关系：

- **LLM Provider** 负责模型能力（请求/响应、策略、解析）
- **Graph / Rule / Controller** 负责业务真值（路径、规则、确认后的 `business_id`）

### EX-2. 整体调用图

```text
Caller / Future Agent (F08+)
        |
        v
    LlmRequest  (+ explicit DataClassification metadata)
        |
        v
 build_llm_provider(settings)
     /                   \
    /                     \
 DemoLlmProvider    OpenAICompatibleLlmProvider
 (local, no net)              |
                              v
                    evaluate_request_remote_policy
                              |
                    DENY -----+----- ALLOW
                     |                 |
                     v                 v
              POLICY_DENIED      httpx POST
                                 /chat/completions
                                       |
                                       v
                                 Company LLM
                                       |
                                       v
                                  LlmResponse
                                  (content only;
                                   reasoning_present bool)
                                       |
                                       v
                          parse_structured_output(...)
                                       |
                                       v
                              typed Pydantic Model
                                       |
                                       v
                         Future Controller / F09
                         (business validation)
                                       |
                                       v
                    F04 Business Decision Graph
                    (deterministic; not LLM)
```

**Structured Parser 不会决定：** `next_node`、`business_id`、Rule PASS/FAIL、材料/地点/渠道/法律依据。

### EX-3. 模块职责

| Module | 职责 |
|--------|------|
| `llm/types.py` | Provider-neutral 输入/输出类型；`DataClassification`；`LlmErrorCode` / `LlmProviderError` / `StructuredParseError` |
| `llm/policy.py` | Remote Data Policy（确定性；无网络/DB/LLM） |
| `llm/structured.py` | 严格 JSON 解析 + extra-field 检查 + Pydantic `model_validate` |
| `llm/provider.py` | `LlmProvider` Protocol；`build_llm_provider` factory；私有 `_NotConfiguredProvider` |
| `llm/demo.py` | 本地确定性 Demo/Fake capability |
| `llm/openai_compatible.py` | 真实公司 OpenAI-compatible HTTP（httpx）；**policy-before-dispatch**；retry/timeout；response map |
| `llm/__init__.py` | 最小 Public API 导出（**不**导出 `_NotConfiguredProvider`） |
| `settings.py` / `.env.example` | 可选 `LLM_*` 配置；`SecretStr`；Local-First 启动 |
| `pyproject.toml` | 主依赖 `httpx`；pytest marker `llm_real` |

### EX-4. `types.py`：契约与 Classification Trust Boundary

主要类型：

| 类型 | 作用 |
|------|------|
| `LlmMessage` | `role` + `content` + `classifications`（显式安全元数据） |
| `LlmRequest` | 非空 `messages` + 可选 `operation` |
| `LlmResponse` | `content`、`provider_name`、`model_id`、`reasoning_present`、`finish_reason` |
| `DataClassification` | 八类安全分类枚举 |
| `LlmErrorCode` / `LlmProviderError` | 受控 Provider 失败（无 raw body / key / Authorization） |
| `ParsingMode` / `StructuredParseError` | 解析模式与受控解析失败 |

**为什么 classification 与 content 分开？**

- `content`：发给模型（或 Demo）的文本
- `classifications`：**调用方显式声明**的 security metadata
- **不是**模型自己判断，也 **不是** F07 根据字符串猜 PII/PUBLIC
- 无法判断 → 使用 `UNKNOWN` → Remote **DENY**（fail closed）

### EX-5. Data Classification（八类）

| Classification | 含义（简述） |
|----------------|--------------|
| `PUBLIC_BUSINESS_METADATA` | 可公开的业务元数据（非个人隐私） |
| `SYSTEM_CONTROL_DATA` | 系统控制指令/合成控制提示（非用户隐私） |
| `SYNTHETIC_TEST_DATA` | 明确构造的测试/合成数据 |
| `USER_FREE_TEXT` | 真实用户自然语言 |
| `USER_PII` | 用户个人身份相关信息 |
| `HIGH_SENSITIVE_IDENTITY` | 高敏感身份类数据 |
| `TO_CONFIRM_OR_INTERNAL` | 待确认或内部敏感信息 |
| `UNKNOWN` | 未声明 / 空集合 / 无法判断 |

### EX-6. Remote ALLOW / DENY

| Classification | Remote Company LLM |
|----------------|--------------------|
| `PUBLIC_BUSINESS_METADATA` | **ALLOW** |
| `SYSTEM_CONTROL_DATA` | **ALLOW** |
| `SYNTHETIC_TEST_DATA` | **ALLOW** |
| `USER_FREE_TEXT` | **DENY**（当前） |
| `USER_PII` | **DENY** |
| `HIGH_SENSITIVE_IDENTITY` | **DENY** |
| `TO_CONFIRM_OR_INTERNAL` | **DENY** |
| `UNKNOWN` | **DENY** |

**Mixed Payload：** 任一 message 带 DENY 分类 → **整个** `LlmRequest` Remote DENY（不会过滤掉 DENY 消息后继续发送）。

**为什么 `USER_FREE_TEXT` 当前 DENY？**
不是公司模型技术上不能处理，而是 F07 只完成了技术接入，**尚未获得**生产真实用户文本远程发送策略授权。Data Policy 当前 fail closed；未来政策确认后须单独重开 Feature/策略变更。

### EX-7. Policy 调用链（Real Provider 内防御）

```text
OpenAICompatibleLlmProvider.complete(request)
  → evaluate_request_remote_policy(request)
      → collect_request_classifications (empty/missing → UNKNOWN)
      → evaluate_remote_policy
  → if DENY:
        log safe metadata (provider/operation/denied_categories)
        raise LlmProviderError(POLICY_DENIED)
        # NO retry loop, NO sleep, NO client.post
  → else:
        map payload → HTTP (see EX-9)
```

**为什么 Policy 放在 Provider 内（defense-in-depth）？**
不能只依赖 F08/F09“记得先查政策”。即使直接实例化 `OpenAICompatibleLlmProvider`，`complete()` 在 HTTP 前仍强制 Policy。

Unit 证据：Policy Denial → **HTTP call_count = 0**，**sleep = 0**。

Demo Provider **不强制**同一 remote deny 语义（本地、无网络）；Design 已冻结。

### EX-8. Demo Provider 调用链与作用

```text
LLM_PROVIDER=DEMO
  → build_llm_provider → DemoLlmProvider
  → complete(request)
  → 固定 content（默认 {"status":"demo"}）或受控 LlmProviderError
  → LlmResponse
```

特点：No Network / No API Key / No External Model / Deterministic。

用途：普通 Unit Test、F08/F09 scaffold、离线开发、failure-path 注入。

**不是**真实 LLM accuracy 模拟器；**不能**证明模型理解效果。

### EX-9. Real Provider 调用链

```text
Settings (LLM_*)
  → build_llm_provider
  → OpenAICompatibleLlmProvider
  → complete(request)
  → Data Policy (EX-7)
  → map roles/content; temperature=0
  → httpx POST {base_url}/chat/completions
       Authorization: Bearer <secret>
  → validate JSON / choices[0].message.content
  → detect reasoning keys → reasoning_present only
  → LlmResponse
  → (caller) parse_structured_output(content, schema)
```

公司 Resource Gate 已验证 OpenAI-compatible `chat/completions` + Bearer。F07 使用 **httpx**，不引入 OpenAI SDK：当前只需 completion、Bearer、timeout、retry、response parsing；不需要 streaming / tool calling / native JSON mode。

**不要在文档中记录真实 Base URL / API Key / 公司 Model ID**；仅使用环境变量名：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL_ID`。

### EX-10. Settings / Provider Selection / SecretStr

| Env | Field | 默认 | 说明 |
|-----|-------|------|------|
| `LLM_PROVIDER` | `llm_provider` | `None` | blank→None；仅 `DEMO` / `OPENAI_COMPATIBLE` |
| `LLM_MODEL_ID` | `llm_model_id` | `None` | blank→None |
| `LLM_BASE_URL` | `llm_base_url` | `None` | http(s)、host 必填；禁 userinfo/query/fragment；允许 path（如 `/v1`） |
| `LLM_API_KEY` | `llm_api_key` | `None` | `SecretStr`；blank→None |
| `LLM_TIMEOUT_SECONDS` | `llm_timeout_seconds` | `60.0` | 1.0–300.0 |
| `LLM_MAX_RETRIES` | `llm_max_retries` | `1` | 0–3 |

`LLM_PROVIDER=None` 时应用仍可启动（Local-First `/health`）。

Factory：

| `llm_provider` | 行为 |
|----------------|------|
| `None` | `_NotConfiguredProvider` → `complete()` → `NOT_CONFIGURED` |
| `DEMO` | `DemoLlmProvider` |
| `OPENAI_COMPATIBLE` + 齐全 config | Real Provider |
| `OPENAI_COMPATIBLE` 缺 URL/Key/Model | `_NotConfiguredProvider`（**不**让 startup 崩溃） |
| unknown | Settings fail-fast；factory 防御性 `UNKNOWN_PROVIDER` |

**无** Real↔Demo 隐式 fallback。

**为何不用 `return None`？**
`_NotConfiguredProvider` 仍满足 Provider Contract；调用 `complete()` 时稳定受控失败，无 network / fake success / fallback。私有类，不进入 `__init__.py` public API。

**SecretStr：** 默认 `repr` / ValidationError（`hide_input_in_errors=True`）不显示明文；仅在构造 `Authorization: Bearer ...` 时 `get_secret_value()`。

`RUN_LLM_REAL`：**不是** Settings 字段；仅 process env 控制真实 integration smoke。

### EX-11. Structured Output 流程

```text
message.content
   ↓
strip；空 → EMPTY_CONTENT
   ↓
DIRECT_JSON?  (json.loads 整个 text)
   |-- YES → must be JSON object (dict)
   |-- NO
         ↓
STRICT_SINGLE_JSON_CODE_FENCE?
   (first line exact ```json or ``` ;
    last line exact ``` ;
    middle 不得再含 ```)
   |-- YES → payload → json.loads → object
   |-- NO → FAIL CLOSED
   ↓
extra-field check (payload keys ⊆ model fields)
   ↓
model_validate
   ↓
StructuredParseResult(value, mode)
```

**DIRECT_JSON：** 直接 `json.loads`；`[]` / `"abc"` / `123` / `true` / `null` 即使 loads 成功也 **REJECT**（必须 object）。

**Strict Fence：** 允许整段 content 仅为一个 fence（language=`json` 或 empty）。禁止 prefix/suffix prose、多 fence、嵌套 fence。

**为何不宽松抽 JSON？**
若允许“好的，答案是：{...}”再 regex 抠出，程序无法区分说明文字、多候选、异常内容。F07 **宁可失败，也不猜**（Fail Closed）。

**Reject cases：** prose+JSON；JSON+prose；multiple JSON；malformed JSON；non-object JSON；unknown extra field；schema validation failure；empty content。

**Pydantic：** generic parser 只保证结构；`allowed_values` / slot 业务阈值 / confidence 业务阈值 → **F09/Controller**，不属于 `structured.py`。

Generic 示例（synthetic / test-only）：

```json
{"name": "demo", "score": 0.9}
```

Real Smoke 使用的 `slot`/`value`/`confidence` 仅为 **TEST-ONLY SYNTHETIC**，不是 production 业务 contract。

### EX-12. Reasoning

Resource/Test 已观察到公司响应可能 `reasoning_present=True`。

F07：

- **只检测** message 是否存在键：`reasoning` / `reasoning_content` / `thinking`
- **不读、不拼接、不日志、不结构化解析** reasoning 内容
- 可解析输出 **仅** `message.content`
- 业务真值仍由 Graph / Rule / Controller 决定；reasoning ≠ 业务接口

### EX-13. HTTP Response Validation / Retry / Client

HTTP 成功路径校验：top-level JSON object → `choices` 非空 → `choices[0].message` → `content` 为非空字符串。异常 → `INVALID_RESPONSE`；空白 content → `EMPTY_CONTENT`（不向上冒裸 `KeyError`）。

**Retry：**

```text
Attempt 1
  → retryable failure?
       NO  → raise controlled error
       YES → sleep min(0.25 * 2^retry_index, 2.0)
Attempt 2 ...
  → until total_attempts = 1 + max_retries
```

| Retryable | Non-retryable |
|-----------|---------------|
| connect/transport | 401 / 403 |
| timeout | 其它 4xx |
| 429 | `POLICY_DENIED` |
| 5xx | `NOT_CONFIGURED` |
| | invalid response / structured / schema（HTTP 已成功后） |

默认 `max_retries=1`；最大 3。delay 序列：`0.25` → `0.50` → `1.00`（cap 2.0）。

**JSON/schema 失败不触发 HTTP retry：** parser 在 `complete()` **之后**由调用方执行；F07 不会偷偷再问模型“修一下 JSON”。

**Client lifecycle：**

| 模式 | Ownership | 行为 |
|------|-----------|------|
| External `httpx.Client` 注入 | **CALLER** | Provider **不** close；适合 MockTransport / 复用 |
| Internal（未注入） | Provider per-`complete()` | `with httpx.Client(...)`；initial+retry **同一** client；结束自动 close |

Protocol **无** `close()`：描述的是 LLM capability，不是 HTTP client；Demo 不应为实现 Real 而假装 close。

### EX-14. Error Mapping / Safety / Logging

| 情况 | Error code |
|------|------------|
| 401 / 403 | `AUTHENTICATION_FAILED` |
| 429 | `RATE_LIMITED` |
| 5xx | `SERVER_ERROR` |
| 其它 4xx | `INVALID_REQUEST` |
| Timeout | `TIMEOUT` |
| Connect/Transport | `NETWORK_UNAVAILABLE` |
| Policy Deny | `POLICY_DENIED` |
| Missing / incomplete config | `NOT_CONFIGURED` |
| Unknown provider (defensive) | `UNKNOWN_PROVIDER` |
| Bad HTTP JSON/shape | `INVALID_RESPONSE` |
| Empty content | `EMPTY_CONTENT` |
| Structured / schema | `STRUCTURED_PARSE_FAILED` / `SCHEMA_VALIDATION_FAILED` |

`LlmProviderError` 仅安全 `code` / `retryable` / 可选 `http_status` / safe `message`。不暴露 raw prompt、raw body、Authorization、API Key、reasoning。

默认日志：

- Raw Prompt Logging = **OFF**
- Raw Response Logging = **OFF**
- Reasoning content Logging = **OFF**

允许安全 metadata（按代码实际）：`provider`、`operation`、`status`/`decision`、`latency_ms`、`attempt`、`error_code`、`http_status`、`reasoning_present`、`response_length`、`denied_categories`。

### EX-15. 测试与 Real Smoke

**普通 `pytest`：** 不访问公司模型。`tests/integration/test_llm_real.py` 真实用例需 `RUN_LLM_REAL=1`，默认 **SKIP**。Fake HTTP 使用 `httpx.MockTransport` + fake endpoint/token/model。

**Real Smoke：**

```text
RUN_LLM_REAL=1
  → 检查正式 LLM_*（缺配置 → FAIL，不是 SKIP）
  → OPENAI_COMPATIBLE Provider
  → Synthetic request（SYSTEM_CONTROL + SYNTHETIC_TEST_DATA only）
  → Policy ALLOW → real HTTP → content → structured parse → Pydantic
```

Opt-in 缺配置必须 **FAIL**：开发者已明确要跑真实模型，自动 SKIP 会造成假绿色。

**Test Evidence（已冻结）：**

| Evidence | Result |
|----------|--------|
| Phase A | **160 / 160 PASS** |
| Default Full | **319 passed / 13 skipped / 1 known warning** |
| Real Provider Smoke | **PASS** |
| Real Structured | **DIRECT_JSON PASS** |
| Policy Denial | HTTP **0** / sleep **0** |
| compileall / pip check | **PASS** |

**Known warning：** Starlette `TestClient` + `httpx` deprecation——既有依赖告警，**非** F07 regression；Explanation/Review Fix **不**为此改代码。

### EX-16. Review 结论与 INFO（非 defect）

| 项 | 状态 |
|----|------|
| F07 Review | **PASS** |
| BLOCKING / MAJOR / MINOR | **0 / 0 / 0** |
| INFO | **3** |
| Review Fix | **NOT REQUIRED** |

| ID | 说明 |
|----|------|
| RI-F07-001 | Real Provider 调用期间内存持有 API key 用于 Authorization；符合当前设计（Settings 仍为 SecretStr） |
| RI-F07-002 | Fence 中间若极端出现 triple-backtick 子串 → fail closed；符合严格策略 |
| RI-F07-003 | 未对所有非 Timeout/Transport 异常 broad-catch；符合设计；上层仍须遵守安全日志纪律 |

### EX-17. 与 F06 / F08 / F09 / Graph / Rule / Knowledge 的边界

| 能力 | 关系 |
|------|------|
| **F06 Embedding** | 语义检索找方向；与 F07 **独立** Provider；LLM **不**调用 EmbeddingProvider |
| **F08 Agent/LangGraph** | 编排层；Node 调用 F07 Provider；F07 **不知道** LangGraph state |
| **F09 Slot/Question/Mapping** | 用户回答 → F07 结构化候选 → F09/Controller 校验 slot/allowed_values/confidence → Graph 确定性推进 |
| **F04 Decision Graph** | 业务路径真值；LLM **不**直接 `next_node` |
| **Rule Engine** | Terminal Candidate 后的确定性规则；LLM **不**产生 Rule PASS |
| **Knowledge Graph** | `business_id` 确认后查 materials/locations/channels/legal basis；LLM 最多把受控事实组织成人话，**不生成事实** |

**目标调用链：**

```text
User → F08 Agent → F07 LLM NLU → structured candidate signal
  → F09 Controller validation → F04 Business Decision Graph
  → deterministic transition → (confirm) business_id → Knowledge facts
```

### EX-18. 推荐阅读与调试顺序

**代码阅读顺序：**

1. `types.py` — 契约与分类
2. `policy.py` — Remote 卡点
3. `provider.py` — Protocol / factory / NotConfigured
4. `demo.py` — 最简单 complete 路径
5. `openai_compatible.py` — Policy + HTTP + retry + map
6. `structured.py` — Fail Closed 解析
7. `settings.py` — 可选配置与 SecretStr
8. Unit tests — 行为规格
9. `tests/integration/test_llm_real.py` — opt-in Real 契约

**LLM 调用失败排查（先别改 Graph）：**

1. `LLM_PROVIDER`
2. Real config 是否完整
3. Data Policy 是否 DENY（先看 classification metadata；**不要**为通测试把 `USER_FREE_TEXT` 改 ALLOW）
4. Network / Timeout
5. HTTP status
6. response shape
7. content empty
8. structured parser（prose+JSON / multi / malformed → **不要**加 loose regex）
9. Pydantic schema
10. 上层业务 validation

**Provider Error ≠ 业务结果：**
`LlmProviderError` ≠ low confidence ≠ no slot ≠ no candidate。未来 Agent 必须区分 **资源/策略/协议失败** 与 **业务理解结果**。

### EX-19. Security Checklist（开发者）

- 不提交真实 API Key
- 不打印 Authorization
- 不记录 raw prompt / raw response / reasoning 内容
- 默认不允许 `USER_FREE_TEXT` remote
- `UNKNOWN` fail closed
- Real Smoke 仅 synthetic / system-control classifications
- 文档示例不使用 `.env` 中的真实 secret
- 不把真实 Base URL / 公司 Model ID 写入仓库文档

### EX-20. Explanation Acceptance / Commit Gate

Explanation 阶段 **未**修改 Production / Tests；**未**运行 pytest / Real Smoke；**未**读取 `.env`；**未**安装依赖；**未** git add/commit/push。

Feature Scope 仍严格 **17 paths**（本 Explanation 仅更新已存在的本 Feature 文档）。

**Commit / Push = NOT STARTED** — 须等待 Owner 单独授权。

> **历史注记（Policy Reopen）：** 上表与本 EX-20 表述保留原 Explanation 当时快照。Original F07 随后已 Commit/Push **COMPLETE** @ `3b68726…`。下文为 Policy Reopen Requirement Addendum，不改写上述历史正文。

---

# Policy Reopen Requirement（Addendum）

| 字段 | 内容 |
|------|------|
| Reopen ID | F07-POLICY-REOPEN |
| Stage | **REQUIREMENT — COMPLETE** |
| Requirement Finalization | **NOT REQUIRED** |
| Resource Gate | **READY**（prior） |
| Authorization | Owner 正式授权：F07 POLICY REOPEN — REQUIREMENT |
| Policy Approval Status | **APPROVED** |
| Policy Approval Source | **OWNER_EXPLICIT_DEMO_POLICY_DECISION** |
| Based on | Original F07 CLOSED + Policy Reopen Resource Gate READY + Owner Demo Policy Decision |
| Document change scope | 仅本 Feature Doc；**不**修改 Code-Reading / Production / Tests |
| Next | Technical Design Reopen — **须等待 Owner 明确授权**；本阶段 **STOP** |

## PR-1. Reopen 背景与原因

Original F07 Remote Data Policy 采用 **fail-closed**：

- Remote Provider 遇到真实 `USER_FREE_TEXT` → **DENY**
- 核心历史 Acceptance Criterion：**AC-F07-19**（保留，不删除、不改号、不改写为「过去一直允许」）

F09 需要 `LlmAnswerMapper` 将用户自然语言（例如「平时接零活，没有固定单位」）映射到受控枚举（例如 `employment_type = other_flexible_employment`）并返回 `confidence`。F09 **不拥有**修改 F07 Policy 的权限（见 **OI-F09-DP-001**，本阶段 **不关闭** 该 OI；仅记录其为本次 Reopen 来源之一）。

因此 F12 E2E 被 **RG-F12-006** 阻塞。本次 Reopen 正式落地 Owner 已批准的 Demo 阶段数据策略例外。

## PR-2. Owner Demo Policy Decision（正式记录）

当前项目处于 **Demo 阶段**。

**允许：** 将用户在政务 Agent 中输入的**业务信息**发送给公司指定的远程 LLM 进行业务处理。Owner 明确允许的业务分类包括：

| Classification | Demo Profile Remote |
|----------------|---------------------|
| `PUBLIC_BUSINESS_METADATA` | ALLOW |
| `SYSTEM_CONTROL_DATA` | ALLOW |
| `SYNTHETIC_TEST_DATA` | ALLOW |
| `USER_FREE_TEXT` | ALLOW |
| `USER_PII` | ALLOW |
| `HIGH_SENSITIVE_IDENTITY` | ALLOW |
| `TO_CONFIRM_OR_INTERNAL` | ALLOW |

以上属于 **Demo 用户业务数据**。

**明确不属于授权范围：** 系统 Secret / Credential。以下内容**不得**进入 LLM Prompt / `messages` / business payload：

- `LLM_API_KEY`
- Authorization Header / Bearer Token
- 数据库密码 / Redis 密码
- 系统访问令牌
- Secret / Credential / 其它运行时认证凭据

Transport Authentication（例如 HTTP `Authorization: Bearer …`）属于 Provider 传输认证，**不是**业务 payload。

## PR-3. Reopen 目标（不是全局取消 Policy）

目标 **不是** 全局永久取消 F07 Remote Policy，也 **不是** 永久全局 `USER_FREE_TEXT` ALLOW。

目标是新增一个 **显式 Demo Remote Data Policy Profile**：

| Profile 语义 | 行为 |
|--------------|------|
| **DEFAULT / NON-DEMO** | 保持原 F07 Remote **fail-closed** 行为完全兼容 |
| **EXPLICIT DEMO** | 允许 Owner 已批准的 Demo 用户业务数据进入**当前显式配置的** Remote LLM Provider |
| `UNKNOWN` | **始终 DENY**（含 Demo Profile 开启时） |
| Secret / Credential | **永不**进入 LLM business payload |

字段名 / enum 名 / Settings 键名 **不在 Requirement 冻结**（留给 Technical Design）。

## PR-4. 核心概念分离（硬 Requirement）

1. **Demo Policy Profile ≠ `DemoLlmProvider`**
   Demo Profile 只决定哪些业务数据允许 Remote Dispatch。F12 后续必须能使用真实 `OPENAI_COMPATIBLE` Provider。

2. **`OPENAI_COMPATIBLE` 仅是 Provider protocol / adapter type**
   不得因协议类型自动获得 Demo data approval。放行必须来自显式 Policy Profile。

3. **显式选择原则**
   Demo Profile 必须由 Deployment / Owner **显式选择**。禁止根据 URL、域名、IP、localhost、公司域名 substring、或「模型部署在公司服务器」隐式切换。

4. **Profile 不得由 content 推断**
   不得根据 `user_text` / prompt / 关键词自动选择 Profile。Profile 必须来自明确 deployment/runtime configuration。

5. **禁止万能 bypass**
   不得通过 `TRUSTED=true` / `ALLOW_ALL=true` / `SKIP_POLICY=true` 等万能开关绕过 Policy。必须表达明确 Policy Profile。

## PR-5. Default Profile 行为兼容（硬 Requirement）

未显式选择 Demo Profile 时，原 F07 Policy **必须保持行为兼容**，尤其：

| Classification | Default / Non-Demo |
|----------------|--------------------|
| `USER_FREE_TEXT` | **DENY**（与 **AC-F07-19** 一致） |
| `USER_PII` | **DENY** |
| `HIGH_SENSITIVE_IDENTITY` | **DENY** |
| `TO_CONFIRM_OR_INTERNAL` | **DENY**（按原 F07） |
| `UNKNOWN` | **DENY** |
| `PUBLIC_BUSINESS_METADATA` | 按原行为（ALLOW） |
| `SYSTEM_CONTROL_DATA` | 按原行为（ALLOW） |
| `SYNTHETIC_TEST_DATA` | 按原行为（ALLOW） |

不得为了 Demo 改变 Default Policy。

**缺失 Demo Profile 时不得自动放行：** 不得因 `AppEnv=dev`、`provider=OPENAI_COMPATIBLE`、存在 API key、endpoint 可访问等隐式进入 Demo Allow。

**无效 / 未识别 Profile：** 永远不得扩大数据权限（不得导致 Demo Allow）。校验方式 / 启动失败 / fallback 细节留给 TD，但需求层保证 **fail closed on invalid profile（权限不扩大）**。

## PR-6. Demo Allowed Classification Set（冻结）

在**显式 Demo Profile** 下，以下 classifications 允许 Remote Dispatch：

- `PUBLIC_BUSINESS_METADATA`
- `SYSTEM_CONTROL_DATA`
- `SYNTHETIC_TEST_DATA`
- `USER_FREE_TEXT`
- `USER_PII`
- `HIGH_SENSITIVE_IDENTITY`
- `TO_CONFIRM_OR_INTERNAL`

**`UNKNOWN` → Remote DENY**（即使 Demo Profile 已开启）。原因：`UNKNOWN` ≠ Owner 已批准的用户业务数据。

**missing / empty / unresolved classification：** 若现有 contract 归入 `UNKNOWN`，继续 **fail closed**；不得因 Demo 自动 ALLOW。

**Multi-label：**

- 请求中所有 classification 均属于 Demo Allow Set → Policy **MAY ALLOW**
- 任意 classification 为 `UNKNOWN` 或其它未明确允许类别 → **DENY**

## PR-7. Policy Evaluation Contract（冻结）

1. Real Provider 必须在实际 **HTTP dispatch 前**完成 Remote Policy evaluation。
2. Policy **DENY** → **0 HTTP calls**。
3. Demo Profile **ALLOW** → 才允许进入 Provider Transport。
4. **禁止** HTTP 调用后再判断 policy。
5. Policy 决策必须 **本地、确定性、可测试**；**不得**使用 LLM 判断 ALLOW/DENY。
6. `PolicyDecision.ALLOW` 只表示允许发送，**不**表示 HTTP/认证/模型/schema 成功；现有 Provider 失败语义保持。

## PR-8. Secret / Credential Boundary（冻结）

当前 `DataClassification` **无** `SECRET` / `CREDENTIAL` 类别。本次 **不要求**新增完整 Secret classification / DLP 系统。

但必须保证：Provider authentication material（API Key、Authorization、Bearer Token）只属于 **Transport Authentication**，不得进入：

- `LlmRequest.messages`
- prompt / system message / user message
- business metadata

## PR-9. F09 / F10 / Graph / Rule 不变边界（硬 Requirement）

### F09 Payload

继续保持最小化：`system instructions` + `required_slot` + `allowed_values` + `user_text`。
不得因 Policy Reopen 要求发送 full `AgentState` / conversation history / checkpoint / `orchestration_trace` / `request_id` / `session_id`。

### F09 Output Validation

Policy Reopen **仅**决定数据能否 Remote Dispatch，**不**改变：

- `mapped_value ∈ allowed_values`（membership）
- `confidence` 满足 `MappingPolicy.min_confidence`（当前 **0.80**）

### F09 Explanation Side Route

例如「灵活就业是什么意思？」仍不得被当作 slot selection；不得写 slot、推进 Business Graph、产生 candidate、改变 rule status。Policy Reopen **不得**破坏该 invariant。

### LLM 权限边界（不变）

即使 Demo 允许更多用户业务数据交给 LLM，LLM **仍不得**决定：

- `next_node` / graph edge
- `candidate_business_id` / `business_id` / `confirmed_business_id`
- Rule result / eligibility result

LLM 仍只负责：自然语言理解、slot extraction、受控 allowed-value mapping、confidence、controlled explanation / wording。

### Business Graph / Rule / F10

不得改变 Business Decision Graph 确定性推进权、Rule Engine 终审权、F10 final matter confirmation authority。

### Demo Profile Scope

仅影响 F07 Remote Data Policy。不得影响 Embedding、RAG、Business Graph、Rule Engine、Knowledge、Redis、PostgreSQL、Session API、F10 confirmation。

## PR-10. Capability / Destination / DLP（OUT OF SCOPE）

Demo 阶段 **不要求**：

- operation-by-operation capability allowlist（`operation` 仍保留为 request metadata；未来 Production 可扩展）
- destination registry / approved endpoint database
- DLP engine / PII redaction / PII 自动识别
- enterprise trust infrastructure / capability approval registry
- endpoint ID registry / provider certificate registry / remote destination DB

显式 Demo Policy Profile + 显式配置的 Remote Provider，已足够表达 Owner 对当前 Demo 部署的批准。

## PR-11. Infrastructure / Dependency / Real LLM

| 项 | Requirement |
|----|-------------|
| New infrastructure | **NO**（Redis / PostgreSQL / pgvector / Neo4j / Kafka / RabbitMQ / 新 HTTP 服务 / 新 policy service 均不得引入） |
| New third-party package | **NO**（使用现有依赖；若 TD 发现必须新增须重新报告 Owner） |
| Real Company API for Requirement / TD | **NO** |
| Deterministic unit / mock-transport tests | **YES**（Code/Test 应可零真实网络验证 Default DENY 与 Demo ALLOW） |
| Real LLM before F12 resumes（RG-F12-004） | **YES**（在 Reopen Code/Test/Review 完成后、回到 F12 Resource Gate 前真实验证；**不属于** Requirement 阶段） |

## PR-12. F12 Golden Path Compatibility（语义；本阶段不运行）

本 Reopen 必须支持后续真实路径：

```
用户：「平时接零活，没有固定单位」
→ F09 LlmAnswerMapper
→ F07 Remote Policy（Demo Profile）允许 USER_FREE_TEXT
→ Real OPENAI_COMPATIBLE Provider
→ structured mapping：other_flexible_employment + confidence
→ F09 local membership + confidence threshold
→ 仅 ACCEPTED 才交给 F04
```

F07 Requirement **不要求**本阶段实际运行该链。

## PR-13. Historical AC Preservation

- **不删除**任何原 `AC-F07-*`
- **不改号**、不改写历史语义
- **AC-F07-19** 保留为：Original Default / Non-Demo 下真实 `USER_FREE_TEXT` Remote **DENY**
- 新增 AC 从 **AC-F07-39** 起（原最大编号为 **AC-F07-38**）

## PR-14. Policy Reopen Acceptance Criteria（新）

| ID | 语义 |
|----|------|
| **AC-F07-39** | Default / Non-Demo Remote Policy 与原 F07 行为兼容（含 `USER_FREE_TEXT` DENY 等） |
| **AC-F07-40** | 必须显式配置 Demo Policy Profile 才能启用 Demo remote business-data allow |
| **AC-F07-41** | Demo Profile 允许：`PUBLIC_BUSINESS_METADATA` / `SYSTEM_CONTROL_DATA` / `SYNTHETIC_TEST_DATA` / `USER_FREE_TEXT` / `USER_PII` / `HIGH_SENSITIVE_IDENTITY` / `TO_CONFIRM_OR_INTERNAL` |
| **AC-F07-42** | `UNKNOWN` 在 Demo Profile 下仍 Remote DENY |
| **AC-F07-43** | missing / empty / unresolved classification 不得因 Demo 自动 ALLOW（归入 UNKNOWN → DENY） |
| **AC-F07-44** | multi-label 请求只要出现未批准分类必须 DENY |
| **AC-F07-45** | Policy DENY 必须在 HTTP dispatch 前发生，且 0 HTTP calls |
| **AC-F07-46** | `OPENAI_COMPATIBLE` 不自动代表 Demo approval（仅 protocol） |
| **AC-F07-47** | 不得通过 URL / IP / hostname 推断 Demo approval |
| **AC-F07-48** | Demo Policy 必须显式配置；禁止万能 bypass flag（如 TRUSTED/ALLOW_ALL/SKIP_POLICY） |
| **AC-F07-49** | API key / Authorization 不得进入 Prompt / messages |
| **AC-F07-50** | F09 mapping payload 继续保持最小化 |
| **AC-F07-51** | F09 `mapped_value` membership validation 保持 |
| **AC-F07-52** | F09 confidence threshold validation 保持（`min_confidence = 0.80`） |
| **AC-F07-53** | LLM 不获得任何 Business Decision Authority（无 next_node / business_id / confirmed_business_id / rule outcome） |
| **AC-F07-54** | Default 与 Demo Profile 行为均可由 deterministic unit tests 验证 |
| **AC-F07-55** | 本次 Reopen 不新增基础设施 |
| **AC-F07-56** | 本次 Reopen 不新增第三方依赖 |
| **AC-F07-57** | F09 explanation side-route invariant 不得被破坏 |
| **AC-F07-58** | 真实 F12 / Company LLM runtime 验证（含 RG-F12-004）在 Reopen Code/Test/Review 完成后进行；不属于 Requirement 阶段 |

## PR-15. Non-Goals（Policy Reopen）

本次 Reopen **不负责 / 不实现**：

| 类别 | 排除项 |
|------|--------|
| Trust 基础设施 | 生产级 destination registry；approved endpoint DB；certificate registry；URL/IP/hostname trust |
| 隐私工程 | DLP；PII 自动识别；身份证/手机号/姓名/地址 redaction |
| Capability | operation-by-operation allowlist；capability approval registry |
| 万能绕过 | `TRUSTED=true` / `ALLOW_ALL` / `SKIP_POLICY`；全局永久 `USER_FREE_TEXT` ALLOW |
| Provider 混淆 | 将 Demo Policy 等同于 `DemoLlmProvider`；将 `OPENAI_COMPATIBLE` 当作 trusted |
| 业务权 | 改变 Business Graph / Rule Engine / F10 / F11 / F12；给 LLM business decision authority |
| 其它系统 | Embedding / RAG 行为变更；Redis / PostgreSQL / 新服务 / 新依赖 |
| 本阶段执行 | 配置真实 LLM；调用真实 Company API；运行 pytest；关闭 OI-F09-DP-001 |

## PR-16. Open Decisions

### Frozen at Requirement（业务已冻结）

1. `UNKNOWN` = DENY（含 Demo Profile）
2. Default / Non-Demo policy 行为不变
3. Demo business classifications allow set（PR-6）
4. Secret/Credential 不进入 prompt / messages
5. Demo Profile 必须显式启用
6. 不做 capability allowlist
7. 不做复杂 destination registry
8. 不做 DLP / PII redaction
9. 禁止 URL trust 与万能 bypass
10. LLM 无 Business Decision Authority；F09/F10/Graph/Rule 边界不变

### Deferred to Technical Design（非 Material Requirement 开放项）

- Profile enum / 名称 / Settings 字段名
- policy 函数签名与 provider wiring
- profile 默认表示与 invalid profile 校验实现细节
- 精确 production paths / test organization
- path count

**Material Requirement Open Decisions：0。**
因此 **Requirement Finalization = NOT REQUIRED**。

## PR-17. Cross-Feature Notes

| 项 | 状态 |
|----|------|
| OI-F09-DP-001 | **保持 OPEN**；本阶段不关闭。Code/Test/Review 完成并验证后再更新 |
| RG-F12-004 | **PENDING**（真实 LLM runtime/config） |
| RG-F12-006 | **REQUIREMENT COMPLETE / IMPLEMENTATION PENDING** |
| F12 Resource Gate | **仍 BLOCKED** |

## PR-18. Requirement Self-Review Checklist

| # | 检查项 | 结果 |
|---|--------|------|
| 1 | Owner Demo Policy 准确记录 | PASS |
| 2 | 无全局永久 USER_FREE_TEXT ALLOW | PASS |
| 3 | Default Policy 保持 | PASS |
| 4 | UNKNOWN = DENY | PASS |
| 5 | USER_PII / HIGH_SENSITIVE Demo ALLOW 与 Owner 一致 | PASS |
| 6 | Secret 与业务数据区分 | PASS |
| 7 | 无 URL trust | PASS |
| 8 | 无万能 TRUSTED bypass | PASS |
| 9 | Provider protocol ≠ trust | PASS |
| 10 | 无 LLM business authority | PASS |
| 11 | 未提前写 TD 实现细节 | PASS |
| 12 | Non-Goals 完整 | PASS |
| 13 | 新 AC 可测试 | PASS |
| 14 | 旧 AC 未删除/改号；AC-F07-19 保留 | PASS |

## PR-19. Stage Gate

| 项 | 值 |
|----|-----|
| Policy Reopen Requirement | **COMPLETE** |
| Requirement Finalization | **NOT REQUIRED** |
| Technical Design Reopen | **COMPLETE**（见下文；当时本表曾写 READY FOR OWNER AUTHORIZATION） |
| Technical Design Finalization | **NOT REQUIRED** |
| Confirm / Code / Test / Review / F12 | **禁止自动进入**（须 Owner 明确授权 Confirm→Code） |

---

# Policy Reopen Technical Design

| 字段 | 内容 |
|------|------|
| Reopen ID | F07-POLICY-REOPEN |
| Stage | **TECHNICAL DESIGN — COMPLETE** |
| TD Finalization | **NOT REQUIRED** |
| Requirement prior | **COMPLETE**（AC-F07-39…58；Material Open Decisions = 0） |
| Requirement changed by TD | **NO** |
| Authorization | Owner 正式授权：F07 POLICY REOPEN — TECHNICAL DESIGN |
| Based on | Requirement Addendum PR-1…PR-19 + 真实 Production import graph / call chain |
| Document change scope | 仅本 Feature Doc；**不**修改 Production / Tests / Code-Reading / F09 docs |
| Next | Confirm → Code — **READY FOR OWNER CONFIRMATION**；本阶段 **STOP** |

## PTD-1. Current Real Call Chain（重建）

真实符号（以代码为准，非历史报告猜测）：

```
Settings（llm_* fields）
  → build_llm_provider(settings: object)          # provider.py
       ├─ llm_provider is None / incomplete Real → _NotConfiguredProvider
       ├─ llm_provider == "DEMO"                 → DemoLlmProvider()
       └─ llm_provider == "OPENAI_COMPATIBLE"    → OpenAICompatibleLlmProvider(
              base_url, api_key, model_id,
              timeout_seconds, max_retries
            )                                    # openai_compatible.py（lazy import）

OpenAICompatibleLlmProvider.complete(request: LlmRequest)
  → evaluate_request_remote_policy(request)      # policy.py；当前仅 1 参数
       → collect_request_classifications(request)
       → evaluate_remote_policy(classifications)
       → PolicyDecision(allowed, denied_categories, reason_code)
  → if not allowed → LlmProviderError(POLICY_DENIED)；0 HTTP
  → else HTTP POST {base}/chat/completions
       headers.Authorization = Bearer {api_key}   # 不在 messages
       payload.messages = role + content only
```

**当前 policy 输入维度：** 仅 `messages[].classifications`（聚合）。**不**读 content / operation / Settings / URL。

## PTD-2. Import Graph（放置约束）

| Module | Imports |
|--------|---------|
| `settings.py` | **不** import `llm.*`（当前） |
| `llm/types.py` | pydantic only（叶节点） |
| `llm/policy.py` | `llm.types` only |
| `llm/demo.py` | `llm.types` only |
| `llm/openai_compatible.py` | `llm.policy`, `llm.types`, httpx |
| `llm/provider.py` | `llm.demo`, `llm.types`；**lazy** import `openai_compatible` |
| `llm/__init__.py` | re-export 上述 |

**结论：** `RemoteDataPolicyProfile` 放在 **`llm/types.py`**（与 `DataClassification` 同层）。
`settings.py` **允许**单向 `from gov_service_agent.llm.types import RemoteDataPolicyProfile`（`llm` **永不** import `settings` → **无环**）。
**禁止**把 Profile enum 放进 `settings.py` 再让 `policy.py` 反向依赖 Settings。

## PTD-3. Technical Decisions（D12…；原最大 D11）

| ID | Decision | Maps AC |
|----|----------|---------|
| **D12** | 新增 `class RemoteDataPolicyProfile(str, Enum)`于 `llm/types.py`；values：`DEFAULT`、`DEMO_APPROVED`；默认语义 = `DEFAULT`。禁止 bool bypass（`trusted`/`allow_all`/`skip_policy`） | AC-39,40,46,48 |
| **D13** | Settings：`llm_remote_data_policy_profile: RemoteDataPolicyProfile = RemoteDataPolicyProfile.DEFAULT`；env：`LLM_REMOTE_DATA_POLICY_PROFILE`；加入 `KNOWN_DOTENV_KEYS` / `APPLICATION_DOTENV_KEYS` / `_APPLICATION_SETTINGS_FIELDS`；`.env.example` 增加 placeholder 注释行 | AC-40,48,55 |
| **D14** | Invalid / 未识别 profile 字符串：**Settings fail-fast**（与 `LLM_PROVIDER` 未知值同模式：normalize upper → typed enum / after-validator；错误不得静默切 DEMO，也不得扩大权限） | AC-40,48 |
| **D15** | 传递链：`Settings.llm_remote_data_policy_profile` → `build_llm_provider` → `OpenAICompatibleLlmProvider(..., remote_data_policy_profile=...)` 存为实例字段 → `complete` 调用 `evaluate_request_remote_policy(request, profile=self._remote_data_policy_profile)`。无 global mutable / 无 `os.environ` / 无 `get_settings()` in policy | AC-40,45,54 |
| **D16** | Signature 冻结：`evaluate_remote_policy(classifications, profile: RemoteDataPolicyProfile = RemoteDataPolicyProfile.DEFAULT) -> PolicyDecision`；`evaluate_request_remote_policy(request, profile: RemoteDataPolicyProfile = RemoteDataPolicyProfile.DEFAULT) -> PolicyDecision`。纯函数；默认参数仅保证未传 profile 时 = DEFAULT（与 unset Settings 同义） | AC-39,45,54 |
| **D17** | DEFAULT allow-set = **复用**现有 `_REMOTE_ALLOW`（不复制第二份 DEFAULT 表） | AC-39 |
| **D18** | DEMO allow-set = frozenset{`PUBLIC_BUSINESS_METADATA`,`SYSTEM_CONTROL_DATA`,`SYNTHETIC_TEST_DATA`,`USER_FREE_TEXT`,`USER_PII`,`HIGH_SENSITIVE_IDENTITY`,`TO_CONFIRM_OR_INTERNAL`}；**不含** `UNKNOWN` | AC-41 |
| **D19** | `collect_request_classifications` 行为保持：empty/missing message classifications → `UNKNOWN`；`evaluate_*`：`classifications ⊆ allow_set(profile)` → ALLOW，否则 DENY 且 `denied_categories = classifications - allow_set` | AC-42,43,44 |
| **D20** | Policy **先于** HTTP；DENY → 现有 `LlmProviderError(LlmErrorCode.POLICY_DENIED)` + **0 HTTP**；ALLOW 仅表示可进入 transport，**≠** HTTP/auth/parse 成功 | AC-45,58 |
| **D21** | **`LlmRequest` = NO CHANGE**；`operation` 保留为 metadata；本轮 policy **不**读 operation；**不加** capability allowlist | AC-50；Non-Goal |
| **D22** | **F09 Production = NO CHANGE**（`LlmAnswerMapper` / explanation / classifications / payload / membership / `min_confidence=0.80` / side-route 全部不动；禁止把 `USER_FREE_TEXT` 伪造成其它类） | AC-50…53,57 |
| **D23** | `DemoLlmProvider` / `_NotConfiguredProvider` = **NO CHANGE**；Profile **不**参与 provider selection；仅注入 `OpenAICompatibleLlmProvider`。正交：`OPENAI_COMPATIBLE+DEFAULT` 与 `OPENAI_COMPATIBLE+DEMO_APPROVED` 均合法 | AC-46,39 |
| **D24** | Test：扩展 `tests/test_llm_policy.py` matrix；扩展 `tests/test_llm_openai_compatible.py`（DEFAULT deny 0-call；DEMO USER_FREE_TEXT allow MockTransport 1-call；DEMO USER_PII allow；DEMO UNKNOWN 0-call）；扩展 `tests/test_settings.py`（default/valid/invalid）。**无**真实 API。F09 tests：**regression-only 运行、不修改** | AC-54,58 |
| **D25** | **无**新 infra / **无**新第三方依赖 / **无** DB·Redis migration / **无** destination registry / **无** DLP / **无** URL trust | AC-47,55,56 |
| **D26** | `PolicyDecision` / `reason_code`（`POLICY_ALLOWED`/`POLICY_DENIED`）= **NO CHANGE**；不新增 reason codes | — |

**Material TD Open Decisions：0** → TD Finalization = **NOT REQUIRED**。

## PTD-4. Policy Profile Type（冻结）

| 项 | 值 |
|----|-----|
| Exact type | `RemoteDataPolicyProfile` |
| Kind | `str, Enum`（对齐 `DataClassification` / `AppEnv`） |
| File | `src/gov_service_agent/llm/types.py` |
| Values | `DEFAULT = "DEFAULT"`；`DEMO_APPROVED = "DEMO_APPROVED"` |
| Default | `DEFAULT` |
| Why here | 叶模块；Settings/policy/provider/openai_compatible 均可单向引用；避免 settings↔policy 环 |

**正交维度：**

| 轴 | Values | 职责 |
|----|--------|------|
| Provider type（`LLM_PROVIDER`） | `DEMO` / `OPENAI_COMPATIBLE` / unset→NOT_CONFIGURED | 如何连接 |
| Policy profile（本字段） | `DEFAULT` / `DEMO_APPROVED` | 哪些业务数据可 Remote |

`OPENAI_COMPATIBLE` **永不**自动等同 Demo approval。

## PTD-5. Settings Contract（冻结）

| 项 | 值 |
|----|-----|
| Python field | `llm_remote_data_policy_profile` |
| Env var | `LLM_REMOTE_DATA_POLICY_PROFILE` |
| Type | `RemoteDataPolicyProfile` |
| Default | `RemoteDataPolicyProfile.DEFAULT` |
| Unset / blank | → `DEFAULT`（不得自动 DEMO） |
| Invalid value | **Fail-fast** ValidationError（不得 fallback DEMO；不得扩大权限） |
| Auto-select from APP_ENV / URL / key / host | **FORBIDDEN** |
| Persist in code as machine default DEMO | **FORBIDDEN** |

`.env.example`：增加一行注释 placeholder（无真实值），例如 `# LLM_REMOTE_DATA_POLICY_PROFILE=DEFAULT`。

## PTD-6. Allow-Sets & Matrix

**DEFAULT** → `_REMOTE_ALLOW`（现有）：

`PUBLIC_BUSINESS_METADATA` · `SYSTEM_CONTROL_DATA` · `SYNTHETIC_TEST_DATA`

**DEMO_APPROVED** → `_REMOTE_ALLOW_DEMO_APPROVED`（新常量名可微调，集合冻结）：

上表七类业务分类；**无** `UNKNOWN`。

| Profile | Classification | Decision |
|---------|----------------|----------|
| DEFAULT | PUBLIC_BUSINESS_METADATA | ALLOW |
| DEFAULT | SYSTEM_CONTROL_DATA | ALLOW |
| DEFAULT | SYNTHETIC_TEST_DATA | ALLOW |
| DEFAULT | USER_FREE_TEXT | DENY |
| DEFAULT | USER_PII | DENY |
| DEFAULT | HIGH_SENSITIVE_IDENTITY | DENY |
| DEFAULT | TO_CONFIRM_OR_INTERNAL | DENY |
| DEFAULT | UNKNOWN | DENY |
| DEMO_APPROVED | 七类 Approved | ALLOW |
| DEMO_APPROVED | UNKNOWN | DENY |
| DEMO_APPROVED | Approved + UNKNOWN（multi） | DENY |
| DEMO_APPROVED | 仅 Approved multi-label | ALLOW |
| either | missing/empty → UNKNOWN | DENY |

**Algorithm：**

```
classes = collect_request_classifications(request)  # empty/missing → {UNKNOWN}
allow = _REMOTE_ALLOW if profile == DEFAULT else _REMOTE_ALLOW_DEMO_APPROVED
denied = classes - allow
if denied: DENY(denied_categories=denied, reason=POLICY_DENIED)
else: ALLOW(denied_categories=empty, reason=POLICY_ALLOWED)
```

## PTD-7. Provider / Factory Changes（冻结）

### `OpenAICompatibleLlmProvider`

- `__init__(..., remote_data_policy_profile: RemoteDataPolicyProfile = RemoteDataPolicyProfile.DEFAULT)`
- 存 `self._remote_data_policy_profile`
- `complete`：第一步 `evaluate_request_remote_policy(request, profile=self._remote_data_policy_profile)`
- DENY / ALLOW / HTTP / logging / auth header 行为保持；**不**把 profile 或 API key 写入 messages
- 构造默认 `DEFAULT` → 现有单测若不传 profile 仍为原 fail-closed

### `build_llm_provider`

- Provider **selection** 逻辑不变（仍只看 `llm_provider` + Real 三件套完整性）
- 仅当构造 `OpenAICompatibleLlmProvider` 时传入 `remote_data_policy_profile=getattr(settings, "llm_remote_data_policy_profile", RemoteDataPolicyProfile.DEFAULT)`（或等价显式读取）
- `DEMO` / NOT_CONFIGURED：**不**传、不使用 Profile

### Unchanged

- `DemoLlmProvider`（本地、无网络、不调 remote policy）
- `_NotConfiguredProvider`
- Auth：key 仅 HTTP `Authorization`；Policy Profile **不**访问/记录/修改 key

## PTD-8. F09 / Authority（设计确认 = NO CHANGE）

| 项 | Design |
|----|--------|
| `LlmAnswerMapper.map_answer` | NO CHANGE；仍 `USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA`；`operation=f09_slot_answer_mapping` |
| Explanation | NO CHANGE；`f09_explain_public_concept`；PUBLIC+SYSTEM |
| Payload | 仍最小化；无 AgentState/history/ids |
| Membership / confidence | 仍本地；threshold **0.80** |
| LLM authority | 仍无 next_node / business_id / confirmed_business_id / rule outcome |
| Graph / Rule / F10 | 不变 |

## PTD-9. Failure Modes

| ID | Mode | Behavior |
|----|------|----------|
| FM1 | Profile unset | DEFAULT |
| FM2 | Profile invalid | Settings fail-fast |
| FM3 | DEFAULT + forbidden class | POLICY_DENIED / 0 HTTP |
| FM4 | DEMO + UNKNOWN / unapproved | POLICY_DENIED / 0 HTTP |
| FM5 | Auth/network | 现有 Provider error mapping |
| FM6 | Invalid response | 现有 parse/contract failure |
| FM7 | mapped_value ∉ allowed_values | F09 本地 reject |
| FM8 | confidence < 0.80 | F09 本地 reject；不推进 Graph |

## PTD-10. Observability

保持现有 safe logging。若记录 policy：最多 `profile` name、allowed/denied、classification names、`reason_code`、`operation`。
**禁止**新增 raw prompt / API key / Authorization 日志。

## PTD-11. Performance / Migration

- Policy lookup = 本地 frozenset membership；额外 latency negligible
- **无** network/DB/Redis for policy
- **无** schema / data / Redis migration

## PTD-12. Test Strategy（冻结）

### Modified tests

| Path | Coverage |
|------|----------|
| `tests/test_llm_policy.py` | DEFAULT 原 allow/deny；DEMO 七类 ALLOW；DEMO UNKNOWN DENY；multi-label；missing/empty DENY；deterministic |
| `tests/test_llm_openai_compatible.py` | A DEFAULT+USER_FREE_TEXT→0 HTTP；B DEMO+USER_FREE_TEXT→MockTransport 1 call；C DEMO+USER_PII allow path；D DEMO+UNKNOWN→0 HTTP；现有 deny cases 默认仍 DEFAULT |
| `tests/test_settings.py` | default=DEFAULT；`DEMO_APPROVED` parse；invalid fail-fast；dotenv key accepted |

### Regression-only（运行、不修改）

| Path | Why |
|------|-----|
| `tests/test_agent_interaction.py` | `LlmAnswerMapper` classifications / confidence / explanation |
| `tests/test_agent_workflow.py` | F09 workflow + USER_FREE_TEXT 不进入 explanation path 等 |

### Explicitly out of automated Reopen unit tests

- Real Company API / `RUN_LLM_REAL`（延后 F12 Resource Gate；RG-F12-004）

## PTD-13. AC → TD Traceability

| AC | TD |
|----|-----|
| AC-F07-39 | D12, D17, D23 |
| AC-F07-40 | D12, D13, D14, D15 |
| AC-F07-41 | D18 |
| AC-F07-42 | D18, D19 |
| AC-F07-43 | D19 |
| AC-F07-44 | D19 |
| AC-F07-45 | D15, D20 |
| AC-F07-46 | D12, D23 |
| AC-F07-47 | D25 |
| AC-F07-48 | D12, D13, D14 |
| AC-F07-49 | D15, D20（auth boundary 保持） |
| AC-F07-50 | D21, D22 |
| AC-F07-51 | D22 |
| AC-F07-52 | D22 |
| AC-F07-53 | D22 |
| AC-F07-54 | D16, D24 |
| AC-F07-55 | D25 |
| AC-F07-56 | D25 |
| AC-F07-57 | D22 |
| AC-F07-58 | D24（defer real LLM to F12） |

**孤立 AC：0。**

## PTD-14. Frozen Path Sets

### Frozen Production Paths（Code 允许修改）

| # | Path | Why |
|---|------|-----|
| 1 | `src/gov_service_agent/llm/types.py` | `RemoteDataPolicyProfile` |
| 2 | `src/gov_service_agent/llm/policy.py` | Demo allow-set + profile 参数 evaluator |
| 3 | `src/gov_service_agent/llm/openai_compatible.py` | 存 profile；evaluate 传参 |
| 4 | `src/gov_service_agent/llm/provider.py` | factory 传入 profile |
| 5 | `src/gov_service_agent/settings.py` | field / env keys / validators |
| 6 | `src/gov_service_agent/llm/__init__.py` | 导出 `RemoteDataPolicyProfile`（及如需的 `evaluate_request_remote_policy`） |
| 7 | `.env.example` | placeholder 一行 |

**Core Production Python（逻辑）：5**（types/policy/openai_compatible/provider/settings）。
**+ package export `__init__.py`（1）+ `.env.example`（1）** = 完整 Production path set **7**。
超出 5 的原因：`__init__.py` 是既有公共导出面（非第二套 policy）；`.env.example` 是配置契约不是运行逻辑。两者不可合并进前五而不破坏 Settings/dotenv 约定。

### Frozen Modified Test Paths

1. `tests/test_llm_policy.py`
2. `tests/test_llm_openai_compatible.py`
3. `tests/test_settings.py`

### Frozen Regression-only Test Paths

1. `tests/test_agent_interaction.py`
2. `tests/test_agent_workflow.py`

### Frozen Docs Paths（完整 Reopen 生命周期；本 TD 阶段仍只改 #1）

1. `docs/features/F07-llm-provider-data-policy.md`（本文件；Requirement+TD 已改）
2. `docs/code-reading/F07-llm-provider-data-policy-code-reading.md`（Explanation 阶段）
3. `docs/features/F09-missing-slot-question-answer-mapping.md`（Code/Test/Review 后更新 **OI-F09-DP-001**；本 TD **不**改）

**超出 F07 的 docs：** 仅 F09 Feature Doc（OI 状态同步）。**无** F12/F10/F11 Production。

后续 Code **不得**擅自增加 path；若必须 → STOP + Owner scope exception。

## PTD-15. F12 Runtime Note（本阶段不配置）

F07 Reopen Code/Test/Review PASS 后，回到 F12 Resource Gate 再配置/验证：

`LLM_PROVIDER` / `LLM_MODEL_ID` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_REMOTE_DATA_POLICY_PROFILE=DEMO_APPROVED`
以及既有 Embedding persistent config。
**本 TD 不配置、不调用真实 LLM。**

| Blocker | Status after this TD |
|---------|----------------------|
| RG-F12-004 | **PENDING** |
| RG-F12-006 | **TD COMPLETE / IMPLEMENTATION PENDING** |
| F12 | **仍 BLOCKED** |

## PTD-16. TD Self-Review

| # | Check | Result |
|---|-------|--------|
| 1 | Requirement 未被改变 | PASS |
| 2 | DEFAULT 行为完全保留 | PASS |
| 3 | DEMO allow set 准确 | PASS |
| 4 | UNKNOWN DENY | PASS |
| 5 | invalid profile fail-safe | PASS（fail-fast） |
| 6 | Profile 显式配置 | PASS |
| 7–8 | 无 URL trust / 无万能 bool | PASS |
| 9–11 | 无 capability / registry / DLP | PASS |
| 12 | 不改 F09 contract | PASS |
| 13 | LLM authority 不变 | PASS |
| 14 | 0 HTTP deny | PASS |
| 15 | Secret 不进 prompt | PASS |
| 16 | 测试不依赖真实 API | PASS |
| 17–18 | 无新依赖 / infra | PASS |
| 19 | 路径冻结完整 | PASS |
| 20 | AC traceability 完整 | PASS |

## PTD-17. Stage Gate

| 项 | 值 |
|----|-----|
| Technical Design Reopen | **COMPLETE** |
| TD Finalization | **NOT REQUIRED** |
| Confirm → Code | **READY FOR OWNER CONFIRMATION** |
| Auto-enter Code / Test / F12 | **FORBIDDEN** |

**STOP。** 等待 Owner 授权 Confirm / Code。

> **历史注记（Explanation）：** 上表保留 TD 结束时快照。后续 Confirm / Code / Test / Review 均已完成；当前阶段见文首 **Current Stage Status** 与下文 **Policy Reopen Explanation**。

---

# Policy Reopen Explanation

| 字段 | 内容 |
|------|------|
| Stage | **EXPLANATION — COMPLETE** |
| Review prior | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 3；Review Fix = NOT REQUIRED） |
| Test prior | **PASS**（full：620 passed / 13 skipped / 0 failed / 0 warnings） |
| Code-Reading | **本阶段不修改**；下一独立阶段更新 |
| Real Company LLM | **NOT YET VERIFIED**（代码能力 READY；运行时仍 PENDING） |

## PEX-1. Reopen Background — 为什么要重开

Original F07 已 **CLOSED**。其 Remote Data Policy 采用 fail-closed：真实 `USER_FREE_TEXT` 默认 **DENY**（历史 **AC-F07-19** + TD D07）。这不是“公司模型不能处理中文”，而是当时**尚未获得**生产/Demo 用户业务文本远程发送的 Owner 授权。

F09 随后实现了 `LlmAnswerMapper`：需要把用户自然语言（例如「平时接零活，没有固定单位」）映射到受控枚举（例如 `employment_type = other_flexible_employment`）并返回 `confidence`。F09 **正确**地把用户回答标为 `USER_FREE_TEXT`，且 **不拥有**修改 F07 Policy 的权限（**OI-F09-DP-001**）。

因此 F12 E2E 被 **RG-F12-006** 阻塞：不是 Mapper 没写，而是 Remote Policy 在 HTTP 前拒绝。

本次 Policy Reopen **只**解决 Demo 阶段 Remote Data Policy：增加显式 `RemoteDataPolicyProfile`，在 Owner 批准下允许指定业务分类 Remote Dispatch；**不**全局永久放开、**不**把业务决策权交给 LLM。

## PEX-2. Owner Demo Policy Boundary

当前项目处于 **Demo 阶段**。Owner 已批准：下列**用户业务数据**可发送给公司指定 Remote LLM 做业务处理：

`PUBLIC_BUSINESS_METADATA` · `SYSTEM_CONTROL_DATA` · `SYNTHETIC_TEST_DATA` · `USER_FREE_TEXT` · `USER_PII` · `HIGH_SENSITIVE_IDENTITY` · `TO_CONFIRM_OR_INTERNAL`

**仍 DENY：** `UNKNOWN`（含 missing/empty 归入 UNKNOWN）。

**不属于授权：** 系统 Secret / Credential。下列内容**不得**进入 LLM `messages` / prompt：

`LLM_API_KEY` · Authorization / Bearer Token · DB/Redis 密码 · 其它运行时认证凭据。

Transport 层 HTTP `Authorization: Bearer …` 属于 Provider 认证，**不是**业务 payload。

**DEMO_APPROVED 不是：** “所有内容可信 / 跳过安全检查 / 无条件 ALLOW 一切远程请求”。
**DEMO_APPROVED 是：** Owner 明确授权的 Demo **用户业务分类**可以 Remote Dispatch；UNKNOWN 与 Secret 边界仍然成立。

## PEX-3. End-to-End Business Flow（第一主线）

```
用户提交当前槽位回答（自然语言）
  → F09 接收 NEED_SLOT 上下文 + user_text
  → LlmAnswerMapper.map_answer 构造最小 LlmRequest
       （system instructions + required_slot + allowed_values + user_text；
        classifications 含 USER_FREE_TEXT）
  → LlmProvider.complete（通常为 OpenAICompatibleLlmProvider）
  → Remote Data Policy Profile 生效（Settings → Factory 注入）
       DEFAULT        → 原 F07 allow-set → USER_FREE_TEXT DENY → 0 HTTP
       DEMO_APPROVED  → Demo allow-set → 业务类 MAY ALLOW
  → DENY：LlmProviderError(POLICY_DENIED)；数据不离开本地 Policy 边界
  → ALLOW：仅表示允许进入 HTTP；仍可能 auth/timeout/parse 失败
  → 结构化输出回到 F09
  → validate_slot_mapping：membership（mapped_value ∈ allowed_values）
  → confidence >= MappingPolicy.min_confidence（0.80）
  → 仅 ACCEPTED → F04 Business Decision Graph 确定性推进
  → Terminal 后仍须 F10 confirmation 才产生 confirmed_business_id
```

## PEX-4. 主流程逐步说明

### Step A — 用户回答当前槽位

用户/系统在做什么：用户在回答 Business Graph 当前 `required_slot` 对应的问题。
代码：Agent F09 node 组装 `AnswerMappingRequest(required_slot, allowed_values, user_text)`，调用 `LlmAnswerMapper.map_answer`（`agent/interaction.py`）。
为什么存在：把自然语言变成受控枚举，供确定性图推进。
输入：槽位名、允许值列表、用户原文。
输出：`AnswerMapperOutput`（kind / mapped_value / confidence）。
交给谁：本地 `validate_slot_mapping`，再决定是否调 F04。
权限边界：Mapper **不**改 `next_node` / `business_id` / rule。

### Step B — F09 构造 LlmRequest（F09 本次 0 change）

F09 原本做的是对的：用户自由文本标为 `USER_FREE_TEXT`，**不得**伪装成 `SYNTHETIC_TEST_DATA` / `SYSTEM_CONTROL_DATA`。真正应改的是 F07 Policy，故 F09 Production **本次零修改**。

Payload 仍最小化：system instructions + `required_slot` + `allowed_values` + `user_text`。
**不**发送 full AgentState / conversation history / `request_id` / `session_id` / checkpoint / orchestration_trace。
`operation="f09_slot_answer_mapping"` 仅为元数据，**不**参与 Policy 判定。

### Step C — Provider 接收请求

`OpenAICompatibleLlmProvider.complete(request)`（`llm/openai_compatible.py`）先读构造时注入的 `remote_data_policy_profile`，再调 Policy。
Provider Type（`DEMO` / `OPENAI_COMPATIBLE` / `NOT_CONFIGURED`）回答“用什么方式调用模型”；
Policy Profile（`DEFAULT` / `DEMO_APPROVED`）回答“哪些业务数据允许 Remote Dispatch”。二者**正交**。
`OPENAI_COMPATIBLE` **≠** trusted。

### Step D — Settings → Factory → Profile

部署显式配置 `LLM_REMOTE_DATA_POLICY_PROFILE` → `Settings.llm_remote_data_policy_profile: RemoteDataPolicyProfile`（默认 `DEFAULT`）。
非法值（如 `ALLOW_ALL`）：Settings **fail-fast**，不静默 DEMO、不 permissive fallback。
`.env.example` 示例语义为默认 `DEFAULT`；Demo 环境须**显式**改为 `DEMO_APPROVED`。
不会因 APP_ENV / API key 存在 / URL / localhost / `OPENAI_COMPATIBLE` 自动开启 Demo。

`build_llm_provider(settings)`（`llm/provider.py`）**不改变** Provider selection；仅在构造 `OpenAICompatibleLlmProvider` 时传入 profile。
Profile **不能**把 `NOT_CONFIGURED` 变成可调用 Real Provider。
（INFO RI-F07R-002：若 duck-typed caller 传入非 enum profile，factory 防御性回落 **DEFAULT**——只收紧权限，永不升到 DEMO_APPROVED。）

### Step E — Policy 本地判定（HTTP 前）

`evaluate_request_remote_policy(request, profile)` → `evaluate_remote_policy(classifications, profile)`（`llm/policy.py`）。
纯本地、确定性、无网络/DB/Redis/环境变量/URL/LLM。
DEFAULT 复用原 `_REMOTE_ALLOW`；DEMO_APPROVED 使用 `_REMOTE_ALLOW_DEMO_APPROVED`（七类业务；**无** UNKNOWN）。

**DENY：** 立即 `LlmProviderError(POLICY_DENIED)`，**0 HTTP**——数据不离开本地 Policy 边界。
**ALLOW：** 仅允许进入现有 HTTP 流程；≠ HTTP/认证/解析成功。

### Step F — LLM 只做 Mapping，本地再审

允许 Remote 后，模型只返回 utterance kind / mapped value / confidence。
例（未来 Golden Path 语义，**本阶段未跑真实 LLM**）：

- 用户：「平时接零活，没有固定单位」
- slot：`employment_type`
- allowed：`self_employed_without_employees` / `part_time_without_employer_insurance` / `other_flexible_employment`
- LLM 可映射：`other_flexible_employment` + confidence

之后 F09 `validate_slot_mapping`：**membership**（`mapped_value ∈ allowed_values`）→ **confidence ≥ 0.80**。任一层失败 → 不推进 Business Graph。Policy Reopen **未取消**这两层。

### Step G — Business Graph / F10

仅 `ACCEPTED` 才交给 F04。Business Decision Graph 按 `current_node`、validated slots、预定义 edges **确定性**推进。
Terminal 的 `candidate_business_id` **≠** `confirmed_business_id`；最终确认仍属 **F10**。F07 Reopen 不改变。

## PEX-5. DEFAULT vs DEMO_APPROVED

| Profile | 如何启用 | 行为摘要 |
|---------|----------|----------|
| **DEFAULT** | 未配置 / blank / 显式 DEFAULT | 完全等价原 F07：`USER_FREE_TEXT`/`USER_PII`/`HIGH_SENSITIVE`/`TO_CONFIRM`/`UNKNOWN` → DENY |
| **DEMO_APPROVED** | **仅**显式 env/Settings | Owner 批准的七类业务 → MAY ALLOW；UNKNOWN → DENY |

## PEX-6. Policy Decision Examples

**Multi-label（必须全部属于 allow-set）：**

- DEMO + `{USER_FREE_TEXT, SYSTEM_CONTROL_DATA}` → **ALLOW**
- DEMO + `{USER_FREE_TEXT, UNKNOWN}` → **DENY**，`denied_categories={UNKNOWN}`
  （不是“有一个允许就 ALLOW”。）

**Empty / missing 为何不会误放行：**
数学上 empty set ⊆ 任意集合。实现上 missing/empty 先经 `_normalize_classifications` / `collect_request_classifications` → **UNKNOWN**，再判定；UNKNOWN ∉ allow-set → **DENY**。这就是 fail-closed。

**PolicyDecision 合同未变：** `allowed` / `denied_categories` / `reason_code`（`POLICY_ALLOWED` / `POLICY_DENIED`）。无 TRUSTED_ALLOW / DEMO_BYPASS 之类额外权限语义。

## PEX-7. Explanation Side Route（未改）

用户问「灵活就业是什么意思？」→ `detect_explanation_request` 识别 `EXPLANATION_REQUEST` → explanation side route。
**不**写 slot、**不**推进 Graph、**不**产生 candidate、**不**改 rule status。Policy Reopen 不影响该 invariant。

## PEX-8. Failure / Fail-Closed Cases

| 情况 | 结果 |
|------|------|
| DEFAULT + 禁止分类 | POLICY_DENIED / 0 HTTP |
| DEMO + UNKNOWN / missing / empty | POLICY_DENIED / 0 HTTP |
| 非法 Settings profile | fail-fast |
| Provider 未配齐 | 仍 NOT_CONFIGURED（与 Profile 无关） |
| Policy ALLOW 后 HTTP/parse 失败 | 现有 Provider/F09 受控失败；不推进 Graph |
| membership / confidence 失败 | 本地 reject；不推进 Graph |

## PEX-9. Test / Review Evidence（不重跑）

| Suite | Result |
|-------|--------|
| `test_llm_policy` | 29 passed |
| `test_llm_openai_compatible` | 34 passed |
| `test_settings` | 88 passed |
| `test_agent_interaction` | 63 passed |
| `test_agent_workflow` | 31 passed |
| Combined targeted | 245 passed / 0 failed / 0 warnings |
| Full suite | **620 passed / 13 skipped / 0 failed / 0 warnings** |

| Review | Result |
|--------|--------|
| Status | **PASS** |
| BLOCKING / MAJOR / MINOR | **0 / 0 / 0** |
| INFO | **3**（无需 Review Fix） |

## PEX-10. Review INFO Disposition

| ID | Disposition |
|----|-------------|
| **RI-F07R-001** | **DISPOSED IN EXPLANATION** — Feature Doc stage 已同步至 Confirm/Code/Test/Review/Explanation |
| **RI-F07R-002** | **EXPLAINED / NO CODE CHANGE** — Settings 非法 fail-fast；duck-typed factory 仅防御性 DEFAULT（收紧） |
| **RI-F07R-003** | **ACCEPTED / NO TEST CHANGE** — helper 命名欠精确，但断言与输入正确，无假阳性 |

## PEX-11. Runtime Validation Still Pending

| 项 | 状态 |
|----|------|
| 代码能力（Demo Profile + Real Provider wiring） | **READY** |
| 真实 Company LLM auth/connectivity/model | **NOT YET VERIFIED** |
| RG-F12-004 | **PENDING** |
| RG-F12-006 | **POLICY IMPLEMENTATION REVIEW PASS / RUNTIME VALIDATION PENDING** |
| F12 Resource Gate | **仍 BLOCKED** |
| OI-F09-DP-001 | **仍 OPEN**（见 F09 doc；关闭条件 = F12 真实 Remote USER_FREE_TEXT probe PASS） |

**禁止宣称：** “真实 LLM 已打通”。本阶段未配置 `LLM_*`、未调用 Company API。

## PEX-12. Explanation Stage Gate

| 项 | 值 |
|----|-----|
| Explanation | **COMPLETE** |
| Code-Reading Update | **READY FOR OWNER AUTHORIZATION**（未授权；**STOP**） |
| Commit / Push / F12 | **FORBIDDEN** without Owner authorization |
