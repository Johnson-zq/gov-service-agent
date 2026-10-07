# F09 Missing Slot Mapping with Controlled Semantics 代码阅读指南

这不是 Requirement，也不是 Technical Design，也不是 API Reference。

本文按一次真实办理请求的顺序，说明 F09 如何把用户的一句话映射成当前节点允许的 machine value，以及这次 Reopen 增加的 controlled semantics 从哪里来、在哪里停下。

权威记录：`docs/features/F09-missing-slot-question-answer-mapping.md`。只看本文也可以理解数据怎么走、从哪个函数开始读、出了问题先看哪里。

**F09 负责：** 当 Business Decision Graph 停在一个缺失槽位时，理解用户这一轮自然语言，把它映射到当前节点明确允许的 controlled value。

这次 Reopen 增加的是 controlled allowed-value semantics。它没有改变 Business Decision Graph 的路径权、F04 的确定性转移、F10 的明确确认，也没有改变 F07 的远程数据策略。

本文重点只在 F09。`semantics.py` 不是整个 Agent。

---

## 1. 先看业务问题

贯穿例子是 Golden。用户说：

> 平时接零活，没有固定单位

当前等待的槽位是 `employment_type`。当前节点允许的 machine value 只有：

| machine value | controlled meaning |
|---------------|--------------------|
| `self_employed_without_employees` | 无雇工的个体工商户 |
| `part_time_without_employer_insurance` | 未在用人单位参加社会保险的非全日制从业人员 |
| `other_flexible_employment` | 其他灵活就业人员 |

期望映射是 `other_flexible_employment`。

改造前，Mapper 只看到这三个英文枚举和用户原话。当时 Production 结果是：mapped value 正确，membership 通过，模型自报 confidence 为 `0.72`。本地门槛是 `0.80`，所以结论是 `LOW_CONFIDENCE`。这不是选错了值。缺口是模型缺少受控业务 wording。

后来的小规模对照里，同一句在补上 meaning 之后 confidence 到了 `0.80`。这只是 `SMALL_SCALE_EVIDENCE_ONLY`。它不是新的 Production 运行结果，也不能写成真实模型现在一定不低于 `0.80`。

---

## 2. 一条真实请求是怎么走的

```text
用户输入
        ↓
POST /api/v1/session/turn
        ↓
SessionTurnService.handle_turn
        ↓
识别会话，必要时从 Redis checkpoint 恢复
        ↓
AgentTurnProcessor.process_turn
        ↓
当前 Business Decision Graph 停在 NEED_SLOT
        ↓
run_slot_interaction_workflow
        ↓
interpret_slot_input
        ↓
detect_explanation_request
        ↓
命中解释请求 → 解释旁路，不选择 value
        ↓
正常回答 → 读当前 node
        ↓
required_slot / allowed_values / source_condition_refs
        ↓
deps.business_repository
        ↓
project_allowed_value_semantics
        ↓
SemanticProjectionResult
        ↓
FULL  → enriched AnswerMappingRequest → LlmAnswerMapper
NONE  → legacy AnswerMappingRequest → LlmAnswerMapper
PARTIAL / INVALID → fail closed，不调用模型
        ↓
Provider 仍经过 F07
        ↓
AnswerMapperOutput
        ↓
mapper_output_to_interpretation
        ↓
validate_slot_mapping
        ↓
先 membership，再 confidence >= 0.80
        ↓
只有 ACCEPTED → advance_until_blocked
        ↓
F04 确定性转移
        ↓
新的受控槽位进入后续图状态
        ↓
以后到达 Terminal Candidate，仍要 F10 明确确认
        ↓
checkpoint 保存 + Audit
        ↓
API 返回本轮结果
```

下面每一步只定位入口、输入、输出和下一步。文件地图放在第 18 节。

---

## 3. F09 在整个 Agent 中的位置

```text
Client
  → Session API          src/gov_service_agent/session/api.py
  → Redis / checkpoint   src/gov_service_agent/session/store.py
  → Agent workflow
  → F09 缺失槽位          本文
  → F04 确定性前行        business_graph/transition.py
  → 以后 F10 确认         agent/terminal.py
  → checkpoint save + Audit
  → API response
```

F11 的位置用一句话就够：`session_turn` 调用 `SessionTurnService.handle_turn`。已有会话走 `_handle_existing_session`，用 `load_active_session` 取出 checkpoint，再 `from_persisted` 恢复状态。`AgentTurnProcessor.process_turn` 跑本轮 Agent。成功后 `commit_successful_turn` 同时写入新 checkpoint 和 `TURN_COMPLETED` audit。F09 只处理“图正在等一个槽位回答”的那一段，不是会话存储，也不是最终事项确认。

`AgentState` 本身没有 `business_id`。当前槽位上下文放在 `artifacts["f09"].slot_context`，类型是 `SlotInteractionContext`。它在图返回 `NEED_SLOT` 或 `INVALID_SLOT` 时形成，字段包括 `current_node_id`、`required_slot`、`allowed_values`、`question_text`。

---

## 4. 当前 slot 上下文从哪里来

入口函数是 `nodes._interpret_slot_input`，由 `_make_interpret_slot_input_node(deps)` 闭包提供。`build_slot_interaction_workflow` 把它挂在 `prepare` 之后。

| 项目 | 内容 |
|------|------|
| 模块 | `src/gov_service_agent/agent/nodes.py` |
| 函数 | `_interpret_slot_input` |
| 输入 | `AgentState.input_text`；`artifacts["f09"].slot_context`；`deps` |
| 输出 | 更新后的 `artifacts["f09"]`：解释结果、映射结果，或语义契约失败 |
| 下一步 | `_route_by_interpretation` |

`slot_context` 回答三个问题：

| 字段 | 业务含义 |
|------|----------|
| `required_slot` | 当前要回答的字段，例如 `employment_type` |
| `allowed_values` | 当前唯一合法的 machine value 集合 |
| 当前 node 上的 `source_condition_refs` | 从图指向 Business Data 的受控引用；不在 `SlotInteractionContext` 里，要从 Decision Graph node 再读 |

用户原话来自 `state["input_text"]`，不是从 checkpoint 里的旧句子重读。

---

## 5. Explanation 为什么先判断

问含义和选择选项是两件事。用户说“什么是灵活就业？”时，是在问当前问题里的词，不是在选择 `other_flexible_employment`。

`detect_explanation_request(user_text, question_text)` 是本地正则，不访问网络。它在 `_interpret_slot_input` 的第一件事。命中后直接返回 `EXPLANATION_REQUEST`，后面的 Repository、投影和 Mapper 都不会执行，也不会写 slot，也不会进入 F04。路由去 `explain_current_topic`，再回到 `resume_current_slot`，把原来的问题再问一遍。

当前 detector 用本地确定性句式识别常见解释问法。原有“什么是……”“……是什么意思”“……是指什么”“请解释一下……”仍然有效。`employment_type` 的问题含有“灵活就业”，所以“什么是灵活就业？”和“什么叫灵活就业？”都会进入 `EXPLANATION_REQUEST`。“什么叫 <topic>”是整句锚定规则，由 `detect_explanation_request` 识别。它不是 `if "叫" in text`。捕获出的 topic 仍经过 `_normalize_topic_candidate`，并且必须出现在当前 `question_text` 里。与当前问题无关的“什么叫 X”不会自动变成这个槽位的解释。

因此下面这些句子不会因为含有“叫”而被判成解释请求：“我叫张三”“这个项目叫自由职业”“他们叫我去窗口办理”。

命中后 Repository 查询为 0，semantic projection 为 0，Answer Mapper 为 0，F04 为 0，也不写 slot。解释结束后 `resume_current_slot` 把原来的问题接回来，继续等待 `employment_type`。Code-Reading 阶段曾发现“什么叫……”当时尚未支持；该缺口已由 `F09-CR-MAJOR-01` 修复。Golden“平时接零活，没有固定单位”仍不是解释请求，继续走 semantic projection 和 enriched mapping。

对应行为看 `tests/test_agent_workflow.py` 里的解释工作流：解释命中时 Mapper 调用次数为 0，`get_conditions` 次数为 0，F04 次数为 0。

---

## 6. source_condition_refs 是什么

F09 发生时还没有 `confirmed_business_id`。`employment_type` 节点在图数据里已经带着引用：

```text
business_id   = DEMO_SS_001
condition_id  = cond-applicant-01
                cond-applicant-02
                cond-applicant-03
```

`SourceConditionRef` 定义在 `business_graph/models.py`，只有 `business_id` 和 `condition_id`。

`ref.business_id` 是 `JsonBusinessRepository` 的查找键。它不是 `candidate_business_id`，不是 `confirmed_business_id`，也不是用户已经选定的事项。

如果必须先确认事项才能读 wording，读完 wording 才能映射，映射完才能确认事项，就会绕回去。当前图节点上的引用在确认之前就存在，所以不存在 F09 依赖 F10、F10 又依赖 F09 的循环。`confirmed_business_id` 只在以后的 F10 里，由 `assign_confirmed_business_id` 在校验 READY 且用户明确 CONFIRMED 时写入。

---

## 7. Business Data 如何变成 controlled semantics

投影函数是 `project_allowed_value_semantics`，在 `business_data/semantics.py`。

它解决的问题是：图知道哪些 machine value 合法，Business Data 知道公开 wording，投影把二者确定地对齐。

| 项目 | 内容 |
|------|------|
| 输入 | 已注入的 `repository`；`slot_name`；`allowed_values`；`source_condition_refs` |
| 输出 | `SemanticProjectionResult`：`coverage`、`semantics`、`reason_code` |
| 下一步 | `FULL` / `NONE` 去 Mapper；`PARTIAL` / `INVALID` fail closed |

`ControlledAllowedValueSemantic` 只有 `value` 和 `meaning`。`value` 是机器契约。`meaning` 是受控描述，不能决定边、规则、事项或确认结果。模型 `frozen=True`、`extra="forbid"`，空白 `value` 或 `meaning` 会被拒绝。

`SemanticProjectionResult` 同样冻结且禁止额外字段。只有 `FULL` 可以携带非空 `semantics`。其余覆盖状态必须是空 tuple。

当前 Demo 的真实链是：

```text
Decision Graph node employment_type
        ↓
source_condition_refs
        ↓
DEMO_SS_001
cond-applicant-01 / 02 / 03
        ↓
JsonBusinessRepository.get_conditions(..., PUBLIC)
        ↓
field = employment_type
normalized_values 恰好一个 machine value
source_text = 对应中文 wording
        ↓
ControlledAllowedValueSemantic
```

F09 不打开 `data/demo/demo_ss_001.json`。snapshot 由上层装载进 Repository。节点只读 `deps.business_repository`。

公开资格不在 `semantics.py` 里重写。`get_conditions` 在 `ConsumptionMode.PUBLIC` 时调用已有的 `is_public_condition`。某条 condition 在 `INTERNAL` 里存在、公开过滤后看不到，投影得到 `invalid_unapproved_ref`，不会改去读内部数据。

顺序也不跟 Repository 返回顺序走。`FULL` 时按 `allowed_values` 重建 tuple：

```python
ordered = tuple(
    ControlledAllowedValueSemantic(value=value, meaning=found[value])
    for value in allowed
)
```

---

## 8. FULL / NONE / PARTIAL / INVALID

| 状态 | 数据情况 | 调用 LLM | legacy | 进入 F04 |
|------|----------|----------|--------|----------|
| `FULL` | 每个 allowed value 恰好一条合法、公开、非空、字段对齐的 meaning | 是，enriched | 否 | 只有随后 `ACCEPTED` 才进入 |
| `NONE` | `source_condition_refs` 为 `None` 或空 | 是，legacy | 是 | 只有随后 `ACCEPTED` 才进入 |
| `PARTIAL` | 引用已接入，已读数据合法，但没盖住全部 allowed values | 否 | 否 | 否 |
| `INVALID` | 引用、字段、取值或 wording 违反契约 | 否 | 否 | 否 |

### FULL

refs 存在。每条 ref 都能在 PUBLIC conditions 里找到。`field` 等于当前 `slot_name`。`normalized_values` 恰好是一个非空字符串，并且属于 `allowed_values`。`source_text` 去掉空白后非空。没有重复值，没有图里不存在的值，而且每个 allowed value 都被覆盖。然后按图的 `allowed_values` 生成有序 semantics，`reason_code` 为 `full`。

`employment_type` 三条 applicant condition 都满足这些条件，所以是 `FULL`。

### NONE

```python
if not source_condition_refs:
    return SemanticProjectionResult(
        coverage=SemanticCoverage.NONE,
        semantics=(),
        reason_code=REASON_NONE,
    )
```

这里直接返回，不调用 `get_conditions`。这表示旧槽位还没接入语义增强，不是 Business Data 坏了。例如 `source_condition_refs` 为 `null` 的系统节点走这条路。节点随后把 `allowed_value_semantics=None` 交给 Mapper。

### PARTIAL

引用已经接上，读到的每条数据本身都合法，但合法 meaning 只覆盖一部分 allowed values。允许 A、B、C，只有 A、B，就是 `PARTIAL`，`reason_code` 为 `partial_missing_values`，`semantics` 为空。

它不能退回 legacy。否则有的选项带着 wording，有的选项仍是裸枚举，模型上下文不对称。节点在 Mapper 之前返回 `semantic_projection_partial`。

### INVALID

按 ref 扫描，第一个缺陷立即返回，`semantics` 为空：

| 情况 | `reason_code` |
|------|----------------|
| ref 找不到，或 business 不存在，或 PUBLIC 过滤后没有 | `invalid_unapproved_ref` |
| `field` 不是当前 slot | `invalid_field_mismatch` |
| `normalized_values` 不是恰好一个非空字符串 | `invalid_normalized_value` |
| `source_text` 空白 | `invalid_blank_meaning` |
| machine value 不在 `allowed_values` | `invalid_extra_value` |
| 同一个 machine value 出现两次 | `invalid_duplicate_value` |

当前节点在图里找不到时，节点自己也记 `invalid_unapproved_ref`，不会把它当成 `NONE`。

这些是系统数据契约错误，不是用户没说清楚。所以不会变成 `UNCERTAIN`、`LOW_CONFIDENCE` 或 `OTHER`。

`PARTIAL` 和 `INVALID` 的模型调用次数是 0，F04 调用次数是 0，slot 写入次数是 0。

---

## 9. FULL 与 NONE 的 Mapper 差异

请求类型在 `agent/interaction.py` 的 `AnswerMappingRequest`。

改造前只有 `required_slot`、`allowed_values`、`user_text`。现在多了 `allowed_value_semantics`：

| 值 | 含义 |
|----|------|
| `None` | legacy raw-enum mapping |
| 与 `allowed_values` 等长、同序的 tuple | semantic-enriched mapping |
| 空 tuple | 非法。长度对不上非空的 `allowed_values` |

请求层只检查数量和 `value` 顺序。它不再检查公开资格、核验状态或来源。那些已经由 semantic projection 负责。这是职责分离。

`NONE` 的 user message 仍是三行，不出现 `allowed_value_meanings=[]`：

```text
required_slot=...
allowed_values=[...]
user_text=...
```

这样尚未接入的旧槽位保持原来的 Prompt。

`FULL` 仍保留 raw `allowed_values`，只在它和 `user_text` 之间插入一行紧凑 JSON：

```text
required_slot=...
allowed_values=[...]
allowed_value_meanings=[{"value":"...","meaning":"..."}]
user_text=...
```

JSON 使用 `ensure_ascii=False` 和 `separators=(",", ":")`，每项只有 `value` 和 `meaning`。不发送 `source_ref`、核验状态、门槛或 Golden。meaning 不能代替 machine value。模型仍必须返回 `allowed_values` 里的那个枚举。

两条路径的 system prompt 是同一段字符串。它要求只返回 `kind`、`mapped_value`、`confidence`，并禁止 `next_node`、`business_id`、`rule_result` 以及材料、地点、渠道、法律依据。

---

## 10. LLMRequest 与 DataClassification

`LlmAnswerMapper.map_answer` 组装 `LlmRequest`，`operation` 为 `f09_slot_answer_mapping`。真正能否远程发送，仍由现有 Provider 上的 F07 policy 决定。本次没有修改 F07。

| 消息 | `NONE` | `FULL` |
|------|--------|--------|
| system | `SYSTEM_CONTROL_DATA` | `SYSTEM_CONTROL_DATA` |
| user | `USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA` | 再加 `PUBLIC_BUSINESS_METADATA` |

`FULL` 多出的分类是因为 controlled meanings 是公开业务元数据。`USER_FREE_TEXT` 没有被拿掉，所以 `DEFAULT` 仍然拒绝把真实用户输入发到远程模型。当前 Demo 远程调用仍依赖既有的 `DEMO_APPROVED`。

---

## 11. LLM 输出以后谁做最终校验

`AnswerMapperOutput` 仍只有 `kind`、`mapped_value`、`confidence`，并且 `extra="forbid"`。`next_node`、`business_id`、`candidate_business_id`、`confirmed_business_id`、`rule_result` 不能出现。这是 LLM 的权限上限。Provider 用 `parse_structured_output` 解析；解析失败走原来的 `MAPPER_PARSE_ERROR`，不是语义契约失败。

`mapper_output_to_interpretation` 只做类型转换：`slot_answer` 变成带值和 confidence 的 `UtteranceInterpretation`，`uncertain` / `other` 变成对应 kind。这里不是业务决策。

本地决定在 `validate_slot_mapping`，由节点 `_validate_slot_answer` 调用。顺序固定：

```text
kind 是不是 slot_answer
        ↓
mapped_value 是否属于 context.allowed_values
        ↓
不属于 → INVALID_VALUE
属于
        ↓
confidence 是否 >= policy.min_confidence
        ↓
低于门槛 → LOW_CONFIDENCE
达到门槛 → ACCEPTED，并写出 ValidatedSlot
```

非法 value 即使 confidence 是 `1.0`，仍然是 `INVALID_VALUE`。membership 的权威是 `allowed_values`，不是 confidence，也不是 meaning。

`MappingPolicy.min_confidence` 默认仍是 `_DEFAULT_MIN_CONFIDENCE = 0.80`。enriched mapping 没有加分、没有归一化、没有地板值。因此 `0.80` 是 `ACCEPTED`，`0.79` 是 `LOW_CONFIDENCE`。

---

## 12. 为什么只有 ACCEPTED 才进入 F04

`_route_by_validation` 只有 `accepted` 才去 `advance_business_graph`。该节点再次确认状态是 `ACCEPTED`，把 `validated_slot` 放进槽位字典，然后调用 `advance_until_blocked(deps.decision_graph, current_node_id, new_slots)`。

F04 根据当前图和已接受的 machine value 做确定性转移。meaning 不参与选边。LLM 没有 `next_node` 权限。`LOW_CONFIDENCE` 和 `INVALID_VALUE` 回到 `resume_current_slot`，槽位保持未接受。

---

## 13. 为什么 F09 不能替代 F10

F09 结束时，最多是当前槽位上有一个受控值，图可能继续走。即使以后走到 `TERMINAL_CANDIDATE`，`candidate_business_id` 仍只是候选。

`confirmed_business_id` 的写入点在 F10：`assign_confirmed_business_id`。它要求终点校验为 `READY_FOR_CONFIRMATION`，并且 `interpret_confirmation` 得到 `CONFIRMED`。controlled semantics 不参与这个判断，也不能跳过它。

---

## 14. PARTIAL / INVALID 如何 fail closed

```text
PARTIAL / INVALID
        ↓
_semantic_contract_failure
        ↓
InteractionFailure
        ↓
artifacts["f09"].failure
        ↓
_route_by_interpretation
        ↓
semantic_contract_failure
        ↓
_complete_node
        ↓
phase = COMPLETED
status = WorkflowStatus.COMPLETED
```

这条边在 `build_slot_interaction_workflow` 里直接连到 `complete`。它不经过 `resume_current_slot`，因为那条路会把失败说成用户没说清楚。

失败对象只有两个字段：

| 字段 | 内容 |
|------|------|
| `kind` | `semantic_projection_partial` 或 `semantic_projection_invalid` |
| `safe_message` | 低基数 `reason_code` |

不保存用户原话、完整 meaning、Prompt 或模型原文。用户看到的固定句子是“当前办理选项的说明不完整，暂时无法继续确认这个选项。”`interpretation` 保持为空，没有 `validated_slot`。

---

## 15. COMPLETED 为什么不是业务成功

`_complete_node` 只把阶段改成 `COMPLETED`，状态改成 `WorkflowStatus.COMPLETED`，`error` 置空，并记下 trace `complete`。

`WorkflowStatus.COMPLETED` 表示这一轮 LangGraph 执行结束。它不是政务事项办理成功，也不是事项已经确认。语义契约失败的测试确认：没有 `confirmed_business_id`，没有 terminal candidate，没有已接受的 slot。`SessionTurnSuccess` 本身也没有 `confirmed_business_id` 字段。

---

## 16. Repository DI / AgentState / Redis 边界

`SlotInteractionDependencies` 是冻结 dataclass。`business_repository: JsonBusinessRepository` 由调用方传入，放在带默认值的 `mapping_policy` 之前。节点只使用 `deps.business_repository`。它不 `new JsonBusinessRepository`，不 `load_snapshot`，也不打开 JSON。这样 Repository 的生命周期留在上层，测试可以传入同一个内存实例并数 `get_conditions` 次数。

semantic projection 只存在于这一次 `AnswerMappingRequest`。它不写入 `AgentState`。会话里继续保存的是图位置、已接受槽位和既有控制信息。因此 Redis checkpoint 不需要新 schema。也没有 PostgreSQL migration、新 cache 或新依赖。

日志在 `_log_semantic_projection`。调试投影时看这四项：`semantic_coverage`、`semantic_count`、`mapper_mode`、`reason_code`。`mapper_mode` 为 `ENRICHED`、`LEGACY` 或 `FAIL_CLOSED`。不要为了调试去打印 `user_text`、完整 Prompt、meaning 全文或 API key。

同一 `business_id` 的多条 ref 会各自调用一次内存 `get_conditions`。当前 Demo 规模不需要为此加 cache。生产代码里没有第二处自己构造 `SlotInteractionDependencies`，必填的 Repository 没有遗漏的生产构造点。这两条是 Review NOTE，不是待修缺陷。

---

## 17. 改造前后对比

| 项目 | 改造前 | 改造后 | 保持不变 |
|------|--------|--------|----------|
| Mapper 上下文 | 只有 raw machine value | raw machine value，`FULL` 时再加 controlled meanings | machine value 仍是返回契约 |
| Prompt | 三行 | `NONE` 仍是三行；`FULL` 多一行 JSON | system prompt 不变 |
| DataClassification | user：`USER_FREE_TEXT` + `SYSTEM_CONTROL_DATA` | `FULL` 的 user 再加 `PUBLIC_BUSINESS_METADATA` | `USER_FREE_TEXT` 仍在 |
| Business Data | F09 不读 | 通过已注入 Repository 的 PUBLIC conditions | 不直接打开 snapshot 文件 |
| threshold | `0.80` | `0.80` | 无加分、无地板 |
| membership | 本地对照 `allowed_values` | 同左 | confidence 不能绕过 |
| F04 | 仅 `ACCEPTED` 后确定性转移 | 同左 | LLM 无 `next_node` |
| F10 | 明确确认后才有 `confirmed_business_id` | 同左 | semantics 不能跳过 |
| F07 | 远程发送前必须评估 | 同左 | `DEFAULT` 仍拒绝用户原文 |

---

## 18. 文件职责图

业务流程到这里已经完整。下面只说明这次 Reopen 碰过的四个文件。

| 文件 | 为什么改 | 主要 symbol | 输入 | 输出 | 它不负责 |
|------|----------|-------------|------|------|----------|
| `business_data/semantics.py` | 把图上的合法值和公开 wording 对齐 | `project_allowed_value_semantics` | slot、allowed values、refs、Repository | `SemanticProjectionResult` | 不调用 LLM，不推进图，不打开 snapshot 文件 |
| `agent/interaction.py` | 让请求能携带 semantics，并保持本地校验 | `AnswerMappingRequest`、`LlmAnswerMapper`、`validate_slot_mapping` | 投影结果或 `None`，以及用户文本 | Prompt、分类、`ACCEPTED` 或拒绝 | 不查公开资格，不决定下一节点 |
| `agent/nodes.py` | 把解释、投影、映射、校验和失败编排起来 | `_interpret_slot_input`、`_semantic_contract_failure` | 状态、`deps` | `artifacts["f09"]` | 不自己创建 Repository |
| `agent/workflow.py` | 注入 Repository，并让契约失败结束本轮 | `SlotInteractionDependencies`、条件边 `semantic_contract_failure` | 依赖与初始状态 | 编译后的 F09 图 | 不实现投影算法 |

---

## 19. Symbol 阅读地图

推荐按这个顺序读代码。正文前面的业务链仍然是主线，这里只是第二次打开文件时的顺序。

1. `nodes._interpret_slot_input`：整段 F09 编排。
2. `project_allowed_value_semantics`：semantics 从哪里来。
3. `ControlledAllowedValueSemantic`、`SemanticCoverage`、`SemanticProjectionResult`：数据契约。
4. `AnswerMappingRequest`、`LlmAnswerMapper.map_answer`：Prompt 和分类。
5. `mapper_output_to_interpretation`、`validate_slot_mapping`：本地权限。
6. 回到 `nodes._route_by_validation` 和 `_advance_business_graph`：什么时候进入 F04。
7. `workflow` 的 `semantic_contract_failure` 边和 `_complete_node`：fail closed 如何结束本轮。

| Symbol | Module | Business Role | Input | Output | Who Calls It | Next Step |
|--------|--------|---------------|-------|--------|--------------|-----------|
| `_interpret_slot_input` | `agent/nodes.py` | 本轮槽位理解的编排 | 用户文本、slot context、deps | f09 artifact | F09 图 `interpret_slot_input` | 路由 |
| `detect_explanation_request` | `agent/interaction.py` | 先把问含义从选择里分开 | user text、question text | 解释 interpretation 或 `None` | `_interpret_slot_input` | 命中则旁路，否则投影 |
| `project_allowed_value_semantics` | `business_data/semantics.py` | 对齐合法值与公开 wording | Repository、slot、allowed values、refs | `SemanticProjectionResult` | `_interpret_slot_input` | FULL/NONE 去 Mapper，否则失败 |
| `ControlledAllowedValueSemantic` | `business_data/semantics.py` | 一个 machine value 加一条 meaning | value、meaning | 冻结对象 | 投影与请求 | 只进入 Prompt |
| `SemanticCoverage` | `business_data/semantics.py` | FULL/NONE/PARTIAL/INVALID | 投影结论 | 枚举 | 投影与节点 | 决定 Mapper 或 fail closed |
| `SemanticProjectionResult` | `business_data/semantics.py` | 覆盖结果和原因码 | coverage、semantics、reason | 冻结结果 | 投影 | 节点消费 |
| `AnswerMappingRequest` | `agent/interaction.py` | 一次映射请求 | slot、allowed values、用户文本、semantics 或 `None` | 校验后的请求 | 节点 | `map_answer` |
| `LlmAnswerMapper.map_answer` | `agent/interaction.py` | 组装 Prompt 并调用 Provider | `AnswerMappingRequest` | `AnswerMapperOutput` | 节点 | 转 interpretation |
| `AnswerMapperOutput` | `agent/interaction.py` | 模型输出上限 | kind、value、confidence | 冻结输出 | Provider 解析 | 本地转换 |
| `mapper_output_to_interpretation` | `agent/interaction.py` | 把模型输出变成本地解释 | `AnswerMapperOutput` | `UtteranceInterpretation` | 节点 | `validate_slot_mapping` |
| `validate_slot_mapping` | `agent/interaction.py` | membership 然后 confidence | interpretation、context、policy | `ACCEPTED` 或拒绝 | `_validate_slot_answer` | 只有接受才进 F04 |
| `advance_until_blocked` | `business_graph/transition.py` | F04 确定性转移 | 图、当前节点、已接受槽位 | `TransitionResult` | `_advance_business_graph` | 下一图状态 |
| `_complete_node` | `agent/nodes.py` | 结束这一轮编排 | 当前状态 | `COMPLETED` | `complete` 节点 | API 返回 |
| `SlotInteractionDependencies` | `agent/workflow.py` | 外部注入 Mapper、图和 Repository | 构造参数 | 冻结依赖 | `run_slot_interaction_workflow` | 各节点只读 `deps` |

---

## 20. Debugging Guide

日志优先看 `message=semantic_projection` 的四个字段。不要打印用户原文、完整 Prompt 或密钥。

**Case A：值选对了，confidence 太低**

看 `semantic_coverage` 是不是 `FULL`，`mapper_mode` 是不是 `ENRICHED`，request 里有没有三句 meaning，user 分类有没有 `PUBLIC_BUSINESS_METADATA`，以及 Provider 返回的 confidence。先确认语义有没有进请求。不要先把 `0.80` 改成 `0.70`。历史 Golden 的 `0.72` 属于改造前只有 raw enum 的路径。

**Case B：直接 fail closed**

看 `coverage` 和 `reason_code`。再核对 `source_condition_refs`、PUBLIC conditions、`field`、`normalized_values` 和 `source_text`。`PARTIAL` / `INVALID` 时期望 Mapper 次数为 0。

**Case C：询问含义被当成选择**

先看 `detect_explanation_request` 是否仍在投影之前，再看这句话是否属于现有确定性句式，以及 topic 是否出现在当前 `question_text`。“什么是……”和“什么叫……”都属于当前支持范围，不要再把“什么叫……”当成已知未支持句式。不匹配的问法会继续进入映射。含“叫”的普通陈述，例如“我叫张三”，不是解释请求。

**Case D：非法 value 被接受**

看 `validate_slot_mapping` 是否先做 `mapped_value not in context.allowed_values`。confidence 为 `1.0` 也不能通过这一步。

**Case E：事项好像被提前确认**

看是否只有 `ACCEPTED` 才调用 `advance_until_blocked`。再看 F10 的 `assign_confirmed_business_id`。F09 artifact 里出现受控槽位，不等于写入了 `confirmed_business_id`。

---

## 21. Golden Runtime Probe 阅读方法

以后用真实 Company LLM 复验“平时接零活，没有固定单位”时，按这个顺序观察。本文件不记录这次复验已经通过。

| 观察点 | 期望 |
|--------|------|
| pending slot | `employment_type` |
| coverage | `FULL` |
| semantic_count | `3` |
| mapper_mode | `ENRICHED` |
| user 分类 | `USER_FREE_TEXT`、`SYSTEM_CONTROL_DATA`、`PUBLIC_BUSINESS_METADATA` |
| policy | `DEMO_APPROVED` 下允许这一组合 |
| mapped_value | `other_flexible_employment` |
| membership | PASS |
| confidence | `>= 0.80` |
| validation | `ACCEPTED` |

不要把期望写成 confidence 必须等于 `0.80`。本地实现已经具备重新验证的条件，但新的 Production Golden probe 尚未执行。

---

## 22. 测试证据

测试用来对照行为，不是逐个函数清单。

| 文件 | 读它是为了看 |
|------|----------------|
| `tests/test_allowed_value_semantics.py` | projection：`FULL`、按 `allowed_values` 排序、`NONE` 不查库、`PARTIAL`、各类 `INVALID`、PUBLIC 过滤 |
| `tests/test_agent_interaction.py` | legacy / enriched Prompt、分类、`None` 与空 tuple、`0.80` / `0.79`、非法 value |
| `tests/test_agent_workflow.py` | 解释旁路、Repository 注入、`FULL` / `NONE` / `PARTIAL` / `INVALID`、F04 边界、`COMPLETED` 不等于确认 |

语义增强闭环时的证据是 projection 21 passed、interaction 69 passed、workflow 37 passed，全量 653 passed、13 skipped、0 failed、0 errors。`F09-CR-MAJOR-01` 修复后的当前证据是 interaction 77 passed、workflow 38 passed、F09 三组 136 passed，全量 662 passed、13 skipped、0 failed、0 errors、0 warnings。13 个 skip 仍来自既有外部环境开关。

---

## 23. Review Notes

Review 结论是 `PASS_WITH_NOTES`。下面两条不是待修 bug。

NOTE-1：同一个 `business_id` 可能因多条 ref 重复调用内存中的 `get_conditions`。Demo 规模不需要 cache 或批量接口。

NOTE-2：生产代码没有别的地方自己构造 `SlotInteractionDependencies`。`business_repository` 变为必填后，没有遗漏的生产构造点。

---

## 24. 当前状态与下一步

本地状态：Code、Test、Explanation 已通过。F09 Review 为 `PASS_WITH_NOTES`。`F09-CR-MAJOR-01` 为 `RESOLVED`。F09 Re-Review 为 `PASS_WITH_NOTES`。Documentation Sync 已完成本阶段。代码侧没有剩余 blocker。Commit 尚未执行。

全量测试：662 passed，13 skipped，0 failed，0 errors，0 warnings。

RG-F12-006 仍然是 `FAILED / LOW_CONFIDENCE`。那次失败对应的是旧的 raw-enum Production 路径。新的 semantic path 还没有用真实 Company LLM 重新验证。662 个本地测试，以及 MAJOR-01 已解决，都不能把它改成 READY。代码、测试和审查已经具备重新做 Production Golden 验证的条件，但新的真实 probe 尚未执行。

下一步是 Owner 审阅。只有 Owner 批准后才能 Commit。未获授权时不运行 RG-F12-006。
