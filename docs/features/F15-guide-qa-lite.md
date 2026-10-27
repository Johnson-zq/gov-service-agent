# F15 简版开发说明 — 办事指南问答与 Side Route

## 1. 目标与非目标

目标：用户办理「灵活就业人员社会保险费申报缴费」时，可以按官方指南询问材料、时限、地点、受理时间、咨询、投诉、法律依据、渠道、常见问题，以及指南中的其他已核验条目。答完后回到原来的办理问题。指南问答不改变当前节点、已校验槽位、候选事项和已确认事项。

非目标：不新增身份证换补领、异地转诊、公积金租赁提取的办理能力；不改决策图、F10 确认规则、0.80 置信度、F11 公开字段、F14 前端。

## 2. 复用

F02 JSON 与 F13 材料预览保持原样。指南扩展放在 sidecar。F04 仍只在槽位答案被接受后推进。F09 的「什么是 / 什么叫」解释旁路原样保留，并先于指南识别放行。F07 Provider 只给可选的事实改写使用；默认回答是模板。F11 仍只返回 `session_id`、`request_id`、`status`、`response_text`、`requires_user_input`。

## 3. 混合知识模型

`data/demo/demo_ss_001.json` 继续作为事项、材料、地点、渠道、条件和决策图的来源。`data/guides/DEMO_SS_001.guide.json` 按 `business_id` 关联，包含 `source_sections` 与 `knowledge_items`。条目有 `topic`、可选 `subtopic`、文本或列表 `value`、`verification_status`、`section_id` 和 `excerpt`。公开条目必须带摘录。`TO_CONFIRM` 不公开。收费栏目没有具体项目时，只记录「未记载」，不写成免费。

可读原文在 `data/sources/灵活就业人员社会保险费申报缴费.txt`，来源文件名写入 `source_file`。

## 4. 查询

`GovernmentKnowledgeService.query(business_id, topic, subtopic=None)` 只做精确匹配。结果为 `FOUND`、`NOT_FOUND`、`NOT_VERIFIED`。未知 `business_id` 视为未找到。同一 topic 的多条已核验 FAQ 可以一起返回。语义检索命中的原文不直接当事实。

## 5. Topic 识别与澄清

识别在槽位映射和 F10 确认解析之前完成。「要什么材料」「多久办好」「去哪办」「几点上班」「咨询电话」「法律依据」「支付宝可以缴费吗」映射到固定 topic。「线下怎么办」进入澄清，请用户在办理地点、办理流程、是否必须到现场之间选择。澄清未结束时，下一句只处理这次知识问题，不写入 `employment_type`。「什么叫灵活就业」仍走原来的解释旁路。

## 6. Side Route

`GuideQueryHandler` 由 `GovernmentAgentTurnProcessor` 在确定轮次模式后调用。命中指南问题时写入 `artifacts["f15"]`，不调用 `advance_until_blocked`，不改 `f09` / `f10` 里的业务字段。回答后把原来的槽位问题或确认提示接回 `response_text`。

## 7. 三种办理状态

等待槽位：事项已能由当前节点的 `source_condition_refs` 唯一确定时才回答该事项指南；更早的节点只提示先完成当前选项。等待 F10：除了精确的「确认 / 不确认」等原有短句，指南问题只回答并再次展示确认提示，不写入 `confirmed_business_id`。已经确认：可以继续问指南，确认结果保持不变，`requires_user_input` 仍为 false。

## 8. Renderer

默认模板只拼接已核验事实和来源节名。可选 LLM 只接收这些事实；若输出出现事实中没有的号码，或出现「免费」「当天一定办结」等事实里没有的说法，就丢弃并改用模板。

## 9. 修改路径与风险

新增 `guide_knowledge` 包、`agent/guide_route.py`、sidecar 和来源文本。修改 `agent/turn_processor.py` 的轮次入口。风险是过宽的词会挡住真实槽位答案，所以槽位短答和不含问句的选项仍放行；另一个风险是确认轮上的精确确认短句必须继续进入 F10。

## 10. 验收场景

材料为身份证。办结期限按指南回答即办，并保留补正、不予受理和退回。现场次数按「0次」回答。地点、受理时间、咨询电话、投诉电话、法律依据和支付宝渠道均来自指南原文。收费未记载时不推断免费。「线下怎么办」先澄清，再说地点后回答地点并恢复 `employment_type`。连续两次指南提问不改变节点和槽位。非指南问题友好兜底且不推进业务。LLM 额外事实不被采纳。原确认流程和 F13 首次材料预览仍可用。

## 11. 最终实现

第 7 节里「更早节点只提示先完成当前选项」是首版约束。最终实现已放宽：F06 只命中一个入图事项时，早期节点也可以回答该事项的公开指南，并先说明「如果您咨询的是……事项」。命中多项时不回答具体指南。下面各节以当前代码为准。

调用顺序：

`GovernmentAgentTurnProcessor.process_turn` 确定轮次后调用 `GuideQueryHandler.try_handle`。未命中时，首轮走 `LlmFirstTurnExtractor.accepted_slots`，再调用既有 `advance_until_blocked`。后续槽位仍走 F09，确认仍走 F10。

新增模块：

- `src/gov_service_agent/guide_knowledge/models.py`
- `src/gov_service_agent/guide_knowledge/service.py`
- `src/gov_service_agent/guide_knowledge/recognize.py`
- `src/gov_service_agent/guide_knowledge/render.py`
- `src/gov_service_agent/agent/guide_route.py`
- `src/gov_service_agent/agent/first_turn_extract.py`

`build_default_guide_handler` 只加载 `data/guides/DEMO_SS_001.guide.json`，渲染器用 `TemplateGuideRenderer`。`FactConstrainedLlmRenderer` 只在测试和显式注入时使用。

## 12. Sidecar

模型在 `guide_knowledge/models.py`：`GuideDocument`、`SourceSection`、`KnowledgeItem`、`GuideValue`。来源记录复用 `business_data.models.SourceRecord`。公开状态只接受 `VerificationStatus.SOURCE_EXPLICIT` 或 `VERIFIED`，并且必须有 `excerpt`。`TO_CONFIRM` 可以入库，查询结果是 `NOT_VERIFIED`，不进入回答。

## 13. 首轮多槽位

`deterministic_slot_candidates` 先看原话。一个槽位只有唯一合法支持短语才接受。`交社保`、`缴费`、`自己交`、`自己缴` 可以确定缴费和本人缴。`离职`、`没有单位` 不能推出就业类型。缴费和转移同时出现，或本人缴和单位缴同时出现，该槽拒绝。

策略允许时，`LlmFirstTurnExtractor` 再做一次结构化调用。`accept_slot_candidates` 只补充确定性结果里还没有的槽，并检查允许值、证据是否为原话子串、证据是否支持该值、以及否定和冲突。模型失败或策略拒绝时，保留已经确定的槽位。

收下的候选交给 `advance_until_blocked`。`_consumed_slots` 只保留图已经走过的槽。日志里的 accepted 数量不等于已经推进的槽位。

## 14. 知识上下文

`artifacts["f12"]` 记录 `knowledge_context_unique` 和 `knowledge_context_business_id`。它只表示可以查阅哪一份公开指南。

`GuideQueryHandler._answer_topic` 按这个顺序取编号：已确认事项、等待确认的候选事项、当前节点唯一的 `source_condition_refs`、最后才是唯一知识上下文。前三种回答不加限定语。只有知识上下文会加上「如果您咨询的是……事项」。三种编号不会互相改写。指南轮次不调用 `advance_until_blocked`，也不解析「确认」。

## 15. 澄清与恢复

`recognize_guide_utterance` 的结果包括直接命中、`AMBIGUOUS`、`UNCERTAIN`、`OUT_OF_GUIDE`、`SMALLTALK` 和放行。`线下怎么办` 进入澄清，本轮只输出澄清问题。用户选定后回答知识，再用「我们继续刚才的问题」接回原槽位问题或确认提示。已确认事项只回答知识。

材料补正、不予受理、银行扣缴和直接缴费使用不同的 topic 或 subtopic。问句像在问办事、但主题还不清楚时，先请用户说明，不直接说超出指南。医保、公积金等其他政务问题仍拒绝编造。笑话和问候走 `render_smalltalk`。

## 16. Renderer 约束

`TemplateGuideRenderer.render_facts` 只改写已核验事实的句子，并附「（来源：章节标题）」。电话、地址、材料从事实文本读取。收费未记载不写成免费。办结时限保留补正、不予受理和退回。支付宝「怎么缴」同时使用缴费渠道和银行扣缴两条事实，并说明指南没有页面点击步骤。

`FactConstrainedLlmRenderer` 若发现新号码，或事实中没有的「免费」「当天一定办结」「保证可以办理」，就退回模板。调用失败也退回模板。

## 17. 人工测试与回归

人工对话已经覆盖：首轮多槽位、意图冲突、早期节点指南查询、材料补正、支付宝银行扣缴、Topic 澄清、原节点恢复、F10 显式确认、F13 材料预览，以及已确认后继续问答。

相关回归命令见 `docs/guides/guide-integration-playbook.md`。结果是 343 passed、0 failed、0 skipped。这是该组相关测试的结果，不是全仓库测试。

## 18. 非阻塞遗留

A. 适用范围中的「服务对象：个人」写在查询条目里，但该条目的 `section_id` 挂在「八、申报条件」。事实与指南一致，来源章节不完全对应。

B. 第三至五章「省级、市级法律依据和县级规定均为无」已写入 sidecar 章节，但法律依据知识项的 `section_id` 仍是「二、国家法律依据」，没有分别挂靠这三章。

这两项都未改成已修复。
