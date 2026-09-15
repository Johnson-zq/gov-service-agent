# F11 Session API / Redis / Checkpoint / Audit 代码阅读指南

> 以业务请求流为主线，从用户输入追踪到 API 响应。
> **先理解业务，再映射代码。** 禁止以 `models → store → service → api` 为阅读主线。

权威 Feature 文档：`docs/features/F11-session-api-redis-checkpoint-audit.md`

---

## 0. 读完本文应能回答

1. 第二轮用户输入为什么能接上第一轮？
2. Session 和 Request 有什么区别？
3. F11 为什么不保存聊天历史？
4. Redis 中到底保存了什么？
5. 为什么 Request Lock 和 Session Lock 都需要？
6. 为什么 Lock 之外还需要 revision + WATCH？
7. 为什么成功响应必须等 Redis durable commit？
8. F09/F10 状态怎样跨 HTTP request？
9. F11 为什么没有真正调用 F03～F10？
10. F12 后续从哪里接入？

---

## 1. 完整业务流程图

```
用户
 │
 │ POST /api/v1/session/turn
 ▼
Session API
 │  create_session_router / session_turn / SessionAPIRoute
 ├─ request validation（SessionTurnRequest）
 │
 ▼
SessionTurnService.handle_turn
 │
 ├─ compute_request_fingerprint
 ├─ _lookup_replay → RedisSessionStore.get_cached_result
 ├─ acquire_request_lock（+ double-check lookup）
 ├─ _handle_new_session / _handle_existing_session
 ├─ hold_lock(session lock)
 │
 ▼
RedisSessionStore.load_active_session
 │  SessionMeta + SessionCheckpoint
 │
 ▼
from_persisted → 重建当前轮 AgentState
 │
 ▼
AgentTurnProcessor.process_turn   ← Protocol；F12 提供具体实现（当前 Production 无 concrete）
 │
 ▼
AgentTurnResult
 │
 ▼
validate_agent_state + turn identity + status/requires 一致性
 │
 ▼
to_persisted（sanitize）
 │
 ▼
RedisSessionStore.commit_successful_turn
 │  WATCH(meta, audit) → TYPE → MULTI/EXEC
 ├─ SessionMeta
 ├─ Checkpoint
 ├─ Audit（TURN_COMPLETED）
 ├─ Request Result Cache
 └─ TTL
 │
 ▼
SessionTurnSuccess → 用户
```

**醒目说明：** 图中的 Government business processor（F03～F10 编排）**目前没有 Production concrete implementation**。F11 只提供 `AgentTurnProcessor` Protocol 接缝；测试里的 processor 是 Test Double，Production Fake = 0。

---

## 2. 用户视角：F11 解决什么

### 业务场景

**第一轮**
用户：「我辞职了，现在没单位，想自己交社保」
系统可能问：「您的就业类型是什么？」

**第二轮**
用户：「平时接零活，没有固定单位」

HTTP 本身无状态。若第二轮不恢复上一轮 controlled state，系统不知道这句话在回答哪个问题。

**F11 解决：** 跨请求保存「问到哪里了」的 controlled checkpoint，再注入**当前轮** `input_text`。

### F11 不是什么

| 不是 | 是 |
|------|----|
| 聊天记录系统 | Session Execution Infrastructure |
| 用户账号 / SSO | 会话 UUID 身份（非认证） |
| LLM Memory | Controlled AgentState 持久化 |
| Business Decision Graph / RAG / Rule Engine / KG | 为上述能力提供跨 HTTP 底座 |
| 完整 Government Agent | 可注入 Capability；Government Processor 属 F12 |

---

## 3. 谁拥有真相（Authority）

| 问题 | Authority |
|------|-----------|
| 当前 HTTP input | 当前 `SessionTurnRequest.input_text`（F11 Request） |
| Session continuity | F11（Redis SessionMeta / Checkpoint） |
| 业务下一节点 | Business Decision Graph（F03/F04） |
| slot interpretation | F09 / controlled mapping |
| terminal candidate | F04 |
| `confirmed_business_id` | **F10**（F11 assignment = 0） |
| materials / location / channel | Knowledge capability（后续） |
| Redis persistence / audit / 幂等 | F11 |

**Source of Truth 层次：**

- HTTP request → 当前 turn input 真相
- Redis checkpoint → 跨 turn controlled state 真相
- `AgentTurnProcessor` → 当前 turn 处理结果真相
- F11 → 只编排 session lifecycle，**不是**业务真相数据库

---

## 4. 关键节点 Input → Output

| Step | Input | Output | Next |
|------|-------|--------|------|
| API | HTTP JSON body | `SessionTurnRequest` 或 controlled 422 | `SessionTurnService.handle_turn` |
| Replay | `request_id` + fingerprint | cached `SessionTurnSuccess` 或 miss | Request Lock / 正常处理 |
| Session Restore | `session_id` + now | `SessionMeta` + `SessionCheckpoint` | `from_persisted` |
| AgentState rebuild | Persisted + 当前 request | `AgentState` | Processor |
| Processor | session/request/input/restored | `AgentTurnResult` | validate / sanitize |
| Sanitize | `AgentState` | `PersistedAgentState` | commit |
| Persistence | meta/cp/audit/result + expected_revision | durable Redis keys | API success |
| Response | `SessionTurnSuccess` | HTTP 200 JSON | 用户 |

---

## 5. 步骤：用户提交本轮消息 → API

### 业务上下文

用户提交一轮政务对话消息。

### 真实代码

| 项 | Symbol |
|----|--------|
| 文件 | `src/gov_service_agent/session/api.py` |
| Router factory | `create_session_router(service: SessionTurnService) -> APIRouter` |
| Route | 嵌套函数 `session_turn`；路径 `POST /api/v1/session/turn` |
| Route class | `SessionAPIRoute`（`APIRouter(route_class=SessionAPIRoute)`） |
| Override | `SessionAPIRoute.get_route_handler` |

### 为什么存在

把 HTTP 世界转成 F11 Session Service 调用。**API 不直接访问 Redis。**

### 输入 / 输出

- 输入：`SessionTurnRequest`（`models.py`）
  - `request_id`：当前 HTTP turn ID（UUID4）
  - `session_id`：多轮会话 ID；新会话可为 `None`
  - `input_text`：1～4000，非空白
- 输出：成功 → `SessionTurnSuccess`；失败 → `_error_response` → `SessionTurnError`

### 关键 invariant

- `create_session_router` 仅依赖注入 `SessionTurnService`（DI-only）
- `main.py` **未** `include_router`（F12 激活）

### 422 安全（Review Fix RV-002）

FastAPI 默认 validation `detail` 可能 echo raw `input`。
`SessionAPIRoute.get_route_handler` 捕获 `RequestValidationError`，经 `_safe_ids_from_request` 仅提取合法 UUID4，返回固定 `INVALID_REQUEST` 文案；**不**返回 `exc.errors()`，**不** log body。不依赖 main.py 全局 handler。

### 相关 tests

- `test_api_request_session_and_input_validation`
- `test_api_422_does_not_echo_raw_sentinel_input`
- `test_api_422_oversized_input_is_not_echoed`
- `test_api_422_invalid_uuid_uses_session_turn_error_shape`

---

## 6. 步骤：进入 SessionTurnService（主编排）

### 业务上下文

一次 turn 的生命周期 orchestration（幂等、锁、恢复、调用 Processor、持久化）。

### 真实代码

| 项 | Symbol |
|----|--------|
| 文件 | `src/gov_service_agent/session/service.py` |
| 类 | `SessionTurnService` |
| 入口 | `SessionTurnService.handle_turn(self, request: SessionTurnRequest) -> SessionTurnSuccess` |

### 为什么存在

F11 **最重要**的 session lifecycle orchestrator。
**不是** Government business orchestrator（不做 RAG/图/F09/F10 业务判断）。

### 输入 / 输出

- 输入：已校验的 `SessionTurnRequest`
- 输出：`SessionTurnSuccess`，或抛 `SessionDomainError`（由 API 映射 HTTP）

### 相关 tests

- `test_new_session_calls_processor_once_with_none_restored_state`
- `test_processor_invocation_contract_has_no_redis_or_http_dependencies`

---

## 7. 步骤：Fingerprint（幂等指纹）

### 业务问题

客户端超时重发：是同一 retry，还是同 `request_id` 换了内容？

### 真实代码

`compute_request_fingerprint(*, session_id: str | None, input_text: str) -> str`

- canonical JSON：`{"session_id", "input_text"}`，`sort_keys=True`，`allow_nan=False`
- `hashlib.sha256(...).hexdigest()`
- **只持久化 digest**，不存 raw input

调用点：`SessionTurnService.handle_turn` 开头。

### 相关 tests

- `test_request_id_reuse_with_different_payload_conflicts_without_second_processor_call`
- `test_request_cache_physical_structure_excludes_raw_input`

---

## 8. 步骤：Replay Cache Lookup

### 业务上下文

同 `request_id` + 同 fingerprint → 直接返回上次公开成功结果。

### 真实代码

1. `SessionTurnService._lookup_replay`
2. → `RedisSessionStore.get_cached_result(request_id)`
3. 比较 `cached.request_fingerprint`
4. 不一致 → `SessionErrorCode.REQUEST_ID_REUSE_CONFLICT`
5. 一致 → `SessionTurnSuccess.model_validate(...)` 再返回

### Replay 语义（关键）

| 行为 | Replay 时 |
|------|-----------|
| Processor 二次调用 | **否** |
| revision +1 | **否** |
| success audit 追加 | **否** |
| Session TTL 刷新 | **否** |

### 相关 tests

- `test_replay_same_request_does_not_reinvoke_processor_or_refresh_session`
- `test_api_replay_returns_same_public_response_without_second_processor_call`

---

## 9. 步骤：Request Lock + Double Check

### 业务问题

两个相同 R1 几乎同时到达，都可能 cache miss → 双重执行 Agent。

### 真实代码

`handle_turn` 内：

1. 首次 `_lookup_replay`
2. miss → `RedisSessionStore.acquire_request_lock(request_id)`
3. `lock.acquire(blocking=False)`；失败且仍无 cache → `REQUEST_IN_PROGRESS`
4. **再** `_lookup_replay`（double-check）
5. `finally`：`request_lock.release()`（吞 `LockError`）

锁 key：`RedisSessionStore._request_lock_key` → `{prefix}:lock:request:{request_id}`
TTL：Settings `request_lock_ttl_seconds` 默认 **120**。

### 相关 tests

- `test_same_request_id_concurrent_race_invokes_processor_only_once`
- `test_api_request_in_progress_mapping_with_held_lock`
- `test_request_and_session_locks_are_per_id_and_token_safe`

---

## 10. 步骤：Session Resolve（新 / 已有）

### A. New Session（`session_id is None`）

**真实代码：** `SessionTurnService._handle_new_session`

1. `_default_id_generator` / 注入的 `id_generator` → UUID4
2. `acquire_session_lock` + `hold_lock`
3. `meta_exists` → 碰撞则重试（最多 `max_new_session_id_attempts`）
4. `_run_and_commit(..., expected_revision=0, restored_state=None)`

**业务：** 无旧 Meta/Checkpoint；Processor 收到 `restored_state=None`；成功 revision **0→1**。

**相关 tests：** `test_new_session_calls_processor_once_with_none_restored_state`；`test_new_session_processor_failure_does_not_return_usable_session`

### B. Existing Session

**真实代码：** `SessionTurnService._handle_existing_session`

1. 客户端只应提供：`session_id` / `request_id` / `input_text`（不信任任何 internal state）
2. Session lock 内：`load_active_session` → `from_persisted(..., request_id=当前, input_text=当前)`
3. `_run_and_commit(..., expected_revision=meta.checkpoint_revision, ...)`

**相关 tests：** `test_existing_session_restores_checkpoint_before_processing_current_input`

---

## 11. 步骤：Session Lock 与锁顺序

### 业务问题

R2、R3 不同 `request_id`，但同 session S1 → 不能并发从同一 revision 互相覆盖。

### 真实代码

- `RedisSessionStore.acquire_session_lock` → `_session_lock_key`
- `hold_lock` context manager（`store.py`）：acquire / `finally` release（`LockError` swallow）

**顺序：** Request Lock → Session Lock；释放 Session → Request。
**无 Global Lock：** Session A/B 不同 lock key，可并行（`test_different_sessions_use_independent_locks`）。

**为什么还要 revision：** Lock TTL 120s；极端超时后锁可能过期。revision + WATCH 是第二层一致性。

---

## 12. 步骤：从 Redis 恢复（核心）

### 真实代码

`RedisSessionStore.load_active_session(session_id, *, now) -> tuple[SessionMeta, SessionCheckpoint]`

顺序（真实实现）：

1. `GET` meta（`_meta_key`）— 缺失 → `SESSION_NOT_FOUND`
2. `SessionMeta.model_validate` — 坏 JSON/校验失败 → `CHECKPOINT_INVALID`
3. schema / session_id 一致性
4. `now > meta.expires_at` → `SESSION_EXPIRED`
5. `GET` checkpoint — 缺失 → `CHECKPOINT_INVALID`
6. schema_version / `SessionCheckpoint.model_validate` / revision 对齐 meta

### SessionMeta（`models.SessionMeta`）

字段：`schema_version`, `session_id`, `created_at`, `last_activity_at`, `expires_at`, `checkpoint_revision`

业务角色：控制头——谁、何时创建/活跃、何时过期、当前 revision。**不含用户问题原文。**
UTC：aware + `astimezone(UTC)`；序：`created_at ≤ last_activity_at ≤ expires_at`（naive 拒绝）。

### SessionCheckpoint（`models.SessionCheckpoint`）

字段：`schema_version`, `session_id`, `revision`, `saved_at`, `state: PersistedAgentState`

### PersistedAgentState

| 字段 | 持久化？ | 原因 |
|------|----------|------|
| `phase` | YES | Agent 当前阶段 |
| `status` | YES | 受控工作流状态 |
| `artifacts` | YES | F09/F10 等跨轮上下文 |
| `error` | YES | 契约字段；稳定 success 必须 `None` |
| `request_id` | **NO** | 每轮不同 |
| `input_text` | **NO** | 必须只来自当前请求 |
| `orchestration_trace` | **NO** | 当前轮执行轨迹 |

### 物理 Redis Key（内部；不对 API 暴露）

前缀默认 Settings `redis_key_prefix` = `govagent:f11`：

| 用途 | Builder | 形态 |
|------|---------|------|
| Meta | `_meta_key` | `{prefix}:session:{id}:meta` |
| Checkpoint | `_checkpoint_key` | `{prefix}:session:{id}:checkpoint` |
| Audit | `_audit_key` | `{prefix}:session:{id}:audit` |
| Request result | `_result_key` | `{prefix}:request:{id}:result` |
| Request lock | `_request_lock_key` | `{prefix}:lock:request:{id}` |
| Session lock | `_session_lock_key` | `{prefix}:lock:session:{id}` |

### 相关 tests

- `test_unknown_expired_and_missing_checkpoint_semantics`
- `test_session_meta_and_checkpoint_physical_shape_excludes_turn_local_fields`
- `test_corrupt_checkpoint_json_fails_closed`
- `test_session_meta_timestamp_order_and_utc_normalize`

---

## 13. 步骤：重建当前轮 AgentState

### 真实代码

`from_persisted(persisted: PersistedAgentState, *, request_id: str, input_text: str) -> AgentState`

逻辑：

```
Redis PersistedAgentState（phase/status/artifacts/error）
  + current request_id
  + current input_text
  + orchestration_trace = []
  → AgentState
  → validate_agent_state(...)
```

### AgentState（F08，`agent/state.py`）

七个顶层字段：`request_id`, `input_text`, `phase`, `status`, `artifacts`, `error`, `orchestration_trace`。
F11 **不**另造 SessionAgentState。

### `validate_agent_state` 调用点

1. `from_persisted` 末尾
2. `to_persisted` 开头
3. `_run_and_commit` 在 Processor 返回后

### 为什么 input 必须是当前轮（F10 例子）

上一轮系统提示确认办理「灵活就业人员社会保险费申报缴费」；下一轮用户说「确认」。
`AgentState.input_text` 必须是「确认」，不能是上一轮业务长句。

### 相关 tests

- `test_persisted_state_excludes_turn_local_fields_and_rebuilds_fresh_ids`
- `test_existing_session_restores_checkpoint_before_processing_current_input`

---

## 14. 步骤：F09 跨轮连续性

### 真实 artifact（`agent/interaction.py`）

Namespace key：`artifacts["f09"]`（`_F09_ARTIFACT_KEY`）
`empty_f09_namespace(slot_context)` **8 keys：**

1. `slot_context`
2. `interpretation`
3. `mapping_validation`
4. `validated_slot`
5. `explanation`
6. `business_transition`
7. `failure`
8. `response_text`

`SlotInteractionContext` 中与连续性相关的关键字段：`required_slot`, `question_text`, `allowed_values`, `current_node_id`, `transition_status`, `current_slots`, …

### 普通槽位场景

Agent 问就业类型 → 用户答「平时接零活…」。
上一轮：`slot_context.required_slot` 等写入 checkpoint。
下一轮：F11 `from_persisted` 恢复 `artifacts["f09"]`，再注入新 `input_text`；未来 F12 Processor 调用 F09 时看到 pending slot + 当前回答。

### Explanation Side Route

用户问「灵活就业是什么意思？」→ F09 解释旁路（`detect_explanation_request` / explanation 状态），**不推进** Business Graph，pending slot 保持。
F11 把含 `explanation` 的 f09 namespace 存进 checkpoint；下一轮仍恢复同一 pending slot。

### 相关 tests

- `test_f09_artifact_round_trip_preserves_pending_slot_without_old_input`

---

## 15. 步骤：F10 跨轮连续性

### 真实 artifact（`agent/terminal.py`）

`empty_f10_namespace` **8 keys：**

1. `mode`（`TerminalConfirmationMode.PREPARE` / `RESOLVE`）
2. `terminal_context`
3. `terminal_validation`
4. `rule_readiness`
5. `confirmation`
6. `confirmed_business_id`
7. `failure`
8. `response_text`

### PREPARE / RESOLVE

- F04 Terminal Candidate **≠** `confirmed_business_id`
- PREPARE：建立等待确认的 controlled context → F11 只负责存
- 下一轮「确认」：F11 restore F10 + `input_text="确认"` → **未来** F12 调 F10 RESOLVE → F10 的 `assign_confirmed_business_id` 才赋权

### Authority

F11 Production **无** `confirmed_business_id = ...` 赋值（assignment count = 0）。序列化/透传 artifacts ≠ 业务赋值。

### 相关 tests

- `test_f10_artifact_round_trip_preserves_eight_keys_and_rejects_stale_input`

---

## 16. 步骤：AgentTurnProcessor（F11/F12 接缝）

### 真实 Protocol

```python
class AgentTurnProcessor(Protocol):
    def process_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        input_text: str,
        restored_state: AgentState | None,
    ) -> AgentTurnResult: ...
```

| 参数 | 含义 |
|------|------|
| `session_id` | 会话身份 |
| `request_id` | 当前 HTTP turn |
| `input_text` | 当前用户原文（仅本轮） |
| `restored_state` | 新会话 `None`；续写为重建后的 AgentState |

### `AgentTurnResult`（`models.AgentTurnResult` dataclass）

`state`, `response_text`, `requires_user_input`, `public_status`

F11 用它们：公开响应 + 校验 + 决定是否可持久化。

### 为什么是 Protocol

依赖倒置：F11 只规定接口，不关心内部 RAG/图/LLM/F09/F10。
**Production concrete Government processor = 0**；测试 Double 仅在 tests。

### F12 未来接入（不设计 F12 细节）

```
F11 SessionTurnService
        │
        ▼
AgentTurnProcessor Protocol
        │  F12 implements
        ▼
GovernmentAgentTurnProcessor
        ├─ semantic retrieval
        ├─ decision graph / F04
        ├─ F09
        ├─ F10
        └─ later knowledge
        │
        ▼
AgentTurnResult → F11 persist
```

---

## 17. 步骤：Processor 返回后的验证

### 真实顺序（`_run_and_commit`）

1. 类型检查 `AgentTurnResult` 字段
2. `validate_agent_state(result.state)`
3. `result.state["request_id"] == request.request_id`
4. `result.state["input_text"] == request.input_text`
5. status / `requires_user_input` 矩阵
6. `to_persisted(result.state)`

不一致 → `AGENT_TURN_FAILED`；**禁止** silent correction。
（结构合法 ≠ turn 身份正确 —— RV-003）

### status 一致性（RV-004）

- `COMPLETED` → `requires_user_input=False`
- `AWAITING_USER_INPUT` → `True`

两层：Service 显式检查 + `SessionTurnSuccess._status_requires_user_input_matrix`；cache replay 也走 `model_validate`。

### 相关 tests

- `test_processor_wrong_request_id_fails_without_durable_commit`
- `test_processor_wrong_input_text_fails_without_success_cache`
- `test_inconsistent_public_status_requires_user_input_fails_closed`

---

## 18. 步骤：Sanitize → Checkpoint

### 真实代码

`to_persisted(state: AgentState) -> PersistedAgentState`

- `validate_agent_state`
- 拒绝 FAILED phase/status / 非 None error
- `copy.deepcopy(artifacts)`
- 只输出 phase/status/artifacts/error

### Strict JSON

`store.dumps_json`：`json.dumps(..., ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)`

禁止：pickle、`default=str`、NaN/Infinity、任意 runtime object 静默落入 artifacts。

### 相关 tests

- `test_strict_json_serialization_rejects_non_finite_float`
- `test_persisted_state_excludes_turn_local_fields_and_rebuilds_fresh_ids`

---

## 19. 步骤：Revision + WATCH + MULTI/EXEC（Durable Success）

### Revision

- 新会话：`expected_revision=0` → 写入 revision **1**
- 已有：`expected_revision=meta.checkpoint_revision`（N）→ **N+1**
来源：`_handle_existing_session` 读到的 meta；新会话固定 0。

### 真实 commit：`RedisSessionStore.commit_successful_turn`

操作顺序：

1. `pipe.watch(meta_key, audit_key)`
2. 读 meta / 校验 revision（0 必须不存在；N 必须匹配）
3. `pipe.type(audit_key)` → 仅允许 `none` / `list`（`_ALLOWED_AUDIT_KEY_TYPES`）
4. 非法 TYPE → `unwatch` + `AUDIT_PERSISTENCE_FAILED`（**MULTI 前**；不 DEL）
5. `pipe.multi()`
6. `SET` meta（ex=session+expired_marker）
7. `SET` checkpoint（ex=session_ttl）
8. `RPUSH` audit
9. `EXPIRE` audit
10. `SET` result（ex=request_dedup）
11. `pipe.execute()`

`WatchError` → `SESSION_CONFLICT`。连接类错误 → `PERSISTENCE_UNAVAILABLE`。

### Redis MULTI ≠ RDBMS 事务（RV-001）

MULTI/EXEC 排队顺序执行，但**某条命令 runtime error 不会自动 rollback 已成功命令**。
`RPUSH` 遇 STRING → WRONGTYPE 时，可能出现 meta/checkpoint/result 已写、audit 未写 → partial durable。
故 TYPE 预检 + WATCH(audit)。

### 为什么必须一起持久化

| 异常组合 | 后果 |
|----------|------|
| checkpoint 成功 / audit 失败 | 业务推进却无审计证据 |
| request cache 成功 / checkpoint 失败 | retry「成功」但状态未存 |

→ durable-success unit。

### 相关 tests

- `test_revision_increments_and_stale_revision_conflicts_via_watch`
- `test_atomic_success_writes_meta_checkpoint_audit_and_request_cache`
- `test_corrupt_audit_string_blocks_commit_without_partial_write`

---

## 20. 步骤：Audit

### Audit ≠ Logging

Logging：运维。Audit：受控业务状态变化证据。

### 真实模型 `AuditEvent`

`schema_version`, `event_id`, `session_id`, `request_id`, `occurred_at`, `event_type`, `outcome`, `before_phase/status`, `after_phase/status`, `checkpoint_revision_before/after`, `failure_code`, `capability`

**不保存：** `input_text`, `response_text`, artifacts, checkpoint JSON, secret, traceback。

### 成功 / 失败

| 路径 | Symbol | revision |
|------|--------|----------|
| Success | 同 `commit_successful_turn` 内 RPUSH；`TURN_COMPLETED` | 0→1 或 N→N+1 |
| Failure | `append_failure_audit`；`_record_agent_failure` | **N→N**；checkpoint 不推进 |

Failure audit 亦：`WATCH(audit)` + TYPE + `with pipeline`（RV-006）。WatchError → `AUDIT_PERSISTENCE_FAILED`。

### 相关 tests

- `test_audit_list_appends_and_excludes_raw_sensitive_fields`
- `test_append_failure_audit_does_not_create_usable_checkpoint_for_new_prefix`
- `test_append_failure_audit_rejects_corrupt_string_audit_key`
- `test_processor_failure_preserves_existing_checkpoint_and_records_failure_audit`

---

## 21. 步骤：Request Result Cache + TTL

### `CachedRequestResult`

`schema_version`, `request_id`, `session_id`, `request_fingerprint`, `public_response: SessionTurnSuccess`, `completed_at`

不存 AgentState / raw input。TTL：`request_dedup_ttl_seconds` 默认 **600**（短时重试，非聊天历史）。

### Settings 默认值（业务走到 TTL 时映射）

| 配置 | 默认 | 用途 |
|------|------|------|
| `session_ttl_seconds` | 1800 | Checkpoint / 活动窗 |
| `session_expired_marker_ttl_seconds` | 86400 | Meta 比 checkpoint 多 24h，区分 NOT_FOUND vs EXPIRED |
| `audit_ttl_seconds` | 604800 | Audit LIST 7 天 |
| `request_dedup_ttl_seconds` | 600 | Request result cache |
| `request_lock_ttl_seconds` | 120 | Request lock |
| `session_lock_ttl_seconds` | 120 | Session lock |
| `session_max_input_chars` | 4000 | 输入上限 |
| `redis_key_prefix` | `govagent:f11` | 生产前缀 |

**Expired Marker：** Checkpoint 30min；Meta 30min+24h → 可区分 `SESSION_NOT_FOUND` / `SESSION_EXPIRED`。

---

## 22. 步骤：成功返回 API

`commit_successful_turn` 成功 → `_run_and_commit` 返回 `SessionTurnSuccess` → `session_turn` 直接返回 → HTTP 200。

### `SessionTurnSuccess` 公开字段

`session_id`, `request_id`, `status`, `response_text`, `requires_user_input`

**不返回：** AgentState、artifacts、revision、Redis keys、locks。

### 相关 tests

- `test_api_new_and_existing_session_round_trip`
- `test_api_public_response_has_no_internal_leakage`

---

## 23. 失败路径与 Error Mapping

### 业务流

```
Processor 失败？ → 保留旧 checkpoint；revision 不变；可 TURN_FAILED；AGENT_TURN_FAILED
首次 Processor 失败？ → 无 usable active session
durable commit 失败？ → 不返回 success
```

### HTTP 映射（真实 `_HTTP_STATUS_BY_CODE` in `api.py`）

| Error Code | HTTP | 业务含义 |
|------------|------|----------|
| `INVALID_REQUEST` | 422 | 参数非法（含受控 422） |
| `SESSION_NOT_FOUND` | 404 | Meta 不存在 |
| `SESSION_EXPIRED` | 410 | Meta 过期 |
| `SESSION_CONFLICT` | 409 | 锁忙 / WATCH / revision 冲突 |
| `REQUEST_ID_REUSE_CONFLICT` | 409 | 同 id 不同 fingerprint |
| `REQUEST_IN_PROGRESS` | 409 | 同 request 正在处理 |
| `CHECKPOINT_INVALID` | 500 | 损坏/缺失 checkpoint |
| `CHECKPOINT_VERSION_UNSUPPORTED` | 500 | schema 不支持 |
| `PERSISTENCE_UNAVAILABLE` | 503 | Redis 不可用 / 损坏 cache fail-closed |
| `AUDIT_PERSISTENCE_FAILED` | 503 | Audit TYPE/写入失败 |
| `AGENT_TURN_FAILED` | 500 | Processor / identity / 状态失败 |
| `UNEXPECTED_INTERNAL_ERROR` | 500 | 未预期异常（无 traceback 泄露） |

### 相关 tests

- `test_api_unknown_session_is_404_and_does_not_create_session`
- `test_api_expired_session_is_410`
- `test_api_checkpoint_invalid_and_unsupported_version_mappings`
- `test_api_persistence_unavailable_and_agent_and_unexpected_mappings`
- `test_persistence_failure_after_processor_success_does_not_return_success`
- `test_no_silent_in_memory_fallback_when_store_unavailable`
- `test_restart_style_continuity_with_real_redis_store`

---

## 24. Golden Scenario（Session 生命周期；非 F12 E2E）

| 轮次 | 用户 | 代码路径要点 |
|------|------|----------------|
| Turn1 | 「我辞职了，现在没单位，想自己交社保」 | `_handle_new_session`；`restored_state=None`；rev 0→1 |
| Turn2 | 「平时接零活，没有固定单位」 | `load_active_session` → `from_persisted` 恢复 F09 pending + 新 input；rev→2 |
| Terminal | — | F04 候选如 `DEMO_SS_001` / canonical「灵活就业人员社会保险费申报缴费」仍是 **candidate** |
| F10 PREPARE | — | `artifacts["f10"]` 入 checkpoint；`confirmed_business_id` 仍非 F11 决定 |
| 确认轮 | 「确认」 | restore PREPARE + 当前 input；**未来** F12→F10 RESOLVE |

**醒目标注：** F11 测试证明 Session/Checkpoint/当前轮 input 重建。**不证明**真实 Semantic Retrieval / Decision Graph / F09 / F10 已被 Session API production processor 整串 E2E——那是 **F12**。

---

## 25. 测试如何按业务能力证明

| 业务能力 | 真实 test |
|----------|-----------|
| Checkpoint 不含 turn-local / raw input | `test_session_meta_and_checkpoint_physical_shape_excludes_turn_local_fields`；`test_persisted_state_excludes_turn_local_fields_and_rebuilds_fresh_ids` |
| Strict JSON | `test_strict_json_serialization_rejects_non_finite_float` |
| Replay | `test_replay_same_request_does_not_reinvoke_processor_or_refresh_session`；`test_api_replay_...` |
| Request reuse | `test_request_id_reuse_with_different_payload_conflicts_without_second_processor_call`；`test_api_request_reuse_conflict_is_409` |
| Concurrency / locks | `test_same_request_id_concurrent_race_...`；`test_same_session_concurrency_...`；`test_different_sessions_...` |
| F09 continuity | `test_f09_artifact_round_trip_preserves_pending_slot_without_old_input` |
| F10 continuity | `test_f10_artifact_round_trip_preserves_eight_keys_and_rejects_stale_input` |
| 422 不泄漏 | `test_api_422_does_not_echo_raw_sentinel_input`；`test_api_422_oversized_input_is_not_echoed` |
| WRONGTYPE / partial-write | `test_corrupt_audit_string_blocks_commit_without_partial_write` |
| Processor identity | `test_processor_wrong_request_id_...`；`test_processor_wrong_input_text_...` |
| Status consistency | `test_inconsistent_public_status_requires_user_input_fails_closed` |
| Failure preserve | `test_processor_failure_preserves_existing_checkpoint_and_records_failure_audit` |
| Restart continuity | `test_restart_style_continuity_with_real_redis_store` |

### 分层与数字

| 层 | 作用 | 数量 |
|----|------|------|
| Store | 真实 Redis 7.4.11 | **16** |
| Service | 生命周期 + Test Double | **20** |
| API | Router+Service + test-only Processor | **13** |
| Combined F11 | | **49** |
| Full suite | | **594 passed / 13 skipped / 0 failed / 0 warnings** |

---

## 26. Review 修复为什么值得读（非新功能）

| Finding | 一句话 | 代码锚点 |
|---------|--------|----------|
| RV-001 | MULTI/EXEC 遇 WRONGTYPE 可能 partial write | `commit_successful_turn` WATCH+TYPE |
| RV-002 | 框架默认 422 可能违反数据最小化 | `SessionAPIRoute` |
| RV-003 | 结构合法 ≠ turn 身份正确 | `_run_and_commit` identity checks |
| RV-004 | 两字段组合可能语义矛盾 | Service + `SessionTurnSuccess` validator |
| RV-005 | Meta 时间 UTC + 序 | `SessionMeta` validators |
| RV-006 | Failure audit pipeline/TYPE/WATCH | `append_failure_audit` |
| RV-007 | 测试缺口随 001/002 补齐 | store/API regressions |

### INFO（不阻塞）

| ID | 摘要 |
|----|------|
| RV-008 | Audit LIST 7 天可无界增长；Phase-1 接受 |
| RV-009 | `session_id` ≠ 认证身份 |
| RV-010 | endpoint 内 ValidationError 基本不可达（defensive） |
| RV-011 | 允许空 `response_text` |

不因此扩 Redis Stream / OAuth / Cluster。

---

## 27. F11/F12 边界与 main.py

```
F11：HTTP / session / persistence / audit / 幂等 / 并发
                │
                ▼
     AgentTurnProcessor Protocol
                │ F12 implements
                ▼
     GovernmentAgentTurnProcessor（NOT IMPLEMENTED）
                ├─ semantic retrieval
                ├─ decision graph
                ├─ F09 / F10
                └─ later knowledge
```

`main.py` 未挂载：真实 Government Processor 尚不存在；不能在正式 app composition 假装完成。F12 提供 processor 后再 activation。

**Router/Service/Store 是真的；缺的是 concrete Government processor。Production Fake = 0。**

### 对外 Capability 出口

`session/__init__.py` re-exports：`create_session_router`, `SessionTurnService`, `AgentTurnProcessor`, `AgentTurnResult`, models、`RedisSessionStore` 等（见 `__all__`）。**不要从 `__init__.py` 开始读业务流。**

依赖：`pyproject.toml` → `redis==5.3.1`（无 fakeredis / RedisSaver）。

---

## 28. 按业务流程的推荐阅读顺序

1. `api.py`：`create_session_router` → `session_turn` → `SessionAPIRoute`
2. `service.py`：`handle_turn`
3. 跟 fingerprint / `_lookup_replay` / request lock double-check
4. `_handle_new_session` / `_handle_existing_session`
5. `store.load_active_session` + models Meta/Checkpoint
6. `from_persisted` + `agent/state.py`
7. `AgentTurnProcessor` / `AgentTurnResult`
8. `_run_and_commit` 校验顺序
9. `to_persisted` + `dumps_json`
10. `commit_successful_turn`（WATCH → TYPE → MULTI）
11. `append_failure_audit` / `_record_agent_failure`
12. 回到 API `_error_response` / Success

（仍然不是文件目录顺序。）

### 代码追踪清单

- [ ] 找到 HTTP route `session_turn`
- [ ] 找到 `SessionTurnService.handle_turn`
- [ ] 找到 `compute_request_fingerprint`
- [ ] 找到 `get_cached_result` / `_lookup_replay`
- [ ] 找到 `acquire_request_lock` + double-check
- [ ] 找到 `acquire_session_lock` / `hold_lock`
- [ ] 找到 `load_active_session`
- [ ] 找到 `from_persisted`
- [ ] 找到 `AgentTurnProcessor.process_turn`
- [ ] 找到 Processor result validation（identity / status）
- [ ] 找到 `to_persisted`
- [ ] 找到 `watch(meta, audit)` / TYPE / `multi` / `execute`
- [ ] 找到 Audit / `append_failure_audit`
- [ ] 找到 request result cache 写入
- [ ] 找到 `SessionTurnSuccess` / `_error_response`

---

## 29. 读代码时最容易犯的 10 个误解

1. 以为 `session_id` = `user_id`
2. 以为 checkpoint = chat history
3. 以为 Redis 保存 `input_text`
4. 以为 F11 会判断「确认」
5. 以为 candidate = confirmed business
6. 以为 `AgentTurnProcessor` 已有真实 production implementation
7. 以为 MULTI/EXEC 任意错误都会 rollback
8. 以为 lock 足够，不需要 revision
9. 以为 replay 会再跑 Agent
10. 以为 F11 Router 已经 `main.py` 激活

---

## 30. 面试时怎么解释 F11（短答）

- **我负责了什么？** 跨 HTTP 的 Session 执行底座：API、Service、Redis Checkpoint/Audit、幂等与并发一致性；业务 Processor 留给 F12。
- **为什么用 Redis？** 进程无关的 controlled state + 锁 + 短期 result cache；支持 restart continuity。
- **为什么幂等？** 网络重试不能双重推进业务；fingerprint 防同 id 换内容。
- **为什么两层锁？** Request 防同请求并发；Session 防同会话丢更新。
- **为什么 WATCH？** Lock 有 TTL；revision/WATCH 防 stale write；audit WATCH/TYPE 防 partial durable。
- **如何避免原文泄漏？** Checkpoint/Audit/Cache 不存 raw input；422 用 `SessionAPIRoute` 受控错误。
- **如何保证多轮连续性？** Persist artifacts（F09/F10）+ 每轮重建当前 `input_text`/`request_id`。

---

## 31. 一句话

**F11 把无状态 HTTP Agent 调用，升级为可跨请求恢复、可审计、可幂等重试、具备并发一致性保护的会话执行能力；具体政务业务处理器由 F12 注入。**
