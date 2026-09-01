# F04 Code Reading Guide — Deterministic Graph Transition + Rule Selection / Readiness

面向已读过 F02 Business Data Contract、F03 Decision Graph / Repository 的开发者（懂 Python / Pydantic 基础），第一次理解「静态 Decision Graph 如何真正运行起来」。

**核心问题：**

> F03 已经定义图长什么样，F04 如何让标准 slots 在图上确定性推进？到达候选事项后，系统如何诚实表达「有没有可执行规则」，而不伪造资格审核结论？

最新验证证据：

| 项 | 结果 |
|----|------|
| Python | 3.11.16（govagent） |
| F04 targeted | **36 passed**, 0 failed, 0 skipped |
| Full pytest | **125 passed**, 0 failed, 0 skipped |
| compileall | PASS |
| pip check | PASS |
| warning | 1 个已知 StarletteDeprecationWarning（upstream，非 F04 Blocking） |

---

## 1. F04 在整体架构中的位置

```
用户自然语言
        ↓
未来 LLM / NLU（槽位抽取 / 受控映射；confidence 在此层处理）
        ↓
标准 slots（Mapping[str, str]）
        ↓
未来 Semantic Retrieval（找方向 → graph_id / entry）
        ↓
F03 DecisionGraph（静态定义）
        ↓
F04 Transition Engine（step / advance_until_blocked）
        ↓
TERMINAL_CANDIDATE / NEED_SLOT / INVALID_SLOT / UNSUPPORTED / FALLBACK
        ↓
F04 Rule Selection / Readiness（select_executable_rules）
        ↓
NO_RULES 或 RULES_AVAILABLE_UNEVALUATED
        ↓
未来 Agent — 事项确认（Matter Confirmation）
        ↓
confirmed business_id
        ↓
F03 JsonBusinessRepository / Knowledge Relation View
        ↓
材料 / 地点 / 渠道 / 法律依据
```

**F04 不负责：** 自然语言理解、Semantic Retrieval、用户最终确认、Rule Evaluation（PASS/FAIL）。

| Feature | 回答的问题 |
|---------|------------|
| **F03** | Graph 长什么样？事实怎么按 id 查？ |
| **F04** | Graph 怎么走？有哪些正式可执行 Rule 待未来 Evaluator？ |
| **F06** | Semantic Retrieval 如何落到 `graph_id`（未启动） |
| **F08/F09** | Agent 如何编排 Transition + Selection + 确认（未启动） |

---

## 2. F03 与 F04 的关系

| | F03 | F04 |
|--|-----|-----|
| 角色 | **静态业务决策图** | **确定性运行时推进器** |
| 定义 | Node / Edge / allowed_values / SLOT_MATCH / ENTRY_FORWARD | 如何用标准 slots 在图上走一步或走到底 |
| 类比 | 地图 | 按地图规则行走 |

F03 保证：唯一 ENTRY、DAG、allowed_values 与 outgoing Edge 严格对齐。  
F04 **信任**已加载/已校验的 Graph，**不**在每次 `step` 重跑全量结构校验。

---

## 3. 推荐阅读顺序

| 顺序 | 文件 | 为什么现在看 |
|------|------|--------------|
| 1 | `data/graphs/demo/social_security.json` | 先看 Demo 路径与 Edge id |
| 2 | `business_graph/transition.py` | Transition 核心实现 |
| 3 | `business_graph/__init__.py` | 公开 API 导出 |
| 4 | `business_rules/selection.py` | Rule Selection 实现 |
| 5 | `business_rules/__init__.py` | Selection 包导出 |
| 6 | `tests/test_graph_transition.py` | Transition 行为 + trace + Contract |
| 7 | `tests/test_rule_selection.py` | NO_RULES / 三层 Verification / 隔离 |
| 8 | `docs/features/F04-...md` | Feature 范围与阶段权威 |

**先 Graph JSON，再 Runtime：** 理解 F03 存的路径，再看 F04 如何消费。

---

## 4. TransitionStatus 逐个解释

| Status | 含义 | 是否异常 |
|--------|------|----------|
| `NEED_SLOT` | 当前 SLOT_GATE 缺所需标准 slot | **否** — 正常对话状态 |
| `INVALID_SLOT` | slot 存在但不在 `allowed_values` | **否** — 可澄清状态 |
| `ADVANCED` | 本步确定性推进成功，停在下一 Node | **否** — 不是「业务成功」，只是推进一步 |
| `TERMINAL_CANDIDATE` | 到达候选终止节点，产出 `candidate_business_id` | **否** — 仍非 confirmed |
| `UNSUPPORTED` | 当前 Demo/数据不支持该方向 | **否** — 非「用户不符合资格」 |
| `FALLBACK` | 结构化回退终止 | **否** — 话术/Intent 切换属上层 |

**不含：** `NO_RULES` / `PASS` / `FAIL`（后者属于 Rule Selection 或未来 Evaluator）。

---

## 5. TransitionResult 字段

| 字段 | 含义 |
|------|------|
| `status` | 上述 TransitionStatus |
| `current_node_id` | **结果最终停留的 Node**（= `visited_node_ids[-1]`） |
| `required_slot` | NEED_SLOT / INVALID_SLOT 时：缺/错的 slot 名 |
| `invalid_value` | INVALID_SLOT 时：保留原非法值 |
| `allowed_values` | 澄清用合法值列表 |
| `question_text` | 节点固定提问文案（非 LLM 生成） |
| `candidate_business_id` | TERMINAL_CANDIDATE 时 |
| `unsupported_reason` | UNSUPPORTED 时 |
| `visited_node_ids` | 本次调用经过的节点（含起点） |
| `traversed_edge_ids` | 本次调用实际走过的边 |

**刻意没有 `next_node_id`：** 最终位置已由 `current_node_id` 表达；历史由 trace 提供。

`step` 与 `advance_until_blocked` **共用同一** `TransitionResult` 模型。

---

## 6. Result fail-fast Contract

`TransitionResult` 通过 Pydantic `model_validator` 禁止语义矛盾：

- `NEED_SLOT`：必须 `required_slot` + 非空 `allowed_values` + `question_text`；不得有 `candidate_business_id`
- `INVALID_SLOT`： additionally 必须 `invalid_value`
- `TERMINAL_CANDIDATE`：必须 `candidate_business_id`；不得同时有 slot 澄清字段或 `unsupported_reason`
- `UNSUPPORTED`：必须 `unsupported_reason`；不得有 candidate
- `FALLBACK`：不得有 candidate / unsupported / slot 澄清字段

测试中有 9 个负向 Contract case（Review Fix TG-F04-03）。

---

## 7. Trace Invariant（通用）

对 **step** 与 **advance_until_blocked** 均适用：

1. `visited_node_ids` 非空  
2. `current_node_id == visited_node_ids[-1]`  
3. `len(traversed_edge_ids) == len(visited_node_ids) - 1`

例：visited = `[entry, action, payment_actor]` → edges 必须恰好 2 条。

**重要：** `NEED_SLOT` / `INVALID_SLOT` **允许**保留已走过的历史 trace（见下节）。  
**禁止**再要求「阻塞时 edges 必须为空」。

---

## 8. NEED_SLOT 也可以有历史 trace

用户已有 `service_action=payment`，缺 `payment_actor`：

```python
advance_until_blocked(graph, "social_security_entry", {"service_action": "payment"})
```

系统已走：entry → action → payment_actor，才发现缺 slot。

最终：

- `status = NEED_SLOT`
- `required_slot = payment_actor`
- `visited_node_ids = [social_security_entry, social_security_action, payment_actor]`
- `traversed_edge_ids = [e-entry-action, e-action-payment]`

**不能因为最终是 NEED_SLOT 就清空前面已走过的路径。**

---

## 9. INVALID_SLOT 同样保留历史

`service_action=payment`，`payment_actor=not_valid`：

- 先走到 `payment_actor`
- 再发现值非法 → `INVALID_SLOT`
- trace 仍保留 entry → action → payment_actor 与 2 条边
- `invalid_value` 保留原值，**不**自动修正、**不**猜最近合法值

INVALID_SLOT 表示「在当前 Gate 被确定性阻塞」，不是「整个 Graph 没执行」。

---

## 10. step() — 单步原语

```python
step(graph: DecisionGraph, current_node_id: str, slots: Mapping[str, str]) -> TransitionResult
```

- 只处理**当前 Node 一次**
- 不递归、不调 Repository、不调 Rule Selection、不调 LLM
- **不修改** `graph` 或 `slots`
- 只读 `slots` 中当前 `node.slot_name`；extra key 忽略

### ENTRY

不需要 slot。找唯一 `ENTRY_FORWARD` → 进入 target。

例：`social_security_entry` → `e-entry-action` → `social_security_action` → 返回 `ADVANCED`。  
若 target 已是 terminal-like，**直接**返回对应终止态（不先 ADVANCED 再 step 一次）。

### SLOT_GATE

读 `node.slot_name`：

- key 不在 slots → `NEED_SLOT`
- value ∉ `allowed_values` → `INVALID_SLOT`
- 合法 → 唯一 `SLOT_MATCH`（EQ）→ 进入 target

### 已在 terminal-like 上调用 step

`current_node_id` 已是 `terminal_demo_ss_001` / `unsupported_transfer` / `social_security_fallback`：

- 直接返回对应状态
- `visited=[current]`，`traversed=[]`
- 不查 outgoing、不从 entry 重启

---

## 11. 为什么不自动猜非法 slot

若 NLU 产出 `payment_actor=personal-pay`，而 allowed 只有 `self_payment` / `employer_payment` / `other`：

F04 **必须** `INVALID_SLOT`，**不能**猜 `personal-pay ≈ self_payment`。

模糊理解与 confidence 阈值属于 **NLU / Agent Controller**。  
F04 只消费**已被上层接受的标准值**。

---

## 12. confidence 为什么不在 F04

未来 LLM 可能输出 `value=self_payment, confidence=0.91`。  
是否接受该值 → NLU / Agent。  
F04 收到的应是 `payment_actor=self_payment` 字符串。

Transition Engine 始终**纯确定性**。

---

## 13. advance_until_blocked() — 便利 API

```python
advance_until_blocked(graph, current_node_id, slots) -> TransitionResult
```

**不是第二套 Graph Engine。** 内部循环调用 `step`：

- `ADVANCED` → 以 `result.current_node_id` 继续
- 停止于：`NEED_SLOT` | `INVALID_SLOT` | `TERMINAL_CANDIDATE` | `UNSUPPORTED` | `FALLBACK`

### Trace 合并（避免重复 Node）

第一次 step：`[entry, action]`  
第二次 step：`[action, payment_actor]`  
合并时只追加 `step.visited_node_ids[1:]`：

→ `[entry, action, payment_actor]`（不能出现重复 `action`）

阻塞 step 的 `visited=[current]` 时，`[1:]` 为空，历史路径保持不变。

轻量防御：`hop_count > len(graph.nodes)` → `TransitionInvariantError`（坏 Graph / 逻辑 bug）。

---

## 14. 完整 Demo Transition

```python
slots = {
    "service_action": "payment",
    "payment_actor": "self_payment",
    "employment_type": "other_flexible_employment",
}
result = advance_until_blocked(graph, graph.entry_node_id, slots)
```

路径：

```text
social_security_entry
→ social_security_action
→ payment_actor
→ employment_type
→ terminal_demo_ss_001
```

最终：

- `status = TERMINAL_CANDIDATE`
- `candidate_business_id = DEMO_SS_001`
- **不是** `confirmed_business_id`

---

## 15. Terminal Candidate ≠ confirmed business

`candidate_business_id` 只表示：根据 Graph + 标准 slots，系统找到**候选事项**。

尚未：用户确认、资格审核通过。

未来上层 **Matter Confirmation** 后才能写入 `confirmed business_id`。

---

## 16. UNSUPPORTED 与 FALLBACK

**UNSUPPORTED**（例：`service_action=transfer`）：

```text
entry → action → unsupported_transfer
```

- 当前 Demo 无转移正式数据
- ≠ 用户不符合资格

**FALLBACK**（例：`service_action=inquiry` 或 `payment_actor=employer_payment`）：

- F04 只给结构化 `FALLBACK` 状态
- 重新询问 / Intent 切换 / Semantic Retrieval → 未来 Agent / F06

---

## 17. Transition 异常 vs 业务状态

| 类型 | 何时 | 含义 |
|------|------|------|
| `TransitionNodeNotFoundError` | 未知 `current_node_id` | **程序调用错误** |
| `TransitionInvariantError` | ENTRY 非唯一 forward、SLOT 非唯一 match、advance 超 hop 等 | Graph 违反 Transition 假设 |
| `NEED_SLOT` / `INVALID_SLOT` | 缺信息 / 非法值 | **正常可澄清业务状态** |

不要把 NEED_SLOT 当 Exception；不要 catch InvariantError 后返回 FALLBACK。

---

## 18. Graph / slots 不可变

F04 只读 `DecisionGraph`：不增删改 Node/Edge/allowed_values。  
slots 只读：无 `pop` / `update` / 赋值。

Graph 配置错误应在 load/validate 阶段 fail-fast，不在运行时修 Graph。

---

## 19. Rule Selection 为什么存在

Transition 到 TERMINAL_CANDIDATE 只说明「候选事项找到」。  
理论上下一步是**资格规则终审**。

但当前 F02：`DEMO_SS_001` **Executable selected = 0**。  
F04 只实现 **Executable Rule Selection / Readiness**：

> 「系统现在有哪些正式规则可以被未来 Evaluator 执行？」

**不是：** 「申请人资格是否通过？」

---

## 20. RuleSelectionStatus

| Status | 含义 |
|--------|------|
| `NO_RULES` | 无正式可执行 VERIFIED Rule；**≠ PASS** |
| `RULES_AVAILABLE_UNEVALUATED` | 有可执行 Rule，但无 Full Evaluator；**≠ PASS / FAIL** |

Runtime **不暴露** `PASS` / `FAIL` / `NEED_MORE_INFO`（F02 `ConditionExecutable` 尚无完整 operand/expression）。

---

## 21. select_executable_rules()

```python
select_executable_rules(business_id: str, repository: JsonBusinessRepository) -> RuleSelectionResult
```

- **不接受** slots / facts / confidence / DecisionGraph
- 显式 `repository.get_conditions(..., consumption=ConsumptionMode.INTERNAL)`
- INTERNAL ≠ 可执行；读取后仍须 filter
- 未知 `business_id` → `BusinessNotFoundError`（≠ NO_RULES）

### Executable Filter（仅 Layer 3）

Selected **当且仅当**：

1. `condition.executable is not None`
2. `executable.verification_status == VERIFIED`
3. `executable.usable_by_rule_engine is True`

**不要求** `source_status == VERIFIED` 或 `normalized_status == VERIFIED`。

合法例：`SOURCE_EXPLICIT` + `SYSTEM_DERIVED` + Layer3 VERIFIED → 可被 selected。

### RuleSelectionResult 字段

- `business_id`
- `status`
- `selected_rule_ids`（condition_id 列表，按 INTERNAL 遍历顺序）
- `skipped_non_executable_count` = `len(internal) - len(selected)`（**不是**执行失败次数）

---

## 22. Decision Edge ≠ Official Rule

Graph 中 `employment_type` 三条 Edge 为 `SOURCE_SUPPORTED`，引用 F02 applicant Conditions。

**SOURCE_SUPPORTED** = 分流设计有来源依据  
**≠** Executable Rule

因此：Graph 有 SOURCE_SUPPORTED Edge，而 `select_executable_rules("DEMO_SS_001")` 仍为 **NO_RULES**。

**代码级隔离：**

- `transition.py` 不 import `business_rules`
- `selection.py` 不 import `DecisionGraph` / Edge

Transition **不会**在到达 terminal 时自动调用 Selection；上层 Agent 编排两者。

---

## 23. DEMO_SS_001 当前真实语义

```text
INTERNAL Conditions = 7
Executable selected   = 0

→ status = NO_RULES
→ selected_rule_ids = []
→ skipped_non_executable_count = 7
```

这不表示：资格通过 / 资格不通过。  
只表示：**当前没有系统可执行的正式资格规则。**

NO_RULES 后仍可做 **事项确认**（「是否办理 DEMO_SS_001？」），不能说「资格审核已通过」。

---

## 24. 未来 Agent 编排（F08/F09）

| Transition 结果 | Agent 可用字段 |
|-----------------|----------------|
| `NEED_SLOT` | `required_slot`, `allowed_values`, `question_text` |
| `INVALID_SLOT` | + `invalid_value` |
| `TERMINAL_CANDIDATE` | `candidate_business_id` → 再调 `select_executable_rules` |
| `NO_RULES` | 不声称资格通过；可继续事项确认 |

F04 不生成 Agent 自然语言文案。

---

## 25. 未来 Full Rule Evaluator

**不属于 F04。** 前置：

1. 扩展 F02 Executable Contract（operand / expression）
2. 业务方确认 VERIFIED executable Rule
3. 定义 Rule Facts Contract
4. 再实现 PASS / FAIL / NEED_MORE_INFO

当前不要提前模拟这些结果。

---

## 26. 如何调试

### Transition

| 现象 | 查什么 |
|------|--------|
| `TransitionNodeNotFoundError` | `current_node_id` 是否在 Graph 中 |
| `TransitionInvariantError` | ENTRY forward 数量、SLOT_MATCH 唯一性、target 是否存在 |
| `NEED_SLOT` | `required_slot` / `allowed_values` / `question_text` |
| `INVALID_SLOT` | `invalid_value` / `allowed_values` |
| 路径不对 | `visited_node_ids` / `traversed_edge_ids` 顺序 |

### Rule Selection

| 现象 | 查什么 |
|------|--------|
| `BusinessNotFoundError` | Repository 是否加载该 business |
| `NO_RULES` | INTERNAL conditions 的 `executable` 是否全 null |
| 预期 selected 却没有 | Layer3 VERIFIED + usable；**不要**看 Graph Edge |

---

## 27. 测试怎么读

| 分组 | 覆盖 |
|------|------|
| **A. Transition behavior** | ENTRY / NEED_SLOT / INVALID_SLOT / terminal / unsupported / fallback |
| **B. Trace Contract** | 完整路径、部分 NEED_SLOT、部分 INVALID_SLOT 历史 |
| **C. Result fail-fast** | 9 个 parametrize 负向 case |
| **D. Immutability** | Graph / slots 不变 |
| **E. Rule Selection** | NO_RULES、UNEVALUATED fixture、unknown business |
| **F. Isolation** | SOURCE_SUPPORTED Edge + NO_RULES |

运行：

```bash
pytest tests/test_graph_transition.py tests/test_rule_selection.py -v
pytest -v
```

---

## 28. Review Fix 摘要

| ID | 状态 |
|----|------|
| RF-F04-001 | CLOSED — 文档 Test 状态同步 |
| TG-F04-01 | CLOSED — 部分推进 INVALID_SLOT trace |
| TG-F04-02 | CLOSED — current UNSUPPORTED/FALLBACK step |
| TG-F04-03 | CLOSED — Result validator 9 cases |
| TG-F04-04 | CLOSED — UNSUPPORTED 完整 trace |
| RF-F04-002 | **Deferred** — `transition.py` 部分字段用 `assert`；合法 Graph 无影响 |

---

## 29. 不能随便改的东西

1. Transition 不能调用 LLM  
2. 不能把 confidence 塞进 F04 slots  
3. 不能动态改 Graph  
4. INVALID_SLOT 不能自动映射成最接近合法值  
5. advance 不能复制第二套 step 逻辑  
6. 阻塞时不能丢失历史 trace  
7. Terminal Candidate ≠ confirmed business  
8. SOURCE_SUPPORTED ≠ executable Rule  
9. NO_RULES ≠ PASS  
10. F04 不能提前暴露 PASS/FAIL  
11. Rule Selection 不能读 Graph  
12. Transition 不能自动执行 Rule Selection  

---

## 30. 相关文档

| 文档 | 用途 |
|------|------|
| `docs/features/F04-deterministic-graph-transition-and-rule-selection.md` | Feature 范围与阶段权威 |
| `docs/code-reading/F03-business-graph-and-json-repository-reading-guide.md` | F03 Graph / Repository 基础 |
| `docs/code-reading/F02-demo-ss-001-business-data-contract-reading-guide.md` | F02 Condition 三层 / executable |
| `AGENTS.md` | 核心架构原则 |
