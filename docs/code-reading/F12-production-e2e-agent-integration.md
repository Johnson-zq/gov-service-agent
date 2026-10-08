# F12 Production E2E Agent Integration 代码导读

F12 的目标不是新增一套业务判断，而是把已有的语义检索（F06）、确定性业务图与图推进（Decision Graph / F04）、槽位问答（F09）、终点确认（F10）和会话事务（F11），按各自已经冻结的权限接成第一条可上线的多轮办理链路。

项目里的分工可以记成一句话：语义检索找方向，业务图谱定事项，规则引擎做终审，知识图谱查办理信息，Agent 统一编排。F12 实际覆盖前三项里的“找方向、定事项、终审式确认”，以及 Agent 编排。知识图谱（Business Knowledge Graph）查材料、地点、渠道和依据，不在 F12。

## 1. F12 解决什么问题

F11 已经能接收 `POST /api/v1/session/turn`，并负责锁、请求幂等、检查点、审计和公开响应。F06、F09、F04、F10 也各自能完成检索、槽位理解、图推进和确认。缺的是一个生产用的办理编排器，把“这一句用户话该走哪条已有能力”定下来，并挂到正式应用入口。

F12 补上的就是三件事：

- `GovernmentAgentTurnProcessor`：本轮编排。
- `composition.py` 里的 `build_session_router`：把已有模块接上这个编排器。
- `main.py` 把会话路由挂进应用，健康检查保持原样。

读代码时先跟着一句话走，再落到函数。不要从文件清单开始。

一次请求的主干如下。F10 的确认准备（PREPARE）和下一轮确认裁决（RESOLVE）是分开的。

```text
用户输入
   |
   v
POST /api/v1/session/turn
   |
   v
SessionTurnService
   |
   v
idempotency / lock
   |
   v
checkpoint restore
   |
   v
GovernmentAgentTurnProcessor
   |
   v
turn mode
   |-- initial ------------------> F06 --> Decision Graph
   |-- pending slot -------------> F09 --> F04（仅接受后）
   |-- terminal confirmation ----> F10 RESOLVE
   |-- confirmed ----------------> short circuit
   |-- safe hold ----------------> 固定说明，不再检索
   |
   v
若本轮图结果是终点候选：F10 PREPARE（同一句用户话，尚未确认）
   |
   v
AgentTurnResult
   |
   v
SessionTurnService 校验
   |
   v
checkpoint / audit
   |
   v
API response

下一句用户话若是明确确认：
restore --> 新一轮生命周期 --> F10 RESOLVE --> confirmed_business_id
```

## 2. 一次请求从哪里进入

### 业务场景

用户提交这一轮想说的话。新对话可以不带会话编号；已经开始的对话必须带上，系统才知道接哪一份检查点。

### 代码入口

- `src/gov_service_agent/session/api.py`：`create_session_router`
- 路由：`POST /api/v1/session/turn`
- 请求模型：`SessionTurnRequest`
- 成功模型：`SessionTurnSuccess`
- 真正办事：`SessionTurnService.handle_turn`

### 输入

- `request_id`：这一次 HTTP 请求的身份，给幂等用。
- `session_id`：可选。一段连续对话的身份。没有它就是新会话。
- `input_text`：这一轮的原话。

### 输出

公开成功响应只有会话编号、请求编号、状态、回复文本，以及是否还要用户继续输入。接口本身不返回事项编号。

### 权限边界

接口可以校验请求形状并把调用交给会话服务。它不能做检索、槽位映射、图推进或事项确认。

### 下一步

`SessionTurnService.handle_turn`。

### 对应测试

`tests/test_f12_app_activation.py` 的 `test_main_registers_session_route_and_preserves_health`，以及 `test_composition_uses_production_processor_without_eager_io` 对请求/成功字段集合的断言。

## 3. F11 如何恢复会话

### 业务场景

同一段对话的第二句及以后，必须先知道上次停在哪一问、已经填了哪些槽、有没有待确认的候选。这些不能让客户端再提交一遍当作权威。

### 代码入口

- `src/gov_service_agent/session/service.py`：`SessionTurnService.handle_turn`
- 状态转换：`src/gov_service_agent/agent/state.py` 的 `to_persisted` / `from_persisted`
- 编排器接手：`GovernmentAgentTurnProcessor.process_turn`

### 输入

会话服务先看请求是不是同一次重放，并持有会话锁。需要继续办理时，从检查点取出已保存状态，再把本轮 `request_id`、`input_text` 和恢复结果交给编排器。

### 输出

新会话的 `restored_state` 是空。老会话得到恢复后的办理状态。编排器返回 `AgentTurnResult` 之后，成功与否仍由会话服务决定要不要提交。

### 权限边界

F11 拥有锁、幂等、检查点读取、成功提交、失败时不成功提交、审计和公开响应。F12 编排器不写 Redis，不自己提交检查点，也不实现分布式锁。F11 是会话事务边界。

### 下一步

`process_turn`。若是重放，会话服务直接交回上次结果，编排器不会再跑。

### 对应测试

`tests/test_f12_session_integration.py`：

- `test_new_session_commits_first_pending_question`
- `test_resume_advances_pending_slot_without_second_retrieval`
- `test_idempotent_replay_does_not_double_advance`

### 检查点里实际有什么

当前持久化字段是 `phase`、`status`、`artifacts`、`error`。业务材料在 `artifacts` 里，所以槽位、图转移、候选和已确认事项能跨轮留下来。

`input_text`、`request_id` 和 `orchestration_trace` 不是这份持久化字段。上一轮原话和那一次流程的执行轨迹，不能当成下一句用户话的身份。这就是后面跨轮生命周期修复要单独重置的原因。

## 4. Processor 如何决定本轮做什么

### 业务场景

用户每一句话的含义不同：第一次来、在回答槽位、在确认事项，或事项已经确认。编排器先分类，再调用对应的已有模块。

### 代码入口

`src/gov_service_agent/agent/turn_processor.py`

- 类：`GovernmentAgentTurnProcessor`
- `process_turn`
- 新用户轮的工作副本：`_copy_working_state`
- 模式：`_determine_turn_mode`

`process_turn` 在没有恢复状态时调用 `create_initial_state`。有恢复状态时调用 `_copy_working_state`，再用 `_determine_turn_mode` 分支。

### 输入

本轮请求编号、原话，以及可选的恢复状态。会话编号在这里被明确忽略，因为办理状态模型没有会话字段，会话身份留在 F11。

### 输出

五种模式之一，见下表。数字小的先判断。

| 优先级 | 状态 | Processor 行为 |
| --- | --- | --- |
| 1 | `confirmed_business_id` 已有非空值 | `_handle_already_confirmed`：直接完成，不再检索、追问或确认 |
| 2 | 有未确认的终点上下文，且确认状态属于等待、不确定、拒绝或阻塞 | `_handle_terminal_confirmation`：只做 F10 RESOLVE |
| 3 | 最新图状态仍是缺槽位，或槽位上下文仍是缺槽位 | `_handle_slot_interaction`：进入 F09 |
| 4 | 最新图转移是回退或暂不支持 | `_handle_safe_hold`：返回受控说明 |
| 5 | 没有任何图上下文 | `_handle_initial_routing`：才允许 F06 |

确认优先于残留槽位，是因为确认准备之后，`f09` 里可能还留着进入终点之前的 `slot_context`。若先看槽位，用户说“确认”会被当成在回答就业类型。`_has_pending_slot` 看到终点、回退或暂不支持的转移时，不再把旧槽位当成待答。

### 权限边界

编排器只选择调用哪条已有路径。它不发明允许值，不第二次推进图，也不自己写出已确认事项。

### 下一步

对应的 `_handle_*`。

### 对应测试

- `test_terminal_confirmation_outranks_stale_slot_context`
- `test_confirmed_state_short_circuits_all_processing`
- `test_restored_state_is_not_mutated`

## 5. 新会话为什么只在开始做 F06

### 业务场景

第一句“我辞职了，现在没单位，想自己交社保”还没有图上下文。系统需要一个方向，才能决定打开哪张办事路径。方向一旦进图，后面回答“缴费”“自己缴”只是在补条件，不应该每轮重新猜方向。

### 代码入口

`GovernmentAgentTurnProcessor._handle_initial_routing`

检索：`SemanticRetrievalService.retrieve`

图上核对：`_first_graph_matched_candidate`

### 输入

本轮 `input_text`。检索服务返回候选列表和状态。

### 输出

能对上图的第一个候选，只记进 `artifacts["f12"]` 的方向元数据。然后从业务图入口继续。对不上，或检索没有可用候选，就返回固定澄清，不创建图状态。

### 权限边界

F06 可以回答“可能是哪一类方向”。它不能写入 `candidate_business_id` 或 `confirmed_business_id`。方向编号 `matched_business_id` 存在 `f12` 里，后续模式判断不读它。

### 下一步

匹配成功则 `advance_until_blocked`。失败则把澄清文案交回 `AgentTurnResult`。

### 对应测试

- `test_initial_routing_enters_graph_but_does_not_confirm`
- `test_unmatched_candidate_does_not_enter_graph`
- `test_pending_slot_reuses_f09_and_advances_one_graph_step`（第二轮检索次数仍为 1）

检索状态在当前实现里的处理：

| Retrieval 状态 | 行为 |
| --- | --- |
| CANDIDATES | 尝试匹配 Decision Graph 上的终点事项编号 |
| NO_USABLE_CANDIDATE | 受控澄清，不进图 |
| INVALID_QUERY | 受控澄清，不进图 |
| NOT_READY | `RuntimeError`，失败向上传播 |
| UNAVAILABLE | `RuntimeError`，失败向上传播 |
| 其它未列出的状态 | `RuntimeError`，不当成成功 |

澄清原文是“暂时无法确定您要办理的业务方向，请补充说明后重试。”

## 6. Decision Graph 如何确定下一问

### 业务场景

方向已经可用，但还没收集办理条件。下一问必须来自预先画好的边，而不是模型现编。

### 代码入口

- 初次进入：`_handle_initial_routing` 调用 `advance_until_blocked`
- 实现：`src/gov_service_agent/business_graph/transition.py` 的 `advance_until_blocked`
- 初次结果写入材料：`_project_initial_transition`

### 输入

入口节点 `entry_node_id`、当前槽位（第一轮是空字典）、图上的预定义边。

### 输出

真实转移状态包括缺槽位（`NEED_SLOT`）、非法槽位（`INVALID_SLOT`）、终点候选（`TERMINAL_CANDIDATE`）、回退（`FALLBACK`）、暂不支持（`UNSUPPORTED`）。Golden 第一轮停在 `service_action`，回复是图上的问句，`requires_user_input` 为真。这一轮的 F06 到此结束。

### 权限边界

下一节点只能由确定性图决定。模型不参与这次调用。

### 下一步

缺槽位就把问句返回用户。若第一轮直接走到终点，才会进入确认准备。Golden 社保图不会在空槽位上直接到终点。

### 对应测试

`test_initial_routing_enters_graph_but_does_not_confirm`：`required_slot` 为 `service_action`，没有 `f10`，映射器调用次数为 0。

## 7. F09 如何处理槽位回答、解释和低置信

### 业务场景

图停住以后，用户下一句可能是在回答，也可能是在问“这个词什么意思”，或者说得不够明确。

### 代码入口

- 编排器：`_handle_slot_interaction`、`_resolve_slot_context`、`_result_from_f09`
- 槽位流程：`run_slot_interaction_workflow`（`src/gov_service_agent/agent/workflow.py`）
- 映射与解释类型：`src/gov_service_agent/agent/interaction.py`

### 输入

当前槽位上下文（节点、要填的槽、允许值、问句、已有槽位）和本轮原话。

### 输出

F09 把这句话分成槽位回答（`SLOT_ANSWER`）、解释请求（`EXPLANATION_REQUEST`）、不确定（`UNCERTAIN`）或其它（`OTHER`）。槽位回答还会带允许值映射和置信度。编排器只在返回的 `business_transition` 确实是一次推进结果时，才按缺槽位、终点、回退或暂不支持往下走。没有这个字段时，它使用 F09 已写好的 `response_text`，并继续等待用户。

### 权限边界

模型可以做自然语言理解、把原话映射到允许值、给出置信度、生成解释措辞。模型不能决定下一节点、事项编号或已确认事项。0.80 这个接受阈值属于 F09 既有策略，编排器不改它，也不补一个置信度。

### 下一步

接受且图继续缺槽位：更新槽位上下文并追问。接受且到达终点：进入第 10 节的确认准备。解释、低置信、不确定：停在原问题。

### 对应测试

- `test_pending_slot_reuses_f09_and_advances_one_graph_step`
- `test_explanation_side_route_keeps_pending_employment_type`
- `test_low_confidence_does_not_advance_graph`

### 受控映射例子

`employment_type` 的允许值包括 `self_employed_without_employees`、`part_time_without_employer_insurance`、`other_flexible_employment`。用户说“无雇工的个体工商户”时，Golden 路径把它映射成 `self_employed_without_employees`，且置信度达到接受线。这是明确的正向例子。

“平时接零活，没有固定单位”不是这条正向例子。冻结合同不要求模型把它确定成某一个允许值。它可以是不确定，也可以给出映射但置信度低于 0.80。两种结果都不推进图。安全停住优先于强行命中。

### 置信度门

阈值是 0.80。若映射值是 `other_flexible_employment`、置信度是 0.75，校验状态为 `low_confidence`。槽位不写入，F04 不执行，不产生候选，确认流程不开始，当前问题仍是 `employment_type`。映射值可以留在解释记录里，但不是已接受事实。

### 解释旁路

“什么叫灵活就业？”是解释请求，不是在选择就业类型。解释服务可以说明这个词。已校验槽位不变，F04 不跑，候选和已确认事项都不变，原来的就业类型问题还在。用户看完解释后，系统仍在等这个槽位。

### `business_transition` 只在真正推进后存在

`business_transition` 是 ADVANCE_ONLY 材料：只有 F04 真的执行并留下转移结果时才有。解释、低置信和不确定都可以是 `None`。这时要读 `slot_context`（还停在哪一问）、`interpretation`（这句话被看成什么）和 `mapping_validation`（接受还是低置信）。不要因为缺少 `business_transition` 就判断当前问题丢了。

## 8. F04 如何确定性推进

### 业务场景

用户的回答已经被接受，图才应该往下走一格。走两次就会跳过下一问。

### 代码入口

- 第一次、也是进入图的那一次：编排器在 `_handle_initial_routing` 直接调用 `advance_until_blocked`
- 之后每一次接受的槽位：F09 的 `run_slot_interaction_workflow` 内部推进
- 编排器侧不再调用第二次：`_handle_slot_interaction` 只调用槽位流程

### 输入

当前节点、已经接受的槽位、预定义边。

### 输出

下一种受控转移：继续追问、到达终点、回退或暂不支持。

### 权限边界

F04 不调用模型选择下一节点。编排器在槽位轮里若再推一次，同一次回答会前进两步，例如从 `service_action` 直接跨过 `payment_actor`。所以槽位轮的推进权只在 F09 的接受路径里。

### 下一步

`_result_from_f09` 读取这一次转移。缺槽位就追问；终点就准备确认；回退或暂不支持就安全停住。

### 对应测试

`test_pending_slot_reuses_f09_and_advances_one_graph_step`：F04 计数为 1，当前节点变为 `payment_actor`。

## 9. 什么时候出现 terminal candidate

### 业务场景

必填条件已经齐了。图认为当前路径对应一个具体事项，但用户还没有点头。

### 代码入口

- 转移状态 `TERMINAL_CANDIDATE`
- `_result_from_f09` 或初次路由在看到该状态时调用 `_prepare_terminal`
- 候选上下文：`build_terminal_candidate_context`

### 输入

F04 的 `TransitionResult`。其中的候选事项来自图节点，不来自检索列表，也不来自模型自由生成的编号。

### 输出

`candidate_business_id`。在 Golden 里这是 `DEMO_SS_001`。此时还没有 `confirmed_business_id`。

### 权限边界

`TerminalCandidateContext` 只能由 `build_terminal_candidate_context(transition)` 从转移结果构建。`f12` 里的 `matched_business_id` 不能喂进去当最终事项。F09 的映射值是槽位值，不是事项编号。

三个编号不要混：

| 字段 | 来源 | 含义 | 是否最终事项 |
| --- | --- | --- | --- |
| `matched_business_id` | 初次检索里对上图的候选，写在 `f12` | 方向能进入这张图 | 否 |
| `candidate_business_id` | F04 终点转移，再进入 F10 | 按已答条件，很可能是这个事项 | 否 |
| `confirmed_business_id` | 下一轮 F10 明确确认 | 用户已经确认 | 是 |

`matched` 不等于 `candidate`，`candidate` 也不等于 `confirmed`。

### 下一步

同一轮进入 F10 PREPARE。

### 对应测试

`test_golden_flow_prepares_then_confirms_on_a_later_turn` 的第 4 轮断言。

## 10. F10 为什么必须分 PREPARE / RESOLVE 两轮

产生候选的那句话，是在回答最后一个槽位。它不能同时被解释成“我确认这个事项”。

```text
槽位回答
   |
   v
F09 接受
   |
   v
F04 到达 TERMINAL_CANDIDATE
   |
   v
Lifecycle Fix #2：同一轮重新打开流程
   |
   v
F10 PREPARE：保存候选，提出确认问题
   |
   v
本轮返回。confirmed_business_id 仍为空

下一句用户话
   |
   v
恢复检查点 + Lifecycle Fix #1
   |
   v
F10 RESOLVE
   |
   v
只有明确确认才写入 confirmed_business_id
```

### 业务场景

第 4 轮用户说的是就业类型。系统应反问是不是要办理该事项。第 5 轮用户另说“确认”，才允许落定。

### 代码入口

- 准备：`_prepare_terminal` → `_rearm_same_turn_workflow` → `prepare_terminal_confirmation`
- 裁决：下一轮 `_handle_terminal_confirmation` → `resolve_terminal_confirmation`
- 实现位于 `src/gov_service_agent/agent/terminal.py` 与 `workflow.py`

### 输入

准备阶段的输入是终点转移结果。裁决阶段的输入是已保存的终点上下文，加上新的一句原话。

### 输出

准备阶段：`f10.mode` 为 `prepare`，候选是 `DEMO_SS_001`，`confirmed_business_id` 为 `None`，确认状态为等待确认。裁决阶段若用户明确确认：`mode` 为 `resolve`，已确认事项等于候选事项。拒绝或不确定只改变确认状态，不写已确认事项。

### 权限边界

最终确认权只在 F10。检索、槽位模型、图推进和编排器都不能在候选出现时直接确认。

### 下一步

准备结束后，本轮 `AgentTurnResult` 仍表示还要用户输入。裁决成功后，公开状态才是完成且不再要输入。

### 对应测试

- `test_golden_flow_prepares_then_confirms_on_a_later_turn`
- `test_rejection_keeps_candidate_and_does_not_retrieve_again`
- `test_uncertain_confirmation_keeps_waiting`

## 11. confirmed_business_id 之后发生什么

### 业务场景

事项已经确认。用户再发一句别的话，不应重新检索、重新填槽或再次确认。

### 代码入口

`_determine_turn_mode` 的第一优先级，以及 `_handle_already_confirmed`。

### 输入

`f10` 中非空的 `confirmed_business_id`，以及已有回复文本。

### 输出

公开状态为完成，`requires_user_input` 为假。检索、映射和 `resolve_terminal_confirmation` 都不再调用。

### 权限边界

这是 F12 的终点。材料、地点、渠道和依据不在这里查询。

### 下一步

`AgentTurnResult` 交回会话服务。之后的用户轮仍走同一短路，直到这段会话结束。同一会话里改办另一件事，当前没有实现。

### 对应测试

`test_confirmed_state_short_circuits_all_processing`。

## 12. Session 如何保存 checkpoint 与返回 API

### 业务场景

编排器认为这一轮有了可返回的结果。要不要把它写成下一轮能恢复的事实，由会话服务决定。

### 代码入口

- 编排器出口：`_awaiting_or_completed`，内部用 `_as_completed` 把本轮成功状态收成完成
- 会话服务：`SessionTurnService` 校验 `AgentTurnResult` 后 `commit_successful_turn`
- 公开响应由会话服务组装，不是编排器组装

### 输入

`AgentTurnResult` 的 `state`、`response_text`、`requires_user_input`、`public_status`。

### 输出

成功时写入检查点并发出 `SessionTurnSuccess`。编排器抛错时，会话服务记录失败，不把这一轮写成成功检查点；若上一份成功检查点还在，保持不动。

### 权限边界

编排器不构造 `SessionTurnSuccess`，不写审计表，不把异常收成成功。完成态和“还要不要用户输入”必须一致，否则会话服务拒绝提交。

### 下一步

客户端只看到公开字段。下一句再从第 3 节恢复。

### 对应测试

- `test_unavailable_retrieval_does_not_commit_success`
- `test_failed_follow_up_preserves_prior_checkpoint`
- `test_mapper_exception_propagates_without_success_result`

## 13. Golden 5-turn：从“自己交社保”到最终确认

贯穿例子不要换成“平时接零活，没有固定单位”。那句属于第 7 节的模糊安全例子。

| 轮次 | 用户输入 | 模式 | 调用 | 槽位变化 | 图状态 | 候选 | 已确认 | 回复目的 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 我辞职了，现在没单位，想自己交社保 | 初次路由 | F06 一次，再从入口推进 | 无已填槽 | 停在 `service_action` | 无 | 无 | 询问办理动作 |
| 2 | 明确的缴费回答，受控值 `payment` | 槽位 | F09 接受，F04 一次 | 写入 `service_action=payment` | 停在 `payment_actor` | 无 | 无 | 询问单位缴还是自己缴 |
| 3 | 明确的自己缴，受控值 `self_payment` | 槽位 | F09 接受，F04 一次 | 再加上 `payment_actor` | 停在 `employment_type` | 无 | 无 | 询问就业类型 |
| 4 | 无雇工的个体工商户 | 槽位，随后同一轮准备确认 | 映射为 `self_employed_without_employees` 并接受；F04 到终点；Fix #2；F10 PREPARE | 就业类型被接受 | `TERMINAL_CANDIDATE` | `DEMO_SS_001` | `None` | 请用户确认事项名称 |
| 5 | 确认 | 终点确认 | 新请求；恢复；Fix #1；F10 RESOLVE | 不再改槽 | 不再推图 | 仍是 `DEMO_SS_001` | `DEMO_SS_001` | 告知事项已确认 |

第 4 轮的顺序不能省略：F09 接受，F04 得到 `DEMO_SS_001`，然后 Lifecycle Fix #2，然后 F10 PREPARE。准备结束后候选是 `DEMO_SS_001`，已确认事项仍是 `None`。

第 5 轮是新的 `request_id` 和新的原文。检查点恢复候选，Lifecycle Fix #1 把本轮设回“刚收到、正在处理”，模式直接进入 F10 RESOLVE。最终 `confirmed_business_id` 才是 `DEMO_SS_001`。

## 14. Lifecycle Fix #1：跨用户轮恢复

### 原问题

上一轮成功结束时，持久化下来的是“已完成 / 已完成”（`COMPLETED` / `COMPLETED`）。下一句如果带着这对状态进入 F09，准备节点只把阶段改成“编排中”（`ORCHESTRATING`），完成状态仍是已完成。

### 为什么会错

“编排中 / 已完成”不是合法的办理状态组合，槽位流程会在校验时失败。根因不是 F09 写错，而是把上一轮的结束状态当成了下一轮的开始状态。

### 最终修复

`_copy_working_state` 调用 `create_initial_state`：

- 保留恢复来的 `artifacts`（函数内部会深拷贝，不改调用方的原对象）
- 使用本轮新的 `request_id` 和 `input_text`
- 设为“刚收到 / 正在处理”（`RECEIVED` / `RUNNING`）
- `error` 为 `None`
- `orchestration_trace` 为 `[]`

### 为什么不是修改上一轮完成态

上一轮成功本来就应该是“已完成 / 已完成”。修复只发生在新的一句用户话进入编排器时。F09 的状态规则没有放宽。

### 测试

- `test_pending_slot_reuses_f09_and_advances_one_graph_step`
- `test_resume_advances_pending_slot_without_second_retrieval`
- `test_restored_state_is_not_mutated`

## 15. Lifecycle Fix #2：同一轮 F09 → F10

### 原问题

第 4 轮里，F09 正常结束时已经是“已完成 / 已完成”。同一句用户话还要立刻做 F10 PREPARE。

### 错误组合

确认准备同样只改阶段、不改完成状态，于是再次出现“编排中 / 已完成”。

### 修复

`_prepare_terminal` 在调用 `prepare_terminal_confirmation` 之前执行 `_rearm_same_turn_workflow`。它仍调用 `create_initial_state`，但是：

- `request_id` 保持这一轮的
- `input_text` 保持这一轮的
- 业务 `artifacts` 保留
- 生命周期重新成为“刚收到 / 正在处理”
- `error` 为 `None`
- `trace` 为 `[]`

这不是新的用户轮，所以不会在这一轮调用 RESOLVE。

### 为什么 trace reset

`orchestration_trace` 是一次编译好的流程内部的执行记录。F09 和 F10 是两次独立流程。F11 的检查点本来也不保存 trace。把 F09 的轨迹带进 F10 的入口没有意义，也会和“轨迹属于当前这次流程”冲突。

### 测试

`test_golden_flow_prepares_then_confirms_on_a_later_turn` 的第 4 轮：准备成功，候选为 `DEMO_SS_001`，已确认为空。

两次修复都把生命周期设回起点，但身份语义不同：

| 对比 | Fix #1 | Fix #2 |
| --- | --- | --- |
| 边界 | 新的一句用户话 | 同一句里的下一个子流程 |
| `request_id` | 新的 | 保持 |
| `input_text` | 新的 | 保持 |
| artifacts | 保留 | 保留 |
| phase / status | RECEIVED / RUNNING | RECEIVED / RUNNING |
| trace | 清空 | 清空 |
| 下一步 | 按模式进入 F09 或 F10 RESOLVE 等 | 只进入 F10 PREPARE |

## 16. 关键 artifacts 地图

| Artifact | Owner | 作用 | 是否业务真相 |
| --- | --- | --- | --- |
| `f09` | F09，编排器只在初次进图时放入第一份转移 | 槽位上下文、这句话的解释、校验、已接受槽、回复 | 是槽位与图推进真相的容器 |
| `slot_context` | F09；推进后编排器会把它对齐到最新追问 | 当前问题、当前节点、已填槽位 | 是。未推进时尤其要读它 |
| `business_transition` | 只有 F04 推进后写入 | 最近一次确定性转移 | 是转移结果；未推进时可以没有 |
| `f10` | F10 | 终点上下文、确认状态、候选、已确认事项 | 是确认阶段的真相 |
| `f12` | 编排器初次路由 | `matched_business_id`、名次、方向、资格范围 | 否。只是方向元数据，控制流不读它 |

## 17. 权限边界：谁能决定什么

| 模块 | 可以做什么 | 不能做什么 |
| --- | --- | --- |
| F06 `SemanticRetrievalService.retrieve` | 给出方向候选 | 写候选事项或已确认事项；不能每轮重跑 |
| F09 `run_slot_interaction_workflow` | 区分回答、解释、不确定和其它；映射允许值；给出置信度；写解释 | 决定下一节点或事项编号；低于 0.80 不得当接受 |
| F04 `advance_until_blocked` | 按当前节点、已接受槽位和预定义边得到下一步 | 调用模型选路 |
| F10 `prepare_terminal_confirmation` / `resolve_terminal_confirmation` | 保存候选并提问；下一轮根据明确确认写入已确认事项 | 把检索编号或槽位映射直接当成事项 |
| F11 `SessionTurnService` | 锁、幂等、恢复、成功提交、失败不提交、审计、公开响应 | 改写槽位规则或图规则 |
| `GovernmentAgentTurnProcessor` | 选择本轮路径，并在进图时调用一次 F04 | 直接调用模型；槽位轮再推一次图；自己写确认；写 Redis |

编排器源码里没有 `provider.complete` 或聊天补全调用。模型只出现在组合根注入的 `LlmAnswerMapper` 和 `LlmExplanationService` 中，并受 F09 权限约束。

## 18. Session / Checkpoint / Idempotency / Audit

会话服务包在编排器外面。同一会话的并发请求先拿到锁，避免两句同时改检查点。相同会话、相同 `request_id`、相同原文再次到达时，F11 交回已缓存的公开结果，业务不会再推进。

重放例子：第一次把 `service_action` 推进到 `payment_actor`。同一次请求重放后，检查点仍停在 `payment_actor`，不会再进到 `employment_type`。编排器不需要再实现一套幂等。

失败例子：检索不可用时成功提交次数为 0。已有检查点后，后续映射失败不会覆盖那一份，修订号也不增加。审计事件仍由会话层记录；编排器不保存原话、模型私有回复或密钥。

对应测试：`test_idempotent_replay_does_not_double_advance`、`test_unavailable_retrieval_does_not_commit_success`、`test_failed_follow_up_preserves_prior_checkpoint`。

## 19. Fail-Closed：系统什么时候选择“不猜”

| 情况 | 当前行为 | 为什么不能伪造事项 |
| --- | --- | --- |
| `NO_USABLE_CANDIDATE` | 固定澄清 | 没有可用方向 |
| `INVALID_QUERY` | 固定澄清 | 问题本身不能检索 |
| `NOT_READY` | 异常向上传播 | 检索未就绪不是“办成了” |
| `UNAVAILABLE` | 异常向上传播 | 依赖不可用不是业务结论 |
| 映射器异常 | 编排器继续抛出 | 没理解成功就不能推进 |
| `low_confidence` | 保持原槽位 | 0.75 低于 0.80，猜测不是事实 |
| `EXPLANATION_REQUEST` | 解释后仍问原问题 | 提问不是选择 |
| `FALLBACK` / `UNSUPPORTED` | 受控停住，不再检索 | 图已经给出不可继续的确定结果 |
| 非法生命周期 | 状态校验失败 | 不能靠吞掉异常假装流程合法 |
| 不在图上的检索编号 | 澄清且 `artifacts` 为空 | 检索不是业务图 |

安全停住的默认说明是“当前办理路径暂时无法继续，请换一种需求说明或开启新的会话。”暂不支持若转移结果自带原因，则使用该原因。

## 20. Composition：这些模块是怎么接起来的

业务路径确定之后再看接线。`src/gov_service_agent/composition.py` 的 `build_session_router` 只组装对象：

1. 用文件位置定位仓库根，加载 `data/graphs/demo/social_security.json`。
2. 用 `JsonBusinessRepository` 加载 `data/demo/demo_ss_001.json`。
3. `build_llm_provider` 按现有配置构造提供者，再包成 `LlmAnswerMapper` 和 `LlmExplanationService`。
4. 这两个对象进入 `SlotInteractionDependencies`，事项库进入 `TerminalConfirmationDependencies`。
5. `SemanticRetrievalService` 与上述依赖一起交给 `GovernmentAgentTurnProcessor`。
6. 用现有 Redis 配置构造客户端和 `RedisSessionStore`，再交给 `SessionTurnService`。
7. `create_session_router` 返回可挂载路由。

这里没有槽位判断、图转移或确认判断。路径来自 `Path(__file__).resolve().parents[2]`，不依赖启动时的 shell 当前目录。

构造应用不等于访问外部系统。`Redis()` 只创建客户端。检索服务的构造函数不加载向量模型。模型提供者的构造函数不发 HTTP。真正的检索、模型补全和 Redis 命令发生在对应业务调用时。因此导入应用和 `GET /health` 可以保持轻量。

`src/gov_service_agent/main.py` 只增加了导入 `build_session_router`，并 `app.include_router(...)`。`health` 仍返回 `{"status": "ok"}`。`main.py` 里没有办理分支。

审查备注 F12-RV-001：编排器构造时保存了 `_business_repository`，自身方法没有读取。事项库已经交给 F09/F10 的依赖使用。严重级别是 NOTE，当前不需要为它改代码。

## 21. 对外 API 为什么没有暴露内部状态

请求保持 `request_id`、`session_id`、`input_text`。成功响应保持 `session_id`、`request_id`、`status`、`response_text`、`requires_user_input`。

不暴露 `candidate_business_id`、`confirmed_business_id`、执行轨迹、置信度和图节点。这些是服务端检查点里的办理事实。若客户端回传它们并被当成权威，就会绕过图和确认。用户能看见的是回复文本，以及还要不要继续回答。

## 22. 测试应该怎么跟着业务风险看

| 业务风险 | 测试证据 |
| --- | --- |
| 初次进图但不确认 | `test_initial_routing_enters_graph_but_does_not_confirm` |
| 检索不能当最终事项；不在图上的候选被拒绝 | `test_unmatched_candidate_does_not_enter_graph` |
| 无候选 / 无效问题只澄清；未就绪 / 不可用则失败 | `test_non_candidate_retrieval_returns_clarification_without_graph`、`test_required_retrieval_failure_propagates` |
| 待答槽位走 F09 且只推进一次 | `test_pending_slot_reuses_f09_and_advances_one_graph_step` |
| 解释不推进 | `test_explanation_side_route_keeps_pending_employment_type` |
| 低置信不推进 | `test_low_confidence_does_not_advance_graph` |
| 跨轮生命周期（Fix #1） | 上一项槽位测试，加上 `test_resume_advances_pending_slot_without_second_retrieval` |
| 同一轮 F09 到 F10（Fix #2）和两轮确认 | `test_golden_flow_prepares_then_confirms_on_a_later_turn` |
| 确认优先于旧槽位；拒绝；不确定 | `test_terminal_confirmation_outranks_stale_slot_context`、`test_rejection_keeps_candidate_and_does_not_retrieve_again`、`test_uncertain_confirmation_keeps_waiting` |
| 已确认后短路 | `test_confirmed_state_short_circuits_all_processing` |
| 回退 / 暂不支持不再检索 | `test_fallback_and_unsupported_stay_without_retrieval` |
| 检查点、幂等、失败不提交 | `tests/test_f12_session_integration.py` 中五个测试 |
| 生产接线、无提前 IO、公开路由和健康检查 | `tests/test_f12_app_activation.py` 两个测试 |
| 三个文件一起跑没有互相污染 | 组合运行 25 项 |
| 旧模块回归 | 安全集合 312 项通过；真实 Redis 节点被排除 |

文件都在 `tests/` 下，编排器文件是 `test_f12_turn_processor.py`。最终证据是编排器 18/18、会话 5/5、激活 2/2、组合 25/25、相关回归 312 通过。默认的全量 `pytest` 没有跑，因为会执行真实 Redis 和其它外部集成。这是资源边界，不是测试失败。

## 23. F12 开发中发现过什么问题

跨轮生命周期（Production Defect #1）：下一句带着上一轮的“已完成 / 已完成”进入槽位流程。根因是结束状态被当成开始状态。处理是 `_copy_working_state`，并有编排器与会话恢复回归。

同一轮交接（Production Defect #2）：槽位流程结束后立刻确认准备，再次形成非法状态。根因是两个子流程共用了结束状态。处理是 `_rearm_same_turn_workflow`，由 Golden 第 4 轮证明。

解释测试（Test Authoring Defect #1）和低置信测试（Test Authoring Defect #2）：测试去读取并不存在的 `business_transition`。根因是把“只有推进才有的字段”当成每轮必有。测试改为读取 `slot_context`、解释种类和校验状态。

激活路由测试（Test Authoring Defect #3）：测试假设挂载路由在顶层被拆成带 `path` 和 `methods` 的扁平对象。根因是绑定了框架内部容器形状。测试改为断言公开 OpenAPI 里存在 `/api/v1/session/turn` 的 `post`，并仍用本地 GET 检查健康检查。

## 24. F12 明确没有实现什么

以下都还没有：

- 业务知识图谱（Business Knowledge Graph），以及材料、地点、办理渠道、法律依据查询
- 导航图
- 语音识别
- 前端页面
- 自动填表或 RPA
- 同一会话内改办另一个事项

用户要办另一件事，当前设计是开启新会话，或等后续能力。不要把“已经能确认事项编号”理解成“已经能办完整个政务事项”。

## 25. 推荐阅读代码顺序

按办事过程读，不要按 Git 差异读。

1. `src/gov_service_agent/session/api.py` 的 `create_session_router`。搞懂请求从哪个 URL 进来，公开模型有哪些字段。
2. `src/gov_service_agent/session/service.py` 的 `SessionTurnService.handle_turn`。搞懂锁、幂等、恢复和成功提交为什么包在编排器外面。
3. `src/gov_service_agent/agent/state.py` 的 `create_initial_state`、`to_persisted`、`from_persisted`。搞懂哪些字段能跨轮，合法生命周期是什么。
4. `GovernmentAgentTurnProcessor.process_turn`。搞懂一句用户话进入编排器后的总入口。
5. `_determine_turn_mode` 和 `_has_pending_slot`。搞懂为什么不是每轮检索，以及确认为什么压过旧槽位。
6. `_handle_initial_routing`。搞懂 F06 加一次图入口。
7. `run_slot_interaction_workflow`。搞懂回答、解释和低置信。
8. `advance_until_blocked`。搞懂下一问从哪来。
9. `build_terminal_candidate_context`、`prepare_terminal_confirmation`、`resolve_terminal_confirmation`。搞懂准备和裁决。
10. `_copy_working_state`。搞懂 Fix #1。
11. `_rearm_same_turn_workflow`。搞懂 Fix #2，并对比上一项的请求身份。
12. `build_session_router`。搞懂依赖如何接上，而不是业务规则写在哪里。
13. `main.py` 的 `include_router` 和 `health`。搞懂上线入口只有挂载。
14. 三个 `tests/test_f12_*.py`。按第 22 节的风险回看断言，而不是从第一行测试读到最后一行。

## 26. 关键函数索引

| 函数/类 | 文件 | 一句话职责 |
| --- | --- | --- |
| `SessionTurnService` | `src/gov_service_agent/session/service.py` | 会话事务：锁、幂等、恢复、提交、审计、公开响应 |
| `create_session_router` | `src/gov_service_agent/session/api.py` | 注册 `POST /api/v1/session/turn` |
| `GovernmentAgentTurnProcessor` | `src/gov_service_agent/agent/turn_processor.py` | 生产办理编排器 |
| `process_turn` | 同上 | 为本轮建立工作状态并按模式分发 |
| `_copy_working_state` | 同上 | 新用户轮保留业务材料并重置生命周期 |
| `_determine_turn_mode` | 同上 | 按确认、终点、槽位、停住、初次检索的顺序分类 |
| `_handle_initial_routing` | 同上 | 初次检索、核对图、从入口推进 |
| `_handle_slot_interaction` | 同上 | 把待答槽位交给 F09 |
| `_result_from_f09` | 同上 | 按 F09 是否真的留下转移决定追问、准备确认或停住 |
| `_prepare_terminal` | 同上 | 同一轮重新打开流程后做确认准备 |
| `_rearm_same_turn_workflow` | 同上 | 同一请求内把生命周期交还给下一个子流程 |
| `_handle_terminal_confirmation` | 同上 | 下一轮只做确认裁决 |
| `_handle_already_confirmed` | 同上 | 已确认事项后的短路 |
| `_handle_safe_hold` | 同上 | 回退或暂不支持时返回受控说明 |
| `SemanticRetrievalService.retrieve` | `src/gov_service_agent/retrieval/service.py` | 只在初次路由执行的方向检索 |
| `advance_until_blocked` | `src/gov_service_agent/business_graph/transition.py` | 确定性图推进 |
| `run_slot_interaction_workflow` | `src/gov_service_agent/agent/workflow.py` | 槽位理解、解释、接受后的那一次 F04 |
| `build_terminal_candidate_context` | `src/gov_service_agent/agent/terminal.py` | 只从转移结果构造候选上下文 |
| `prepare_terminal_confirmation` | `src/gov_service_agent/agent/workflow.py` | 保存候选并等待确认 |
| `resolve_terminal_confirmation` | 同上 | 根据下一轮原话决定是否写入已确认事项 |
| `build_session_router` | `src/gov_service_agent/composition.py` | 装配生产依赖和会话路由 |
| `health` | `src/gov_service_agent/main.py` | 返回 `{"status": "ok"}` |

## 27. 一分钟理解 F12

新会话先检索方向，再进入确定性业务图。缺什么槽位就问什么。用户的话由 F09 解释；只有接受才由 F04 推进一步。走到终点时只产生候选，并在同一轮里做确认准备。下一句用户话才由 F10 确认。F11 负责记住会话。F12 只负责把这些已有能力按权限串起来。

## 28. 当前 F12 状态

- Resource Gate：CLOSED
- Requirement：APPROVED / FROZEN / REMOTE-FROZEN
- Technical Design：APPROVED / FROZEN / REMOTE-FROZEN
- Code：IMPLEMENTED / FIX #1 + FIX #2 APPLIED
- Test：PASS / OWNER REVIEW APPROVED
- Review：PASS / OWNER REVIEW APPROVED
- Explanation：COMPLETE / OWNER REVIEW APPROVED
- Code-Reading Document：COMPLETE / READY FOR OWNER REVIEW
- Commit：NOT STARTED
- Push：NOT STARTED

F12 还没有 CLOSED。
