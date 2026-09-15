# F11 Session API / Redis / Checkpoint / Audit

## 1. Feature Status

| 字段 | 内容 |
|------|------|
| Feature ID | F11 |
| Feature Name | Session API / Redis / Checkpoint / Audit |
| 中文定位 | 跨 HTTP 请求的 Session、Checkpoint、Audit 与 Redis 持久化边界 |
| Current Stage | **Code-Reading = COMPLETE**；Recommended Next = **Commit**（须 Owner 单独授权） |
| 前置 Feature | F00–F10 = CLOSED |
| Git Baseline HEAD | `85f4a7cb1e3ed632525974a4f297e9d115314381` on `develop` |
| Acceptance Criteria | **92**（AC-F11-001 … AC-F11-092；内容未改） |
| Requirement Open Items | **0** |
| Requirement Finalization | **NOT REQUIRED** |
| Technical Design Decisions | **D-F11-001 … D-F11-040**（40） |
| TD Open Items | **0** |
| Technical Design Finalization | **COMPLETE** |
| Final Planned Paths | **12**（Code-Reading Doc 已创建；落地路径 = 12） |
| Production Code This Stage | **session package + Settings + redis==5.3.1**（Code-Reading 只读；未改 Production/Tests） |

| 阶段 | 状态 |
|------|------|
| F11 Resource Gate | **CLOSED / READY** |
| F11 Requirement | **COMPLETE** |
| F11 Requirement Finalization | **NOT REQUIRED** |
| F11 Technical Design | **FINAL / CLOSED** |
| F11 Technical Design Finalization | **COMPLETE** |
| F11 Confirm | **COMPLETE** |
| F11 Code | **COMPLETE** |
| F11 Test | **PASS** |
| F11 Review | **PASS** |
| F11 Review Fix | **COMPLETE** |
| F11 Re-Review | **PASS** |
| F11 Explanation | **COMPLETE** |
| F11 Code-Reading | **COMPLETE** |
| F11 Commit | **NOT STARTED** |
| F11 Push | **NOT STARTED** |

**本阶段 = Code-Reading COMPLETE。禁止自动进入 Commit / Push（须 Owner 单独授权）。本阶段仅新增 Code-Reading Doc 并更新本 Feature Doc。**

**一句话定位：** F11 负责跨 HTTP 请求的会话连续性（Session / Checkpoint / Audit）；**不**拥有业务事项决策权，**不**替代 F08–F10；真实 Government Processor 与 `main.py` activation 属 **F12**。

---

## 2. Business Problem

F08–F10 已具备 Agent State、缺槽交互、解释旁路、终点校验与用户确认等 capability。
这些能力当前主要在「一次显式 Python 调用」或「调用方手工保存 context」下成立。

真实用户交互中，第一句与第二句通常是**两个独立 HTTP Request**。若没有跨请求持久化：

- 系统不知道是否同一会话；
- 不知道上一轮走到何处、等待哪个 slot、哪些事实已确定；
- 每一轮可能从头开始。

**F11 要解决：跨 HTTP Request 的政务业务会话连续性。**

---

## 3. Business Goal

F11 必须提供：

1. Session API（业务交互入口边界）
2. Session identification（opaque session identity）
3. Checkpoint restore（恢复上一轮受控状态）
4. One-turn Agent invocation boundary（委托业务处理）
5. Checkpoint save（保存本轮稳定受控状态）
6. Audit recording（持久业务审计事件）
7. Controlled API response（受控对外返回）

从而实现：**同一 session 可跨多个 HTTP Request 持续推进同一次政务业务交互。**

---

## 4. Architecture Position

### 4.1 Canonical Flow 中的位置

```text
用户自然语言
→ Agent Orchestration（F08）
→ Semantic Retrieval（F06；方向召回）
→ Business Decision Graph（F04）
→ Missing slots / answer mapping（F09）
→ Terminal validation / confirmation（F10）
→ Session / Redis / Checkpoint / Audit（F11）   ← 本 Feature
→ E2E Demo（F12）
```

### 4.2 业务真相来源不变

| 能力 | 职责 |
|------|------|
| Semantic Retrieval | 找方向 / 候选 |
| LLM | 自然语言理解 / 受控映射 |
| Business Decision Graph | 确定性推进 |
| Rule layer | readiness / 后续 deterministic validation |
| F10 | 最终事项身份确认 |
| **F11** | Session / Checkpoint / Audit infrastructure |

**禁止：** LLM / Session / Redis / Checkpoint / Audit 决定 `next_node` 或 `business_id` / `confirmed_business_id`。
F11 只保存与恢复**已由受控业务能力产生**的状态。

### 4.3 Resource Gate 已确认事实（输入，非 TD）

| 资源 | 事实 |
|------|------|
| Python | 3.11.16 |
| FastAPI | READY（现有 `app`） |
| LangGraph | 1.2.11 READY |
| AgentState serialization | FEASIBLE |
| Dev Redis | Docker Redis **7.4.11**，`govagent-redis-dev`，`127.0.0.1:6379`，loopback only |
| Local Resource Gate AUTH | NONE（**仅开发 Resource Gate**；≠ 生产） |
| redis-py | 5.3.1；PING True |
| PostgreSQL / Company LLM / Embedding / KG | F11 Resource Gate **NOT REQUIRED** |

Legacy Windows Redis 3.2.100 = **RETIRED FROM F11 DEV RUNTIME**（安装保留）。

---

## 5. User-to-Result Business Flow

Requirement、未来 Explanation、未来 Code-Reading 的**主线**：

```text
用户发送本轮输入
        ↓
Session API
        ↓
判断：新 session 还是已有 session
        ↓
已有 session：恢复上一轮 checkpoint
        ↓
准备本轮 Agent State（恢复态 + 本轮 input）
        ↓
调用 Agent Turn Processing Boundary
        ↓
得到本轮处理后的 controlled state
        ↓
保存新的 checkpoint
        ↓
记录 audit event
        ↓
生成 public API response
        ↓
用户拿到：本轮结果 + session identity（及 request identity）
```

顺序约束：

1. **已有 session：** 必须先 validate session → load checkpoint → validate checkpoint → prepare current turn → Agent processing。
   **禁止**先处理新 input 再恢复。
2. **成功 turn：** 先形成本轮稳定 controlled state，再保存 checkpoint。
   **禁止**把未处理 input 当最终 checkpoint。
3. **失败 turn：** 不得覆盖上一轮最后有效 checkpoint。

---

## 6. Session Semantics

### 6.1 新 Session

- 客户端首次交互**允许不提供** session identity。
- 系统必须创建新 session，并分配 **opaque session identifier**，供下一轮继续。
- identifier **不得**：由用户业务原文派生；包含业务真相/敏感字段；采用易猜测简单递增（实现细节 TD）。
- 创建 session **不等于**已识别业务类别、已选择/确认事项。

### 6.2 已有 Session

- 客户端提供已有 identity 时，系统必须尝试恢复该 session 的**最新有效 checkpoint**。
- 成功后，本轮输入必须在**恢复后的业务上下文**上继续。
- **禁止**创建同 ID 空 session 并假装恢复成功。

### 6.3 Unknown / Expired

| 情况 | 要求 |
|------|------|
| Unknown session | **Fail closed** → controlled failure / session unavailable；**禁止** silent-create |
| Expired session | controlled session-expired result；**禁止**偷偷新建 session 继续原输入 |

Exact HTTP status / error code / JSON → **TD**。

### 6.4 Session ≠ User Account

F11 Phase 1 **不实现**登录、账号、OAuth、SSO、实名绑定。
session identity **不能**被表述为用户身份证明。Production identity/auth = 后续独立能力。

### 6.5 Isolation

Session A **不得**读取 Session B 的 checkpoint。不同 session 状态不混用。

---

## 7. Request vs Session Identity

| 标识 | 语义 |
|------|------|
| **session identity** | 一段多轮业务交互的身份（跨多轮不变） |
| **request identity** | 单个 HTTP Request / 单轮处理身份 |

示例：Session S1 的 Turn1/2/3 可有 R1/R2/R3；session 始终 S1。
**禁止**把 request identity 当作 session identity。

---

## 8. Checkpoint Semantics

### 8.1 定义

**Checkpoint** = 为使下一次 HTTP Request 能继续上一轮业务流程，所保存的**最小必要、受控、可恢复** Agent 状态快照。

Checkpoint **不是**：聊天全文、LLM Memory、整个 Python Runtime。

### 8.2 业务作用

下一轮**不得**靠把历史对话重扔给 LLM 去猜「上一轮走到哪」。应直接恢复已确定的 controlled state（语义上可含：phase、transition、pending slot、validated slots、F09/F10 相关受控状态等）。
**Exact schema → TD。**

### 8.3 最小化与禁止持久化对象

只保存恢复下一轮真正需要的数据。

**禁止**作为 checkpoint：LLM provider、Redis client、DB connection、Repository、compiled graph、callable、Exception、HTTP Request、dependency container、API key、password。

Runtime dependency 继续通过注入传递；**不得**为 Redis 方便塞进 AgentState。

### 8.4 序列化与版本

- 必须 JSON-safe 或等价稳定 serialization contract；**禁止** pickle 任意 runtime object。实现 → TD。
- 必须有 schema/version identity；版本不支持 → fail closed。Phase 1 **不要求**自动 migration。
- Phase 1：每个 active session **至少**维护 **latest recoverable checkpoint**。
  **不要求**完整历史列表、time-travel、undo、checkpoint browser。

### 8.5 Latest / Failure

- 本轮失败（Agent / serialization / persistence / validation）**不得**覆盖最后有效 checkpoint。
- corrupt / 缺字段 / malformed / semantic invalid → fail closed；**禁止**让 LLM 猜恢复内容；**禁止**覆盖 corrupt 并假装新 session。

---

## 9. Data Minimization

1. Checkpoint **默认不保存**完整历史 raw `USER_FREE_TEXT`；不得累积 `user_messages=[...]` 式 transcript memory。
2. `input_text` 是**当前 turn runtime input**；完成本轮后，持久 checkpoint 只保留恢复下一轮所需最小 controlled state。历史 USER_FREE_TEXT **默认不进**长期 checkpoint。Sanitize → TD。
3. F11 **不实现** conversation transcript memory；完整对话历史若未来需要，须独立 Feature / 数据策略。
4. **不建立**跨 session 用户画像 / 长期个人记忆。
5. current-turn input 与 persisted business context **语义分离**（保护 F10 stale-input 安全）。实现 → TD。

---

## 10. Redis Responsibility

| Redis 是 | Redis 不是 |
|----------|------------|
| live Session / Checkpoint 持久化载体（Phase-1 Demo SoT） | 业务规则库 / 知识库 / Business Graph / 向量库 / LLM Memory / 业务真相来源 |

约束：

- Redis 查不到时：**禁止** silent 回退 process memory。正式 runtime 必须 controlled fail。
- 只要 Redis 仍保留 checkpoint，FastAPI process restart 后已有 session **必须可恢复**。
- Phase 1 **不保证** Docker container 删除、数据彻底丢失、磁盘故障后的恢复。Production HA/durability = out of scope。
- Session/checkpoint 必须支持 **configurable inactivity TTL**（不可写死在业务代码）；exact 秒数/刷新算法 → TD。
- Local Docker Redis no-auth + loopback = **开发 Resource Gate 事实**；**不是**生产 Requirement。非 loopback 部署须有适当网络隔离与 credential handling（方案 DEFERRED）。

---

## 11. Multi-turn Continuity

- 同一 session 连续 turn 必须能恢复上一轮业务状态。
- 上一轮已验证状态不得因新 HTTP request 丢失。
- Active session 恢复后，F11 **不强制**每轮重新 global RAG；intent switch / re-entry 由 Agent/business workflow 决定。
- Session A 结束后，Session B **不得默认**继承 A 的 slot/state。

---

## 12. F09 Compatibility

F11 必须支持：

1. **Pending slot：** 上一轮缺槽提问后，checkpoint 使下一轮知道等待哪个 slot；用户回答后在恢复态上交给 F09，而非全局意图检索重开。
2. **Explanation side route：** 用户问「选项是什么意思」时，恢复仍等待原 slot 的状态；解释后 checkpoint 仍等待原 slot；真正回答后继续同一 pending slot。**禁止**因解释丢掉原业务节点。

---

## 13. F10 Compatibility

F11 必须支持：

1. **PREPARE：** 保存下一轮可安全进入 RESOLVE 的 controlled context。
2. **RESOLVE：** 下一轮用户「确认」等输入在恢复后交给 F10 RESOLVE。
3. **Stale-input：** PREPARE 不得把导致 terminal 的旧句误当确认；restore 不得让旧 `input_text` 被重新解释为确认。current input 与 persisted context 语义分离。
4. **Invariant：** `TERMINAL_CANDIDATE` / `candidate_business_id` **≠** `confirmed_business_id`，直至用户在新确认 turn 明确确认。Redis 存在不改变此不变式。
5. **Authority：** `confirmed_business_id` **只能**来自 F10 controlled path；F11/客户端 **不得**自行赋值或 HTTP 覆盖。

---

## 14. Agent Turn Boundary

必须存在 **Agent Turn Processing Boundary**：

- **输入：** 恢复后的 controlled state + 本轮 input
- **输出：** 本轮新 controlled state + 本轮 public response information

F11 API **只负责调用**该 boundary；**禁止** Session Service 自行实现 slot mapping、graph transition、confirmation parsing、RAG、knowledge lookup。
function name / sync-async / DI → **TD**。

---

## 15. API Public Behaviour

### 15.1 客户端可提交

session identity（可选，新会话可不提供）+ 本轮业务输入 + 未来可能的受控 request metadata。

### 15.2 客户端不得提交作为权威

完整 AgentState、`current_node`、`candidate_business_id`、`confirmed_business_id`、pending slot 等以覆盖 server checkpoint。
**Checkpoint authority = server side。**

### 15.3 成功响应（逻辑最小集）

至少语义包含：

- session identity
- request identity
- 本轮 response text
- controlled processing status
- 必要时：是否仍需用户输入 / next interaction state（受控公共信息）

**Exact JSON names → TD。**

### 15.4 禁止默认返回

完整 AgentState、完整 artifacts、checkpoint dump、Redis/checkpoint key、internal node ID、debug trace。

### 15.5 输入校验

Transport-level：missing / empty / whitespace-only / oversized → controlled failure。
Exact 最大长度 / model / HTTP code → TD。
业务内容是否有效社保输入 → **不归** Session API，交给 Agent/downstream。

### 15.6 response_text

由 Agent turn result 产生；F11 只包装受控 public response。

### 15.7 Phase-1 不提供

session list、public delete、session search、transcript endpoint、public audit query API。

---

## 16. TTL / Expiration

- Session / checkpoint：**configurable inactivity TTL**。
- 成功处理 active turn 后应更新 activity。
- 过期 session：**不得**从不可信残留继续执行；返回 controlled expired result。
- Exact TTL / refresh / Redis command → **TD**。
- Live session state **不是**永久数据。

---

## 17. Concurrency / Retry

1. **Same-session concurrency：** 禁止两个请求同读旧 checkpoint 后互相覆盖（lost update）。须有 session-scoped concurrency protection 或等价冲突预防。机制（lock/version/CAS/…）→ TD。
2. **Different sessions：** 不应因全局单锁全部串行；隔离以 session scope 为核心。
3. **Retry/duplicate：** HTTP 重试可能导致同一输入处理两次。TD **必须**考虑 request-level duplicate protection 或等价机制。
   Requirement **不冻结** idempotency key schema；记为 **REQUIRED DESIGN CONSIDERATION**。
   不要求金融级 exactly-once，但须防止明显重复导致业务图推进两次、确认执行两次、checkpoint lost update。

---

## 18. Audit Semantics

### 18.1 目的

回答：属于哪个 session / 哪次 request、何时发生、从何受控状态开始、本轮状态变化类型、成功或失败、最终受控状态。
Audit **不决定**业务流程。

### 18.2 与 Logging / Trace

F01 Application Logging ≠ F11 Business Audit。
`orchestration_trace` ≠ durable Audit。

### 18.3 持久化

- Phase 1 Audit event 须跨 FastAPI process restart 仍可保留；**禁止**仅 console log。
- Storage 可为 Redis；**PostgreSQL 非强制**。Exact → TD。
- Session checkpoint 过期/删除 **不语义上强制** Audit 同时消失；Audit 有独立 retention lifecycle。Exact retention → TD/config。

### 18.4 内容约束

| 允许（逻辑） | 禁止 |
|--------------|------|
| session/request identity、timestamp、event type、outcome、before/after phase-status、checkpoint version、failure category / controlled error code、capability/stage name | 完整 raw USER_FREE_TEXT；secret；provider/repo/Redis client/Exception 序列化 |

### 18.5 Append

Audit = 事件记录；**append / immutable-event style**；禁止每次覆盖上一条。结构 → TD。

### 18.6 Public API

Phase 1 **不要求**公开 Audit 查询 endpoint / UI / 导出。

### 18.7 失败

- 可持久化时，失败 turn 应产生 safe failure audit。
- Redis 整体不可用导致 Audit backend 不可用时，不要求不可能完成的持久 Audit；可用 Application Logging 记 operational error，**不得**声称其为 durable audit。
- 正常情况下 Audit 持久化失败 **不可静默忽略**；须明确内部失败结果。与 Checkpoint 一致性机制 → TD。

---

## 19. Failure Behaviour

### 19.1 Controlled error families（逻辑类别；exact 名/HTTP → TD）

INVALID_REQUEST、SESSION_NOT_FOUND、SESSION_EXPIRED、CHECKPOINT_INVALID、CHECKPOINT_VERSION_UNSUPPORTED、SESSION_CONFLICT、PERSISTENCE_UNAVAILABLE、AUDIT_PERSISTENCE_FAILED、AGENT_TURN_FAILED。

### 19.2 规则

- 新 session 无法持久化初始化 → **不得**返回看似可用的 session identity。
- Agent 算出新 state 但 save 失败 → **不得**声称下一轮可继续；controlled persistence failure；不破坏最后有效 checkpoint。
- 成功 turn：**仅当**所需持久状态成功保存后，才可视为 durably completed。
- Unexpected exception：对外 controlled error；对内 structured logging；**禁止**返回 stack/Redis URL/secret/internal object。

---

## 20. Security / Data Policy

1. Checkpoint / Audit / public response / Git / Feature Doc **不得**含 Redis credential、LLM key、DB secret、Authorization、token。
2. Local no-auth Redis = **dev-only Resource Gate fact**。
3. Production Redis security / network / credential = **DEFERRED**（Requirement 要求未来非 loopback 须有适当措施，但不冻结方案）。
4. Session ID：opaque、不含业务数据、不可易枚举。
5. 客户端不知 Redis/checkpoint/audit storage key。

---

## 21. Architecture Boundaries

| F11 做 | F11 不做 |
|--------|----------|
| Session API、Checkpoint lifecycle、Redis live persistence、Audit、HTTP continuity | 新 Business Graph、slot mapping、confirmation parser、RAG、KG、新 LLM 决策权 |
| 复用现有 FastAPI `app` | 第二 HTTP Server / 新 FastAPI port |
| Phase-1 可用 Redis 满足 Demo | 强制 PostgreSQL |
| HTTP turn boundary checkpoint | 每 LangGraph node 自动 checkpoint |

Redis **不是**业务 truth source。

---

## 22. F11 vs F12

| Feature | 负责 |
|---------|------|
| **F11** | Session API、Checkpoint lifecycle、Redis persistence、Audit、HTTP continuity |
| **F12** | 完整 Demo E2E（NLU/RAG、Graph、F09、F10、后续业务查询等串联） |

F11 **不得**为展示而把 F03–F10 重组成新的完整业务系统。

---

## 23. Business Scenarios

### A. 新 Session

用户首次：「我辞职了，现在没单位，想自己交社保」（无 session ID）。
F11：创建 session → 分配 identity → 初始 controlled state → Agent Turn → save checkpoint → audit → 返回 session/request identity、response text、controlled status。用户无需理解 Redis。

### B. 继续 Session

客户端带回同一 session ID；用户：「平时接零活，没有固定单位」。
F11：恢复 checkpoint → restored state + 本轮 input → Agent。用户体验为接着上一轮，而非重问「你要办什么」。

### C. F09 Explanation

等待 slot 时用户问「这个选项是什么意思」。
恢复仍等待该 slot → F09 explanation → 新 checkpoint 仍等待原 slot → 下一轮真正作答后继续。

### D. F10 Confirmation

PREPARE 请用户确认候选事项 → F11 保存等待确认 context → 用户「确认」→ 恢复后 F10 RESOLVE → 仅 F10 可产生 `confirmed_business_id` → F11 保存新状态。
**F11 不得**因看到「确认」自行 `confirmed = candidate`。

### E. Redis 不可用

下一轮时 Redis 不可访问 → controlled unavailable；**禁止**空 state 继续。

### F. Session Expired

过期 session ID → controlled expired/unavailable；**禁止**当新 session。重新办理须主动新开 session。

### G. Concurrent Requests

同 session 近乎同时两请求 → 须防同读旧 checkpoint 后互相覆盖。机制 → TD。

---

## 24. Acceptance Criteria

共 **92** 条。均可验证，且不与 F08–F10 invariant 冲突。Exact 实现细节属 TD。

### A. Session API

| ID | Criterion |
|----|-----------|
| **AC-F11-001** | 客户端可发起新 session turn，无需预先提供 session identity |
| **AC-F11-002** | 新 session 成功后返回可供下一轮使用的 opaque session identity |
| **AC-F11-003** | 客户端可用已有 session identity 继续同一业务交互 |
| **AC-F11-004** | 每一轮 HTTP request 具有独立 request identity |
| **AC-F11-005** | session identity 与 request identity 语义独立 |
| **AC-F11-006** | API 不接收客户端完整 AgentState 作为 server state authority |
| **AC-F11-007** | API 不直接暴露完整 internal AgentState/artifacts |
| **AC-F11-008** | 成功响应提供 session identity、request identity、response text、controlled status |

### B. Session Identity

| ID | Criterion |
|----|-----------|
| **AC-F11-009** | session identifier opaque |
| **AC-F11-010** | session identifier 不包含业务敏感字段 |
| **AC-F11-011** | session identifier 不可简单依赖可枚举递增值 |
| **AC-F11-012** | unknown session 不得 silent-create |
| **AC-F11-013** | expired session 不得 silent-create |
| **AC-F11-014** | Session A 不得恢复 Session B state |
| **AC-F11-015** | new session 不等于业务事项已确定 |

### C. Checkpoint

| ID | Criterion |
|----|-----------|
| **AC-F11-016** | 已有 session 在处理新 input 前先恢复 checkpoint |
| **AC-F11-017** | checkpoint 保存恢复下一轮所需最小 controlled state |
| **AC-F11-018** | checkpoint 不持久化 runtime dependency object |
| **AC-F11-019** | checkpoint 不持久化 secret |
| **AC-F11-020** | checkpoint 可稳定序列化 |
| **AC-F11-021** | checkpoint 有 schema/version identity |
| **AC-F11-022** | 至少维护 latest recoverable checkpoint |
| **AC-F11-023** | 本轮失败不得破坏最后有效 checkpoint |
| **AC-F11-024** | unsupported checkpoint version fail closed |
| **AC-F11-025** | corrupt checkpoint fail closed |
| **AC-F11-026** | checkpoint 恢复不得依赖 LLM 重新猜历史 controlled facts |

### D. Data Minimization

| ID | Criterion |
|----|-----------|
| **AC-F11-027** | checkpoint 默认不保存完整历史 raw USER_FREE_TEXT |
| **AC-F11-028** | F11 不建立完整 transcript memory |
| **AC-F11-029** | F11 不建立跨 session user profile memory |
| **AC-F11-030** | current-turn input 与 persisted business state 语义分离 |
| **AC-F11-031** | public response 不得默认包含 Redis/checkpoint key |

### E. Redis Persistence

| ID | Criterion |
|----|-----------|
| **AC-F11-032** | Redis 是 Phase-1 live session/checkpoint persistence source |
| **AC-F11-033** | Redis unavailable 时不得 silent in-memory fallback |
| **AC-F11-034** | Redis state 保留时，FastAPI process restart 后 session 可恢复 |
| **AC-F11-035** | Session/checkpoint 支持 configurable inactivity TTL |
| **AC-F11-036** | session expiration 产生 controlled result |
| **AC-F11-037** | F11 不要求 Redis container deletion 后仍可恢复 session |

### F. Multi-turn Continuity

| ID | Criterion |
|----|-----------|
| **AC-F11-038** | 同一 session 连续 turn 能恢复上一轮业务状态 |
| **AC-F11-039** | 上一轮 validated state 不因新 HTTP request 丢失 |
| **AC-F11-040** | 不同 session state 隔离 |
| **AC-F11-041** | F11 不强制每一轮重新 global RAG |

### G. F09 / F10 Compatibility

| ID | Criterion |
|----|-----------|
| **AC-F11-042** | F09 pending slot 可跨 request 保存和恢复 |
| **AC-F11-043** | F09 explanation side route 后原 pending slot 可继续 |
| **AC-F11-044** | F10 PREPARE waiting state 可跨 request 保存 |
| **AC-F11-045** | 下一 request 可在恢复 context 后进入 F10 RESOLVE |
| **AC-F11-046** | F10 stale-input safety 不被 checkpoint restore 破坏 |
| **AC-F11-047** | TERMINAL_CANDIDATE 不得因 persistence 自动变 confirmed_business_id |
| **AC-F11-048** | confirmed_business_id 仍只能来自 F10 controlled path |

### H. Audit

| ID | Criterion |
|----|-----------|
| **AC-F11-049** | F11 产生 durable business audit event |
| **AC-F11-050** | Logging 不等于 Audit |
| **AC-F11-051** | Audit 采用 append/event semantics |
| **AC-F11-052** | Audit 默认不保存完整 raw USER_FREE_TEXT |
| **AC-F11-053** | Audit 不保存 secret |
| **AC-F11-054** | Audit 记录 session/request identity |
| **AC-F11-055** | Audit 记录 controlled outcome |
| **AC-F11-056** | Audit 生命周期与 session checkpoint 语义分离 |
| **AC-F11-057** | Phase 1 不要求 public audit query API |

### I. Consistency / Concurrency

| ID | Criterion |
|----|-----------|
| **AC-F11-058** | 成功 turn 不能在 checkpoint 未持久化时对外宣称 durable success |
| **AC-F11-059** | checkpoint save failure 不覆盖最后有效 checkpoint |
| **AC-F11-060** | 可完成时 Audit persistence failure 不可静默忽略 |
| **AC-F11-061** | same-session concurrent requests 不能 silent lost update |
| **AC-F11-062** | different sessions 不因全局串行锁被强制全部串行 |
| **AC-F11-063** | duplicate/retry 风险必须进入 TD 设计 |

### J. Failure Handling

| ID | Criterion |
|----|-----------|
| **AC-F11-064** | missing/empty input → controlled failure |
| **AC-F11-065** | whitespace-only input → controlled failure |
| **AC-F11-066** | oversized input → controlled failure |
| **AC-F11-067** | unknown session → controlled failure |
| **AC-F11-068** | expired session → controlled failure |
| **AC-F11-069** | invalid checkpoint → controlled failure |
| **AC-F11-070** | unsupported checkpoint version → controlled failure |
| **AC-F11-071** | Redis unavailable → controlled failure |
| **AC-F11-072** | Agent Turn failure → controlled failure |
| **AC-F11-073** | unexpected exception 不向用户暴露 traceback/internal secret |

### K. Architecture Boundaries

| ID | Criterion |
|----|-----------|
| **AC-F11-074** | F11 不实现新的 Business Decision Graph logic |
| **AC-F11-075** | F11 不实现新的 slot mapping |
| **AC-F11-076** | F11 不实现新的 confirmation parser |
| **AC-F11-077** | F11 不新增 LLM decision authority |
| **AC-F11-078** | F11 不新增 RAG business authority |
| **AC-F11-079** | F11 不新增 Knowledge Graph authority |
| **AC-F11-080** | Redis 不成为业务 truth source |
| **AC-F11-081** | 客户端不能直接覆盖 confirmed_business_id |
| **AC-F11-082** | F11 通过 Agent Turn boundary 委托业务处理 |
| **AC-F11-083** | F12 负责完整 E2E 业务串联 |

### L. Runtime / Deployment / Documentation

| ID | Criterion |
|----|-----------|
| **AC-F11-084** | F11 复用现有 FastAPI application |
| **AC-F11-085** | F11 不新增 HTTP server port |
| **AC-F11-086** | PostgreSQL 不是 F11 Phase-1 硬依赖 |
| **AC-F11-087** | Local Docker Redis no-auth ≠ production security requirement |
| **AC-F11-088** | Production Redis security 保持独立 deployment consideration |
| **AC-F11-089** | Explanation 按用户输入到结果的业务生命周期讲解 |
| **AC-F11-090** | Code-Reading 按用户输入到结果的业务生命周期讲解 |
| **AC-F11-091** | Code-Reading 每步说明 module/function、business purpose、input、output、next consumer |
| **AC-F11-092** | Code-Reading 最终必须讲到用户实际收到的 API response |

---

## 25. Out of Scope

F11 Phase 1 **不包含**：

完整 F03–F10 E2E wiring；Knowledge Graph query；Navigation；ASR；full conversation transcript；user account/login；SSO；session search/list；public session delete API；public audit query API；audit UI；admin console；multi-device account sync；cross-session personal memory；production Redis cluster/Sentinel/HA/backup；node-level workflow checkpoint；full checkpoint history；rollback/time-travel；PostgreSQL migration；business rule evaluator；production deployment hardening。

---

## 26. Deferred Decisions（Technical Design）

| ID | Topic |
|----|-------|
| **D-F11-REQ-001** | Exact HTTP contract（path / JSON / status） |
| **D-F11-REQ-002** | Exact Redis namespace/key schema |
| **D-F11-REQ-003** | Exact TTL duration / refresh |
| **D-F11-REQ-004** | Checkpoint physical schema |
| **D-F11-REQ-005** | Checkpoint serialization implementation |
| **D-F11-REQ-006** | Audit physical schema/storage structure |
| **D-F11-REQ-007** | Audit retention duration |
| **D-F11-REQ-008** | Same-session concurrency mechanism |
| **D-F11-REQ-009** | Retry/idempotency mechanism |
| **D-F11-REQ-010** | Redis sync/async client choice |
| **D-F11-REQ-011** | LangGraph checkpointer vs custom persistence |
| **D-F11-REQ-012** | Production Redis auth/network deployment |

另不冻结：Pydantic/class/function 名、Redis command、APIRouter 是否引入、pipeline/MULTI/Lua、exact error enum 字符串等。

---

## 27. Requirement Open Items

**Count = 0。**

无阻塞业务语义、需 Owner 额外拍板的 Requirement Open Item。
技术选型均已列入 Deferred Decisions，不作为 Requirement Open Item。

**Requirement Finalization Needed = NO。**

---

## 28. Requirement Evidence

| 项 | 结论 |
|----|------|
| 基于 Resource Gate READY | YES |
| 业务主线 = 用户输入→结果 | YES |
| F08–F10 invariant 保持 | YES |
| AC ≥ 80 | YES（92） |
| Exact TD 细节未冻结 | YES |
| Production/Tests/deps/Docker 项目文件未改 | YES |

---

## 29. Resource Gate Evidence（保留）

以下为已关闭 Resource Gate 的真实记录摘要，**不得覆盖删除迁移事实**。

### 29.1 Final Resource Decision

| 维度 | 状态 |
|------|------|
| F11 Resource Gate | **CLOSED / READY** |
| Legacy Redis 3.2.100 | STOPPED / RETIRED FROM F11 DEV RUNTIME；path `G:\AWaiMai\Redis`；config unmodified；not uninstalled |
| Docker Redis | `redis:7.4-alpine` → server **7.4.11**；container `govagent-redis-dev` |
| Host bind | `127.0.0.1:6379`（loopback only；非 0.0.0.0） |
| Local AUTH | NOT CONFIGURED（dev Resource Gate only） |
| CLI PING | PONG |
| redis-py | **5.3.1**；Python PING True；pip check PASS |
| pyproject.toml | UNCHANGED（manifest DEFERRED） |
| Image pull note | docker.io unreachable；via `docker.m.daocloud.io/library/redis:7.4-alpine` then tagged；digest `sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf` |

### 29.2 Findings Closure

| ID | Status |
|----|--------|
| RF-F11-RG-001 | RESOLVED |
| RF-F11-RG-006 | RESOLVED |
| RF-F11-RG-015 | RESOLVED FOR LOCAL RESOURCE GATE |
| RF-F11-RG-016 | RESOLVED |
| RF-F11-RG-017 | INFO（mirror pull path） |

### 29.3 Non-production disclaimer

Local Resource Gate runtime（Redis 7.4 Docker、loopback、no AUTH）**不是**生产永久无密码、不是生产固定 7.4、不是生产固定 Docker。Production Redis security = Requirement/TD deferred consideration。

---

## 30. Future Explanation / Code-Reading Rule

自 F11 起，Explanation / Code-Reading **必须以业务请求生命周期为主线**，不能以文件结构为主线。

固定开头：

```text
用户输入
→ HTTP API
→ Session resolution
→ Checkpoint load
→ Agent Turn
→ Checkpoint save
→ Audit
→ API response
```

每一步至少回答：

1. 用户此时想完成什么？
2. HTTP 请求来到哪里？
3. 系统调用哪个模块 / function？
4. 该模块业务上为什么存在？
5. 它读什么？
6. 它输出什么？
7. 下一步谁消费？
8. 失败时用户看到什么？

示例口径：用户第二次发消息时，Session 层按 session identity 从 Redis 恢复 checkpoint——Redis **不**判断办什么事项，只恢复已确定业务状态，再交给 Agent 处理本轮新输入。指南必须讲到用户最终收到的 API response。

---

## 31. Technical Design Overview

本 TD 将 Requirement 的 92 条 AC 落成可实现设计。设计主线仍是：

```text
用户一轮 HTTP 输入 → Session API → 恢复/创建 → Agent Turn Boundary → 持久化 → Audit → Public Response
```

**真实代码盘点结论（Agent Turn Processor Gate）：**

| 现有 public runner | 作用 | 是否满足「统一 one-turn business processor」 |
|--------------------|------|-----------------------------------------------|
| `run_agent_workflow` | F08 skeleton：prepare→complete | **否** |
| `run_slot_interaction_workflow` | F09 专用 | **否** |
| `prepare_terminal_confirmation` / `resolve_terminal_confirmation` | F10 专用 | **否** |

**CURRENT PRODUCTION BINDING = NOT CURRENTLY AVAILABLE**（且**不得**把任一 runner 冒充统一 Processor）。

**TD Finalization 关闭方案（Dependency Inversion）：**

| 层 | Owner |
|----|-------|
| `AgentTurnProcessor` Protocol + `AgentTurnResult` | **F11**（正式 Production integration contract） |
| Session API capability（router factory / service / store / models） | **F11** |
| Concrete Government Agent Turn Processor | **F12** |
| Composition root（`main.py` include_router + wiring） | **F12** |

F11 **不**实现 Default/Fake/Echo/Stub/Noop/Placeholder Production Processor。Tests 可用 deterministic test-only fake。详见 §55、OI-F11-TD-001 = **CLOSED**。

---

## 32. End-to-End Request Lifecycle

```text
POST /api/v1/session/turn
        ↓
API Request Validation（SessionTurnRequest）
        ↓
Request Idempotency Gate（fingerprint + result cache）
        ↓
New / Existing Session Resolution
        ↓
Acquire Request Lock
        ↓
Acquire Session Lock
        ↓
Load Session Meta + Checkpoint（existing）/ prepare empty（new）
        ↓
Checkpoint Validation
        ↓
AgentState Reconstruction（current request_id + input_text + persisted fields）
        ↓
AgentTurnProcessor.process_turn(...)
        ↓
validate_agent_state
        ↓
Persisted State Sanitization（drop raw input / request_id / trace）
        ↓
Revision Check（WATCH）
        ↓
MULTI/EXEC: SessionMeta + Checkpoint + Audit + Dedup Result + TTLs
        ↓
Release Session Lock → Release Request Lock
        ↓
Public Success Response
```

Failure：保留上一有效 checkpoint → 可行时写 failure audit → Controlled API Error。

Lock 顺序冻结：**request lock → session lock**；释放：**session lock → request lock**。

---

## 33. HTTP API Contract

### D-F11-001 — Endpoint

| Decision | `POST /api/v1/session/turn` |
|----------|-----------------------------|
| Rationale | 现有仅 `GET /health` 直挂 `app`；无冲突 convention；`/api/v1/...` 为清晰公共业务 API 前缀 |
| Mapping | AC-F11-001…008, 084, 085 |
| Impact | `session/api.py`：`create_session_router(service=...)`；**F11 不修改** `main.py`；F12 composition root `include_router` |

**AC-F11-084 clarification（不改 Requirement 正文）：** F11 HTTP capability **设计为**可直接挂载于现有 FastAPI app；**不**创建第二个 FastAPI server / 新 HTTP port。最终 `app.include_router(...)` 由 **F12 composition root** 完成——这不违反 AC-F11-084（capability 针对 existing app 构建；真实业务 dependency binding = F12）。

### D-F11-002 — SessionTurnRequest

| Field | Rule |
|-------|------|
| `request_id` | **required**；UUID4 字符串（client-generated） |
| `session_id` | **optional**；缺省/null = 新 session；有值 = UUID4 existing |
| `input_text` | **required** string；strip 后非空；raw length ≤ **4000** |

- 不对 `input_text` 做 lowercase / 去标点 / 语义 normalize。
- Validation 可用 strip 副本判空，**不改变**交给 Agent 的核心文本语义（仅拒绝纯空白）。

### D-F11-003 — Public Success Response（`SessionTurnSuccess`）

| Field | 语义 |
|-------|------|
| `session_id` | opaque UUID |
| `request_id` | echo |
| `status` | `COMPLETED` \| `AWAITING_USER_INPUT` |
| `response_text` | 来自 AgentTurnResult（业务受控输出） |
| `requires_user_input` | bool |

Public `status` **不是** `AgentState.status` / F09/F10 内部 enum。

### D-F11-004 — Public Error Response（`SessionTurnError`）

| Field | 语义 |
|-------|------|
| `request_id` | echo（若已解析） |
| `session_id` | 可空 |
| `status` | 固定 `FAILED` |
| `error.code` | controlled family |
| `error.message` | safe user-facing |

禁止：traceback、Redis key、internal node、secret、repository detail。

### D-F11-005 — HTTP Status Mapping

| Error family | HTTP |
|--------------|------|
| INVALID_REQUEST | 422 |
| SESSION_NOT_FOUND | 404 |
| SESSION_EXPIRED | 410 |
| SESSION_CONFLICT | 409 |
| REQUEST_ID_REUSE_CONFLICT | 409 |
| REQUEST_IN_PROGRESS | 409 |
| CHECKPOINT_INVALID | 500 |
| CHECKPOINT_VERSION_UNSUPPORTED | 500 |
| PERSISTENCE_UNAVAILABLE | 503 |
| AUDIT_PERSISTENCE_FAILED | 503 |
| AGENT_TURN_FAILED | 500 |
| UNEXPECTED_INTERNAL_ERROR | 500 |

**无** public `PROCESSOR_NOT_CONFIGURED`（缺失 Processor = composition/config error，构造期 fail-fast）。

Route 只做 parse → `SessionTurnService` → map；**不**含 Redis/业务逻辑。

---

## 34. Session / Request Identity Design

### D-F11-006 — request_id

- **Authority：** client 生成 UUID4；server 校验格式。
- **Why：** 网络超时重试必须复用同一 `request_id` 才能幂等。
- **禁止：** 由 `input_text` hash 生成；禁止 server 每次强制新发导致 retry 无法关联。

### D-F11-007 — session_id

- **Authority：** server 生成 UUID4。
- **Why：** opaque、难枚举、无业务字段、stdlib、无新依赖。
- **禁止：** 自增 ID；业务字段拼接。

---

## 35. Agent Turn Processor Boundary

### D-F11-008 — Protocol（Production integration contract；非 Test-only）

```text
AgentTurnProcessor.process_turn(
  *,
  session_id: str,
  request_id: str,
  input_text: str,
  restored_state: AgentState | None,
) -> AgentTurnResult
```

`restored_state`：新 session 可为 `None`；已有 session 为恢复后的 controlled `AgentState`。

`AgentTurnResult`：

| Field | 语义 |
|-------|------|
| `state` | 本轮最终完整 `AgentState`（须通过 `validate_agent_state`） |
| `response_text` | 对本轮用户的受控回复（Processor-owned） |
| `requires_user_input` | bool |
| `public_status` | controlled F11-facing：`COMPLETED` \| `AWAITING_USER_INPUT` |

F11 **只信任** Processor 返回的 controlled result，随后 validate → sanitize → persist。
F11 **不**猜测改了哪些 artifact；**不**实现 Default/Fake/Echo/Stub/Noop/Placeholder Production Processor。
Tests 允许 deterministic test-only double。

### D-F11-009 — Production Binding Gate（Finalization CLOSED）

| Item | Value |
|------|-------|
| CURRENT PRODUCTION BINDING today | **NOT CURRENTLY AVAILABLE** |
| Misrepresent F08/F09/F10 runner as unified processor | **FORBIDDEN** |
| F11 ships | Protocol + injectable Session API capability |
| F11 Production Fake Processor | **FORBIDDEN**（count must be 0 at Review） |
| F11 direct F03–F10 business wiring | **FORBIDDEN**（count must be 0 at Review） |
| Concrete Government processor | **F12 ownership** |
| Application activation (`main.py`) | **F12 ownership** |
| OI-F11-TD-001 | **RESOLVED / CLOSED** |

**Why missing concrete processor no longer blocks F11 Code：** F11 交付物是 Session infrastructure + dependency-inverted Protocol；concrete Government implementation 已明确归属 F12。缺少 concrete processor 是 **F12 composition** 问题，不是 F11 Session capability 实现 blocker。

缺少 Processor **不得**变成用户请求时的 public `PROCESSOR_NOT_CONFIGURED`：`SessionTurnService(processor=..., store=...)` 与 `create_session_router(service=...)` 均为 **required**；错误 composition 在构造期 fail-fast。

---

## 36. Persistence Models

### D-F11-010 — SessionMeta（schema_version=1）

| Field | Type |
|-------|------|
| `schema_version` | 1 |
| `session_id` | str UUID |
| `created_at` | UTC ISO-8601 |
| `last_activity_at` | UTC ISO-8601 |
| `expires_at` | UTC ISO-8601 |
| `checkpoint_revision` | int ≥ 1（active） |

不存 raw input；不存业务真相副本（业务在 checkpoint）。

### D-F11-011 — PersistedAgentState

| 保留 | 丢弃 |
|------|------|
| `phase`, `status`, `artifacts`, `error` | `input_text`, `request_id`, `orchestration_trace` |

- 稳定成功 checkpoint：`error` **必须为 None**。
- Failure turn：**不写** checkpoint。
- 保留 `error` 字段仅为 shape consistency；validation 要求 None。

### D-F11-012 — SessionCheckpoint（schema_version=1）

| Field | 语义 |
|-------|------|
| `schema_version` | 1 |
| `session_id` | str |
| `revision` | int；新 session 首次成功 = 1；每成功 durable turn +1 |
| `saved_at` | UTC ISO-8601 |
| `state` | PersistedAgentState |

非 version 1 → `CHECKPOINT_VERSION_UNSUPPORTED`；**无**自动 migration。

### D-F11-013 — Sanitizer / Restore（pure functions）

- `to_persisted(state) -> PersistedAgentState`：deep copy；丢弃 raw/transport/trace。
- `from_persisted(persisted, request_id, input_text) -> AgentState`：注入本轮 id/input；`orchestration_trace=[]`；调用 `validate_agent_state` / `create_initial_state` 等价路径。
- **禁止**恢复旧 `input_text`（F10 stale-input safety）。

### D-F11-014 — Artifact persistence strategy

| Choice | **B**：`validate_agent_state` JSON-safe + strict `json.dumps`（**禁止** `default=str`）+ scrub transport fields；unknown non-JSON → fail closed |
|--------|--------------------------------------------------------------------------------------------------------------------------------------------|
| Rationale | 避免 F11 allowlist 迫使每个 Feature 改 F11；F09/F10 artifacts 已是 JSON-safe dict |
| f09/f10 `response_text` | 属**系统受控输出**（非 USER_FREE_TEXT）；保留于 artifacts 不破坏 F09/F10 contract；Public/Audit 另有规则 |

---

## 37. Redis Keyspace

### D-F11-015 — Custom Redis Store（不用 LangGraph RedisSaver）

| Decision | `RedisSessionStore` 单组件 |
|----------|----------------------------|
| Rationale | `langgraph-checkpoint-redis` 未装；F11 边界是 HTTP turn 非 node checkpoint；需统一 Session/Checkpoint/Audit/Idempotency/Locks |
| LangGraph checkpointer | **NOT USED in F11** |

### D-F11-016 — Exact keys（prefix=`govagent:f11`）

| Purpose | Key |
|---------|-----|
| Session meta | `govagent:f11:session:{session_id}:meta` |
| Checkpoint | `govagent:f11:session:{session_id}:checkpoint` |
| Audit list | `govagent:f11:session:{session_id}:audit` |
| Request result | `govagent:f11:request:{request_id}:result` |
| Request lock | `govagent:f11:lock:request:{request_id}` |
| Session lock | `govagent:f11:lock:session:{session_id}` |

Physical keys **永不**进入 Public API / Audit payload。

---

## 38. Checkpoint Serialization

### D-F11-017

- JSON via Pydantic `model_dump(mode="json")` + `json.dumps` / `json.loads` + validation。
- **禁止** pickle；**禁止** `json.dumps(..., default=str)`。
- 所有持久 timestamp：timezone-aware **UTC** ISO-8601。

---

## 39. Restore / Save Algorithms

### Existing session load

```text
meta = GET meta
if missing → SESSION_NOT_FOUND
validate meta schema_version
if now > meta.expires_at → SESSION_EXPIRED
cp = GET checkpoint
if missing → CHECKPOINT_INVALID
validate checkpoint schema/version
assert cp.session_id == requested
assert cp.revision == meta.checkpoint_revision
return cp.state
```

### New session success

```text
validate → replay check → request lock
session_id = UUID4 → session lock
result = processor.process_turn(restored_state=None)
validate_agent_state → sanitize
expected_revision=0（meta 不得已存在）
MULTI: meta(rev=1) + checkpoint(rev=1) + audit TURN_COMPLETED + request result + TTLs
EXEC → release locks → success response
```

UUID 冲突（meta 已存在）：controlled `SESSION_CONFLICT` 或重新生成一次后仍冲突则失败（Code 实现二选一；推荐 fail closed conflict）。

### Existing session success

```text
… load meta+cp → revision_before=N
reconstruct AgentState(current request_id, input_text, persisted fields)
result = processor.process_turn(restored_state=...)
validate → sanitize
WATCH meta; assert revision==N
MULTI: meta(N+1) + checkpoint(N+1) + audit + request result + TTLs
EXEC else SESSION_CONFLICT
```

### Agent failure

- **不**更新 checkpoint revision。
- Existing：checkpoint 仍为 N；可行则 RPUSH `TURN_FAILED` audit。
- New session：`AgentTurnResult` 失败 → **不**创建 active SessionMeta/checkpoint；**不**返回可用 `session_id`；仅 Application Log（及可选短生命周期内部 audit，不公开）。

---

## 40. TTL / Expiration

### D-F11-018 — Defaults（均可配置）

| Setting | Default |
|---------|---------|
| `session_ttl_seconds` | **1800**（30m inactivity） |
| `session_expired_marker_ttl_seconds` | **86400**（24h） |
| `audit_ttl_seconds` | **604800**（7d） |
| `request_dedup_ttl_seconds` | **600**（10m） |
| `request_lock_ttl_seconds` | **120** |
| `session_lock_ttl_seconds` | **120** |

### D-F11-019 — Expired marker

- Checkpoint Redis TTL = `session_ttl_seconds`
- SessionMeta Redis TTL = `session_ttl_seconds + session_expired_marker_ttl_seconds`
- Active expiry 仍由 `expires_at` 判定
→ 区分 **never existed** vs **expired**。

成功 turn 更新 `last_activity_at` / `expires_at` 并刷新相关 TTL。
**Idempotent replay 不刷新** session activity/TTL。

---

## 41. Idempotency

### D-F11-020

- Fingerprint = SHA-256(canonical `session_id-or-null` + `\n` + `input_text` UTF-8 bytes)；**只存 digest**。
- Request result cache 存：schema_version、fingerprint、public success payload、session_id、completed_at。
  **不存** raw `input_text`；**不存** AgentState/checkpoint。
- Same `request_id` + same fingerprint → 直接返回 cached public response；**不再** Agent / revision++ / success audit。
- Same `request_id` + different fingerprint → `REQUEST_ID_REUSE_CONFLICT`。
- Dedup TTL = 600s。

### D-F11-021 — Request lock

- Key：`...:lock:request:{request_id}`；`redis.lock.Lock`；non-blocking。
- Acquire fail → 再查 cache；仍无 → `REQUEST_IN_PROGRESS`。
- Token-safe release（**禁止**裸 DEL）。

---

## 42. Concurrency / Revision Control

### D-F11-022 — Session lock

- Per-session lock；不同 session 不全局串行。
- TTL 120s（可配置）；token-safe release。

### D-F11-023 — Revision + WATCH/MULTI/EXEC

成功路径同事务写入：

1. SessionMeta（含新 revision）
2. SessionCheckpoint
3. Audit event append（RPUSH）
4. Request result cache
5. 相关 TTL

仅 **EXEC success** 后才 durable success。
WATCH 防 stale overwrite → `SESSION_CONFLICT`。

说明：此为 **同 Redis backend** 一致性边界，**不是**宣称数据库级 ACID / exactly-once。

网络歧义：EXEC 成功但客户端未收到 → 同 `request_id` retry → 命中 cache。

---

## 43. Audit Design

### D-F11-024 — Structure

- Redis **LIST** at audit key；`RPUSH` append-only；**不**用 Stream（Phase-1 无 consumer/search 需求）。
- TTL = `audit_ttl_seconds`（与 checkpoint 分离）。
- Schema version = 1。

### D-F11-025 — AuditEvent fields

`schema_version`, `event_id`（UUID4）, `session_id`, `request_id`, `occurred_at`, `event_type`（`TURN_COMPLETED`|`TURN_FAILED`）, `outcome`, `before_phase`, `before_status`, `after_phase`, `after_status`, `checkpoint_revision_before`, `checkpoint_revision_after`, `failure_code`（可选）, `capability`（可选，如 `SESSION_TURN`）。

**禁止：** `input_text`、`response_text`、secret、traceback、Redis physical key。

无 public audit query API；tests 可经 store 内部读取。

---

## 44. Failure Mapping

| Situation | Behavior |
|-----------|----------|
| Validation fail | 422 INVALID_REQUEST；无 session 副作用 |
| Unknown / expired | 404 / 410；不 silent-create |
| Processor fail（existing） | checkpoint 不变；可写 TURN_FAILED；500 AGENT_TURN_FAILED |
| Processor fail（new） | 不返回可用 session_id |
| EXEC fail / Redis down | 503 PERSISTENCE_UNAVAILABLE；不破坏上一 checkpoint |
| Audit-only fail on success path | 因同 MULTI，与 checkpoint 同成败；不可 silent ignore |
| Unexpected | 500 UNEXPECTED_INTERNAL_ERROR；safe message + structured log |

Domain exceptions / result types 由 Service 抛出；Route 统一翻译。
**禁止** `except Exception: pass`；**禁止** Redis 挂了 dict fallback。

---

## 45. Settings / Dependency Plan

### D-F11-026 — Settings fields（接入现有 pydantic-settings + KNOWN_DOTENV_KEYS）

| Field | Default / note |
|-------|----------------|
| `redis_host` | `127.0.0.1` |
| `redis_port` | `6379` |
| `redis_db` | `0` |
| `redis_username` | optional None |
| `redis_password` | optional `SecretStr` None |
| `redis_key_prefix` | `govagent:f11` |
| `session_ttl_seconds` | 1800 |
| `session_expired_marker_ttl_seconds` | 86400 |
| `audit_ttl_seconds` | 604800 |
| `request_dedup_ttl_seconds` | 600 |
| `request_lock_ttl_seconds` | 120 |
| `session_lock_ttl_seconds` | 120 |
| `session_max_input_chars` | 4000 |

Local no-auth = **dev-only**。Production credential support via optional username/password；**不**设计 TLS/Sentinel/Cluster/Vault。

### D-F11-027 — Dependency

- Code 阶段 `pyproject.toml` 增加 **`redis==5.3.1`**（与 Resource Gate 实测一致）。
- **不**加 `langgraph-checkpoint-redis` / `fakeredis` / hiredis extra。

### D-F11-028 — Sync client + sync route

- Sync FastAPI route（线程池执行）+ sync redis-py + connection pool 复用。
- **不**把 Redis client 放入 AgentState。
- **不**整体异步化工程。

---

## 46. Test Strategy

| Layer | Approach |
|-------|----------|
| Unit | `SessionStore` Protocol double + **test-only** deterministic `AgentTurnProcessor` |
| Redis integration | 真实 `RedisSessionStore` + `127.0.0.1:6379`；**禁止 FLUSHDB**；unique prefix `govagent:test:f11:{uuid}`；teardown 只删该 prefix |
| API | FastAPI test app **include 真实 F11 router** + 真实 `SessionTurnService` + 真实 Redis store；**仅** Processor = test-only fake |
| F09/F10 compat | artifacts round-trip（可并入现有最合适 F11 test file）；PREPARE restore 后旧 input 不恢复；**不做**完整 Government Agent E2E |
| Restart | Service A persist → 新 Service B 同 Redis restore |
| Concurrency | 同 session 两并发：一成功一 conflict/in-progress；不同 session 可并行 |

**F11 Test 证明：** 给定符合 Protocol 的 Processor，F11 可正确完成 Session / Redis / Checkpoint / Audit / API 生命周期。
**F11 Test 不证明：** 完整政府 Agent 已 E2E 可用（属 F12）。

Integration 必测：new/continue、TTL/expired、revision conflict、replay、reuse conflict、audit append、transaction、no raw input in checkpoint/audit、restart restore。

---

## 47. F09 / F10 Compatibility

| Feature | Continuity vehicle |
|---------|-------------------|
| F09 | `artifacts["f09"]`：`slot_context`, interpretation, mapping, validated_slot, explanation, business_transition, failure, `response_text` |
| F10 | `artifacts["f10"]`：`mode`, `terminal_context`, validation, rule_readiness, confirmation, `confirmed_business_id`, failure, `response_text` |

- F11 Store **只**序列化/反序列化；**不**修改 `confirmed_business_id`。
- 注意：现有 `run_slot_interaction_workflow` / F10 runners **每轮刷新**各自 namespace——跨请求连续依赖 **AgentTurnProcessor（F12）** 从 restored artifacts 重建 `SlotInteractionContext` / `TerminalCandidateContext` 并选择 PREPARE vs RESOLVE。
- F11 保证：JSON-safe artifacts 跨请求不丢；旧 `input_text` 不恢复。

---

## 48. Security / Data Minimization

- Checkpoint / Audit / request cache：**无** raw USER_FREE_TEXT。
- Request fingerprint = hash only。
- Request result cache 可含短期 `response_text`（系统输出）；Audit **不含** `response_text`。
- Secret 永不进入 checkpoint/audit/public/Git/Feature Doc。
- 无 public session list/delete/search/transcript/audit query。

---

## 49. Planned File Changes

### Path count change（TD Finalization）

| | Count |
|--|-------|
| Old Final Planned Paths | **13** |
| New Final Planned Paths | **12** |
| Removed | `src/gov_service_agent/main.py` |
| Added | **none**（禁止为凑数新增 binding/composition/factory 文件） |

### Final Planned Paths（12）

| # | Path | Action |
|---|------|--------|
| 1 | `src/gov_service_agent/session/__init__.py` | create |
| 2 | `src/gov_service_agent/session/models.py` | create |
| 3 | `src/gov_service_agent/session/store.py` | create |
| 4 | `src/gov_service_agent/session/service.py` | create |
| 5 | `src/gov_service_agent/session/api.py` | create |
| 6 | `src/gov_service_agent/settings.py` | modify（Redis/TTL fields + known keys） |
| 7 | `pyproject.toml` | modify（`redis==5.3.1`） |
| 8 | `tests/test_session_store.py` | create |
| 9 | `tests/test_session_service.py` | create |
| 10 | `tests/test_session_api.py` | create |
| 11 | `docs/features/F11-session-api-redis-checkpoint-audit.md` | modify |
| 12 | `docs/code-reading/F11-session-api-redis-checkpoint-audit-code-reading.md` | create（**Explanation/Code-Reading 阶段**；现已计入计划；**现在不创建**） |

| Bucket | Count |
|--------|-------|
| Production planned | **7**（5 session + settings + pyproject） |
| Test planned | **3** |
| Docs planned | **2**（Feature Doc + future Code-Reading） |
| Core self-written Production Python | **5**（session package）+ Settings modify |

**Why `main.py` removed from F11 plan：** F11 阶段无 Concrete Production `AgentTurnProcessor`。若 F11 修改 `main.py` 挂载 router，现有正式 FastAPI app 会暴露**无真实业务 Processor** 的 endpoint。Application-level activation = **F12**。`main.py` = F12 planned integration path（见 §55）。

**不**新增 `processor.py` / `binding.py`：Protocol 放 `service.py` 或 `models.py`；`SessionStore` Protocol 同理放 `store.py` / `service.py` / `models.py` 最合适处。

模块职责：`models`=contracts；`store`=Redis only；`service`=lifecycle+idempotency+processor boundary；`api`=HTTP only（`create_session_router`）。

---

## 50. AC → Design Traceability

| AC groups | Covered by |
|-----------|------------|
| A Session API 001–008 | D-F11-001…005, 008, 037, 038 |
| B Identity 009–015 | D-F11-006, 007, 019 |
| C Checkpoint 016–026 | D-F11-011…014, 017, 023 |
| D Data min 027–031 | D-F11-011, 020, 025 |
| E Redis 032–037 | D-F11-015, 016, 018, 019, 028 |
| F Multi-turn 038–041 | §32, §47, D-F11-013, 037 |
| G F09/F10 042–048 | §47, D-F11-009, 013, 039 |
| H Audit 049–057 | D-F11-024, 025, 023 |
| I Consistency 058–063 | D-F11-020…023 |
| J Failure 064–073 | §44, D-F11-005, 038 |
| K Boundaries 074–083 | D-F11-008, 009, 015, 037, 039；§56 |
| L Runtime/Docs 084–092 | D-F11-001, 030, 026, 027；§30/§55/§57 |

**AC-F11-082：** F11 提供 `AgentTurnProcessor` Protocol；SessionTurnService 仅调用注入的 Processor；业务实现 = F12。
**AC-F11-083：** 完整 E2E（F03–F10 orchestration + concrete processor + app activation）= F12。
**AC-F11-084：** F11 实现可挂载于 existing FastAPI 的 router capability；F12 执行 `include_router`；不新建第二 server。

**92/92 AC 均有 Design 或 Test Strategy 映射；无 AC 无人负责（见 §56 Ownership Matrix）。**

---

## 51. Technical Design Decisions（索引）

| ID | Decision |
|----|----------|
| D-F11-001 | Endpoint `POST /api/v1/session/turn`；F11 不改 main.py |
| D-F11-002 | SessionTurnRequest contract |
| D-F11-003 | Public success model + statuses |
| D-F11-004 | Public error model |
| D-F11-005 | HTTP status mapping（无 PROCESSOR_NOT_CONFIGURED） |
| D-F11-006 | Client UUID4 request_id |
| D-F11-007 | Server UUID4 session_id |
| D-F11-008 | AgentTurnProcessor Protocol + AgentTurnResult（Production contract） |
| D-F11-009 | Dependency inversion；OI-F11-TD-001 CLOSED；no Production fake |
| D-F11-010 | SessionMeta schema |
| D-F11-011 | PersistedAgentState fields |
| D-F11-012 | SessionCheckpoint + revision |
| D-F11-013 | Sanitize/restore pure functions；no old input |
| D-F11-014 | Artifact strategy B（strict JSON，无 default=str） |
| D-F11-015 | Custom RedisSessionStore；no RedisSaver |
| D-F11-016 | Exact Redis key schemas |
| D-F11-017 | JSON UTC serialization |
| D-F11-018 | TTL defaults |
| D-F11-019 | Expired marker TTL |
| D-F11-020 | Idempotency fingerprint + cache |
| D-F11-021 | Request lock |
| D-F11-022 | Session lock |
| D-F11-023 | WATCH + MULTI/EXEC + revision |
| D-F11-024 | Audit LIST append |
| D-F11-025 | AuditEvent fields / no raw text |
| D-F11-026 | Settings fields（仍属 F11） |
| D-F11-027 | redis==5.3.1 manifest（仍属 F11 Code） |
| D-F11-028 | Sync route + sync Redis pool |
| D-F11-029 | SessionTurnService：required store + processor；thin route |
| D-F11-030 | `create_session_router(service)`；activation = F12；F11 不改 main.py |
| D-F11-031 | New-session agent failure：no usable session |
| D-F11-032 | Replay does not refresh session TTL |
| D-F11-033 | Test strategy（real API+Redis；test-only processor） |
| D-F11-034 | Planned paths = **12**（removed main.py） |
| D-F11-035 | Code-Reading business-flow rule（path planned；F11 vs F12 tags） |
| D-F11-036 | max input 4000 chars |
| D-F11-037 | F11/F12 integration contract（concrete processor = F12） |
| D-F11-038 | Fail-fast composition；no public PROCESSOR_NOT_CONFIGURED |
| D-F11-039 | F12 must preserve F08–F10 authority（LLM≠next_node/business_id；F10 owns confirmed） |
| D-F11-040 | AC ownership matrix（F11 capability vs F12 integration） |

---

## 52. Technical Design Open Items

| ID | Priority | Status | Summary | Blocks |
|----|----------|--------|---------|--------|
| **OI-F11-TD-001** | ~~P0 BLOCKING~~ | **RESOLVED / CLOSED** | F11 freezes `AgentTurnProcessor` as production dependency-inversion contract；F11 ships injectable Session API capability without concrete government-business processor；F12 owns concrete processor and application-level activation；no fake/stub production processor is permitted. | — |

**Remaining TD Open Items count = 0。**
**Remaining Blocking OI count = 0。**
**Technical Design = FINAL / CLOSED。**
**Technical Design Finalization = COMPLETE。**
**Confirm Readiness = READY FOR CONFIRM**（须 Owner 单独授权；本阶段 **STOP**）。

---

## 53. Technical Design Evidence

| Check | Result |
|-------|--------|
| Requirement 92 AC covered | YES（内容未改） |
| Resource Gate facts used（Redis 7.4.11 / redis-py 5.3.1） | YES |
| Real code inventory for Processor | YES → NOT AVAILABLE today；runners not misrepresented |
| OI-F11-TD-001 | RESOLVED / CLOSED |
| Blocking OI remaining | **0** |
| No Production/Tests/Settings/deps/Docker modified this Finalization | YES |
| Fake Production Processor | NO（forbidden） |
| LangGraph RedisSaver | NOT USED |
| main.py in F11 plan | **REMOVED** |

### Code-Reading design rule（保留并强化）

未来 `docs/code-reading/F11-session-api-redis-checkpoint-audit-code-reading.md` 必须以用户输入开头，例如 Turn2「平时接零活…」→ `session/api.py` route → `SessionTurnService`（为何先看 request_id）→ `RedisSessionStore`（为何恢复 checkpoint）→ `AgentTurnProcessor` 边界 → Sanitizer（为何不存 input_text）→ MULTI/EXEC → 用户最终 API response。

必须使用明显标签：

- **「F11 已实现」**：HTTP / Session / Redis / Checkpoint / Audit / Protocol boundary
- **「F12 将注入」**：Concrete Government Processor 内部（RAG / Decision Graph / F09 / F10）

不得让读者误以为 F11 已完成完整业务 E2E。

Golden scenario（讲解用）：用户「我辞职了，现在没单位，想自己交社保」→ F11 真实负责 HTTP/Session/Redis/Checkpoint/调用 Processor Boundary/持久化/返回；Processor 内部 RAG/Graph/F09/F10 = F12 接入后执行。

---

## 54. Composition Root / Router Factory（Finalization）

### D-F11-029 — SessionTurnService

```text
SessionTurnService(
  *,
  store: SessionStore,           # required；Protocol；concrete = RedisSessionStore
  processor: AgentTurnProcessor, # required；不得 None
  clock: ... | None,             # optional test injection if needed
  id_generator: ... | None,      # optional test injection if needed
)
```

- Service **不**内部 `import Redis` / global processor。
- Service **不**做业务决策（next_node / business_id / confirmation）。
- Router **不**创建 store / processor。

### D-F11-030 — Router factory + activation boundary

**Exact Production factory symbol：**

```text
create_session_router(service: SessionTurnService) -> APIRouter
```

Production dependency graph：

```text
FastAPI App
    ↓
Session Router          ← F11 capability（factory）
    ↓
SessionTurnService      ← F11
    ├── AgentTurnProcessor   ← Protocol F11；concrete F12
    └── RedisSessionStore    ← F11
```

**F11：** 不修改 `main.py`；不 module-level singleton processor；不自动实例化假 implementation。
**F12 composition root（`main.py` 或未来 wiring module）：**

```text
processor = GovernmentAgentTurnProcessor(...)   # F12 symbol TBD
store = RedisSessionStore(...)
service = SessionTurnService(processor=processor, store=store)
router = create_session_router(service=service)
app.include_router(router)
```

### D-F11-038 — Fail-fast composition

- `processor` / `store` / `service` 均为 required。
- 错误 composition → 启动/构造失败。
- **禁止** public runtime error `PROCESSOR_NOT_CONFIGURED`（用户访问 endpoint 才发现缺失）。

---

## 55. F11 / F12 Integration Contract

### D-F11-037 — Contract

| Obligation | Owner |
|------------|-------|
| `AgentTurnProcessor` Protocol + `AgentTurnResult` | F11 |
| Session HTTP models / router factory / service / store / checkpoint / audit / idempotency / concurrency | F11 |
| Concrete Government `AgentTurnProcessor` implementation | F12 |
| Call/orchestrate F03–F10（及后续）inside processor | F12 |
| `main.py` / app-level `include_router` activation | F12 |
| Full Government Agent E2E proof | F12 |

F12 Processor **必须**：

- 接受：`session_id`, `request_id`, `input_text`, `restored_state`（新 session 可为 `None`）
- 返回：valid `AgentTurnResult`（`state` / `response_text` / `requires_user_input` / `public_status`）
- 不得让 raw runtime object 进入 `state`
- F11 随后 validate / sanitize / persist

### D-F11-039 — Business authority unchanged

即使 F12 实现 Processor，仍必须保持：

- LLM **不**决定 `next_node`
- LLM **不**决定 `business_id`
- Business Decision Graph 确定性推进
- **F10** 拥有 `confirmed_business_id` authority
- F11 Redis = session continuity SoT，**不是**业务真相源

Endpoint 保持：`POST /api/v1/session/turn`（activation deferred **不**改 path）。

### Session API ≠ placeholder

F11 Router = **真实 Production code**：可接受真实 HTTP、执行真实 Session/Redis/Checkpoint/Audit。唯一不自行拥有的是 Government business processing implementation（经 Protocol 注入）。**不是** fake/placeholder API。

---

## 56. AC Ownership Matrix

### D-F11-040

| Capability / AC focus | F11 Implementation | F12 Integration |
|-----------------------|--------------------|-----------------|
| Session HTTP contract（001–008） | Router/models/mapping | Mount router + concrete processor |
| Multi-turn / F09 / F10 continuity（038–048） | Checkpoint sanitize/restore | Processor rebuilds F09/F10 contexts & orchestrates |
| Agent Turn Boundary（082） | Protocol + service call | Concrete process_turn |
| F12 E2E boundary（083） | —（out of F11 Code） | Full wiring + E2E proof |
| Existing FastAPI app（084） | Mountable APIRouter capability | `include_router` on existing app |
| Redis checkpoint / audit / TTL / locks | Store + service | Provide Redis settings at composition |
| AgentTurnProcessor Protocol | Define & ship | Implement |
| Concrete Government processor | **NO** | **YES** |
| main app activation | **NO**（path removed） | **YES** |
| F03–F10 full orchestration | **NO** | **YES** |

---

## 57. Future Review / Explanation Gates（预冻结）

**F11 Review 必须检查：**

| Check | Expected |
|-------|----------|
| Production Fake AgentTurnProcessor count | **0** |
| Production direct F03/F06/F09/F10 business wiring count | **0** |
| F11 `main.py` activation | **0** |
| Tests may use deterministic fake | YES |

**F11 Explanation 主线：**

```text
用户 HTTP 输入
  → Session API（F11 已实现）
  → SessionTurnService（F11）
  → 恢复 Redis Checkpoint（F11）
  → 调用 AgentTurnProcessor 接口（F11 边界；F12 将注入 concrete）
  → 收到新 State
  → validate / sanitize / persist / audit（F11）
  → 返回用户
```

「政府业务这一轮如何从自然语言走到事项」= F12 Processor。

---

## 58. Confirm Evidence

### 58.1 Confirm Result

| Item | Value |
|------|-------|
| F11 Confirm | **COMPLETE** |
| Code Readiness | **READY FOR CODE** |
| Confirm Date | 2026-09-14 |
| Git Baseline | `develop` @ `85f4a7cb1e3ed632525974a4f297e9d115314381` |
| Confirm changed paths | **1**（本 Feature Doc only） |
| BLOCKING / MAJOR findings | **0** |
| Need Resource Gate reopen | **NO** |
| Need Requirement reopen | **NO** |
| Need TD reopen | **NO** |

### 58.2 Freeze Gate（preserved）

| Gate | Status |
|------|--------|
| Requirement | COMPLETE；AC **92**；Open Items **0**；Finalization NOT REQUIRED |
| Technical Design | FINAL / CLOSED；Decisions **40**；Open Items **0** |
| TD Finalization | COMPLETE |
| OI-F11-TD-001 | RESOLVED / CLOSED |
| Requirement AC content modified this stage | **NO** |
| TD redesign this stage | **NO** |

### 58.3 F11 / F12 Boundary（reconfirmed）

| Owner | Owns |
|-------|------|
| **F11** | Session API capability；`SessionTurnService`；`AgentTurnProcessor` Protocol；`AgentTurnResult`；`RedisSessionStore`；Checkpoint / Audit / Idempotency / Concurrency；Settings；`redis==5.3.1` |
| **F12** | Concrete Government Processor；F03–F10 orchestration；composition root / `main.py` activation；full E2E proof |

- Production Fake Processor required / planned = **NO**（expected count **0**）
- Test-only deterministic Processor = **allowed**
- Concrete Government Processor missing **does not** block F11 Code

### 58.4 Real Agent Capability Inventory

| Symbol | Path | Unified one-turn Government Processor? |
|--------|------|------------------------------------------|
| `run_agent_workflow` | `agent/workflow.py` | **NO** |
| `run_slot_interaction_workflow` | `agent/workflow.py` | **NO** |
| `prepare_terminal_confirmation` | `agent/workflow.py` | **NO** |
| `resolve_terminal_confirmation` | `agent/workflow.py` | **NO** |

Current unified Production Government Processor = **NOT AVAILABLE**（与 TD Finalization 一致；未误表为统一 Processor）。

### 58.5 AgentState / Protocol Feasibility

| Check | Result |
|-------|--------|
| Path | `src/gov_service_agent/agent/state.py` |
| Top-level field count | **7** |
| Real fields | `request_id`, `input_text`, `phase`, `status`, `artifacts`, `error`, `orchestration_trace` |
| Validator | `validate_agent_state(state: Any) -> AgentState` |
| Factory | `create_initial_state(request_id, input_text, *, artifacts=None) -> AgentState` |
| Protocol feasible without F12 wiring | **YES / FEASIBLE**（Protocol + Result 可在 session package 定义） |
| Persisted subset | keep `phase`/`status`/`artifacts`/`error`；drop `request_id`/`input_text`/`orchestration_trace` |
| Restore without old input | **FEASIBLE**（probe：注入新 `input_text` 后 artifacts 连续） |

### 58.6 F09 / F10 Continuity

| Check | Result |
|-------|--------|
| F09 namespace | `artifacts["f09"]`；keys：`slot_context`, `interpretation`, `mapping_validation`, `validated_slot`, `explanation`, `business_transition`, `failure`, `response_text` |
| F09 pending slot location | `f09.slot_context.required_slot`（controlled；JSON-safe via `model_dump(mode="json")`） |
| F09 resume without old raw input | **YES** |
| F10 key count | **8** |
| F10 keys | `mode`, `terminal_context`, `terminal_validation`, `rule_readiness`, `confirmation`, `confirmed_business_id`, `failure`, `response_text` |
| F10 next turn needs | persisted controlled context + **current** `input_text` |
| Old F10 input restored | **NO**（design forbids） |
| F10 stale-input invariant | **PASS**（PREPARE 文本不会被下一 turn 当 confirmation 重解释，因旧 `input_text` 不持久/不恢复；RESOLVE 只读本轮 `state["input_text"]`） |
| `confirmed_business_id` authority | still **F10** `assign_confirmed_business_id`；F11 serialize/restore only |
| F11 planned assignment to confirmed_business_id | **NO** |
| F09/F10 artifacts strict JSON | **YES**（empty namespace probe；无 repository/provider/callable/graph/Redis client） |
| Artifact strategy | validate_agent_state JSON-safe + strict `json.dumps`（no `default=str`）+ scrub；**not** F09/F10-only allowlist |

### 58.7 FastAPI / Endpoint / Contracts

| Check | Result |
|-------|--------|
| Existing app | `src/gov_service_agent/main.py` → `app = FastAPI(...)`；routes include `GET /health` only |
| Second FastAPI server | **NOT required** |
| APIRouter available | **YES**（fastapi dependency present） |
| Router factory | `create_session_router(service: SessionTurnService) -> APIRouter` **FEASIBLE** |
| Exact endpoint | `POST /api/v1/session/turn` |
| Endpoint conflict | **NO** |
| main.py in F11 planned paths | **NO** |
| F11 needs main.py modify | **NO**（test app can include router；F12 activates production app） |
| Request/Response/Error models | FEASIBLE via Pydantic v2 + FastAPI |
| Public statuses | `COMPLETED` / `AWAITING_USER_INPUT`（F11 API layer；≠ AgentState/F09/F10 enums） |
| HTTP error families | TD list mappable；no public `PROCESSOR_NOT_CONFIGURED`；no raw Redis exception to client |

### 58.8 Settings / Dependency

| Check | Result |
|-------|--------|
| Settings path | `src/gov_service_agent/settings.py` |
| Pattern | pydantic-settings `BaseSettings` + `SecretStr` + `KNOWN_DOTENV_KEYS` |
| Planned F11 fields | redis_host/port/db/username/password；redis_key_prefix；session/audit/dedup/lock TTLs；session_max_input_chars |
| Optional credentials | **FEASIBLE**（`SecretStr | None` pattern already used） |
| Local defaults | compatible with TD（127.0.0.1:6379；prefix `govagent:f11`；TTL defaults） |
| Manifest path | `pyproject.toml` |
| `redis` currently declared | **NO** |
| Code-stage `redis==5.3.1` | **FEASIBLE**；no fakeredis / RedisSaver / hiredis extra required |

### 58.9 Redis / redis-py Runtime（read-only）

| Check | Result |
|-------|--------|
| Container | `govagent-redis-dev` **running** |
| Server version | **7.4.11** |
| Port mapping | `6379/tcp -> 127.0.0.1:6379` |
| Loopback only | **YES** |
| `0.0.0.0` exposed | **NO** |
| CLI PING | **PONG** |
| Python | 3.11.16（govagent） |
| redis-py | **5.3.1** |
| Python PING | **True** |
| Business Redis mutation | **NO**（PING-only） |
| Lock | `redis.lock.Lock`；`release` / ownership helpers present；token-safe release feasible；no bare DEL |
| WATCH / MULTI / EXEC / pipeline SET/RPUSH/EXPIRE | **FEASIBLE** |
| Same-tx meta+checkpoint+audit+result+TTL | **FEASIBLE** |
| Expired-marker TTL model | **consistent**（missing meta=NOT_FOUND；meta+expires_at passed=EXPIRED；active meta+missing checkpoint=INVALID） |
| Revision + lock ordering | **feasible**；lock TTL expiry still protected by revision WATCH |

### 58.10 Planned Paths / Tests / Docs

| # | Path | Class |
|---|------|-------|
| 1–5 | `src/gov_service_agent/session/{__init__,models,store,service,api}.py` | NEW（currently absent） |
| 6 | `src/gov_service_agent/settings.py` | MODIFY |
| 7 | `pyproject.toml` | MODIFY |
| 8–10 | `tests/test_session_{store,service,api}.py` | NEW（currently absent） |
| 11 | Feature Doc | MODIFY |
| 12 | `docs/code-reading/F11-session-api-redis-checkpoint-audit-code-reading.md` | NEW later（**not created now**） |

| Check | Result |
|-------|--------|
| Path count | **12**；`main.py` excluded |
| Unexpected pre-existing NEW path | **NONE** |
| Core new Production Python | **5** |
| Test files | **3** cover store/service/API + F09/F10 compat + restart + concurrency（no 4th file required） |
| Real Redis tests | unique prefix `govagent:test:f11:<uuid>`；no FLUSHDB |
| Code-Reading rule | user-input → API response；labels **【F11 已实现】** / **【F12 将注入】**；golden scenario preserved |
| AC coverage | **92/92** with TD/Test/F12 ownership；no unowned AC |
| TD contradictions | **NONE found** |

### 58.11 Confirm Findings

| Severity | Count | Notes |
|----------|-------|-------|
| BLOCKING | 0 | — |
| MAJOR | 0 | — |
| MINOR | 0 | — |
| INFO | 0 | — |

---

## 59. Code Implementation Evidence

### 59.1 Code Result

| Item | Value |
|------|-------|
| F11 Code | **COMPLETE** |
| Test Readiness | **READY FOR TEST** |
| Code Date | 2026-09-14 |
| Ending changed paths | **8**（exact planned Code Stage set） |
| Concrete Government Processor | **NOT implemented**（F12） |
| Production Fake Processor count | **0** |
| `main.py` modified | **NO**（hash unchanged） |
| F09/F10/AgentState production modified | **NO**（hashes unchanged） |
| Test files created | **NO** |
| Code-Reading Doc created | **NO** |

### 59.2 Implemented modules

| Path | Role |
|------|------|
| `session/models.py` | HTTP/persistence contracts、error codes、`AgentTurnResult` |
| `session/store.py` | `SessionStore` Protocol、`RedisSessionStore`、locks、WATCH/MULTI/EXEC |
| `session/service.py` | `AgentTurnProcessor` Protocol、`SessionTurnService`、sanitize/restore |
| `session/api.py` | `create_session_router(service)` → `POST /api/v1/session/turn` |
| `session/__init__.py` | explicit public exports（no wildcard） |
| `settings.py` | Redis/session TTL/lock/max-input fields + `SecretStr` password |
| `pyproject.toml` | `redis==5.3.1` |

### 59.3 Public API / Protocol boundary

- Router factory：`create_session_router(service: SessionTurnService) -> APIRouter`
- Endpoint：`POST /api/v1/session/turn`（未挂载 `main.py`）
- Protocol：`AgentTurnProcessor.process_turn(*, session_id, request_id, input_text, restored_state) -> AgentTurnResult`
- Service dependencies：`store` + `processor` required（fail-fast；无 `PROCESSOR_NOT_CONFIGURED`）
- Store：Redis physical keys / TTL / revision / audit LIST / request cache
- Persistence scrub：no `input_text` / `request_id` / `orchestration_trace` in checkpoint
- Fingerprint：SHA-256 over canonical JSON `{session_id, input_text}`（digest only）

### 59.4 Smoke evidence

| Check | Result |
|-------|--------|
| `py_compile`（5 session files + settings） | **PASS** |
| `import gov_service_agent.session` | **PASS**（no Redis connect / no LLM / no DB） |
| pytest | **NOT RUN** |
| Redis mutation | **NONE** |

### 59.5 F11 / F12 boundary (preserved)

F11 ships injectable Session API capability only. F12 owns concrete Government processor、F03–F10 orchestration、`main.py` activation、full E2E proof.

---

## 60. Test Evidence

### 60.1 Test Result

| Item | Value |
|------|-------|
| F11 Test | **PASS** |
| Review Readiness | **READY FOR REVIEW** |
| Test Date | 2026-09-14 |
| Ending changed paths | **11** |
| Production hashes during Test | **unchanged** |
| `main.py` / F09 / F10 / AgentState | **unchanged** |
| Code-Reading Doc | **NOT CREATED** |
| Extra test files / conftest | **NONE** |
| Need Code reopen | **NO** |

### 60.2 Redis runtime

| Item | Value |
|------|-------|
| Container | `govagent-redis-dev` running |
| Server | **7.4.11** |
| Bind | `127.0.0.1:6379` only |
| PING | PONG |
| redis-py | **5.3.1** |
| Test prefix | `govagent:test:f11:<uuid>` |
| FLUSHDB / FLUSHALL | **0** |
| Production prefix `govagent:f11` touched | **NO** |

### 60.3 Targeted results

| Suite | Result |
|-------|--------|
| `tests/test_session_store.py` | **13 passed** |
| `tests/test_session_service.py` | **17 passed** |
| `tests/test_session_api.py` | **10 passed** |
| Combined F11 | **40 passed / 0 failed / 0 skipped / 0 warnings** |

### 60.4 Regressions + full suite

| Suite | Result |
|-------|--------|
| F08 `test_agent_state` + `test_agent_workflow` | **94 passed** |
| F09 `test_agent_interaction` | **63 passed** |
| F10 `test_agent_terminal` + `test_agent_workflow` | **100 passed** |
| Full default pytest | **585 passed, 13 skipped, 0 failed, 0 warnings** |
| Historical pre-F11 full baseline | 545 passed / 13 skipped |
| `compileall -q src tests` | **PASS** |
| `pip check` | **PASS**（No broken requirements found） |

### 60.5 Contract evidence (summary)

- Checkpoint / meta / audit / request cache：**无** raw `input_text`；**无** persisted `request_id` / `orchestration_trace` in state
- Old input / request_id / trace restore：**NO**
- F09 pending slot + explanation side-route continuity：**PASS**
- F10 8-key round-trip；`"确认"` uses current input；`confirmed_business_id` not assigned by F11：**PASS**
- Replay：Processor second call / revision++ / duplicate success audit / TTL refresh：**0**
- Same-session concurrency：no silent lost update；different sessions independent locks
- Atomic MULTI/EXEC + stale revision WATCH conflict：**PASS**
- Restart-style continuity（new Python store/service, same Redis prefix）：**PASS**
- API HTTP mappings：404/410/409/500/503 as frozen；no traceback / Redis key / AgentState leakage
- Golden continuity texts used as Session lifecycle proof only — **not** full F12 E2E
- Test-only `DeterministicTestAgentTurnProcessor` confined to tests；Production Fake count：**0**

### 60.6 F11 / F12 reminder

F11 Golden / Session tests prove **Session / Checkpoint / Audit / API lifecycle**.
They do **not** prove real RAG / Decision Graph / F09 / F10 government E2E — that remains **F12**.

---

## 61. Review Evidence

### 61.1 Review Result

| Item | Value |
|------|-------|
| F11 Review | **NEEDS_FIX** |
| Next | **READY FOR REVIEW FIX** |
| Review Date | 2026-09-14 |
| Ending changed paths | **11**（仅 Feature Doc 内容更新；路径集合不变） |
| Production / Tests / Settings / pyproject hashes | **unchanged** during Review |
| pytest rerun | **NO** |
| Redis mutation | **NO** |
| BLOCKING | **0** |
| MAJOR | **3** |
| MINOR | **4** |
| INFO | **4** |
| Review Fix required | **YES** |

### 61.2 Scope & architecture

Reviewed: `session/{models,store,service,api,__init__}.py`、`settings.py`、`pyproject.toml`、3 test files；对照 Feature Doc / AgentState / F09 / F10 contracts。

| Check | Result |
|-------|--------|
| Dependency direction | models ← store ← service ← api；`__init__` re-exports only |
| Circular imports | **none** |
| Models→Redis / Store→API / API→Redis | **NO** |
| Service→FastAPI | **NO**（仅 `LockError` from redis） |
| F03/F06/F09/F10 business wiring in Production | **0** |
| Concrete / Fake Production Processor | **0** |
| `main.py` activation | **0**（unchanged；仅 `/health`） |
| Protocol / AgentTurnResult | matches TD |
| confirmed_business_id assignment in F11 | **0** |
| Checkpoint scrub（no input/request_id/trace） | **YES** |
| Restore current id/input + fresh trace | **YES** |
| WATCH → read revision → MULTI → EXEC | **correct order** |
| Request-lock double-check / lock ordering | **correct** |
| Load-after-session-lock | **YES** |
| Session lock covers processor turn | **YES** |
| Replay before session lock；no Processor/revision/audit/TTL refresh | **YES** |
| Corrupt request cache fail-closed（not miss） | **YES**（`PERSISTENCE_UNAVAILABLE`） |
| pickle / default=str | **absent** |
| allow_nan=False | **YES** |
| UUID4 validators | **YES** |
| redis==5.3.1 only new dep | **YES** |

### 61.3 Findings

#### RF-F11-RV-001 — MAJOR

| Field | Content |
|-------|---------|
| Path | `src/gov_service_agent/session/store.py` |
| Symbol | `RedisSessionStore.commit_successful_turn`（≈376–415）；`append_failure_audit` |
| Problem | Redis `MULTI/EXEC` 中 `RPUSH audit` 若遇 **WRONGTYPE**（audit key 非 LIST），其它 `SET meta/checkpoint/result` 仍可能已执行；`pipe.execute()` 虽默认 `raise_on_error=True` 会抛错并映射为 persistence failure，但 **无法回滚已写入命令**，破坏「meta+checkpoint+audit+result 同事务 durable」语义。随后若 `request result` 已写入，同 `request_id` retry 可能走 replay 成功。 |
| Why | 违反原子 durable success / audit 不可静默丢失的一致性目标。 |
| Trigger | audit key 被污染为 STRING/HASH 等非 LIST；或同类 runtime command error。 |
| TD/AC | D-F11-023/024；AC consistency/audit persistence |
| Fix direction | 优先 **Lua script** 单原子写入+类型校验；或 MULTI 前 `TYPE` 校验 fail-closed；并检查 `execute()` 结果；补充 WRONGTYPE/partial-write 测试。 |
| Needs Review Fix | **YES** |

**Resolution**

| Field | Content |
|-------|---------|
| Resolution Status | **RESOLVED** |
| Fix paths | `src/gov_service_agent/session/store.py`；`tests/test_session_store.py` |
| Fix summary | Success commit：`WATCH(meta, audit)` → revision 校验 → `TYPE(audit)` 仅允许 `none`/`list`，非法类型在 MULTI 前 `AUDIT_PERSISTENCE_FAILED` fail-closed（不 DEL）；failure audit 同步 TYPE 校验 + `with pipeline`。 |
| Regression test | `test_corrupt_audit_string_blocks_commit_without_partial_write`；`test_append_failure_audit_rejects_corrupt_string_audit_key` |
| Test result | **PASS**（真实 Redis 7.4.11） |
| Residual risk | 竞态在 TYPE 与 EXEC 之间改写 audit → `WatchError`→`SESSION_CONFLICT`；未单独加 sleep-based race 测试（WATCH 语义已覆盖）。 |
| Re-Review Final Status | **RESOLVED / VERIFIED** |

#### RF-F11-RV-002 — MAJOR

| Field | Content |
|-------|---------|
| Path | `src/gov_service_agent/session/api.py` + FastAPI request validation |
| Symbol | `session_turn` / `SessionTurnRequest` |
| Problem | Request body 校验失败时走 **FastAPI 默认 422**（`{"detail":[... "input": <raw>...]}`），**不是** `SessionTurnError`。实测 oversized/`input_text` 校验会把完整用户原文回显到响应（含数千字 marker）。 |
| Why | 破坏 public data-minimization；与冻结 Error contract shape 不一致。 |
| Trigger | 非法 UUID、空白 input、>4000 chars 等。 |
| TD/AC | D-F11-004/005；数据最小化 AC |
| Fix direction | 自定义 validation exception handler，映射为 `SessionTurnError` + safe message，**禁止** echo `input`；API tests 断言 422 body 不含 raw text。 |
| Needs Review Fix | **YES** |

**Resolution**

| Field | Content |
|-------|---------|
| Resolution Status | **RESOLVED** |
| Fix paths | `src/gov_service_agent/session/api.py`；`tests/test_session_api.py` |
| Fix summary | `SessionAPIRoute` 捕获 `RequestValidationError`，返回冻结 `SessionTurnError`/`INVALID_REQUEST`；仅尝试提取合法 UUID4 的 request_id/session_id；不 echo body / `exc.errors()`；不依赖 `main.py` handler。 |
| Regression test | `test_api_422_does_not_echo_raw_sentinel_input`；`test_api_422_oversized_input_is_not_echoed`；`test_api_422_invalid_uuid_uses_session_turn_error_shape` |
| Test result | **PASS** |
| Residual risk | 非法 request_id 时 response.request_id=`None`（不伪造 UUID）。 |
| Re-Review Final Status | **RESOLVED / VERIFIED** |

#### RF-F11-RV-003 — MAJOR

| Field | Content |
|-------|---------|
| Path | `src/gov_service_agent/session/service.py` |
| Symbol | `SessionTurnService._run_and_commit` |
| Problem | Processor 返回的 `state["request_id"]` / `state["input_text"]` **未**与当前 HTTP request 对齐校验，即以 Processor 返回 state 直接 sanitize/persist。 |
| Why | buggy/malicious Processor 可把错误 turn-local 身份写入后续 artifacts 生命周期（尽管 F11 scrub 不持久化这两字段，仍污染本轮 validate 与后续业务语义）。 |
| Trigger | Processor 返回篡改/过期的 request_id 或 input_text。 |
| TD/AC | Protocol trust boundary；turn identity |
| Fix direction | persist 前断言 `state.request_id == current` 且 `state.input_text == current`，否则 `AGENT_TURN_FAILED`。 |
| Needs Review Fix | **YES** |

**Resolution**

| Field | Content |
|-------|---------|
| Resolution Status | **RESOLVED** |
| Fix paths | `src/gov_service_agent/session/service.py`；`tests/test_session_service.py` |
| Fix summary | `validate_agent_state` 后强制校验 `request_id`/`input_text` 与当前 turn 一致；不一致 fail-closed → `AGENT_TURN_FAILED`，不覆盖、不 sanitize/persist/success-audit/cache。 |
| Regression test | `test_processor_wrong_request_id_fails_without_durable_commit`；`test_processor_wrong_input_text_fails_without_success_cache` |
| Test result | **PASS** |
| Residual risk | 无。 |
| Re-Review Final Status | **RESOLVED / VERIFIED** |

#### RF-F11-RV-004 — MINOR

| Field | Content |
|-------|---------|
| Path | `session/service.py` / `session/models.py` |
| Symbol | `AgentTurnResult` / success assembly |
| Problem | 未校验 `public_status` 与 `requires_user_input` 一致性（如 COMPLETED + True）。 |
| Fix direction | 显式矩阵校验或文档允许组合。 |
| Needs Review Fix | **YES** |

**Resolution**

| Field | Content |
|-------|---------|
| Resolution Status | **RESOLVED** |
| Fix paths | `session/models.py`（`SessionTurnSuccess`）；`session/service.py`；`tests/test_session_service.py` |
| Fix summary | COMPLETED⇒`requires_user_input=False`；AWAITING_USER_INPUT⇒`True`。Service 对 Processor 结果 fail-closed→`AGENT_TURN_FAILED`；模型层拦截损坏 cache replay。 |
| Regression test | `test_inconsistent_public_status_requires_user_input_fails_closed` |
| Test result | **PASS** |
| Residual risk | 无。 |
| Re-Review Final Status | **RESOLVED / VERIFIED** |

#### RF-F11-RV-005 — MINOR

| Field | Content |
|-------|---------|
| Path | `session/models.py` |
| Symbol | `SessionMeta` |
| Problem | 未强制 `created_at <= last_activity_at <= expires_at`；仅要求 tz-aware，未归一到 UTC。 |
| Fix direction | model validators + UTC normalize。 |
| Needs Review Fix | **YES** |

**Resolution**

| Field | Content |
|-------|---------|
| Resolution Status | **RESOLVED** |
| Fix paths | `session/models.py`；`tests/test_session_store.py` |
| Fix summary | 时间戳 `astimezone(UTC)`；`created_at <= last_activity_at <= expires_at` model_validator。过期语义仍由 `now > expires_at` 判定（三者内部序不变）。 |
| Regression test | `test_session_meta_timestamp_order_and_utc_normalize` |
| Test result | **PASS** |
| Residual risk | 损坏 meta 时间序 → `CHECKPOINT_INVALID`（先于 expiry 判定）。 |
| Re-Review Final Status | **RESOLVED / VERIFIED** |

#### RF-F11-RV-006 — MINOR

| Field | Content |
|-------|---------|
| Path | `session/store.py` |
| Symbol | `append_failure_audit` |
| Problem | failure-audit pipeline 未用 `with pipeline` context manager（与 success commit 不一致），异常路径资源归还较弱。 |
| Fix direction | 与 commit 相同 `with client.pipeline(True)`。 |
| Needs Review Fix | **YES** |

**Resolution**

| Field | Content |
|-------|---------|
| Resolution Status | **RESOLVED** |
| Fix paths | `session/store.py`；`tests/test_session_store.py` |
| Fix summary | `with client.pipeline(True)` + WATCH/TYPE 校验后 MULTI RPUSH/EXPIRE。 |
| Regression test | `test_append_failure_audit_rejects_corrupt_string_audit_key`（兼覆盖 pipeline 路径） |
| Test result | **PASS** |
| Residual risk | 无。 |
| Re-Review Final Status | **RESOLVED / VERIFIED** |

#### RF-F11-RV-007 — MINOR

| Field | Content |
|-------|---------|
| Path | `tests/test_session_*.py` |
| Symbol | store/API suites |
| Problem | 缺少 MULTI runtime/WRONGTYPE partial-write 测试；API 422 仅断言 status，未断言无 raw input / SessionTurnError shape。 |
| Fix direction | 增加对应 negative/contract tests（随 Production fix）。 |
| Needs Review Fix | **YES** |

**Resolution**

| Field | Content |
|-------|---------|
| Resolution Status | **RESOLVED** |
| Fix paths | `tests/test_session_store.py`；`tests/test_session_api.py`（随 RV-001/002） |
| Fix summary | 已增加 WRONGTYPE/partial-write 与受控 422 shape/no-echo regressions。 |
| Regression test | 见 RV-001 / RV-002 |
| Test result | **PASS**；F11 suite **49**（原 40 + 9） |
| Residual risk | 无。 |
| Re-Review Final Status | **RESOLVED / VERIFIED** |

#### RF-F11-RV-008 — INFO

Audit LIST 在 retention 窗口内可无界增长（Demo scaling limitation）。

**Resolution Status:** **ACCEPTED / OPEN-INFO**（Phase-1 边界；不扩大为 Stream/Cluster）。
**Re-Review Final Status:** **ACCEPTED INFO**

#### RF-F11-RV-009 — INFO

Phase-1 无认证：持有 `session_id` 即可续写会话（已知边界）。

**Resolution Status:** **ACCEPTED / OPEN-INFO**（不引入 OAuth/鉴权）。
**Re-Review Final Status:** **ACCEPTED INFO**

#### RF-F11-RV-010 — INFO

`api.session_turn` 内 `except ValidationError` 对 body 预校验基本不可达；真正 422 来自 FastAPI。

**Resolution Status:** **ACCEPTED / OPEN-INFO**（RV-002 已用 route-local handler 覆盖真正 422；内层 ValidationError 保留为防御性分支）。
**Re-Review Final Status:** **ACCEPTED INFO**

#### RF-F11-RV-011 — INFO

允许空 `response_text`；未在 Doc 明确策略。

**Resolution Status:** **ACCEPTED / OPEN-INFO**（保持允许空字符串）。
**Re-Review Final Status:** **ACCEPTED INFO**

### 61.4 Positive confirmations (selected)

Replay/idempotency、lock ordering、token-safe release + LockError swallow、WATCH placement、load-after-lock、corrupt cache fail-closed、F11/F12 boundary、no pickle、UUID4、Settings TTL>0、Test Evidence 40/585 与文档一致。

### 61.5 Review Fix Evidence

| Item | Value |
|------|-------|
| F11 Review Fix | **COMPLETE** |
| Re-Review Readiness | **READY FOR RE-REVIEW** |
| F11 Review（本阶段后） | **仍为 NEEDS_FIX / AWAITING RE-REVIEW**（不得自行 PASS） |
| MAJOR resolved | **3 / 3**（RV-001..003） |
| MINOR resolved | **4 / 4**（RV-004..007） |
| INFO | **4** ACCEPTED / OPEN-INFO（未扩大 scope） |
| Ending changed paths | **11**（无第 12 path；无 Code-Reading） |
| F11 targeted tests | **49 passed**（原 40 + 9 regressions） |
| Full suite | **594 passed, 13 skipped, 0 failed**（原 585 + 9） |
| compileall / pip check | **PASS** |
| Redis used | **7.4.11** localhost；prefix `govagent:test:f11:<uuid>`；无 FLUSHDB/ALL |
| Production Fake Processor | **0** |
| main.py / F08–F10 Production | **unchanged** |

### 61.6 Re-Review Evidence

| Item | Value |
|------|-------|
| F11 Re-Review | **PASS** |
| F11 Review Final | **PASS** |
| Explanation Readiness | **READY FOR EXPLANATION** |
| Method | 独立代码审查 + 既有 regression/suite 证据；**未**改 Production/Tests；**未**无故重跑 full suite；**无** Redis mutation |
| BLOCKING / MAJOR / MINOR remaining | **0 / 0 / 0** |
| INFO remaining | **4**（RV-008…011 ACCEPTED INFO；未升级） |
| RV-001…007 | 逐条对照 `store/api/service/models` + 对应 regression **VERIFIED** |
| Architecture / F11-F12 / raw-input / confirmed_business_id gates | **PASS** |
| Ending changed paths | **11**（仅 Feature Doc 内容更新） |
| Production/Test/Settings/pyproject hash freeze | **unchanged**（相对 Re-Review 开始） |

---

## 62. F11 Explanation / Implementation Walkthrough

> 本章按**业务流程**解释 F11，不以文件目录为主线。符号（如 `SessionTurnService`）仅作映射锚点。
> Review / Review Fix / Re-Review 证据见 §61，本章不删除历史。

### 62.1 一句话总结

**F11 负责把一次无状态的 HTTP Agent 调用，升级为可跨请求恢复、可审计、可幂等重试并具备并发一致性保护的会话执行能力；具体政务业务处理器由 F12 注入。**

### 62.2 F11 解决什么问题（用户在做什么）

用户**不是**在操作 Redis。用户只是在连续和政务 Agent 对话。

例：

1. 第一轮：「我辞职了，现在没单位，想自己交社保」——系统可能还要确认就业类型。
2. 第二轮：「平时接零活，没有固定单位」——系统必须知道这句话属于**同一业务会话**的下一答，而不是全新对话。

F08–F10 已能在**单次 Python 调用**内处理槽位/确认；但真实交互是**两轮独立 HTTP Request**。没有跨请求持久化，第二轮就不知道「上一轮问到哪里了」。

F11 的本质：把上一轮 **controlled 业务状态**存起来；下一轮先恢复「问到哪里了」，再处理用户**新回答**。

**它不等于聊天记录。** Checkpoint 保存的是业务处理状态（缺哪个槽、是否在解释旁路、是否等待 F10 确认），不是整段 transcript。

### 62.3 Session vs Request（且 Session ≠ User Account）

| 概念 | 含义 | 示例 |
|------|------|------|
| `session_id` | 一次连续政务对话的身份 | Turn1/Turn2 共用 `S1` |
| `request_id` | 这一轮 HTTP 请求的身份 | Turn1=`R1`，Turn2=`R2` |
| User Account | 登录/认证身份 | **不属于 F11** |

Session ≠ Request。Session ≠ User Account。持有 `session_id` UUID **不等于**通过 SSO/OAuth（见 INFO RV-009）。

### 62.4 主业务流程（端到端）

```
用户输入
  ↓
POST /api/v1/session/turn          （SessionTurnRequest / create_session_router）
  ↓
request_id / session_id 校验
  ↓
Request Replay / Idempotency       （fingerprint + request result cache）
  ↓
Request Lock                       （同 request_id 串行）
  ↓
Session Resolve                    （新 session 生成 id / 已有 session 加载）
  ↓
Session Lock                       （同 session 串行）
  ↓
SessionMeta / Checkpoint Restore
  ↓
重建当前轮 AgentState              （from_persisted + 当前 request）
  ↓
AgentTurnProcessor                 （Protocol；Government 实现属 F12）
  ↓
State Validation / Sanitization    （含 turn identity、status 一致性）
  ↓
Revision + WATCH(meta, audit)
  ↓
MULTI/EXEC Durable Commit          （Meta + Checkpoint + Audit + Request Result + TTL）
  ↓
Release Locks
  ↓
SessionTurnSuccess → 返回用户
```

### 62.5 New Session（首次请求）

客户端只提供：`request_id` + `input_text`（无 `session_id`）。

1. `SessionTurnService` 生成新 `session_id`。
2. Redis 无旧 checkpoint → `restored_state = None`。
3. 调用 `AgentTurnProcessor.process_turn(...)`。
4. 成功后 revision：**0 → 1**。
5. 同事务写入：`SessionMeta`、`SessionCheckpoint`、`AuditEvent(TURN_COMPLETED)`、`CachedRequestResult`，并设置 TTL。
6. 把 `session_id` 返回客户端，供后续续写。

若**首次** Processor 就失败：不得创建可继续使用的 active session（没有稳定 checkpoint）。

### 62.6 Existing Session（续写）

客户端带：`session_id = S1`，但 `request_id` 必须是新的 `R2`。

1. Session Lock 之后 `load_active_session`。
2. 恢复 checkpoint 中的：`phase` / `status` / `artifacts` / `error`。
3. **绝不恢复**上一轮的：`input_text`、`request_id`、`orchestration_trace`。
4. 用当前 HTTP 的 `request_id` / `input_text` + 空的 `orchestration_trace` 重建 `AgentState`。
5. Processor 处理本轮；成功则 revision **N → N+1**。

### 62.7 Checkpoint 与 AgentState 重建

**Checkpoint 不是**聊天记录、LLM Memory dump、或整个 Python runtime。它是下一轮继续业务所需的**最小 controlled state**。

`AgentState` 七个顶层字段：`request_id`、`input_text`、`phase`、`status`、`artifacts`、`error`、`orchestration_trace`。

`PersistedAgentState`（checkpoint）只存：`phase`、`status`、`artifacts`、`error`。稳定成功 checkpoint 要求 `error = None`。

恢复公式：

```
Redis Persisted：phase / status / artifacts / error
        +
Current Request：request_id / input_text
        +
fresh：orchestration_trace = []
        ↓
Current AgentState
```

**为什么旧 `input_text` 不能恢复：**
上一轮可能已进入 F10「等待确认」。下一轮用户说「确认」。若恢复旧输入（如整段业务描述），F10 可能再次看到上一轮业务原文，而不是本轮「确认」。故当前轮 `input_text` **只来自当前 HTTP request**。

**为什么 `orchestration_trace` 不恢复：** 它描述**本请求内部**发生了什么，不是长期业务事实；每轮重新开始，避免把历史轨迹误当当前事实。

### 62.8 F09 / F10 跨轮连续性

**F09：** 若上一轮在问「您的就业类型是什么？」，`artifacts["f09"]` 保存 pending slot / `required_slot` / `slot_context` / 解释旁路状态等。下一轮用户答「平时接零活…」时，F11 恢复 F09 controlled context，并注入**新的** `input_text`，F09 才知道这句话是在回答那个缺失槽位。

**F09 Explanation Side Route：** 用户若问「灵活就业是什么意思？」走解释旁路，Business Graph 不推进，pending slot 保持。Checkpoint 必须保存该状态；下一轮真正回答就业类型时仍续写原 pending slot。

**F10：** F04 只产生 Terminal Candidate，不是 `confirmed_business_id`。F10 PREPARE 把确认上下文放入 `artifacts["f10"]`；F11 只负责跨请求保存。下一轮用户输入「确认」时，F11 恢复 PREPARE state，但 `input_text` 用当前「确认」。**未来** F12 的 concrete processor 再调 F10 RESOLVE；**F11 自己不解析「确认」语义，也不做 `candidate → confirmed` 赋值。**

**F11 `confirmed_business_id` 赋值 = 0。** 权威仍在 F10。

### 62.9 AgentTurnProcessor 与 F11/F12 边界

F11 **不知道**真实政府 Agent 如何编排业务。它定义 `AgentTurnProcessor` Protocol：

- 输入：`session_id`、`request_id`、当前 `input_text`、恢复后的 `AgentState|None`
- 输出：`AgentTurnResult`（新 `AgentState`、`response_text`、`requires_user_input`、`public_status`）

若 F11 现在直接拼 F03/F06/F09/F10，会把「会话基础设施」与「政务业务编排」混在一起。故：

- **F11**：通用会话运行底座（API / Service / Redis / Checkpoint / Audit / 幂等 / 并发）
- **F12**：实现 `GovernmentAgentTurnProcessor`，编排 F03–F10（及未来 KG）

```
HTTP
 │
 ▼
F11 Session API（create_session_router / SessionAPIRoute）
 │
 ▼
F11 SessionTurnService
 │
 ├── Redis restore / locks / replay
 │
 ▼
AgentTurnProcessor Protocol
 │
 │  ← F12 implements this（目前 NOT IMPLEMENTED）
 │
 ▼
GovernmentAgentTurnProcessor（未来）
 │
 ├── F06 Semantic Retrieval
 ├── F03/F04 Decision Graph
 ├── F09 Interaction
 ├── F10 Confirmation
 └── future KG
 │
 ▼
new AgentState
 │
 ▼
F11 persistence / audit / request cache
 │
 ▼
HTTP response
```

**`main.py` 未 `include_router`：** 因为正式挂载需要真实 Government Processor（F12）。F11 已是**生产级可注入 Capability**，不是「假 API」。假的只是 tests 里的 Test Double；**Production Fake Processor = 0**。

Router / Service / Store / Checkpoint / Audit 都是真实现。

### 62.10 Idempotency / Fingerprint / Replay

场景：客户端发 `request_id=R1` 已成功，但网络超时后重发同一 `R1` + 同一 payload。若再次调 Agent，可能双重推进业务。

F11 成功后写入 **Request Result Cache**。仅 `request_id` 不够——误用同一 id 发不同内容须冲突。故计算 **SHA-256 fingerprint**（canonical JSON：`session_id-or-null` + `input_text`），**只存 digest，不存 raw input**。

```
request_id 已有？
 ├─ NO → 正常处理
 └─ YES
      fingerprint 一致？
       ├─ YES → 返回 cached public result
       │         （Processor 二次调用=0；revision+1=0；success audit 追加=0；Session TTL 刷新=0）
       └─ NO  → REQUEST_ID_REUSE_CONFLICT
```

### 62.11 并发：Request Lock / Session Lock

**Request Lock：** 两个相同 R1 几乎同时到达，都可能 cache miss。先 lookup → miss → 获 Request Lock → **再 lookup** → 只有一个真正执行。

**Session Lock：** R2/R3 不同 request_id 但同 session S1；若并行都从 revision 3 起步会互相覆盖。故同 session 串行。

**顺序：** 先 request lock，再 session lock；释放相反。无 global lock——不同 session 可并行。

**锁不够：** Lock TTL 默认 120s；Processor 极端超时后锁可能过期。故还有第二层：**revision + WATCH**。

### 62.12 Revision / WATCH / MULTI（及 RV-001）

Checkpoint revision 类似状态版本号：成功轮次 1、2、3…。请求读到 N，提交前必须证明 Redis 仍为 N，才允许 N→N+1。

Redis `WATCH`：基于被监视 key 的乐观并发；EXEC 前若被改，则失败。F11：`WATCH(meta, audit)` → 读 revision → 检查 audit `TYPE`（仅允许 `none`/`list`）→ `MULTI` → SET meta / SET checkpoint / RPUSH audit / EXPIRE audit / SET result(+TTL) → `EXEC`。

**RV-001（已修）：** Redis MULTI 不是 RDBMS 式「任一 runtime 错误整笔 rollback」。Audit 用 `RPUSH`；若 audit key 被污染成 STRING，可能 SET 已成功而 RPUSH WRONGTYPE → **partial durable state**。修复：MULTI 前 TYPE fail-closed，且 audit 加入 WATCH，竞态改写触发 `WatchError`→`SESSION_CONFLICT`。不自动 DEL 损坏 audit。

### 62.13 SessionMeta / TTL / Expired Marker / 三态区分

`SessionMeta`：控制头（`schema_version`、`session_id`、`created_at`、`last_activity_at`、`expires_at`、`checkpoint_revision`）。不存用户问题原文。时间戳均为 **timezone-aware UTC**，且 `created_at ≤ last_activity_at ≤ expires_at`。

默认 Session inactivity TTL：**1800s（30min）**。成功新 turn 刷新 `last_activity_at` / `expires_at` / checkpoint TTL；**Replay 不刷新**。

若 30min 后所有 key 一起消失，无法区分「从未存在」与「刚过期」。故 Checkpoint TTL=30min，Meta TTL=30min+**24h expired-marker window**。

| 现象 | 结果 |
|------|------|
| Meta 不存在 | `SESSION_NOT_FOUND` |
| Meta 在但 `now > expires_at` | `SESSION_EXPIRED` |
| Meta 仍 active 但 checkpoint 丢失 | `CHECKPOINT_INVALID` |

不得自动新建 session 掩盖问题。

Request Result Cache TTL 默认 **600s**（短时网络重试，非永久历史）。Audit TTL 默认 **604800s（7天）**，与 Session 30min 分离。

### 62.14 Audit（≠ Logging）

Logging：运维/排障。Audit：回答「某 Session 发生了哪些受控业务状态变化」。

事件：`TURN_COMPLETED` / `TURN_FAILED`。记录 session/request、时间、before/after phase·status、revision before/after、failure code。**不记录**用户原文、`response_text`、artifacts、traceback、secret。

成功：与 meta/checkpoint/result 同事务；new session 0→1，existing N→N+1。
失败：checkpoint **不推进**，revision N→N，可追加 `TURN_FAILED`。
Persistence 失败：即使 Processor 已算出答案，也**不得**对用户返回 success（否则下一轮状态丢失）。

**Restart continuity：** 状态在 Redis，不依赖进程内 dict；Service 重建只要 Redis 在即可续写。

内部 key（前缀默认 `govagent:f11`）：`session:{id}:meta|checkpoint|audit`、`request:{id}:result`、locks——**不返回给 API client**。

### 62.15 Failure Path

```
Processor 成功？
 ├─ NO
 │   ├─ 保留旧 checkpoint
 │   ├─ revision 不变
 │   ├─ 尝试 TURN_FAILED audit（已有 session）
 │   └─ AGENT_TURN_FAILED
 │
 └─ YES
     │
     ▼
  durable commit 成功？
     ├─ NO → 不返回 success（PERSISTENCE_UNAVAILABLE 等）
     └─ YES → 返回 public success
```

### 62.16 数据最小化、422、Processor Identity、Status 一致性

- Checkpoint / Audit / Request Cache / Logging / 公开 422：**不存/不回显 raw USER input**。
- FastAPI 默认 422 可能 echo `input`。F11 用 `SessionAPIRoute` 捕获 `RequestValidationError` → 固定 `SessionTurnError` / `INVALID_REQUEST`。**不依赖** main.py 全局 handler；不返回 `exc.errors()`。
- Processor 返回后：`validate_agent_state`，再强制 `state.request_id` / `state.input_text` 等于当前请求。不一致 → `AGENT_TURN_FAILED`，**禁止** silent correction 后继续持久化（会隐藏 Processor bug）。
- `COMPLETED ⇒ requires_user_input=False`；`AWAITING_USER_INPUT ⇒ True`（Service + `SessionTurnSuccess`；损坏 cache 亦 fail-closed）。

公开 Success：仅 `session_id`、`request_id`、`status`、`response_text`、`requires_user_input`。
公开 Error：受控 code + 固定安全文案；无 Redis 异常、traceback、secret。

### 62.17 Golden Scenario（Session 连续性；非 F12 E2E）

| 轮次 | 用户 | F11 行为 | 业务含义（未来 F12） |
|------|------|----------|----------------------|
| Turn1 | 「我辞职了…想自己交社保」 | 建 `S1`/`R1`，`restored=None`，rev 0→1 | RAG/F03/F09 可能形成「需确认就业类型」 |
| Turn2 | 「平时接零活…」 | 载 rev1，恢复 F09 pending + 新 input，rev→2 | F09 映射槽位，图继续推进 |
| 后续 | — | checkpoint 保存 F10 PREPARE | F04 候选如 DEMO_SS_001；**仍是 candidate** |
| 确认轮 | 「确认」 | 恢复 F10 PREPARE + input=「确认」 | F12→F10 RESOLVE 才设 `confirmed_business_id` |

**F11 测试中的 Golden 验证的是：** Session/Checkpoint 连续性与当前轮 input 重建。**不证明**真实 RAG / Decision Graph / F09 / F10 已通过 Session API 整串 E2E——那是 **F12**。

### 62.18 测试分层与最终基线

| 层 | 作用 | 数量 |
|----|------|------|
| Store | 真实 Redis 7.4.11 基础设施 | **16 passed** |
| Service | 生命周期 + Test Double Processor | **20 passed** |
| API | 真实 Router+Service + test-only Processor | **13 passed** |
| Combined F11 | | **49 passed** |
| Full suite | | **594 passed / 13 skipped / 0 failed / 0 warnings** |

Test-only Processor 合法：可控返回与异常、统计调用次数；**仅存在于 tests**。Production Fake = 0。

### 62.19 Known INFO Boundaries（不扩 Scope）

| ID | 摘要 |
|----|------|
| RV-008 | Audit LIST 在 7 天 retention 内可无界增长；Phase-1 Demo 接受；未来再谈 cap/archive/stream |
| RV-009 | `session_id` 非认证身份；无 SSO/OAuth 属已知边界 |
| RV-010 | endpoint 内部分 ValidationError 在 route-local 处理后基本不可达；保留 defensive branch |
| RV-011 | 允许 `response_text=""`；当前 contract 接受，非 correctness bug |

不因此引入 Redis Stream / OAuth / Cluster / PostgreSQL。

### 62.20 给初学者

若完全没有 F11：第一轮 Agent 问「就业类型？」；第二轮用户答「平时接零活」——后端不知道在回答什么。F11 保存的是「问到哪里了」的 **controlled checkpoint**，不是聊天流水账。

### 62.21 How to Read F11 Next（Code-Reading 预告）

下一阶段 **Code-Reading** 必须继续采用业务流程主线：

用户输入 → API → 幂等 → 锁 → Redis 恢复 → AgentTurnProcessor → 新状态 → 持久化 → Audit → Response，

再映射到具体文件与函数。

**不得**以「先读 `models.py`，再读 `store.py`」为主线。每一步说明：用户在做什么 → 调用哪个模块/函数 → 为什么有这个组件 → 输入是什么 → 输出给谁。

独立 Code-Reading 文档路径：`docs/code-reading/F11-session-api-redis-checkpoint-audit-code-reading.md` —— **本阶段尚未创建**。

### 62.22 Explanation Evidence

| Item | Value |
|------|-------|
| F11 Explanation | **COMPLETE** |
| Code-Reading Readiness | **READY FOR CODE-READING** |
| Production / Tests / Settings / pyproject | **unchanged** |
| pytest / Redis mutation | **NO** |
| Ending changed paths | **11**（仅 Feature Doc） |
| Code-Reading Doc | **NOT CREATED**（当时；现见 §64） |

---

## 64. Code-Reading Evidence

| Item | Value |
|------|-------|
| F11 Code-Reading | **COMPLETE** |
| Code-Reading Doc | `docs/code-reading/F11-session-api-redis-checkpoint-audit-code-reading.md` |
| Commit Readiness | **READY FOR COMMIT** |
| Main spine | 用户输入 → API → 幂等 → 锁 → Redis 恢复 → AgentState 重建 → Processor → validate/sanitize → WATCH/MULTI → Audit/Cache → Response |
| File-order as primary spine | **NO** |
| Real symbols verified | `create_session_router` / `session_turn` / `SessionAPIRoute` / `SessionTurnService.handle_turn` / `compute_request_fingerprint` / `_lookup_replay` / `get_cached_result` / `acquire_request_lock` / `acquire_session_lock` / `hold_lock` / `load_active_session` / `from_persisted` / `to_persisted` / `AgentTurnProcessor.process_turn` / `commit_successful_turn` / `append_failure_audit` / `dumps_json` |
| F09 continuity mapped | `empty_f09_namespace` 8 keys + `slot_context` / explanation |
| F10 continuity mapped | `empty_f10_namespace` 8 keys；PREPARE/RESOLVE；`confirmed_business_id` authority = F10 |
| Review fixes mapped | RV-001～007 code impact；INFO RV-008～011 |
| Test mapping | 按业务能力映射真实 test function names；16/20/13/49；full suite 594/13/0/0 |
| F11/F12 boundary | Protocol 接缝；Government Processor NOT IMPLEMENTED；`main.py` 未激活 |
| Production / Tests / Settings / pyproject | **unchanged** |
| Ending changed paths | **12** |

---

## 65. STOP

F11 Resource Gate = **CLOSED / READY**。
F11 Requirement = **COMPLETE**。
F11 Requirement Finalization = **NOT REQUIRED**。
F11 Technical Design = **FINAL / CLOSED**。
F11 Technical Design Finalization = **COMPLETE**。
F11 Confirm = **COMPLETE**。
F11 Code = **COMPLETE**。
F11 Test = **PASS**。
F11 Review = **PASS**。
F11 Review Fix = **COMPLETE**。
F11 Re-Review = **PASS**。
F11 Explanation = **COMPLETE**。
F11 Code-Reading = **COMPLETE**。
F11 Commit = **NOT STARTED**。
F11 Push = **NOT STARTED**。

**Next Readiness = READY FOR COMMIT。**

**STOP。禁止自动进入 Commit / Push。等待 Owner 单独授权。**
