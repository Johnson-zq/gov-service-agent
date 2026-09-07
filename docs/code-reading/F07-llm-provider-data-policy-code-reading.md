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

**功能状态：** Resource Gate / Requirement / Technical Design / Code / Test / Review / Explanation 均已完成；Review Fix = NOT REQUIRED。本文为 Owner 批准的 Code-Reading 文档（最终 Feature Scope = **18 paths**）。

验证证据（权威，来自 F07 Test / Review）：

| 项 | 结果 |
|----|------|
| Phase A unit | **160 / 160 PASS** |
| Default Full | **319 passed / 13 skipped / 1 known warning** |
| Real Provider Smoke | **PASS**（opt-in） |
| Real Structured | **DIRECT_JSON PASS** |
| Policy Denial | HTTP **0** / sleep **0** |
| compileall / pip check | **PASS** |
| Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 3） |

Known warning：Starlette `TestClient` + `httpx` deprecation（既有依赖告警，非 F07 regression）。

完整 Requirement / Design / Test / Review 依据见：

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
| `USER_FREE_TEXT` | 真实用户自然语言 | **DENY**（当前） |
| `USER_PII` | 用户个人身份相关 | **DENY** |
| `HIGH_SENSITIVE_IDENTITY` | 高敏感身份类 | **DENY** |
| `TO_CONFIRM_OR_INTERNAL` | 待确认或内部敏感 | **DENY** |
| `UNKNOWN` | 未声明 / 无法判断 | **DENY** |

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
- `USER_FREE_TEXT` 当前 Remote DENY；`UNKNOWN` Fail Closed
- Mixed 含 DENY → 整请求拒绝
- Real Smoke 只 synthetic / system-control
- 不从自然语言宽松抽 JSON
- 文档不写真实 Base URL / API Key / 公司 Model ID

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

完整 Requirement、Technical Design、Test Evidence、Explanation：

→ [`docs/features/F07-llm-provider-data-policy.md`](../features/F07-llm-provider-data-policy.md)
