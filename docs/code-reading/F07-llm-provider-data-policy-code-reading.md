# F07 Code Reading — LLM Abstraction + Demo Provider + Real Company Provider + Data Policy

面向已读过 F01 Settings、F05/F06 基础设施与检索链路的开发者。

**核心问题：**

> F07 如何让 Agent 以统一、安全、可测试的方式调用 LLM，却不让模型抢走 Graph / Rule / Controller 的业务真值？

**一句话定位：**

F07 提供 **LLM 调用基础设施**（Provider 抽象、Demo、真实公司 OpenAI-compatible 接入、Remote Data Policy、严格结构化解析）。

F07 **不负责** 政务业务决策。

| 层 | 职责 |
|----|------|
| **LLM Provider** | 模型能力层（请求/响应、策略、解析） |
| **Business Decision Graph / Rule Engine / Controller** | 业务真值层 |

**功能状态（分层）：**

| 层 | 状态 |
|----|------|
| **Original F07** | **CLOSED** @ `3b68726…`（Resource Gate → Code-Reading → Commit/Push 均完成） |
| **F07 Policy Reopen** | Resource Gate READY → Requirement/TD/Confirm/Code **COMPLETE** → Test **PASS** → Review **PASS**（Fix NOT REQUIRED）→ Explanation **COMPLETE** → **本 Code-Reading Update COMPLETE**；**Awaiting Commit Authorization** |
| F12 | **仍 BLOCKED**（RG-F12-004 PENDING；RG-F12-006 = POLICY IMPLEMENTATION REVIEW PASS / RUNTIME VALIDATION PENDING） |

> 下文 §1–§20 保留 Original F07 Code-Reading 正文（含当时「USER_FREE_TEXT Remote DENY」表）。**DEFAULT Profile 仍等于该原策略。** Demo 例外见文末 **§21+ Policy Reopen Code-Reading Update**（业务流程优先）。

Original F07 验证证据（历史）：

| 项 | 结果 |
|----|------|
| Phase A unit | **160 / 160 PASS** |
| Default Full（当时） | **319 passed / 13 skipped / 1 known warning** |
| Real Provider Smoke | **PASS**（opt-in） |
| Real Structured | **DIRECT_JSON PASS** |
| Policy Denial | HTTP **0** / sleep **0** |
| compileall / pip check | **PASS** |
| Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 3） |

Policy Reopen 验证证据（权威）：

| 项 | 结果 |
|----|------|
| compileall / pip check | **PASS** |
| Combined targeted | **245 passed / 0 failed / 0 warnings** |
| Full suite | **620 passed / 13 skipped / 0 failed / 0 warnings** |
| Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 3；Fix NOT REQUIRED） |

Known warning（Original）：Starlette `TestClient` + `httpx` deprecation（既有依赖告警，非 F07 regression）。

完整 Requirement / Design / Test / Review / Explanation / Reopen：

`docs/features/F07-llm-provider-data-policy.md`

---

## 1. 目录结构

```text
src/gov_service_agent/llm/
├── __init__.py              # 最小 Public API
├── types.py                 # 请求/响应/分类/错误契约
├── policy.py                # Remote Data Policy
├── structured.py            # 严格 JSON + Pydantic
├── provider.py              # Protocol + Factory + NotConfigured
├── demo.py                  # 本地确定性 Demo Provider
└── openai_compatible.py     # 真实公司 HTTP Provider（httpx）
```

相关配置与测试：

| Path | 角色 |
|------|------|
| `src/gov_service_agent/settings.py` | 可选 `LLM_*` + `SecretStr` |
| `.env.example` | placeholder（无真实密钥） |
| `tests/test_llm_policy.py` | Policy 单元测试 |
| `tests/test_llm_structured.py` | 严格解析单元测试 |
| `tests/test_llm_demo.py` | Demo + Factory |
| `tests/test_llm_openai_compatible.py` | Fake HTTP Real Provider |
| `tests/integration/test_llm_real.py` | Opt-in 真实 Smoke |
| `tests/test_settings.py` | Settings LLM 覆盖（MODIFY） |

**没有** 新增 `/llm` HTTP endpoint；**未改** `main.py`。

---

## 2. 推荐阅读顺序

| 顺序 | 文件 | 为什么先看 |
|------|------|------------|
| 1 | `types.py` | 先建立契约：消息、分类、响应、错误长什么样 |
| 2 | `policy.py` | 再看 Remote 卡点：谁允许发往公司模型 |
| 3 | `provider.py` | Protocol / Factory / NotConfigured 如何选型 |
| 4 | `demo.py` | 最短 `complete()` 路径，无网络 |
| 5 | `openai_compatible.py` | Policy → HTTP → retry → 响应映射 |
| 6 | `structured.py` | `content` 如何 Fail Closed 变成 typed 对象 |
| 7 | `settings.py` | 可选配置与 SecretStr |
| 8 | Unit tests | 行为规格（0 公司网络） |
| 9 | `tests/integration/test_llm_real.py` | Opt-in Real 契约 |

---

## 3. `types.py` — Provider-neutral 契约

| 类型 | 作用 |
|------|------|
| `DataClassification` | 八类安全分类枚举 |
| `LlmMessage` | `role` + `content` + `classifications` |
| `LlmRequest` | 非空 `messages` + 可选 `operation` |
| `LlmResponse` | `content`、`provider_name`、`model_id`、`reasoning_present`、`finish_reason` |
| `LlmErrorCode` / `LlmProviderError` | 受控 Provider 失败 |
| `ParsingMode` / `StructuredParseError` | 解析模式与受控解析失败 |

**`content` 与 `classification` 必须分开：**

- `content`：文本载荷（可能发给模型）
- `classifications`：调用方显式提供的 **security metadata**
- **不是**模型自己猜；F07 **不**根据自然语言推断 PII/PUBLIC
- 缺失 / 空集合 → 按 `UNKNOWN` 处理（见 Policy）

---

## 4. Data Classification 与 Remote Policy

| Classification | 含义 | Remote Company LLM |
|----------------|------|--------------------|
| `PUBLIC_BUSINESS_METADATA` | 可公开业务元数据 | **ALLOW** |
| `SYSTEM_CONTROL_DATA` | 系统控制/合成控制提示 | **ALLOW** |
| `SYNTHETIC_TEST_DATA` | 明确构造的测试数据 | **ALLOW** |
| `USER_FREE_TEXT` | 真实用户自然语言 | **DENY**（**DEFAULT Profile / Original F07**；Demo 例外见 §21+） |
| `USER_PII` | 用户个人身份相关 | **DENY**（DEFAULT；Demo 例外见 §21+） |
| `HIGH_SENSITIVE_IDENTITY` | 高敏感身份类 | **DENY**（DEFAULT；Demo 例外见 §21+） |
| `TO_CONFIRM_OR_INTERNAL` | 待确认或内部敏感 | **DENY**（DEFAULT；Demo 例外见 §21+） |
| `UNKNOWN` | 未声明 / 无法判断 | **DENY**（**含 DEMO_APPROVED**） |

**Mixed Payload：** 同一 `LlmRequest` 只要含任一 DENY 分类 → **整请求 DENY**。不会删除敏感部分再发剩余内容。

**`USER_FREE_TEXT` 当前 DENY：** 不是公司模型技术不能处理，而是尚未获得生产真实用户文本远程发送策略授权；当前 fail closed，未来须正式政策重开。

---

## 5. `policy.py` — Remote Data Policy

主要 API：

- `collect_request_classifications(request)` — 聚合各 message；空/缺失 → `UNKNOWN`
- `evaluate_remote_policy(classifications)` — ALLOW/DENY
- `evaluate_request_remote_policy(request)` — 对整请求求值
- `PolicyDecision` — `allowed` / `denied_categories` / `reason_code`（**不含** prompt/content/secret）

调用链：

```text
LlmRequest
  → classification aggregate
  → evaluate
  → ALLOW / DENY
```

DENY 时（在 Real Provider 内）：

- `LlmProviderError(POLICY_DENIED)`
- **HTTP calls = 0**
- **sleep = 0**
- **retries = 0**

**为什么放在 Provider 内：** defense-in-depth。即使未来 F08/F09 直接实例化 Real Provider，也无法跳过 HTTP 前的 Policy。

Demo Provider 本地无网络，Design **不强制**同一 remote deny 语义。

---

## 6. `provider.py` — Protocol / Factory / NotConfigured

`LlmProvider` Protocol（**sync only**）：

- `provider_name` / `model_id`
- `complete(request) -> LlmResponse`

**没有：** async、stream、`close`、tool calling。

`build_llm_provider(settings)`：

| `LLM_PROVIDER` | 行为 |
|----------------|------|
| `None` | `_NotConfiguredProvider` |
| `DEMO` | `DemoLlmProvider` |
| `OPENAI_COMPATIBLE` + 齐全 URL/Key/Model | Real Provider |
| `OPENAI_COMPATIBLE` 缺配置 | `_NotConfiguredProvider`（不崩 startup） |
| unknown | Settings fail-fast；factory 防御性 `UNKNOWN_PROVIDER` |

**无** Real↔Demo 隐式 fallback。

`_NotConfiguredProvider`：

- **不是** Fake success Provider
- 基础 app 无 LLM 配置仍可启动
- `complete()` → 稳定 `NOT_CONFIGURED`
- 私有；**不**进入 `llm/__init__.py` public export

Factory **不发网络**。

---

## 7. `demo.py` — Deterministic Demo Provider

特点：**No Network / No API Key / No External Model / Deterministic**。

默认中性 synthetic content：`{"status":"demo"}`。

可选注入固定 `response_content` 或受控 `failure`（`LlmProviderError`）。

用途：Unit Test、F08/F09 scaffold、离线开发。

**不是**真实模型准确率模拟器。

---

## 8. `openai_compatible.py` — Real Provider

技术选型：**httpx** + OpenAI-compatible `POST …/chat/completions` + Bearer Auth。

**没有：** OpenAI SDK / DashScope SDK / LiteLLM / instructor。

完整调用链：

```text
LlmRequest
   |
   v
OpenAICompatibleLlmProvider.complete
   |
   v
Remote Data Policy
   |
   +-- DENY --> POLICY_DENIED
   |
   v
Map messages (role/content), temperature=0
   |
   v
httpx POST {base_url}/chat/completions
   Authorization: Bearer <secret>
   |
   v
HTTP / JSON / choices[0].message validation
   |
   v
content (non-empty string)
   |
   +--> reasoning_present (bool only; 不读内容)
   |
   v
LlmResponse
```

生产 `complete` **不**调用 `GET /models`。

配置只通过环境变量名引用：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_ID`（文档不写真实值）。

---

## 9. `structured.py` — 严格结构化解析

```text
content
  → strip（空 → EMPTY_CONTENT）
  → DIRECT_JSON?  (json.loads 整个 text → 必须 dict)
  → 否则 STRICT_SINGLE_JSON_CODE_FENCE
       (首行精确 ```json 或 ``` ；末行精确 ``` ；中间不得再含 ```)
  → extra-field check（payload keys ⊆ model fields）
  → model_validate
  → StructuredParseResult(value, mode)
```

**DIRECT_JSON：** `list` / `string` / `number` / `bool` / `null` 即使 JSON 合法也 **reject**（必须 object）。

**Strict Fence：** 整个 `message.content` 只能是这一个 envelope。

**Fail Closed reject：** prose+JSON；JSON+prose；multiple JSON；malformed；non-object；unknown extra fields；schema invalid；empty content。

**为什么不 regex 抠 JSON：** 程序不能从任意自然语言猜测哪个 JSON 才是真正结果；宁可失败，不自动修复。

**F07 vs F09：**

| 层 | 负责 |
|----|------|
| F07 generic parser | 结构正确（JSON object + schema fields） |
| 未来 F09 / Controller | 业务校验（allowed_values、当前 slot、confidence 阈值等） |

---

## 10. Reasoning 隔离

真实公司响应可能 `reasoning_present=True`（已验证）。

F07：

- 仅检测键是否存在：`reasoning` / `reasoning_content` / `thinking`
- **不**读内容、**不**拼进 `content`、**不** structured parse、**不**日志内容、**不**参与业务决策

原因：业务真值由 Decision Graph / Rule Engine / Controller 决定；LLM reasoning 不是政策真值。

---

## 11. Retry / Timeout / Backoff

| 项 | 值 |
|----|-----|
| `LLM_MAX_RETRIES` 默认 | `1`（额外次数） |
| 合法范围 | `0..3` |
| `total_attempts` | `1 + max_retries` |
| `LLM_TIMEOUT_SECONDS` 默认 | `60.0`（`1..300`） |

较大 timeout 是因为部分 thinking 模型响应可能较慢（**不要**在文档写具体公司模型名）。

**Retryable：** connect/transport、timeout、429、5xx。

**不 Retry：** 401/403、其它 4xx、`POLICY_DENIED`、`NOT_CONFIGURED`、invalid response、structured/schema（HTTP 成功之后）。

Backoff（第 `retry_index` 次 retry 前）：

```text
delay = min(0.25 * (2 ** retry_index), 2.0)
→ 0.25s → 0.50s → 1.00s
```

Structured parse 失败 **不会**触发再次 HTTP 问模型。

---

## 12. httpx Client 生命周期

| 模式 | Ownership | 行为 |
|------|-----------|------|
| 注入 external `httpx.Client` | **CALLER** | Provider **不** close（MockTransport / 复用） |
| 未注入 | Provider per-`complete()` | `with httpx.Client(...)`；initial+retry **同一** client；结束自动 close |

Protocol 无 `close()`：描述的是 LLM capability，不是 HTTP client 生命周期。

---

## 13. Error Mapping

| 情况 | `LlmErrorCode` |
|------|----------------|
| 401 / 403 | `AUTHENTICATION_FAILED` |
| 429 | `RATE_LIMITED` |
| 5xx | `SERVER_ERROR` |
| 其它 4xx | `INVALID_REQUEST` |
| Timeout | `TIMEOUT` |
| Connect / Transport | `NETWORK_UNAVAILABLE` |
| Policy Deny | `POLICY_DENIED` |
| Missing / incomplete config | `NOT_CONFIGURED` |
| Unknown provider (defensive) | `UNKNOWN_PROVIDER` |
| Bad JSON / shape | `INVALID_RESPONSE` |
| Empty content | `EMPTY_CONTENT` |
| Structured / schema | `STRUCTURED_PARSE_FAILED` / `SCHEMA_VALIDATION_FAILED` |

`LlmProviderError` 只暴露安全 code / retryable / 可选 http_status / safe message。
**不暴露：** raw prompt、raw body、Authorization、API Key、reasoning。

默认日志：Raw Prompt / Raw Response / Reasoning content = **OFF**。
允许：provider、operation、latency、attempt、error_code、reasoning_present、response_length、denied_categories 等安全 metadata。

---

## 14. Settings / Secret / `.env.example`

| Env | 默认 | 说明 |
|-----|------|------|
| `LLM_PROVIDER` | `None` | `DEMO` / `OPENAI_COMPATIBLE`；blank→None |
| `LLM_MODEL_ID` | `None` | blank→None |
| `LLM_BASE_URL` | `None` | http(s)+host；禁 userinfo/query/fragment；允许 path |
| `LLM_API_KEY` | `None` | **`SecretStr`** |
| `LLM_TIMEOUT_SECONDS` | `60.0` | 1..300 |
| `LLM_MAX_RETRIES` | `1` | 0..3 |

- 无 LLM 配置 → 应用仍可启动；**无 Startup Network**
- Secret 仅在构造 Authorization 时读取；禁止硬编码 / Git / 日志 / Exception 明文
- `.env.example` 只有 placeholder
- `RUN_LLM_REAL`：**不是** Settings 字段；仅 process env 控制 Real Smoke

---

## 15. 普通测试与 Real Smoke

**普通 `pytest`：** 0 公司网络。Real integration 默认 **SKIP**。

**Real Smoke：** 仅当 `RUN_LLM_REAL=1`。缺正式 `LLM_*` → **FAIL**（不是 SKIP），防止假绿色。

Real Smoke 数据分类仅：`SYNTHETIC_TEST_DATA` + `SYSTEM_CONTROL_DATA`。
不发送真实 `USER_FREE_TEXT` / PII / 高敏 / `TO_CONFIRM_OR_INTERNAL`。

已验证（不写 content/endpoint/key/model id）：

- Real Provider Smoke = PASS
- Structured mode = DIRECT_JSON
- Pydantic = PASS
- Reasoning present = YES（内容未读）

---

## 16. 与 F06 / F08 / F09 / Graph / Rule / Knowledge

| Feature | 关系 |
|---------|------|
| **F06** | Embedding 找方向；与 F07 **独立** Provider；LLM 不调用 Embedding |
| **F08** | Agent/LangGraph 编排；调用 F07；F07 不维护 Agent State |
| **F09** | Slot/Question/Answer Mapping；结构化结果后做业务校验 |
| **F04 Graph** | 确定性推进；LLM **绝不**直接 `next_node` |
| **Rule Engine** | 不由 F07 执行；LLM 不产生 Rule PASS |
| **Knowledge Graph** | `business_id` 确认后查 materials/locations/channels/legal basis；LLM 最多组织已有受控事实 |

目标链：

```text
User → F08 Agent → F07 LLM NLU → structured candidate signal
  → F09 validation → F04 Business Decision Graph
  → deterministic transition
```

---

## 17. 调试顺序

1. `LLM_PROVIDER`
2. Real config 是否完整
3. Data Policy（先看 classification；**勿**为通测试把 `USER_FREE_TEXT` 改 ALLOW）
4. Network
5. Timeout
6. HTTP status
7. Response shape
8. Empty content
9. Structured parser（prose+JSON 等 → **勿**加 loose regex）
10. Pydantic
11. 上层业务 validation

**不要混淆：**

- Provider Error ≠ low confidence
- Provider Error ≠ missing slot
- Provider Error ≠ no candidate

网络/鉴权错误后，**先别改 Graph**。

---

## 18. Security Checklist

- 不提交 API Key；不输出 Authorization
- 不记录 raw prompt / raw response / reasoning 内容
- `USER_FREE_TEXT`：**DEFAULT** Remote DENY；`UNKNOWN` Fail Closed（**含 Demo Profile**）
- Mixed 含 DENY → 整请求拒绝
- Real Smoke 只 synthetic / system-control（Original 契约）
- 不从自然语言宽松抽 JSON
- 文档不写真实 Base URL / API Key / 公司 Model ID
- Demo 业务放宽须 **显式** `LLM_REMOTE_DATA_POLICY_PROFILE=DEMO_APPROVED`（见 §21+）；**非**生产默认

---

## 19. Review INFO（非 defect）

| ID | 说明 |
|----|------|
| RI-F07-001 | Real Provider 调用期间进程内存持有 API key 用于 Authorization（Settings 仍为 SecretStr） |
| RI-F07-002 | 严格 fence 对极端 triple-fence payload fail closed |
| RI-F07-003 | 非 Timeout/Transport 的非预期异常不做 broad catch；上层须遵守安全日志纪律 |

BLOCKING / MAJOR / MINOR = **0**；Review Fix = **NOT REQUIRED**。

---

## 20. Feature 文档索引

完整 Requirement、Technical Design、Test Evidence、Explanation、Policy Reopen：

→ [`docs/features/F07-llm-provider-data-policy.md`](../features/F07-llm-provider-data-policy.md)

F09 Data Policy Open Item（仍 OPEN / RUNTIME VALIDATION PENDING）：

→ [`docs/features/F09-missing-slot-question-answer-mapping.md`](../features/F09-missing-slot-question-answer-mapping.md) · **OI-F09-DP-001**

---

# 21. Policy Reopen Code-Reading Update — 业务流程优先

> **历史层次：** Original F07 **CLOSED**。原策略：真实 Remote `USER_FREE_TEXT` 默认 **DENY**。Reopen **不推翻**原策略，而是增加显式 Demo Policy Profile；**DEFAULT = 原行为**。

## 21.1 你应该能回答的问题

读完本节应能回答：用户自然语言从哪进 F09；为何 F09 不直接决定事项；如何构造 `LlmRequest`；为何 HTTP 前要 Policy；DEFAULT vs DEMO_APPROVED；为何 Demo 可发 `USER_PII` 但 `UNKNOWN` 仍不能；DENY 为何 0 HTTP；LLM 回来后为何不能直接推进图；membership/confidence 在哪一层；何时 ACCEPTED 进 Graph；为何 `candidate_business_id ≠ confirmed_business_id`；为何 F10 仍有最终确认权。

## 21.2 核心业务主线

```text
用户：「平时接零活，没有固定单位」
  → F09 接收（当前 pending：employment_type）
  → detect_explanation_request？否 → slot mapping path
  → LlmAnswerMapper.map_answer(AnswerMappingRequest)
  → 构造最小 LlmRequest（含 USER_FREE_TEXT）
  → LlmProvider.complete → OpenAICompatibleLlmProvider
  → evaluate_request_remote_policy(request, profile)
       profile ← Settings.llm_remote_data_policy_profile
       DEFAULT        → 原 _REMOTE_ALLOW → USER_FREE_TEXT DENY → 0 HTTP
       DEMO_APPROVED  → Demo allow-set → MAY ALLOW
  → DENY → LlmProviderError(POLICY_DENIED) → STOP（不进 httpx）
  → ALLOW → 现有 OpenAI-compatible HTTP（≠ 已验证真实公司可用性）
  → structured mapping 回 F09
  → validate_slot_mapping：membership → confidence ≥ 0.80
  → ACCEPTED → F04 Business Decision Graph 确定性推进
  → Terminal candidate（如 DEMO_SS_001）仍须 F10 confirmation
       → confirmed_business_id
```

**Implementation Ready ≠ Real Runtime Verified。** 真实 Company LLM（RG-F12-004）仍 **PENDING**。

## 21.3 Step-by-step（业务 → 代码）

### Step 1 — 用户回答当前问题

| | |
|--|--|
| **业务** | 用户只是回答当前 slot（`employment_type`），不是直接选 `business_id`，也不是最终确认事项。 |
| **输入** | 自然语言：「平时接零活，没有固定单位」 |
| **权限** | 用户输入 ≠ 业务决策。 |
| **代码** | Agent F09 工作流节点消费 `input_text` + pending slot 上下文。 |

### Step 2 — F09 接收输入

| | |
|--|--|
| **业务** | 把自然语言解释成受控 slot value；**不**决定 Graph 怎么走。 |
| **组件** | `AnswerMappingRequest` · `LlmAnswerMapper` · `validate_slot_mapping` · `detect_explanation_request` |
| **位置** | `src/gov_service_agent/agent/interaction.py` |
| **权限** | F09 可：mapping / 本地校验；不可：`next_node` / `business_id` / rule。 |

### Step 3 — Explanation 优先旁路

| | |
|--|--|
| **业务** | 「灵活就业是什么意思？」= **问概念**；「平时接零活…」= **可能选 slot**。二者不可混淆。 |
| **组件** | `detect_explanation_request` → `EXPLANATION_REQUEST` → explanation side route |
| **权限** | 不写 slot、不推进 Graph、不产生 candidate、不改 rule；解释完仍回到同一 pending slot。 |
| **Reopen** | **未改变**该 invariant。 |

### Step 4 — 构造 LlmRequest（F09 Production 本次 0 change）

| | |
|--|--|
| **业务** | 需要 LLM 做受控映射时，只给模型：当前句子、当前 slot、允许值。 |
| **组件** | `LlmAnswerMapper.map_answer` |
| **Payload** | system instructions + `required_slot` + `allowed_values` + `user_text` |
| **不发送** | full AgentState / conversation history / checkpoint / orchestration_trace / `request_id` / `session_id` |
| **Classification** | USER message：`USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA`；SYSTEM message：`SYSTEM_CONTROL_DATA`。**禁止**为绕 Policy 伪造成 `SYNTHETIC_TEST_DATA`。 |
| **operation** | `f09_slot_answer_mapping`（元数据；**不**参与 Policy） |

### Step 5 — Provider 接手（不是 F09 直接 httpx）

| | |
|--|--|
| **业务** | 调用者与远程协议解耦。 |
| **组件** | `LlmProvider` Protocol → 实际 Remote：`OpenAICompatibleLlmProvider.complete` |
| **位置** | `llm/provider.py` · `llm/openai_compatible.py` |

### Step 6 — Provider Type ≠ Policy Profile（正交）

| 轴 | 回答的问题 | 取值 |
|----|------------|------|
| **Provider Type**（`LLM_PROVIDER`） | 怎么调用模型？ | `DEMO` / `OPENAI_COMPATIBLE` / unset→`NOT_CONFIGURED` |
| **Policy Profile**（`LLM_REMOTE_DATA_POLICY_PROFILE`） | 哪些业务数据允许 Remote？ | `DEFAULT` / `DEMO_APPROVED` |

**`OPENAI_COMPATIBLE` ≠ trusted。** Profile 不会改变 Provider selection；`NOT_CONFIGURED` + `DEMO_APPROVED` 仍不可调用。

### Step 7 — Settings 选择 Profile

| | |
|--|--|
| **配置** | `LLM_REMOTE_DATA_POLICY_PROFILE` → `Settings.llm_remote_data_policy_profile: RemoteDataPolicyProfile` |
| **默认** | `DEFAULT`（未配置 ≠ 自动 DEMO） |
| **非法** | 如 `ALLOW_ALL` → Settings **fail-fast**（不静默 DEMO） |
| **位置** | `settings.py`；类型定义 `llm/types.py` · `RemoteDataPolicyProfile` |
| **Factory** | `build_llm_provider` 仅向 `OpenAICompatibleLlmProvider(..., remote_data_policy_profile=...)` 传参 |
| **INFO RI-F07R-002** | 正式 Settings：fail-fast。Duck-typed 非法 object：防御性回落 **DEFAULT**（只收紧；非主配置路径）。 |

### Step 8 — HTTP 前 Policy Gate（核心）

| | |
|--|--|
| **业务** | 用户业务数据离开本进程前，必须过本地门禁。 |
| **顺序** | `complete` → `evaluate_request_remote_policy(request, profile)` → 仅 ALLOW 才 `httpx` |
| **DENY** | `LlmProviderError(POLICY_DENIED)` → **0 HTTP** → STOP |
| **Evaluator** | `evaluate_request_remote_policy` / `evaluate_remote_policy`（`llm/policy.py`）纯本地：只看 classifications + profile；不调 LLM、不读 Settings/env/URL/DB/Redis |

**DEFAULT** = 原 `_REMOTE_ALLOW`（**未因 Reopen 扩大**）：USER_FREE_TEXT / USER_PII / HIGH_SENSITIVE / TO_CONFIRM / UNKNOWN → **DENY**。

**DEMO_APPROVED** = Owner Demo 授权 allow-set：七类业务 MAY ALLOW；**UNKNOWN 仍 DENY**。

**DEMO_APPROVED 不是：** `skip_policy` / `allow_all` / `trusted=true` / `OPENAI_COMPATIBLE` 同义词 /「所有字符串可发」/ 生产默认。

### Step 9 — Multi-label / empty-set / PolicyDecision

| 例 | Demo 结果 |
|----|-----------|
| `{USER_FREE_TEXT, SYSTEM_CONTROL_DATA}` | **ALLOW**（全部 ∈ allow-set） |
| `{USER_FREE_TEXT, USER_PII}` | **ALLOW** |
| `{USER_FREE_TEXT, UNKNOWN}` | **DENY**；`denied_categories={UNKNOWN}` |

算法语义：`classifications ⊆ allow_set` → ALLOW，否则 DENY。
**Empty-set 风险：** 数学上 ∅ ⊆ allow_set 为真。实现先把 missing/empty **normalize → UNKNOWN**，再判定 → DENY。

`PolicyDecision`：`allowed` / `denied_categories` / `reason_code`（`POLICY_ALLOWED` / `POLICY_DENIED`）。合同未扩权。

**ALLOW 只表示：** 可继续交给 Remote Provider。
**不等于：** HTTP 成功 / mapping 合法 / confidence 足够 / Graph 可推进。

### Step 10 — Secret boundary

Owner 授权的是**用户业务数据**，不是系统凭据。
`LLM_API_KEY` / Authorization / Bearer / DB·Redis 密码 **不进** Prompt/`messages`；key 仅用于 HTTP transport auth。

### Step 11 — LLM 返回后：Mapping ≠ Business Decision

LLM 只返回 kind / mapped_value / confidence（例：`other_flexible_employment`）。
**不**等于已决定 `DEMO_SS_001`。

### Step 12–13 — 本地 membership + confidence

| | |
|--|--|
| **组件** | `validate_slot_mapping` + `MappingPolicy.min_confidence`（**0.80**） |
| **membership** | `mapped_value ∈ allowed_values`，否则 REJECT |
| **confidence** | `< 0.80` → 不交给 Graph 作为 validated slot |
| **ACCEPTED** | 才交给 F04 |

### Step 14 — Business Graph + F10

| 角色 | 权限 |
|------|------|
| **LLM** | 语言理解 / mapping / confidence |
| **F09** | 本地 validation |
| **F04 Business Graph** | 确定性推进（current_node + validated slots + edges） |
| **Rule Engine** | 规则终审 |
| **F10** | Terminal validation + 用户确认 → **`confirmed_business_id`** |
| **Knowledge** | 按 confirmed id 查事实 |

`candidate_business_id ≠ confirmed_business_id`。
RAG 找方向不变；F11 Session/Redis/checkpoint/audit **未改**。

## 21.4 权限总表

```text
LLM ──理解──► F09 校验 ──ACCEPTED──► F04 Graph ──candidate──► F10 确认 ──► Knowledge
     ✗ next_node / business_id / rule / confirmed_business_id
```

## 21.5 去哪里看代码（索引，非主结构）

| 关注点 | 位置 |
|--------|------|
| Profile 类型 | `llm/types.py` · `RemoteDataPolicyProfile` |
| Settings | `settings.py` · `llm_remote_data_policy_profile` |
| Factory | `llm/provider.py` · `build_llm_provider` |
| Remote Provider | `llm/openai_compatible.py` · `OpenAICompatibleLlmProvider` |
| Policy | `llm/policy.py` · `evaluate_*` · `_REMOTE_ALLOW` · `_REMOTE_ALLOW_DEMO_APPROVED` |
| F09 Mapper / validation / explanation detect | `agent/interaction.py` |
| Public export | `llm/__init__.py` |
| 安全示例配置 | `.env.example`（默认 DEFAULT） |

## 21.6 建议阅读顺序（业务）

1. Golden 用户输入（本 §21.2）
2. F09 如何构造 mapping request（`map_answer`）
3. Settings 如何选择 Profile
4. Provider 如何在 HTTP 前调 Policy
5. Policy 如何算 ALLOW/DENY（含 empty→UNKNOWN）
6. F09 membership / confidence
7. Business Graph 如何推进
8. F10 如何确认事项

（不要按文件名顺序当作主路径。）

## 21.7 常见误区

| # | 误区 | 正确 |
|---|------|------|
| 1 | `OPENAI_COMPATIBLE` = trusted | 仅协议；信任靠显式 Profile |
| 2 | `DEMO_APPROVED` = allow-all | 仅 Owner 批准业务分类；UNKNOWN 仍 DENY |
| 3 | Policy ALLOW = mapping 已接受 | 仍须 membership + confidence |
| 4 | LLM 可自行推进 Graph | 无 `next_node` 权 |
| 5 | Terminal candidate = confirmed | 须 F10 |
| 6 | Explanation = 选了某 slot | 旁路；不写 slot |

## 21.8 Test / Review Evidence（不重跑）

| Suite | Result |
|-------|--------|
| `test_llm_policy` | 29 passed |
| `test_llm_openai_compatible` | 34 passed |
| `test_settings` | 88 passed |
| `test_agent_interaction`（regression；未改） | 63 passed |
| `test_agent_workflow`（regression；未改） | 31 passed |
| Combined | 245 passed / 0 failed / 0 warnings |
| Full | **620 passed / 13 skipped / 0 failed / 0 warnings** |

| Review | Result |
|--------|--------|
| Status | **PASS**；BLOCKING/MAJOR/MINOR = **0**；INFO = **3**；Fix **NOT REQUIRED** |

### Review INFO Disposition

| ID | Disposition |
|----|-------------|
| RI-F07R-001 | Explanation 已同步 Feature Doc stage |
| RI-F07R-002 | Duck-typed → DEFAULT（fail-closed）；accepted；无 Code 改动 |
| RI-F07R-003 | Test helper 命名；无假阳性；无 Test 改动 |

## 21.9 Runtime Validation Still Pending

| 已证明 | 尚未证明 |
|--------|----------|
| Code capability READY | Company LLM authentication |
| Automated tests PASS | Endpoint reachability / model availability |
| Review PASS | Real response schema / real F09 USER_FREE_TEXT mapping |

| Blocker | Status |
|---------|--------|
| RG-F12-004 | **PENDING** |
| RG-F12-006 | **POLICY IMPLEMENTATION REVIEW PASS / RUNTIME VALIDATION PENDING** |
| F12 | **仍 BLOCKED** |
| OI-F09-DP-001 | **OPEN / RUNTIME VALIDATION PENDING**（关闭条件 = F12 真实 Remote USER_FREE_TEXT probe PASS） |

**禁止宣称：** 真实公司 LLM 已打通 / Golden E2E 已跑通 / F12 READY / RG-F12-004 已解除。

## 21.10 Original F07 §1–§20 怎么读

§1–§20 描述 Original CLOSED 基础设施。读 Policy 表时记住：**DEFAULT = 该表**；Demo 例外只在显式 `DEMO_APPROVED` 下生效，且 **UNKNOWN 永远 DENY**。
