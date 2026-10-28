# F16 Lite — 三个新政务事项接入

## 目标

在保留 DEMO_SS_001（灵活就业社保缴费）的前提下，接入身份证换补领、异地转诊备案、公积金公租房租赁提取三个事项。按 `business_id` 选图、多 Guide 加载；不编造未核验指南事实。

## 范围

- **F16-1**：多图注册表、会话绑图、Guide 多文档、识别/首轮槽位隔离。
- **F16-2**：居民身份证换补领（领证未满五年）。
- **F16-3（当前）**：异地转诊人员备案。
- **F16-4**：住房公积金租赁提取(公租房)按月转账业务。

## 核心设计决策

1. 四事项同时在线；注册表逐步挂载。
2. 多图注册表：按 `business_id` 取 Business Data 与 Decision Graph；不做跨域大图。
3. 仅当检索候选在注册表中且 **唯一** `business_id` 时入图；多候选不取最高分强行入图。
4. 入图后会话绑定 `bound_business_id` / `bound_graph_id`；指南问答不重新选图。
5. 申报条件为「无」时允许少槽位，但仍须 F10 显式确认。
6. 公积金 FAQ 对象描述不升格为准入条件。
7. 不实现 F17；不改 F04/F10/F13 判定语义与 F11 五字段合同。

## 当前阶段

F16-3 异地转诊人员备案已接入（申报条件「无」→ 浅图 + F10 显式确认）。

## 异地转诊接入（F16-3）

- **business_id**：`REFERRAL_YIDI_BA`
- **Business Data**：`data/demo/referral_yidi_ba.json`
- **Decision Graph**：`data/graphs/demo/referral_yidi_ba.json`（`entry → TERMINAL`，无资格槽位）
- **Guide**：`data/guides/REFERRAL_YIDI_BA.guide.json`
- **原文**：`data/sources/异地转诊人员备案.txt`

| 栏目 | 记载要点 |
| --- | --- |
| 申报条件 | **无**（不得编造资格门槛） |
| 材料 | 医保电子凭证/身份证件/社保卡；《基本医疗保险参保人员异地转诊备案表》（医院盖章） |
| 时限 | 即办 |
| 收费 | 栏目未记载具体项目/标准（不得写成免费） |
| 受理点 | 上城区政务服务中心一楼 12-16 号医保综合窗口 |
| FAQ | 各城区医保经办机构等；浙江政务服务网 / 浙里办APP（渠道类型 ONLINE，非 MINI_PROGRAM） |

## 身份证接入（F16-2）

- **business_id**：`IDCARD_RC_LT5Y`
- **Business Data**：`data/demo/idcard_rc_lt5y.json`
- **Decision Graph**：`data/graphs/demo/idcard_replace_lt5y.json`（`graph_id=idcard_replace_lt5y`）
- **Guide**：`data/guides/IDCARD_RC_LT5Y.guide.json`
- **原文**：`data/sources/居民身份证换补领（领证未满五年）.txt`

### 业务图主分支（UX-Fix）

`entry → handling_case → submitted_photo_not_self → appearance_change_major → bad_credit_record → biometric → validity → hukou → TERMINAL`

- 丢失补领 / 损坏换领（已说明则不重复问）
- 指南条款（二）拆成 `submitted_photo_not_self` 与 `appearance_change_major`（OR）；不良信用独立；任一项为是 → 线下分流
- 「不符合适用对象」由资格 AND 失败路径表达
- 受理点按指南列明上城区 **14** 家派出所，不得表述为仅清波/湖滨
- 首轮纯指南咨询：F06 唯一准入后答 Knowledge，不绑图、不确认

### 已核验主要条件（来源：申报条件表 + 特别提示 + 收费栏）

| 条件 | 记载 |
| --- | --- |
| 信息要求 | 相片、指纹采集未满5年且有效 |
| 证件要求 | 有效期 10 年及以上 |
| 办理情形 | 丢失、损坏需补领（收费栏区分丢失补领 / 损坏换领） |
| 户口 | 登记在浙江省 |
| 线下分流 | 不符合适用对象；照片非本人或相貌较大变化；不良信用 |
| 费用 | 丢失补领、损坏换领 40元/证 |
| 承诺时限 | 10工作日（法定 60 日等另载，不与受理即办混用） |
| 现场次数 | 0次；FAQ 全程网办；不覆盖须线下例外 |
| 条件组合 | **Owner 已确认 AND**（非指南原文；见 `cond-condition-group-and`） |
| 现场正面照片 | 指南：须现场拍摄、不作证件制作照片。**Owner 确认**：采集后可在线发起申请；≠整项必须线下（独立依据 `src-idcard-owner-confirm-f16-2` / Guide `sec-owner-confirm`） |

### Owner 已确认业务规则（非指南原文）

1. **申报条件组合**：资格条件之间为 **AND**。Decision Graph 保持全部满足才进终端；已从 TO_CONFIRM 改为 VERIFIED（人工确认来源）。
2. **现场正面照片**：材料要求现场拍摄 ≠ 整个申请必须线下办理；完成采集后可用该电子材料在线申请。三类特别提示线下例外仍分流。

不得将上述 Owner 解释写入指南原文栏目或冒充 `SOURCE_EXPLICIT` 摘录。

## 涉及文件

- `data/matters/registry.json`
- `data/retrieval/f06_online_eligibility.json`
- `src/gov_service_agent/matters/`
- `composition.py`、`turn_processor.py`、`guide_route.py`
- `guide_knowledge/recognize.py`、`agent/first_turn_extract.py`
- `tests/test_f16_matter_foundation.py`、`tests/test_f16_idcard.py`

## 测试策略

Fake Provider；F16 定向 + F06/F09/F10/F11/F12/F13/F15 回归。Session Redis 测使用 `127.0.0.1:6379`（与默认 Settings 一致；Docker `govagent-redis-dev` 映射同端口）。测试夹具 `TEST_F16_STUB` 非正式政务事实。

### F16-2 测试结果

| 套件 | 结果 |
| --- | --- |
| `tests/test_f16_idcard.py` | 19 passed（含 Owner AND / 现场照片≠线下 定向） |
| `tests/test_f16_matter_foundation.py` | 14 passed |
| Owner 确认后定向+相关回归 | **67 passed**（idcard + foundation + F15 accuracy + retrieval） |
| Redis Checkpoint 绑图恢复 | 已通（6379） |

原文 TXT 根目录与 `data/sources/` 副本 SHA256 一致。

### F06 真实检索注意（F16-2 验收）

Admission / Registry 增加事项后，**必须重建** PostgreSQL `semantic_retrieval_*` 投影，否则在线召回仍只有旧文档。

- 根因（本轮）：投影 `document_count=1` 且仅 `DEMO_SS_001`（built 2026-09-29），身份证查询对社保文档 score≈0.33–0.42 &lt; 0.50 → `NO_USABLE_CANDIDATE` → 兜底「暂时无法确定您要办理的业务方向」。
- 重建后文档：`DEMO_SS_001` + `IDCARD_RC_LT5Y`；Owner 四句实测均可 top-1 命中且 score≥0.65。
- `SemanticRetrievalService` 已缓存 LOCAL Embedding Provider，避免每轮 `embedding_model_loaded`（需重启 Backend 生效）。

### F16-3 测试与投影

| 套件 | 结果 |
| --- | --- |
| `tests/test_f16_referral.py` + idcard + foundation + F15 + retrieval builder/service + F12 turn | **145 passed**（Fake LLM） |
| 本地 pgvector 重建 | `document_count=3`：`DEMO_SS_001` / `IDCARD_RC_LT5Y` / `REFERRAL_YIDI_BA`（gte-base-zh / cpu） |

在线 Backend 若已缓存旧投影元数据，Owner 验收前需**自行重启** Backend（本阶段不代启服务）。

## 非目标

跨事项切换、付费 LLM 联调、F14 UI、修改已有 DEMO 社保核验事实、放宽 0.80 槽位门槛、F16-4 正式数据。
