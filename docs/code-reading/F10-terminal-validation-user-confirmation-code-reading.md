# F10 Terminal Validation / User Confirmation / Confirmed Business ID 代码阅读指南

## 1. 阅读目标

这不是 Requirement。
这不是 Technical Design。
这不是 API Reference。

这是：**从代码入口出发，理解 F10 为什么这样实现、数据如何流动、关键安全边界如何保证、测试如何证明这些边界** 的阅读指南。

面向：后续维护者、新人、面试复习、代码审查、下一 Feature 集成。

权威 Feature 文档：`docs/features/F10-terminal-validation-user-confirmation.md`

**一句话：** F10 不帮用户选事项；它接收 F04 的 `TERMINAL_CANDIDATE`，做确定性终点校验 + 最终事项确认；只有 READY 且用户明确 CONFIRMED，才 exact propagate `confirmed_business_id`。

| 验证项（引用既有证据；本阶段不重跑） | 结果 |
|------|------|
| `tests/test_agent_terminal.py` | **69 passed** |
| `tests/test_agent_workflow.py` | **31 passed** |
| Combined F10 | **100 passed / 0 failed / 0 warnings** |
| F09 regression | **94 passed** |
| F08 regression | **PASS**（`test_agent_state` 63 + workflow baseline） |
| Full suite | **545 passed / 13 skipped / 0 failed / 0 warnings** |
| Review | **PASS**（INFO×3；Review Fix = NOT REQUIRED） |

---

## 2. 推荐阅读顺序

| 顺序 | 路径 | 为什么 |
|------|------|--------|
| 1 | `src/gov_service_agent/agent/terminal.py` | Domain / validation / parser / confirmed gate 全集中于此 |
| 2 | `src/gov_service_agent/agent/nodes.py` | 把 domain 包装成 6 个 execution nodes + 3 logical routers |
| 3 | `src/gov_service_agent/agent/workflow.py` | PREPARE / RESOLVE specialized LangGraph orchestration |
| 4 | `src/gov_service_agent/agent/__init__.py` | Public surface；无业务逻辑 |
| 5 | `tests/test_agent_terminal.py` | 证明安全边界（parser=0、revalidation、UNEVALUATED…） |
| 6 | `tests/test_agent_workflow.py` | 拓扑可达性 + F08/F09 回归 |
| 7 | Feature Doc | 需求 / TD / 证据总览 |

**为什么先读 `terminal.py`：** 先理解「业务规则」，再理解「Agent 怎么编排」。nodes/workflow 主要是把已有 deterministic capability 接到 LangGraph。

---

## 3. F10 在整体架构中的位置

```text
自然语言 → F06 找方向 → F04 推进（可与 F09 槽位交互交错）
        → TERMINAL_CANDIDATE + candidate_business_id
        → F10 PREPARE（validate → AWAITING）
        → 用户新一轮确认话语
        → F10 RESOLVE（revalidate → parse → 可能 confirmed）
        → 未来 Knowledge / F11 Session / F12 E2E
```

F10 输入 authority：**F04 terminal candidate**（或 F09 序列化后的受控 `business_transition`）。不是 RAG，不是 LLM。

---

## 4. candidate 与 confirmed

### 核心第一问：为什么 `TERMINAL_CANDIDATE` ≠ `confirmed_business_id`？

| 概念 | Authority | 代码含义 |
|------|-----------|----------|
| `candidate_business_id` | **F04** Business Decision Graph | 图已到达候选终点 |
| `confirmed_business_id` | **F10** | 用户明确确认「要办这个」之后的 exact propagate |

F04 只确定候选；F10 才负责最终用户确认。读代码时看到 `TransitionStatus.TERMINAL_CANDIDATE`，**不要**把它当成已写入最终事项。

### Candidate Authority（F10 不能做什么）

F10 **不能**：自己选 business、RAG、LLM mapping、按 `canonical_name` 反查 ID。

### Confirmed Authority

不是「生成」ID。语义伪代码：

```text
if validation.status != READY_FOR_CONFIRMATION:  do_not_assign
if intent != CONFIRMED:                          do_not_assign
confirmed_business_id = candidate_business_id    # exact propagation
```

真实 helper：`assign_confirmed_business_id`（`terminal.py`）。

---

## 5. terminal.py 总览

按职责读，不要逐行背：

| 区块 | 关键 symbol |
|------|-------------|
| Enums | `TerminalConfirmationMode`、`TerminalValidationStatus`、`ConfirmationIntent`、`ConfirmationStatus`、`TerminalConfirmationFailureKind` |
| Protocol / Deps | `BusinessRepositoryReader`、`TerminalConfirmationDependencies`、`_select_executable_rules_adapter` |
| Context | `TerminalCandidateContext`、`build_terminal_candidate_context`、`terminal_candidate_context_from_business_transition` |
| Validation | `validate_terminal_candidate`、`rule_readiness_from_selection`、`RuleReadinessSnapshot`、`TerminalValidationResult` |
| Parser | `normalize_confirmation_text`、`interpret_confirmation` |
| Confirmed gate | `assign_confirmed_business_id` |
| Response / ser | `compose_terminal_response_text`、`empty_f10_namespace`、`merge_f10_artifacts`、serialize_* |

**不含：** LangGraph topology、`advance_until_blocked`、RAG、LLM、Knowledge。

---

## 6. TerminalCandidateContext

```text
transition_status
current_node_id
candidate_business_id
visited_node_ids
traversed_edge_ids
```

- `frozen=True`、`extra="forbid"`：防止静默塞入多余字段
- candidate / node id **nonblank**
- model validator：必须是 `TERMINAL_CANDIDATE`；`current_node_id == visited_node_ids[-1]`；edge/node 长度契约

**不保存 raw user text / LLM / Business / Repository / 完整 F09 artifact。**
Context = 受控业务候选上下文，不是 conversation snapshot。

---

## 7. F04 / F09 Context Adapters

### `build_terminal_candidate_context(TransitionResult)`

只接受真实 F04 `TransitionResult`，且 status 必须是 `TERMINAL_CANDIDATE`。非 terminal **不能**进入 F10 confirmation。

### `terminal_candidate_context_from_business_transition(payload)`

输入 F09 `serialize_transition_result` 受控子集。即使是 dict，也必须 **strict re-validate** terminal contract。

### Arbitrary dict 不够

```json
{ "candidate_business_id": "DEMO_SS_001" }
```

缺少 `TERMINAL_CANDIDATE` authority 与 trace 契约 → 不可信。

### F09 字段最小化

Adapter **不**复制：`question_text`、`allowed_values`、`invalid_value`、`unsupported_reason`、raw input。这些不属于 terminal confirmation authority。

相关测试：`test_f04_factory_rejects_non_terminal`、`test_f04_factory_accepts_terminal`、`test_f09_adapter_from_serialized_transition`、`test_f09_adapter_strict_failures`。

---

## 8. Terminal Validation

真实顺序（`validate_terminal_candidate`）：

```text
context / candidate presence
  → repository.has_business
  → repository.get_business
  → Business.business_id exact match
  → canonical_name usable
  → deps.rule_selector → F04 select_executable_rules
  → RuleReadinessSnapshot
  → READY_FOR_CONFIRMATION | RULES_UNEVALUATED | …
```

**顺序为何重要：** candidate 不存在时 **selector calls = 0**（fail early + authority separation）。见 `test_candidate_not_found_selector_not_called`。

| Status | 读代码时记住 |
|--------|----------------|
| `READY_FOR_CONFIRMATION` | 可进入确认流程 |
| `INVALID_TERMINAL_CONTEXT` | 契约/空白失败 |
| `CANDIDATE_NOT_FOUND` | Graph 与 Business Data 不一致 |
| `CANDIDATE_ID_MISMATCH` | 不以 repository 为准「自动改 candidate」（那会篡改 F04 authority） |
| `CANONICAL_NAME_UNAVAILABLE` | 无可靠显示名 |
| `RULES_UNEVALUATED` | 有 selected executable，但无 evaluator → fail closed |

---

## 9. Business Repository 与 canonical_name

- `BusinessRepositoryReader`：**Protocol**，不是新 backend
- 真实 truth source：仍是 **`JsonBusinessRepository`**
- 用户可见名称：**仅** `Business.canonical_name`（禁止 LLM / RAG title / alias / business_id fallback）

`TerminalConfirmationDependencies` 只承载：`business_repository` + `rule_selector`。
**不放** LLM / Redis / DB / Embedding / Retriever。

---

## 10. Rule Selection 与 Rule Readiness

```text
select_executable_rules (F04)
  → RuleSelectionResult
  → rule_readiness_from_selection
  → RuleReadinessSnapshot
```

### `RuleReadinessSnapshot` 四字段

`selection_status` / `selected_rule_count` / `skipped_non_executable_count` / `evaluation_performed`
Phase-1：`evaluation_performed` 恒 `False`。
**不**把 selected rule objects 写入 AgentState（减体积、防泄漏、简化序列化）。

### CF-F10-002 / `_select_executable_rules_adapter`

Protocol vs F04 签名要求 `JsonBusinessRepository` → thin typing adapter。
Adapter **不**：筛规则、判 VERIFIED、判 usable、改 `RuleSelectionStatus`、吞异常——只 **delegate** 给真实 `select_executable_rules`。

---

## 11. NO_RULES / UNEVALUATED

| F04 status | F10 行为 | 误解 |
|------------|----------|------|
| `NO_RULES`（selected=0） | → `READY_FOR_CONFIRMATION` | **≠** eligibility PASS / rules passed |
| `RULES_AVAILABLE_UNEVALUATED`（selected>0） | → `RULES_UNEVALUATED` / BLOCKED | 不能把「未求值」当 PASS |

**为何 UNEVALUATED 比 NO_RULES 更严：**
- `NO_RULES`：当前没有可执行规则结果可等待 → 只做 Matter Identity 确认
- `UNEVALUATED`：已知有可执行规则但结果未知 → fail closed

**Rule Evaluator / Rule DSL：** F10 **未实现**；未来另开 Feature（operator / facts / UNKNOWN / AND-OR / trace / versioning）。本指南不暗示已有 DSL。

Golden DEMO：`DEMO_SS_001` → conditions=7，selected=**0**，skipped=**7**，`NO_RULES`。
**7 skipped ≠ 7 passed。**

---

## 12. Confirmation Parser

```text
normalize_confirmation_text → exact frozenset membership → ConfirmationIntent
```

**不是 LLM。** LOCAL / SYNC / DETERMINISTIC / HIGH PRECISION。

### Normalization

NFKC → strip → collapse whitespace → 仅剥 **边缘**标点。
例：`"  确认。 "` → `"确认"`；`"不确认"` → `"不确认"`。
**禁止**删除内部否定词（否则「不确认」→「确认」）。

### Positive exact set

确认 / 确认办理 / 是的 / 就是这个 / 没错

### Negative exact set

不确认 / 不办理 / 不是 / 不是这个 / 不是这个事项 / 不是我要办的 / 我办的不是这个 / 不对

### Default UNCERTAIN

好的 / 行 / 可以 / 嗯 / 对 / 好像是吧 / 应该是 / 随便 / 只复述 canonical_name …

策略：**宁可多问一次，也不要误确认政务事项。**

### Substring hazard

若 `"确认" in text`，则「不确认」也会命中 → 故用 **normalized exact match**。
测试：`test_buqueren_not_confirmed_via_substring`。

### Intent vs Status

| | 含义 | PREPARE 例子 |
|--|------|--------------|
| `ConfirmationIntent` | 本轮话语含义 | `None`（未 parse） |
| `ConfirmationStatus` | 流程生命周期 | `AWAITING_CONFIRMATION` |

Intent：`CONFIRMED` / `REJECTED` / `UNCERTAIN`
Status：`AWAITING_CONFIRMATION` / `CONFIRMED` / `REJECTED` / `UNCERTAIN` / `BLOCKED`

---

## 13. confirmed_business_id 唯一赋值点

| 指标 | 值 |
|------|-----|
| Physical non-None assignment points | **1**（`_finalize_confirmation_node`） |
| Semantic authority | **1**（`assign_confirmed_business_id`） |

Finalizer **defense-in-depth**：再次检查 READY + CONFIRMED。
Router 只决定流程；真正业务状态变更仍由 finalizer 验证 precondition，防止未来错误调用或图改动绕过。

exact propagation：非 UUID / alias / LLM / RAG mapping。

---

## 14. PREPARE 主线（stale-input safety）

典型风险：

```text
User:「平时接零活，没有固定单位」
  → F09 slot answer → F04 TERMINAL_CANDIDATE
  → AgentState.input_text 仍可能是那句槽位回答
```

阅读链路：

```text
prepare_terminal_confirmation
  → _run_terminal_confirmation(mode=PREPARE)
  → fresh artifacts["f10"]
  → _prepare_node
  → validate_terminal_candidate node
  → _route_by_terminal_validation
      → READY 时内部调用 _route_by_terminal_mode
      → PREPARE → compose_terminal_response
  → _complete_node
```

**结构上不可达：** `_interpret_confirmation_node`、`_finalize_confirmation_node`。

即使 `input_text="确认"` 调 PREPARE：仍 `AWAITING_CONFIRMATION`，intent=`None`，confirmed=`None`（API-level safety）。

**为何不暴露** `run_terminal_confirmation(mode="prepare")` 作主 public API：减少 caller mode misuse；公开入口是 `prepare_terminal_confirmation` / `resolve_terminal_confirmation`。

测试：`test_prepare_stale_confirm_input_safe`、`test_prepare_stale_slot_answer`、`test_f10_prepare_workflow_path_no_interpret_finalize`。

---

## 15. RESOLVE 主线（revalidation）

```text
resolve_terminal_confirmation
  → fresh f10（不信任旧 AWAITING artifact）
  → validate again
  → only if READY → interpret(state["input_text"])
  → intent router
  → CONFIRMED only → finalize → assign_confirmed_business_id
  → REJECTED / UNCERTAIN → compose（无 finalize）
```

旧 PREPARE 的 `AWAITING_CONFIRMATION` **不是**下一轮 authority。
保护：stale candidate、repository drift、mismatch、rule readiness 变化、forged artifact、caller misuse。

**Validation before parsing：** not-found / UNEVALUATED → parser calls = 0（比「先 parse 再 block」更安全）。

测试：`test_resolve_revalidation_not_found_after_prepare`、`test_unevaluated_confirm_bypass_parser_unreachable`、`test_resolve_confirm`。

---

## 16. nodes.py

共享文件：F08 prepare/complete + F09 slot nodes **并存**；F10 新增以下（读 F10 时聚焦这些）：

| Symbol | 职责 | 读 input_text | Repo/Selector | confirmed ID |
|--------|------|---------------|---------------|--------------|
| `_prepare_node` | lifecycle / invocation | 否 | 否 | 否 |
| `_make_validate_terminal_candidate_node` | **唯一**业务校验节点 | 否 | **是** | 写 `None` |
| `_interpret_confirmation_node` | 仅 RESOLVE+READY | **是** | 否 | 写 `None` |
| `_finalize_confirmation_node` | **唯一** confirmed 赋值 | 否 | 否 | **唯一 non-None** |
| `_compose_terminal_response_node` | deterministic template | 否 | 否 | 否 |
| `_complete_node` | F08/F09 同款 lifecycle | 否 | 否 | 否 |

Routers（pure）：

- `_route_by_terminal_validation`（READY 时内部调 `_route_by_terminal_mode`）
- `_route_by_terminal_mode`
- `_route_by_confirmation_intent`

0 repository / selector / LLM / network；不产生 business truth。

---

## 17. workflow.py

F10 = **specialized** capability，**不替换**：

- F08：`build_agent_workflow` / `run_agent_workflow`
- F09：`build_slot_interaction_workflow` / `run_slot_interaction_workflow`

### 计数

- Execution nodes = **6**（prepare / validate_terminal_candidate / interpret_confirmation / finalize_confirmation / compose_terminal_response / complete）
- Logical routers = **3**（validation / mode / confirmation）

### RF-F10-REV-003（accepted INFO）

逻辑上 3 routers；实现上 mode router 由 validation router **内部调用**。
LangGraph 只有 2 个 `add_conditional_edges`，无独立 mode hop node；**behavioral semantics 仍等价** validation → mode → confirmation。不需要为「API hop 数量」修代码。

### 拓扑

```text
PREPARE READY / BLOCKED:
  START → prepare → validate → compose → complete → END

RESOLVE CONFIRMED:
  … → validate → interpret → finalize → compose → complete → END

RESOLVE REJECTED / UNCERTAIN:
  … → interpret → compose → complete → END   # 无 finalize

BLOCKED:
  … → validate → compose → complete → END    # 无 interpret / finalize
```

Runner：`_run_terminal_confirmation` deep copy state；`empty_f10_namespace` 刷新 f10；保留其它 namespace（如 `f09`）。

---

## 18. Public API（`__init__.py`）

**在这里找 exports，不在这里找业务逻辑。**

| 分类 | Symbols |
|------|---------|
| Domain / Enum | `TerminalCandidateContext`、`TerminalValidationStatus`、`TerminalValidationResult`、`RuleReadinessSnapshot`、`ConfirmationIntent`、`ConfirmationStatus`、`TerminalConfirmationFailureKind`、`BusinessRepositoryReader` |
| Dependencies | `TerminalConfirmationDependencies` |
| Context adapters | `build_terminal_candidate_context`、`terminal_candidate_context_from_business_transition` |
| Parser（便于单测） | `interpret_confirmation` |
| Workflow builder | `build_terminal_confirmation_workflow` |
| Runners | `prepare_terminal_confirmation`、`resolve_terminal_confirmation` |

**非 public contract：** `_select_executable_rules_adapter`、allowlists、`normalize_confirmation_text`、routers、private nodes、response helpers、`_run_terminal_confirmation`。

---

## 19. artifacts["f10"]（exact 8 keys）

| Key | 内容 |
|-----|------|
| `mode` | `"prepare"` / `"resolve"`（stable primitive） |
| `terminal_context` | controlled terminal subset |
| `terminal_validation` | 受控 validation 投影 |
| `rule_readiness` | selection projection（非 rule objects） |
| `confirmation` | `{status, intent}`；PREPARE 时 intent=`None` |
| `confirmed_business_id` | 默认 `None`；成功后 = candidate ID |
| `failure` | known blocked kind/message；REJECTED/UNCERTAIN 时为 `None` |
| `response_text` | deterministic 用户可见文本 |

**不存：** raw confirmation（已有 `AgentState.input_text`）、Business、Condition、`RuleSelectionResult`、Repository、Dependencies、Exception。

每次 runner **fresh** 替换 `f10`；**Preserve** 其它 namespace。
JSON-safe：`json.dumps(..., allow_nan=False)` 已由测试验证。
Caller immutability：deep copy，避免隐式改上游 state / context。

测试：`test_artifact_exact_layout_and_json_safe`、`test_fresh_f10_and_preserve_other_namespaces`、`test_caller_and_context_immutability`。

---

## 20. Failure Semantics

| 结果 | 类型 |
|------|------|
| `INVALID_TERMINAL_CONTEXT` | BLOCKED failure |
| `CANDIDATE_NOT_FOUND` | BLOCKED failure |
| `CANDIDATE_ID_MISMATCH` | BLOCKED failure |
| `CANONICAL_NAME_UNAVAILABLE` | BLOCKED failure |
| `RULES_UNEVALUATED` | BLOCKED failure |
| `CONFIRMED` | success |
| `REJECTED` | **normal interaction**（非 failure） |
| `UNCERTAIN` | **normal interaction**（非 failure） |

无 broad `except Exception → UNCERTAIN`。Repository programming bug 应 **propagate**，不可伪装成用户不确定。

---

## 21. Response Semantics

全部 `compose_terminal_response_text` deterministic templates；**0 LLM**。
用户侧：显示 `canonical_name`；默认不展示内部 ID（如 `DEMO_SS_001`）；不声称资格通过；不含材料/地点/渠道/费用/时限/法律依据。

---

## 22. Golden Scenario

```text
F09 slot → F04 TERMINAL_CANDIDATE → DEMO_SS_001
  → F10 PREPARE
      Business lookup
      canonical_name = 灵活就业人员社会保险费申报缴费
      Rule Selection = NO_RULES；selected=0；skipped=7；evaluation_performed=False
      READY → AWAITING；confirmed=None
  → new turn「确认」
  → F10 RESOLVE → revalidate → CONFIRMED
  → confirmed_business_id = DEMO_SS_001
```

测试：`test_golden_demo_ss_001_prepare_and_resolve`。

---

## 23. Negative / Uncertain / Blocked

| 场景 | 结果 |
|------|------|
| 「不是这个」 | REJECTED；confirmed=`None`；无 finalize；不重做 RAG |
| 「好像是吧」 | UNCERTAIN；confirmed=`None` |
| selected>0 → `RULES_AVAILABLE_UNEVALUATED` | `RULES_UNEVALUATED` / BLOCKED；parser 不可达 |
| candidate 不在 repository | `CANDIDATE_NOT_FOUND`；selector=0；BLOCKED |

REJECT 后如何回 RAG/Graph → **F12 / 上层 orchestrator**，不是 F10。

---

## 24. Tests 怎么证明安全边界

### `test_agent_terminal.py`（按族读，勿背 69 条）

Context / Adapters / Parser / Validation / Rule Readiness / PREPARE / RESOLVE / Artifacts / Immutability / Golden / Public imports。

**最值得读的真实测试：**

| Test | 证明什么 |
|------|----------|
| `test_prepare_stale_confirm_input_safe` | PREPARE + `"确认"` 仍 AWAITING；parser 结构不可达（monkeypatch raise） |
| `test_prepare_stale_slot_answer` | 槽位回答不会误确认 |
| `test_unevaluated_confirm_bypass_parser_unreachable` | UNEVALUATED 时即使用户「确认」也不可达 parser |
| `test_candidate_not_found_selector_not_called` | not-found → selector=0 |
| `test_resolve_revalidation_not_found_after_prepare` | 旧 PREPARE artifact 非 authority |
| `test_artifact_exact_layout_and_json_safe` | exact 8 keys + JSON safety |
| `test_fresh_f10_and_preserve_other_namespaces` | fresh f10 + 保留 f09 |
| `test_caller_and_context_immutability` | deepcopy / 不改 caller |
| `test_golden_demo_ss_001_prepare_and_resolve` | 端到端 Golden |
| `test_buqueren_not_confirmed_via_substring` | substring hazard |

**为何 parser-call=0 测试重要：** 仅看 `confirmed=None` 不够；必须证明节点结构上不可达（monkeypatch raise）。
**为何 revalidation 测试更关键：** 比单纯 RESOLVE「确认」更能证明旧 artifact 非 authority。

### `test_agent_workflow.py`（F10 段）

| Test | 焦点 |
|------|------|
| `test_build_terminal_confirmation_workflow_compiles` | graph 可编译 |
| `test_f10_prepare_workflow_path_no_interpret_finalize` | PREPARE 拓扑 |
| `test_f10_resolve_confirm_workflow_path` | CONFIRMED 路径 |
| `test_f10_resolve_reject_skips_finalize` | reject 绕过 finalize |
| `test_f10_resolve_uncertain_skips_finalize` | uncertain 绕过 finalize |
| `test_f10_blocked_skips_interpret_and_finalize` | blocked 绕过 |
| `test_f08_default_workflow_unaffected_by_f10` | F08 未被替换/破坏 |

共享 `nodes.py` / `workflow.py` / `__init__.py` 被 F10 修改 → **必须**回归 F08 default 与 F09 specialized。

### 证据摘要

terminal 69 + workflow 31 = Combined **100**；F09 **94**；Full **545 / 13 skipped**；相对 F09 历史 469，full suite **+76 passed**（总增量，不等于「新增 76 个 test function」）；compileall / pip check **PASS**（引用既有阶段）。

---

## 25. Feature Boundaries

| Feature | 边界 |
|---------|------|
| **F04** | Graph candidate + Rule Selection；F10 **0** `advance_until_blocked` |
| **F06** | 上游找方向；F10 **0** retrieval |
| **F07** | F10 Core **0** LLM；确认不依赖 Remote `USER_FREE_TEXT` interpretation |
| **F08** | 复用 AgentState / lifecycle；**未改** `state.py` |
| **F09** | 槽位交互；可产生 terminal transition；**不**产生 confirmed |
| **F11** | 未来 Redis / Session / Checkpoint / Audit；F10 只做 capability |
| **F12** | 未来 E2E 编排（含 REJECT 后回退） |
| **Knowledge** | 仅 confirmed 之后查材料/地点/渠道/法律依据；F10 不查 |

---

## 26. Debugging Guide

| 现象 | 先看哪里 |
|------|----------|
| 一直 AWAITING | 调的是 `prepare_terminal_confirmation` 还是 `resolve_…` |
| 「确认」仍 BLOCKED | `artifacts["f10"]["terminal_validation"]` → `rule_readiness` |
| 「好的」不确认 | exact positive set（设计如此 → UNCERTAIN） |
| confirmed 不产生 | READY **且** CONFIRMED；再看 `_finalize_confirmation_node` |
| 名称不对 | Repository `Business.canonical_name`，勿查 LLM/RAG |
| 拒绝后不换事项 | F12 / 上层编排 |

---

## 27. Interview Explanation

### 30 秒

F10 是事项最终确认层。F04 只给 `candidate_business_id`，我不会直接把 terminal candidate 当最终业务 ID。F10 用 PREPARE/RESOLVE 两阶段避免把上一轮槽位回答误判为最终确认；PREPARE 只校验候选并生成确认提示，RESOLVE 下一轮重新校验候选，再用本地精确匹配判断确认语义。只有 validation READY 且用户明确 CONFIRMED，才把 candidate ID 原样赋给 `confirmed_business_id`。`NO_RULES` 只代表当前没有可执行规则，不代表资格通过；若存在 `RULES_AVAILABLE_UNEVALUATED`，则 fail closed。

### 约 1 分钟（补 authority / 测试）

再强调：candidate authority 属 F04；F10 只消费 terminal context。Rule Selection ≠ Evaluation。Confirmation 是 local exact allowlist，不是 LLM。`artifacts["f10"]` 仅 8 个 JSON-safe keys，fresh namespace，保留 `f09`。LangGraph 上是 specialized workflow，与 F08/F09 并存。测试用 monkeypatch 证明 PREPARE/UNEVALUATED 下 parser 结构不可达，并用 revalidation 证明旧 artifact 非 authority。Full suite 545 passed；Review PASS，仅 3 条 INFO。

### 追问速答

1. **为何不在 F04 terminal 直接设 confirmed？** F04 只做图决策；最终确认是用户状态变更，属 F10。
2. **为何确认不用 LLM？** 高风险；本地 high-precision 更可控可测。
3. **为何 PREPARE/RESOLVE 分开？** 防 slot answer 误确认。
4. **为何 RESOLVE 再 validation？** 防 stale/forged；不信旧 f10。
5. **NO_RULES 为何能继续？** 确认事项身份，不是资格审核。
6. **UNEVALUATED 为何 BLOCK？** 已知有可执行规则但未求值，不能当 PASS。
7. **为何不实现 Evaluator？** ConditionExecutable 非完整 DSL；另开 Feature。
8. **confirmed 如何防伪造？** fresh revalidation + 唯一 finalizer + READY∧CONFIRMED。
9. **为何 artifact 不存 raw confirmation？** 已有 `input_text`；减复制与隐私扩散。
10. **F10 vs F11/F12？** F10=capability；F11=session 持久化；F12=E2E 编排。

---

## 28. Common Misunderstandings

1. Terminal candidate = confirmed → **错**
2. `NO_RULES` = eligibility pass → **错**
3. 「好的」应算 confirmed → F10 **intentionally** UNCERTAIN
4. RESOLVE 可直接信 PREPARE result → **错**
5. F10 应重新推荐业务 → **错**（属上游 / F12）
6. Rule selector = Rule evaluator → **错**

---

## 29. 修改代码时的注意事项

| 变更意图 | 要求 |
|----------|------|
| 扩大 positive phrases | 高风险评估 + 测试 |
| LLM confirmation | 重走 Requirement / Data Policy / TD |
| Rule Evaluation | **新 Feature**（DSL / facts / UNKNOWN…） |
| 改 artifact schema | 检查 F11/F12 集成 |
| 改 shared `nodes.py` / `workflow.py` | **必须**回归 F08/F09 |

---

## 30. 阅读 Checklist

读完应能回答：

- [ ] candidate 从哪里来？
- [ ] confirmed 谁负责？
- [ ] PREPARE 为什么不 parse？
- [ ] RESOLVE 为什么 revalidate？
- [ ] `NO_RULES` 是什么意思？
- [ ] `UNEVALUATED` 为什么 block？
- [ ] `canonical_name` 从哪里来？
- [ ] 确认 parser 为什么 exact match？
- [ ] confirmed ID 在哪里赋值？
- [ ] artifact 为什么只有 8 keys？
- [ ] F10 为什么不调用 RAG/LLM/KG？
- [ ] F11/F12 未来负责什么？

---

## Appendix — Review INFO 阅读提示

| ID | 内容 | 为何不修 |
|----|------|----------|
| RF-F10-REV-001 | govagent Python 3.11.16 vs shell 默认 | 环境 INFO |
| RF-F10-REV-002 | thin rule_selector typing adapter | 不复制规则逻辑 |
| RF-F10-REV-003 | mode router 内嵌于 validation router | 关注 routing semantics，非 hop API 数量 |

Review Fix = **NOT REQUIRED**。
