# F08 Agent State + LangGraph 代码阅读指南

Agent 编排状态与最小 LangGraph 工作流。

面向已读过 F03/F04 Business Decision Graph、F07 LLM Provider 边界的开发者。

**核心问题：**

> Agent 如何在一次本地 invocation 中保存 typed 运行状态，并按预定义顺序驱动节点——同时不抢走 Business Decision Graph 的事项决定权？

**一句话定位：**

F08 提供 **Agent orchestration foundation**（TypedDict AgentState、显式校验、2 节点 LangGraph skeleton、同步 build/invoke）。

F08 **不负责** 政务事项决策、缺槽问答、终端确认、Session/Redis、E2E Demo。

| 层 | 职责 |
|----|------|
| **LangGraph Agent Graph** | 编排：先跑哪个节点、State 怎么传、workflow 何时结束 |
| **Business Decision Graph / Rule / Controller** | 业务真值：`next_node`、规则、候选事项 |

**功能状态：** Resource Gate / Requirement / Technical Design / Code / Test / Review / Explanation / Code-Reading 均已完成；Review Fix = NOT REQUIRED。最终 Feature Scope = **9 paths**。

验证证据（权威，来自 F08 Test / Review）：

| 项 | 结果 |
|----|------|
| F08 Targeted | **73 / 73 PASS** |
| Full Regression | **392 passed / 13 skipped / 0 warnings** |
| LangGraph | **1.2.11**（`>=1.2.11,<1.3`） |
| Real LLM / Company Network | **NOT RUN / 0** |
| compileall / pip check | **PASS** |
| Review | **PASS**（BLOCKING/MAJOR/MINOR = 0；INFO = 3） |

完整 Requirement / Design / Test / Review 依据见：

`docs/features/F08-agent-state-langgraph.md`

---

## 1. 阅读目标

读完后应理解：

1. 为什么需要 F08
2. `AgentState` 是什么（以及不是什么）
3. LangGraph 与 Business Decision Graph 有什么区别
4. 为什么用 TypedDict 还要写 `validate_agent_state`
5. Trace reducer（`operator.add`）是什么
6. `prepare` / `complete` 怎么执行
7. `run_agent_workflow` 怎么跑
8. 为什么当前没有 LLM / Redis / Checkpointer
9. 未来 F09 大概从哪里接入

---

## 2. 推荐阅读顺序

| 顺序 | 文件 | 为什么先看 |
|------|------|------------|
| 1 | `state.py` | 先建立 State 契约、校验、工厂 |
| 2 | `nodes.py` | 再看节点如何消费 State、返回 partial update |
| 3 | `workflow.py` | 再看 StateGraph 如何 build / invoke |
| 4 | `__init__.py` | Public API 边界 |
| 5 | `tests/test_agent_state.py` | State contract 如何被测 |
| 6 | `tests/test_agent_workflow.py` | 真实 LangGraph 行为如何被测 |
| 7 | `pyproject.toml` | `langgraph` 依赖如何声明 |

先状态，再节点，再编排。

---

## 3. 项目路径结构（仅 F08）

```text
src/gov_service_agent/agent/
├── __init__.py      # 最小 Public API
├── state.py         # AgentState + validator + factory
├── nodes.py         # _prepare_node / _complete_node（私有）
└── workflow.py      # build_agent_workflow / run_agent_workflow

tests/
├── test_agent_state.py
└── test_agent_workflow.py
```

`pyproject.toml` 增加 main dependency：`langgraph>=1.2.11,<1.3`。

**没有** `/agent` HTTP endpoint；**未改** `main.py` / `settings.py` / `.env.example`。

---

## 4. 核心执行流程

```text
Caller
  ↓
create_initial_state(request_id, input_text, artifacts?)
  ↓
AgentState  (phase=RECEIVED, status=RUNNING, error=None, trace=[])
  ↓
run_agent_workflow(initial_state)
  ↓
validate_agent_state(initial)
  ↓
deepcopy → execution_state
  ↓
build_agent_workflow() → compile()
  ↓
START
  ↓
prepare   → phase=ORCHESTRATING; trace += ["prepare"]
  ↓
complete  → phase=COMPLETED; status=COMPLETED; error=None; trace += ["complete"]
  ↓
END   （= Agent orchestration 结束；≠ Business TERMINAL_CANDIDATE）
  ↓
validate_agent_state(final)
  ↓
返回 final AgentState
```

---

## 5. LangGraph 和 Business Decision Graph 不是一回事

| | LangGraph（F08） | Business Decision Graph（F03/F04） |
|--|------------------|-----------------------------------|
| 问题 | 先调用哪个 **能力模块**？ | 根据已验证槽位，业务 **下一节点** 是什么？ |
| 边 | 代码预定义的编排边 | 业务图预定义 edges |
| 真值 | workflow lifecycle | `next_node` / terminal candidate |
| LLM | F08 当前 **0** LLM 调用 | LLM **不得**决定业务 `next_node` |

**口诀：**

- LangGraph：编排「怎么走流程」
- Business Graph：决定「办什么事」

LLM（未来 F09）只做 NLU / slot / mapping signal；**Business next_node 仍由 F04 deterministic transition**。

---

## 6. `state.py`：AgentState 契约

### 6.1 七个字段（恰好 7）

| Field | 含义 |
|-------|------|
| `request_id` | 单次 invocation 请求标识（不是 `session_id`；调用方提供；strip 非空；≤128） |
| `input_text` | 本地 runtime 输入文本（in-memory only） |
| `phase` | 编排阶段：`RECEIVED` / `ORCHESTRATING` / `COMPLETED` / `FAILED` |
| `status` | 生命周期：`RUNNING` / `COMPLETED` / `FAILED` |
| `artifacts` | 临时 JSON-safe 中间结果 map |
| `error` | `None` 或 `{code, message}` |
| `orchestration_trace` | Agent 节点名列表（带 add reducer） |

**AgentState 不是：** Business Data SoT、规则结果、材料/地点/渠道/法律依据仓库。

### 6.2 TypedDict 不等于运行时自动检查

`TypedDict` 主要给类型检查器用。真正运行时靠：

`validate_agent_state(...)`

它在：

- `create_initial_state` 返回前
- 每个 node 入口
- `run_agent_workflow` invoke 前 / 后

都会执行。

### 6.3 Lifecycle（只允许四组合）

| phase | status | error | 合法？ |
|-------|--------|-------|--------|
| RECEIVED | RUNNING | None | YES |
| ORCHESTRATING | RUNNING | None | YES |
| COMPLETED | COMPLETED | None | YES |
| FAILED | FAILED | WorkflowError | YES |
| COMPLETED | RUNNING | * | **NO** |
| RECEIVED | COMPLETED | * | **NO** |
| FAILED | FAILED | None | **NO** |

其它组合 → `AgentStateValidationError`（fail closed）。

### 6.4 Strict JSON-safe（artifacts）

**允许：** `None` / `str` / `bool` / `int` / finite `float` / `list` / `dict[str, …]`

**拒绝：** NaN、±Infinity、tuple、set、bytes、bytearray、Path、datetime、Enum、Exception、任意对象。

**为什么连 StrEnum 也拒：** 即使 `AgentPhase` 也是 `str` 子类，artifacts 仍先 `isinstance(..., Enum)` 拒绝。未来若要存 Enum，先转成稳定字符串；不要靠 custom JSON encoder。

**dict key：** 必须 `type(key) is str`（普通 str，不是 Enum key）。

### 6.5 artifacts 安全边界（非 DLP）

`artifacts` 是开放 JSON-safe map，**不是**敏感信息扫描器。

当前 F08 Production **没有** secret-producing 代码（无 LLM response / API Key / HTTP Client / DB Session 写入）。

调用方 contract：不得写入 credential、Authorization、raw reasoning、raw provider body。

未来 F09+ 接入 subsystem 时，必须继续 enforce 对应安全边界（含 F07 Data Policy）。

### 6.6 Deep copy ownership

```text
caller artifacts ──validate──► deepcopy ──► state["artifacts"]
```

调用方之后改 nested list，**不得**影响 State 内树；反之亦然。

`artifacts=None` 时每次新建 `{}`，禁止 mutable default `artifacts={}`。

### 6.7 ValidationError 安全

`AgentStateValidationError` 只带安全 `message`。不 `repr(state)`，不 dump `input_text` / artifacts。

### 6.8 Unknown top-level keys

实际 keys 必须 **恰好等于** 7 个允许字段。因此 `api_key` / `reasoning` / `business_id` / `next_node` 等无法作为额外顶层字段静默进入。

---

## 7. Trace Reducer（务必理解）

State 字段注解等价于：

```text
orchestration_trace: Annotated[list[str], operator.add]
```

含义：

1. State 已有 `["prepare"]`
2. `complete` 返回 `{"orchestration_trace": ["complete"]}`
3. LangGraph 用 `operator.add` merge → `["prepare", "complete"]`

因此节点 **只能返回本节点 delta**，不能返回「旧 trace + 新名字」——否则会重复累加。

最终期望：`["prepare", "complete"]`。不包含 LangGraph `START`/`END`，也不混用 F04 的 `visited_node_ids`。

---

## 8. `nodes.py`：两个私有节点

| Node | 做了什么 | 没做什么 |
|------|----------|----------|
| `_prepare_node` | validate → `phase=ORCHESTRATING` + `trace+=["prepare"]` | 不改 artifacts；不调 LLM/DB/Graph |
| `_complete_node` | validate → `phase/status=COMPLETED`，`error=None`，`trace+=["complete"]` | 不写 `business_id` / candidate |

**为什么不 `state["phase"] = ...`？**
节点应返回 **partial update**，由 LangGraph merge。直接 mutation 破坏可预测传播，也难测。

**为什么只有两个节点？**
不是设计残缺，而是 Scope A：先证明 State + Graph 独立成立。retrieval / NLU / Business Graph Controller / question / confirmation 属于后续 Feature。

节点 **不** 从 `agent/__init__.py` 导出。

---

## 9. `workflow.py`：build vs run

### 9.1 `build_agent_workflow`

```text
StateGraph(AgentState)
  → add_node("prepare", ...)
  → add_node("complete", ...)
  → START → prepare → complete → END
  → compile()   # 无 checkpointer / InMemorySaver / thread_id
```

只建图，不 invoke，不访问网络。

### 9.2 `run_agent_workflow`

1. `validate_agent_state(initial)`
2. `deepcopy(initial)`（保护 caller）
3. `build_agent_workflow()`
4. `invoke(execution_state)`
5. `validate_agent_state(result)`
6. 返回 final

无 `except Exception: return FAILED`——编程错误应暴露，不伪装成合法 workflow failure。

### 9.3 END 语义再强调

文档与代码注释一致：

> LangGraph END = 本次 Agent orchestration 结束
> ≠ Business Decision Graph `TERMINAL_CANDIDATE`

---

## 10. 为什么现在没有 LLM / F04 / F06 / Redis

| 能力 | 现状 | 原因 |
|------|------|------|
| F07 LLM | 不 import | foundation 先独立；NLU 节点留给 F09 注入 |
| F04 Business Graph | 不 import | 不重新实现 transition；未来由 Controller node 调用 |
| F06 Retrieval | 不 import | 同理；且 RAG score ≠ final `business_id` |
| Redis / Checkpointer | 无 | F08 的 in-memory = **单次 invoke 内传播**，不是 MemorySaver；持久化属 F11 |
| `thread_id` / conversation memory | 无 | F11 Session |

把「看起来像 Agent」的空 LLM 节点硬塞进来，只会制造耦合与假绿。

---

## 11. Data Policy 提醒

F07 当前：真实 **`USER_FREE_TEXT` → Remote Company Provider = DENY**。

因此：即使 `AgentState` 有 `input_text`，F08 **也不会**、**也不允许**自行 Remote dispatch。State 有字段 ≠ Policy 放行。

---

## 12. Tests 怎么读

### `test_agent_state.py`

真正调用 Production：`create_initial_state` / `validate_agent_state`。

重点覆盖：unknown keys、lifecycle、strict JSON、NaN/±Inf、Enum、deep copy、error leakage、`json.dumps(..., allow_nan=False)`。

### `test_agent_workflow.py`

真正调用：`build_agent_workflow` / `run_agent_workflow`（不是只手调 `_prepare_node`）。

重点覆盖：build、invoke、trace 精确顺序、determinism、caller immutability、重复调用隔离、非法初始态 invoke 前 reject。

**数量：** Targeted **73/73 PASS**；Full **392 passed / 13 skipped**（含 Real LLM 等 opt-in，默认不跑，不是 failure）。

---

## 13. 安全清单（F08）

1. State 无 secret / reasoning 字段
2. ValidationError 不 dump State
3. F08 不调用 Real LLM；0 Company Network（普通测试）
4. `input_text` 不自动 remote
5. `artifacts` 不是 DLP；调用方不得塞 secret
6. 未来 integration 继续遵守 F07 Policy

---

## 14. 常见问题与排查

**Q1. import langgraph 失败？**
确认 conda `govagent`、Python 3.11.x，以及 `pyproject` 中 `langgraph>=1.2.11,<1.3` 已 `pip install -e ".[dev]"`。不要用 base 3.12。

**Q2. 一跑就 `AgentStateValidationError`？**
检查是否恰好 7 字段；phase/status/error 是否合法组合；artifacts 是否 JSON-safe；phase/status 是否真正 Enum 实例（普通 `"received"` 字符串会 reject）。

**Q3. trace 变成 `["prepare","prepare","complete"]`？**
节点是否错误返回了完整旧 trace。应只返回 `["prepare"]` / `["complete"]` delta。

**Q4. artifacts 被 reject？**
常见原因：Enum、set、tuple、Path、NaN、非 str key。

**Q5. 为什么 workflow 不需要 Redis？**
F08 没有 persistent checkpoint；只有单次 invoke 内存传播。

**Q6. 为什么 END 不代表事项确定？**
那是 Agent graph terminal，不是 Business graph terminal。

---

## 15. F09 会怎样接进来（概念，不冻结方案）

未来可能类似：

```text
START → intake/NLU → … → Business Graph Controller → response → END
```

具体节点名 **未冻结**。

预期不变：

- LLM：slot extraction / allowed-value mapping / confidence
- **Business next_node：仍由 F04 deterministic**
- Provider / Client / Session：**不进 AgentState**；用 factory / builder 注入

---

## 16. 阅读完成后的自测

1. **为什么 F08 用 TypedDict 还要 validator？**
   TypedDict 主要服务类型检查；运行时 fail-closed 靠 `validate_agent_state`。

2. **为什么 node 的 trace 只返回 delta？**
   字段带 `operator.add` reducer；返回完整旧列表会重复累加。

3. **为什么 LangGraph END ≠ Business Terminal？**
   END 只结束编排；业务终端候选仍属 Business Graph + 后续确认（F10）。

4. **为什么 F08 没有 Redis？**
   跨请求 Session/checkpoint 属 F11；本 Feature 只做单次 invoke。

5. **为什么 artifacts 不能存 Provider？**
   必须 JSON-safe；依赖对象是 workflow dependency，不是 State。

6. **为什么有 `input_text` 也不能自动发 Real LLM？**
   F07 `USER_FREE_TEXT` Remote DENY；F08 也不 import F07。

7. **F09 接入后谁负责 business next_node？**
   仍是 F04 Business Decision Graph（确定性），不是 LangGraph/LLM。

---

## 17. 已知边界（INFO，非缺陷）

- **RF-F08-003：** artifacts 非 DLP；未来集成继续 enforce secret/reasoning 边界。
- **RF-F08-002：** F07 Feature Doc 可能文案滞后；不在本 Feature 修改 F07。

完整 Feature 记录见：`docs/features/F08-agent-state-langgraph.md`。
