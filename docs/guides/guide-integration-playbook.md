# 政务办事指南接入与知识问答复用手册

本文记录 F15 已经落地的接法，供后续事项复用。它不是新事项的需求说明。灵活就业的条件、槽位和词表不能直接套到其他事项。

## 1. 复用架构

事项主数据仍在 Business Data。合法路径仍由 Decision Graph 和 `advance_until_blocked` 推进。指南放在 Guide Knowledge Sidecar，不改 F02 快照。

`GovernmentKnowledgeService` 只返回已核验事实。`recognize_guide_utterance` 判断用户在问哪一类指南问题。`TemplateGuideRenderer` 把事实说成短句。`GuideQueryHandler` 作为 Side Route，在槽位映射和确认解析之前处理。Session 仍保存 `AgentState`，公开响应仍是 F11 的五个字段。

分工：模型理解原话并给出候选；知识库提供可核对的事实；决策图决定下一步；F10 只在用户明确说出确认短句后写入已确认事项。

## 2. 准备指南数据

1. 以官方指南原文为准，保留章节标题和表格内容。空栏目写成「未记载」或「未填写」，不要写成「无」「免费」或「不需要材料」。
2. 每个章节做一条 `SourceSection`：`section_id`、`title`、`text`。
3. 可回答的事实做 `KnowledgeItem`。`excerpt` 必须能在对应章节原文中找到。
4. `verification_status` 为 `SOURCE_EXPLICIT` 或 `VERIFIED` 时，模型要求必须有 `excerpt`。没有摘录就不能当公开知识。
5. `TO_CONFIRM` 可以留在文件里。查询会返回 `NOT_VERIFIED`，回答不会使用它。
6. 同一来源里的多条事实分开存放。例如直接缴费和银行扣缴协议是两条，回答时再组合。

原文副本放在 `data/sources/`，文件名写入 `SourceRecord.source_file`。不要把磁盘路径写进数据。

## 3. 数据模型

代码在 `src/gov_service_agent/guide_knowledge/models.py`。

| 模型 | 作用 |
| --- | --- |
| `GuideDocument` | 一份事项的 sidecar：`schema_version`、`business_id`、`source`、`source_sections`、`knowledge_items` |
| `SourceSection` | 章节原文 |
| `KnowledgeItem` | 一条可查询事实：`item_id`、`topic`、`subtopic`、`value`、`verification_status`、`source_id`、`section_id`、`excerpt` |
| `GuideValue` | `kind` 为 `text` 或 `list` |

`source` 复用 `gov_service_agent.business_data.models.SourceRecord`。`topic` 是稳定查询名。`subtopic` 只在同一 topic 下还要区分处理方式时使用，不是每个事项的必填业务字段。灵活就业里的 `material_correction`、`bank_withholding` 只属于该事项。

加载函数是 `load_guide_document`。下面只说明结构，不代表任何真实事项：

```json
{
  "schema_version": "1",
  "business_id": "BUSINESS_ID",
  "source": {
    "source_id": "src-example",
    "source_title": "事项指南标题",
    "source_type": "OFFICIAL_GUIDE",
    "source_file": "事项指南.txt"
  },
  "source_sections": [
    {
      "section_id": "sec-example",
      "title": "章节标题",
      "text": "该章节的原文"
    }
  ],
  "knowledge_items": [
    {
      "item_id": "ki-example",
      "topic": "materials",
      "subtopic": null,
      "value": {"kind": "text", "text": "只填写已核对的原文事实"},
      "verification_status": "SOURCE_EXPLICIT",
      "source_id": "src-example",
      "section_id": "sec-example",
      "excerpt": "与章节原文一致的短摘录"
    }
  ]
}
```

## 4. GovernmentKnowledgeService

路径：`src/gov_service_agent/guide_knowledge/service.py`。

构造参数是 `documents: dict[str, GuideDocument]`，可选 `business_repository`。仓库里不存在该 `business_id` 时，查询结果为 `NOT_FOUND`。

`source_title(business_id)` 返回指南标题，供未确认事项的限定语使用。

`query(business_id, topic, subtopic=None, overview_only=False)` 按 topic 精确匹配。`subtopic` 为空时返回该 topic 的全部条目；`overview_only=True` 时只返回 `subtopic` 为空的条目。状态：

- `KnowledgeQueryStatus.FOUND`：至少有一条 `SOURCE_EXPLICIT` 或 `VERIFIED` 事实
- `NOT_FOUND`：没有对应条目，或事项不存在
- `NOT_VERIFIED`：有条目，但都不是上述两种公开状态

输出是 `KnowledgeQueryResult`。每条 `KnowledgeFact` 含 `text`、`source_section`（章节标题）、`excerpt`、`source_title`、`source_file`。语义检索结果不能直接变成 `KnowledgeFact`。

`query_many(business_id, lookups)` 合并多组 `(topic, subtopic)`。同一 `item_id` 只保留一次。`subtopic` 为空的查找会带 `overview_only=True`。有任何公开事实则为 `FOUND`；全部未核验则为 `NOT_VERIFIED`；否则 `NOT_FOUND`。

## 5. Topic 与 Subtopic

识别在 `src/gov_service_agent/guide_knowledge/recognize.py` 的 `recognize_guide_utterance`。它返回 `Recognition`，种类为 `TOPIC`、`AMBIGUOUS`、`UNCERTAIN`、`OUT_OF_GUIDE`、`SMALLTALK`、`FALL_THROUGH`。`lookups` 可以带多组查询。当前实现先匹配更具体的说法，再匹配通用 topic。没有按整句原话绑定答案。

F15 已经分开的含义：

- 「需要什么材料」查询 `materials`。「资料少了」「漏交」「不符合法定形式」查询 `process/material_correction`。「不属于受理范围」查询 `process/out_of_scope`。「材料需要核实」查询办理流程，不回到材料清单。
- 「支付宝可以缴吗」只查缴费渠道。「怎么缴纳」同时查渠道和 `faq/bank_withholding`。「自动扣费」「银行缴费协议」只查扣缴协议。
- 「是否支持」用短句。「如何办理」带出指南里已有的入口，不补写页面点击步骤。

`线下怎么办` 返回 `AMBIGUOUS`。`match_clarification_topic` 只在用户说出唯一选项后继续。问句像办事问题但主题不清时返回 `UNCERTAIN`，请用户说明，不宣称超出指南。其他政务事项返回 `OUT_OF_GUIDE`。

短语表现在写在 `recognize.py` 的模块常量里，没有按事项分开的配置文件。新事项可以增加自己的 topic 和短语，但要避免把演示事项的槽位短答误判成指南问题。不要复制灵活就业的业务词当通用词表。

## 6. Side Route 与会话状态

`src/gov_service_agent/agent/guide_route.py` 的 `GuideQueryHandler.try_handle` 由 `GovernmentAgentTurnProcessor.process_turn` 调用。它处理等待槽位、等待确认和已确认三种轮次。精确的确认或拒绝短句继续交给 F10。

知识回答不修改 `current_node`、已校验槽位、`candidate_business_id`、`confirmed_business_id`，也不调用 `advance_until_blocked`。

| 会话状态 | 指南行为 |
| --- | --- |
| 首次路由之后，节点还没有事项引用 | 仅当 `artifacts["f12"].knowledge_context_unique` 为真时回答，并加上「如果您咨询的是……事项」，然后恢复原问题 |
| 多个检索候选 | `knowledge_context_unique` 为假，不回答具体指南 |
| 等待槽位，节点已有唯一事项引用 | 直接回答，再接回槽位问题 |
| 等待 F10 | 回答后再次展示确认提示，不写入确认结果 |
| 已确认 | 只回答知识，不重复材料预览 |

`knowledge_context_business_id` 只用于查公开指南。它不会被写成候选事项或已确认事项。澄清未结束时，本轮不拼接业务问题；澄清下一句优先消费 `artifacts["f15"].pending_clarification`。

## 7. 新事项接入步骤

1. 取得官方指南并逐章核对，包括空表和常见问题。
2. 按现有 Business Data 契约建立事项数据。不要把指南长文塞进 F02 快照。
3. 新建该事项自己的 sidecar 和原文副本。
4. 为该事项建立 Decision Graph。槽位和分支按该事项的规则确定。
5. 让 F06 能检索到该事项。检索仍然只提供方向。
6. 为该事项补充 topic、subtopic 和同义短语。
7. 把 `GuideDocument` 放进 `GovernmentKnowledgeService` 的 `documents`。
8. 继续使用 `GuideQueryHandler`，不要另写一条会推进决策图的问答路径。
9. 用该事项的真实指南编写问答测试和业务图测试。
10. 用虚构用户信息做多轮验收，覆盖澄清、确认和已确认之后继续提问。

当前有三处还不能只靠配置完成：

- `build_default_guide_handler` 固定读取 `data/guides/DEMO_SS_001.guide.json`。服务本身接受多份文档，默认装配还没有扫描其他指南。
- 识别短语集中在 `recognize.py`，新增短语会影响所有事项。
- `first_turn_extract.py` 里的 `_SUPPORT` 只覆盖演示图的 `service_action`、`payment_actor`、`employment_type`。其他槽位名不会被这套短语自动接受。

这三处需要在接入时扩展加载和映射。不需要改 `query`、`query_many`、Renderer 的事实校验，也不需要改 F04 或 F10。

## 8. 测试

F15 已有：

- `tests/test_f15_guide_qa.py`
- `tests/test_f15_ux.py`
- `tests/test_f15_guide_accuracy.py`

相关回归还包括 `tests/test_f12_turn_processor.py`、`tests/test_f12_app_activation.py`、`tests/test_f12_session_integration.py`、`tests/test_agent_interaction.py`、`tests/test_agent_terminal.py`、`tests/test_agent_workflow.py`、`tests/test_session_api.py`、`tests/test_session_service.py`、`tests/test_f13_preview_materials.py`、`tests/test_f13_preview_activation.py`、`tests/test_f13_preview_session_integration.py`、`tests/test_graph_transition.py`。

最近一次执行：

```text
python -m pytest tests/test_f15_guide_accuracy.py tests/test_f15_guide_qa.py tests/test_f15_ux.py tests/test_f12_turn_processor.py tests/test_f12_app_activation.py tests/test_f12_session_integration.py tests/test_agent_interaction.py tests/test_agent_terminal.py tests/test_agent_workflow.py tests/test_session_api.py tests/test_session_service.py tests/test_f13_preview_materials.py tests/test_f13_preview_activation.py tests/test_f13_preview_session_integration.py tests/test_graph_transition.py
```

结果：343 passed，0 failed，0 skipped。这不是全仓库测试。自动化测试使用 Fake Provider。

新事项至少要自己覆盖这些场景：事实和来源章节一致；未核验事实不公开；空的收费栏目不推断免费；FAQ 步骤不丢失；材料清单和补正分开；同义说法能识别；歧义时先澄清；唯一知识上下文可用，多项候选不回答；首轮槽位先确定性校验再进入决策图；Side Route 不推进 F04、不自动确认、不重复 F13 材料；F11 的重试和公开字段不变。只重跑上面的 F15 命令，不能说明新事项已经通过。

## 9. F15 已经遇到的问题

1. 首轮模型少返回一个槽。现象是同句有时收下两槽，有时只剩办理动作。根因是只依赖模型候选。处理是先做 `deterministic_slot_candidates`，模型只补充空槽。见 `first_turn_extract.py`、`tests/test_f15_ux.py`。
2. 证据不是原话子串。现象是模型写了原话里没有的证据。`accept_slot_candidates` 以 `evidence_not_in_utterance` 拒绝。见同文件。
3. accepted 不等于已经推进。现象是日志计数为 1，对话仍从第一问开始。图只消费 `_consumed_slots` 留下的槽。见 `turn_processor.py`。
4. 指南问题被当成槽位答案。现象是「线下怎么办」可能写入就业类型。Side Route 先消费 `pending_clarification`。见 `guide_route.py`、`tests/test_f15_guide_qa.py`。
5. 早期节点没有指南上下文。现象是还在办理动作时不能查材料。F06 唯一命中写入 `knowledge_context_unique`，多项候选则澄清事项。见 `turn_processor.py`、`guide_route.py`。
6. 材料补正被当成材料清单。现象是「不齐全」「少了一份」回答成身份证。补正短语先于「材料」。见 `recognize.py`、`tests/test_f15_guide_accuracy.py`。
7. 相关 FAQ 没有一起回答。现象是「怎么缴」只说可以走支付宝。`lookups` 同时取渠道和扣缴协议，Renderer 区分直接缴费与代扣。见 `recognize.py`、`render.py`。
8. 回答像字段拼接。`TemplateGuideRenderer` 按 topic 改成短句，仍附章节标题。模型改写不能增加事实。见 `render.py`。
9. 未记载费用被说成免费。收费事实写明不能判断是否收费，约束词包含「免费」。见 sidecar 与 `FactConstrainedLlmRenderer`。
10. 澄清时连问两个问题。澄清轮 `include_resume=False`，答完知识后再恢复原问题。见 `guide_route.py`。

## 10. 后续事项提醒

后续要单独核验的指南是：

- 居民身份证换补领（领证未满五年）
- 异地转诊人员备案
- 住房公积金租赁提取（公租房）按月转账业务

每份指南都要重新核对事实、空栏目和来源章节。可以复用第 4 节到第 6 节的服务、渲染和旁路。必须单独建立事项数据、决策图、sidecar 和 topic 映射。不要复制 `DEMO_SS_001` 的申请条件、槽位值或缴费词表。本文没有为这三份指南生成规则或 JSON。
