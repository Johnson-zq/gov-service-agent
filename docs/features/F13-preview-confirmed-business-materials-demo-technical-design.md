# F13-Preview Confirmed Business Materials Demo Technical Design

已确认事项材料展示的实现设计。

本文件只说明怎么做。产品决定以已冻结的 `docs/features/F13-preview-confirmed-business-materials-demo.md` 为准，提交 `ef58d0b8217f9301df9704fccce052226b5118c9`。本设计不改写这些决定。

## 1. 设计目标

在不改 F12 业务权限和状态语义的前提下，于首次成功确认事项之后，用已确认编号查询现有公开材料，并且只增强本轮 `response_text`。

F12 处理器先完成全部确认。Preview 是事后展示增强。它观察确认前后的已确认编号，读取受控业务数据，再把展示段追加到原回复后面。

## 2. Frozen Requirement Trace

以下行为按需求原样实现：

- 只在首次确认触发。处理前已确认编号为空，并且处理后非空。
- 第 4 轮只有候选 `DEMO_SS_001`、已确认为空，不展示。
- 第 5 轮从空变为 `DEMO_SS_001`，展示。
- 查询键只能是 `confirmed_business_id`。
- 规范名称来自受控业务数据。
- 材料来自现有公开材料规则。
- 保留 F12 原回复，再追加展示段。
- 没有公开材料时，确认仍成功，并给出受控空材料提示。
- Preview 自己的查询或渲染失败采用退让：保留 F12 成功结果。
- F12 基础失败原样向外传播。
- 办理状态和已确认编号不被 Preview 修改。
- 公开接口字段不变。
- 模型和检索不产生材料事实。

审查备注 F13P-RQ-RV-001 不修改需求原文。本设计使用“权威业务产物”描述“不新增新的业务真相”。需求文档中的“权威业务材料”措辞保持不动。

## 3. Existing Contracts

`process_turn` 是同步方法，不是异步。协议在 `src/gov_service_agent/session/service.py` 的 `AgentTurnProcessor`。

ACTUAL_PROCESS_TURN_SIGNATURE：

```text
def process_turn(
    self,
    *,
    session_id: str,
    request_id: str,
    input_text: str,
    restored_state: AgentState | None,
) -> AgentTurnResult
```

`GovernmentAgentTurnProcessor.process_turn` 使用同一签名。

AGENT_TURN_RESULT_TYPE：`src/gov_service_agent/session/models.py` 中的冻结数据类 `AgentTurnResult`。字段为 `state`、`response_text`、`requires_user_input`、`public_status`。`state` 的类型是 `AgentState`，即 `TypedDict`。

已确认事实通过 `read_f10(artifacts)` 读取。该函数在 `src/gov_service_agent/agent/terminal.py`。它返回 `artifacts["f10"]` 的字典；缺失或类型不对时返回空字典。已确认编号字段是该字典中的 `confirmed_business_id`。

ACTUAL_CANONICAL_NAME_API：`JsonBusinessRepository.get_business(business_id)` 返回 `Business`。规范名称是 `business.canonical_name`。定义分别在 `src/gov_service_agent/business_data/repository.py` 和 `src/gov_service_agent/business_data/models.py`。未知编号抛出 `BusinessNotFoundError`。

GET_MATERIALS_FILTERING_SEMANTICS：`get_materials(business_id, *, consumption=ConsumptionMode.PUBLIC)` 在默认公开模式下已经过滤。它只返回 `is_public_material` 为真的材料，并保持快照中的原顺序。传入 `ConsumptionMode.INTERNAL` 才会返回全部材料。

ACTUAL_PUBLIC_MATERIAL_POLICY_API：`is_public_material`，定义在 `src/gov_service_agent/business_data/repository.py`。`VerificationStatus` 定义在 `src/gov_service_agent/business_data/models.py`。Preview 不复制这套判断。

材料展示字段是 `Material.source_text`。

幂等发生在处理器之前。`SessionTurnService.handle_turn` 先调用 `_lookup_replay`。命中缓存就直接返回，不再调用 `process_turn`。

IDEMPOTENCY_BEFORE_PROCESSOR = YES。

## 4. Architecture Overview

生产路径：

```text
POST /api/v1/session/turn
        ↓
SessionTurnService
        ↓
ConfirmedBusinessMaterialsPreviewProcessor
        ↓
GovernmentAgentTurnProcessor
        ↓
首次确认判断
        ↓
受控业务数据查询与确定性渲染
        ↓
AgentTurnResult
        ↓
F11 校验、成功提交、审计、公开响应
```

Wrapper 是装饰器：它包住现有处理器，自己实现同一个 `AgentTurnProcessor` 协议。F11 只看到最外层处理器。

不把 Preview 写进 `GovernmentAgentTurnProcessor`。F12 已关闭。材料展示不属于 F06、F09、F04 或 F10。基础处理器先完成确认，Preview 只做事后展示。

## 5. Wrapper / Decorator

新增类：`ConfirmedBusinessMaterialsPreviewProcessor`。

模块：`src/gov_service_agent/agent/materials_preview.py`。

DIRECT_DEPENDENCIES：

- `base_processor`：满足 `AgentTurnProcessor` 的对象。生产中是 `GovernmentAgentTurnProcessor`。
- `business_repository`：`JsonBusinessRepository`。

不依赖语言模型提供者、语义检索、向量模型、PostgreSQL、Redis 客户端或决策图。

构造函数只保存这两个引用。构造时不读材料、不连 Redis、不加载向量、不调用模型、不查数据库。

`process_turn` 使用第 3 节的精确签名。

概念顺序：

```text
process_turn(...):
    before_id = _read_confirmed_id(restored_state)
    base_result = base_processor.process_turn(
        session_id=session_id,
        request_id=request_id,
        input_text=input_text,
        restored_state=restored_state,
    )
    after_id = _read_confirmed_id(base_result.state)
    if not is_first_confirmation(before_id, after_id):
        return base_result
    try:
        section = _build_preview_section(repository, after_id)
        return replace(
            base_result,
            response_text=append_preview(
                base_result.response_text,
                section,
            ),
        )
    except Exception:
        log_preview_failure(after_id, exception)
        return base_result
```

`replace` 是 `dataclasses.replace`。基础调用在退让用的 `try` 之外。

BASE_CALL_OUTSIDE_PREVIEW_FAIL_SOFT_BLOCK = YES。

基础处理器每次 `process_turn` 只调用一次。未触发时直接返回它的结果。

## 6. First Confirmation Detection

`_read_confirmed_id(state)` 是只读辅助函数：

- `state is None` 时返回 `None`。不创建 `f10`，不改状态，不调用确认收尾。
- 从 `state["artifacts"]` 取出映射后调用 `read_f10`。
- 读取返回字典中的 `confirmed_business_id`。
- 非字符串或空白字符串视为空，返回 `None`。
- 否则返回去掉首尾空白后的编号。

`is_first_confirmation(before_id, after_id)` 是纯函数：

| before | after | 结果 |
| --- | --- | --- |
| 空 | 空 | 否 |
| 空 | 非空 | 是 |
| 同一非空编号 | 同一非空编号 | 否 |
| 任一非空 | 任何值 | 否 |

因此，已确认编号从一个非空值变成另一个非空值时不触发。需求只定义首次确认。

不增加候选编号检查、原文是否等于“确认”、F10 状态字符串猜测或回复文本匹配。已确认编号是唯一触发事实。

处理前的编号来自传入的 `restored_state`。处理后的编号来自 `base_result.state`。两处都只读。

## 7. Business Data Lookup

首次确认成立后：

```text
after_confirmed_id
    → get_business(after_confirmed_id).canonical_name
    → get_materials(after_confirmed_id)
    → 确定性渲染
```

不使用 `input_text`、检索结果或模型输出。

规范名称只来自 `get_business(...).canonical_name`。不从 F12 回复、图上问题、检索标题或用户原话提取。

材料调用为 `get_materials(business_id)`，使用默认 `consumption=ConsumptionMode.PUBLIC`。不传 `INTERNAL`。不调用 `sort`、`set`，不做语义重排或模型重排。顺序就是仓库返回顺序。

找不到业务时，`get_business` 或 `get_materials` 抛出 `BusinessNotFoundError`。这属于 Preview 自己的数据不一致，进入退让，不展示“未知”、事项编号或猜测名称。

REPOSITORY_READ_API_GAP = NO。现有 `get_business` 和 `get_materials` 足够。Preview 不直接打开 JSON，不自己 `json.load`，不拼接 `data/demo` 路径。

## 8. Public Material Policy Reuse

PUBLIC_FILTER_REUSE_DESIGN：CASE A。

默认 `get_materials(business_id)` 已经只返回公开材料。Preview 直接消费这个列表，不再调用第二次 `is_public_material`，也不在 Preview 里写 `source_status` 判断。

`VerificationStatus` 的公开规则仍只存在于现有 `is_public_material`。

非公开材料测试使用真实 `JsonBusinessRepository.get_materials` 的默认公开模式。测试数据里同时放一条能通过现有规则的材料和一条不能通过的材料。断言只看公开结果是否出现，不把规则正文复制进生产代码。

## 9. Deterministic Rendering

模块内纯函数 `render_materials_preview(canonical_name, public_materials) -> str`。

固定展示文案是系统用语，定义为模块级常量，不写入业务数据：

- `办理事项：`
- `需要准备的材料：`
- `当前暂无可展示的办理材料信息。`

业务事实与系统用语分开。事实是 `canonical_name` 和 `material.source_text`。系统用语只来自这个渲染函数。

有公开材料时：

```text
办理事项：<canonical_name>
需要准备的材料：
1. <source_text>
2. <source_text>
```

编号从 1 开始，顺序与入参一致。

没有公开材料时，这不是异常：

```text
办理事项：<canonical_name>
当前暂无可展示的办理材料信息。
```

规范名称或某条 `source_text` 不是非空字符串时，渲染函数抛出异常，交给退让边界。不编造替代文本。

渲染函数不调用模型。不生成“全部”“仅需”“材料完整”“保证办理”。

追加规则：

- 原 `response_text` 非空：原文字符 + `"\n\n"` + 展示段。
- 原 `response_text` 为空：只返回展示段。

不 `strip`，不改写，不总结，不替换原文字符。

## 10. AgentTurnResult Preservation

成功增强时只用 `dataclasses.replace(base_result, response_text=新文本)`。

保持不变的字段：

- `state`
- `requires_user_input`
- `public_status`

`replace` 会生成新的 `AgentTurnResult`，并继续引用原来的 `state` 对象。实现不得写入 `state`，不得深拷贝后再改，不得增删产物，不得修改 `f09` 或 `f10`，不得把 Preview 结果写回状态。

不新增 `artifacts["f13_preview"]`、材料产物或 Preview 状态产物。材料展示不是新的权威业务产物。

测试用深度相等核对 `f09`、`f10`、图转移、槽位和已确认编号。不额外要求对象身份不变，尽管 `replace` 在正常路径上会保留同一个 `state`。

## 11. Preview Fail-Soft

基础处理器成功返回之后，只有下面这一段允许退让：

- 读取规范名称
- 读取材料
- 依赖仓库已完成的公开过滤结果
- 渲染展示段
- 组装新的回复文本

这些步骤放在同一个 `try` 中。捕获 `Exception` 后返回原始 `base_result`，不增强回复，不构造替代材料，不改状态。

这个捕获是有意划定的退让边界，不是通用吞异常。它不包住 `base_processor.process_turn`。

未知业务、仓库异常、畸形预览数据、材料读取异常和渲染异常都走这条路径。

PREVIEW_FAILURE_OBSERVABILITY_DESIGN：复用现有 `logging.getLogger("gov_service_agent")`，不新增日志框架。退让时写一条 warning，只包含事件名 `materials_preview_failed`、已确认事项编号和异常类名。不记录用户原文、完整办理状态、材料来源、接口密钥、个人身份信息或模型原文。不记录 `str(exception)`，避免异常文本带出额外内容。

## 12. Base Failure Propagation

如果基础处理器抛出异常，Wrapper 不捕获，不转换成成功，不查材料，不制造已确认编号。异常原样传播，随后仍由 F11 既有失败语义处理。

基础异常测试要求仓库查询次数为 0。

## 13. F11 Session Boundary

`SessionTurnService` 继续只接收一个 `AgentTurnProcessor`。它不知道内部还有 F12 处理器。

会话顺序保持：恢复状态，调用处理器，校验 `AgentTurnResult`，成功提交，审计，公开响应。

Wrapper 不访问会话存储，不自己提交检查点，不实现第二套锁或幂等，不构造 `SessionTurnSuccess`。

检查点仍只保存 F12 产生的办理状态。不新增 Preview 检查点结构。材料文本如果随公开结果进入 F11 既有幂等缓存，沿用该缓存，不另做一套。

同一请求重放在 `_lookup_replay` 命中后直接返回，处理器不会执行第二次。

## 14. Composition Wiring

只改 `src/gov_service_agent/composition.py` 的 `build_session_router`。

接线顺序：

```text
base_processor = GovernmentAgentTurnProcessor(...)
processor = ConfirmedBusinessMaterialsPreviewProcessor(
    base_processor=base_processor,
    business_repository=business_repository,
)
SessionTurnService(..., processor=processor)
```

`business_repository` 就是上面已经创建、并传给 F12 的同一个 `JsonBusinessRepository` 实例。不为 Preview 再加载第二份快照。

REPOSITORY_INSTANCE_REUSED = YES。

`main.py` 已包含会话路由，不需要修改。

MAIN_CHANGE_REQUIRED = NO。

F12_PROCESSOR_CHANGE_REQUIRED = NO。

F10_CHANGE_REQUIRED = NO。

BUSINESS_DATA_CHANGE_REQUIRED = NO。

API_CHANGE_REQUIRED = NO。

`SessionTurnRequest` 和 `SessionTurnSuccess` 的字段保持 `session_id`、`request_id`、`status`、`response_text`、`requires_user_input`。路径仍是 `POST /api/v1/session/turn`。

## 15. Lazy IO

材料查询只发生在首次确认判断为真之后。应用导入、健康检查和处理器构造都不触发查询。

未触发的轮次，包括确认准备、低置信、解释请求和已经确认的后续轮，查询次数为 0。

## 16. Production File Scope

PROPOSED_PRODUCTION_SCOPE：

PRODUCTION_ADD：

- `src/gov_service_agent/agent/materials_preview.py`

PRODUCTION_MODIFY：

- `src/gov_service_agent/composition.py`

PRODUCTION_UNCHANGED：

- `src/gov_service_agent/agent/turn_processor.py`
- `src/gov_service_agent/main.py`
- `src/gov_service_agent/session/service.py`
- `src/gov_service_agent/agent/terminal.py`
- `src/gov_service_agent/agent/nodes.py`
- 决策图
- 业务数据，包括 `data/demo/demo_ss_001.json`

NEW_CONFIG = NONE。不新增环境变量、超时或提供者设置。

NO FEATURE FLAG。不增加 `F13_PREVIEW_ENABLED` 之类开关。当前生产会话路径默认带上 Preview。

不引入通用业务知识图谱、知识路由器、意图分类器、插件框架、提供者框架或事件总线。这是一层很薄的演示增强。

Alembic、PostgreSQL 迁移和业务数据迁移都不做。

## 17. Test Design

PROPOSED_TEST_SCOPE：

TEST_ADD：

- `tests/test_f13_preview_materials.py`
- `tests/test_f13_preview_session_integration.py`
- `tests/test_f13_preview_activation.py`

TEST_MODIFY：无。

TEST_UNCHANGED：全部现有测试，包括三份 F12 测试。

F13-Preview 测试默认不调用真实公司模型、真实 Redis、真实 PostgreSQL、向量加载或外网。依赖真实资源的旧测试在后续测试阶段静态排除，不靠试跑去碰外部资源。

### 单元测试

`tests/test_f13_preview_materials.py` 使用假的基础处理器和可控仓库，配合真实领域模型。需要核对公开过滤时，使用真实 `JsonBusinessRepository.get_materials` 默认公开模式。

- 首次确认：处理前为空，基础结果确认 `DEMO_SS_001`。原回复完整保留。增强文本包含“灵活就业人员社会保险费申报缴费”和“身份证”。不包含 `source_id`、核验状态、候选编号、已确认编号。
- 确认准备：候选存在且已确认为空。即使仓库能返回材料，查询次数也是 0，回复不变。
- 已经确认：恢复状态和基础结果都是 `DEMO_SS_001`。查询次数是 0，回复不变。
- 低置信和解释请求：基础结果的已确认编号仍为空，不查询、不展示。
- 无公开材料：事项和规范名称有效，公开材料为空。确认和编号保留，展示规范名称和“当前暂无可展示的办理材料信息。”
- 非公开材料：默认公开查询结果里不出现该材料名称。
- 仓库异常和未知业务：返回的回复、状态和已确认编号与基础结果一致，不伪造材料。
- 基础处理器直接抛异常：同一异常向外传播，仓库调用次数为 0。
- 状态不可变：增强前后办理状态深度相等。
- 无模型和无检索：Wrapper 构造参数和模块依赖不包含语言模型或 `SemanticRetrievalService`。不通过改写 F12 内部合法调用来下结论。

### 会话集成

选择 B：真实 Preview Wrapper、真实 `SessionTurnService`、假的基础处理器、内存会话存储。不使用真实 Redis。F12 会话测试里的 `MemoryStore` 是参照，F13 测试自备同等的内存存储，不改 F12 测试文件。

覆盖：

- 首次确认的公开结果带材料文本。
- 同一 `request_id` 和原文重放返回同一成功语义，处理器调用次数不增加。
- Preview 查询异常被 Wrapper 退让后，F11 仍按基础成功结果提交，不把本轮变成确认失败。

### 激活测试

`tests/test_f13_preview_activation.py` 检查 `build_session_router` 注入的处理器是 Preview Wrapper，并且其基础处理器是 `GovernmentAgentTurnProcessor`。两者共用同一个仓库实例。

构造或导入应用时材料查询次数为 0。健康检查仍为 200 和 `{"status":"ok"}`。公开接口仍只有既有 `POST /api/v1/session/turn` 字段，不新增材料或编号字段。不依赖 FastAPI 私有路由内部结构；沿用现有激活测试已经采用的 OpenAPI 观察方式。

### 回归

后续测试阶段必须运行：

- `tests/test_f12_turn_processor.py`
- `tests/test_f12_session_integration.py`
- `tests/test_f12_app_activation.py`

业务数据相关的本地安全回归：

- `tests/test_business_repository.py`
- `tests/test_business_data_contract.py`

`tests/integration/` 中需要数据库、向量或外网的测试不纳入本 Feature 的默认执行集合。

## 18. Test Scenario Traceability

| 场景 | 计划测试 | 依赖 | 期望 |
| --- | --- | --- | --- |
| T-F13P-001 | `test_f13_preview_materials.py` 首次确认 | 假处理器 + 可控仓库 | 原回复保留，含规范名称和“身份证” |
| T-F13P-002 | 同文件，确认准备 | 假处理器 + 查询计数仓库 | 查询 0 次，不展示 |
| T-F13P-003 | 同文件，已经确认 | 同上 | 查询 0 次，回复不变 |
| T-F13P-004 | 同文件，低置信 | 假处理器，已确认为空 | 不展示 |
| T-F13P-005 | 同文件，解释请求 | 同上 | 不展示 |
| T-F13P-006 | 同文件，公开材料为空 | 事项存在，材料列表为空 | 成功，保留编号，显示空材料提示 |
| T-F13P-007 | 同文件，非公开材料 | 真实 `get_materials` 默认公开模式 | 非公开名称不出现 |
| T-F13P-008 | 同文件，仓库异常 | 查询时抛异常 | 回复和状态等于基础成功结果 |
| T-F13P-009 | 同文件，未知事项 | `BusinessNotFoundError` | 原回复保留，不猜测 |
| T-F13P-010 | 同文件，基础异常 | 假处理器抛异常 | 异常原样传播，查询 0 次 |
| T-F13P-011 | 同文件，状态深度相等 | 假状态含 `f09`、`f10`、槽位、图转移 | 增强后状态不变 |
| T-F13P-012 | 同文件，依赖形状 | Wrapper 构造参数 | 无模型依赖 |
| T-F13P-013 | 同文件，依赖形状 | Wrapper 构造参数 | 无语义检索依赖 |
| T-F13P-014 | `test_f13_preview_activation.py` | 组合根与 OpenAPI | 公开字段不变 |
| T-F13P-015 | `test_f13_preview_session_integration.py` | 真实会话服务 + 内存存储 | 重放不第二次调用处理器 |
| T-F13P-016 | 现有三份 F12 测试，不改文件 | 既有 F12 测试替身 | Golden 回归继续通过 |

## 19. Requirement AC Traceability

| 验收项 | 设计落点 | 计划验证 |
| --- | --- | --- |
| AC-F13P-REQ01 | `is_first_confirmation` | T-F13P-001 |
| AC-F13P-REQ02 | 处理前读恢复状态，处理后读 `result.state` | T-F13P-001、T-F13P-003 |
| AC-F13P-REQ03 | 已确认为空则直接返回 | T-F13P-002 |
| AC-F13P-REQ04 | 空到非空才增强 | T-F13P-001 |
| AC-F13P-REQ05 | 非空到非空不触发 | T-F13P-003 |
| AC-F13P-REQ06 | 只把 `after_id` 传给仓库 | T-F13P-001 |
| AC-F13P-REQ07 | `get_business(...).canonical_name` | T-F13P-001 |
| AC-F13P-REQ08 | 默认 `get_materials` | T-F13P-001、T-F13P-007 |
| AC-F13P-REQ09 | Preview 不写第二套状态判断 | 代码范围审查 |
| AC-F13P-REQ10 | 原回复作前缀 | T-F13P-001 |
| AC-F13P-REQ11 | 有材料渲染 | T-F13P-001 |
| AC-F13P-REQ12 | 空列表走正常渲染 | T-F13P-006 |
| AC-F13P-REQ13 | Preview `try` 退让 | T-F13P-008 |
| AC-F13P-REQ14 | 基础调用在 `try` 外 | T-F13P-010 |
| AC-F13P-REQ15 | 未知业务退让 | T-F13P-009 |
| AC-F13P-REQ16 | `replace` 不改 `state` | T-F13P-011 |
| AC-F13P-REQ17 | 不写 `confirmed_business_id` | T-F13P-011 |
| AC-F13P-REQ18 | 不改 F12、F10、F11 实现 | 文件范围 + F12 回归 |
| AC-F13P-REQ19 | 无模型依赖 | T-F13P-012 |
| AC-F13P-REQ20 | 无检索依赖 | T-F13P-013 |
| AC-F13P-REQ21 | 无数据库结构变更 | 范围审查 |
| AC-F13P-REQ22 | 无新端点或端口 | 激活测试 |
| AC-F13P-REQ23 | 响应模型不改 | T-F13P-014 |
| AC-F13P-REQ24 | 复用 `_lookup_replay` | T-F13P-015 |
| AC-F13P-REQ25 | 不新增检查点结构 | 会话集成看提交状态仍是基础结果 |
| AC-F13P-REQ26 | `render_materials_preview` | T-F13P-001、T-F13P-006 |
| AC-F13P-REQ27 | 不排序 | 单元测试固定两条公开材料顺序 |
| AC-F13P-REQ28 | 渲染只用规范名称和 `source_text` | T-F13P-001 |
| AC-F13P-REQ29 | 不实现知识图谱 | 范围审查 |
| AC-F13P-REQ30 | 不读地点、渠道、依据 | 范围审查 |
| AC-F13P-REQ31 | Golden 名称来自受控数据 | T-F13P-001 |
| AC-F13P-REQ32 | Golden 材料为“身份证” | T-F13P-001 |
| AC-F13P-REQ33 | 渲染常量不含完整性承诺 | 渲染测试断言不含“仅需”“全部材料”“保证办理” |
| AC-F13P-REQ34 | 不改 F12 文件 | 范围审查 |
| AC-F13P-REQ35 | 第 18 节全部 16 项有归属 | 测试阶段按该表执行 |

## 20. Failure Matrix

| 失败 | 归属 | Preview 行为 | F12 状态 | 接口结果 |
| --- | --- | --- | --- | --- |
| 基础处理器异常 | F12 | 不捕获，不查询 | 不产生成功状态 | 异常继续传播，由 F11 按原失败语义处理 |
| 未知业务 | Preview | 退让，返回基础结果 | 保持基础成功状态和已确认编号 | 原成功回复 |
| 仓库异常 | Preview | 退让，返回基础结果 | 保持基础成功状态 | 原成功回复 |
| 畸形业务记录 | Preview | 渲染或读取抛错后退让 | 保持基础成功状态 | 原成功回复 |
| 材料查询异常 | Preview | 退让，返回基础结果 | 保持基础成功状态 | 原成功回复 |
| 公开材料为空 | 不是失败 | 正常追加空材料提示 | 保持基础成功状态 | 原回复加规范名称和空材料提示 |
| 渲染异常 | Preview | 退让，返回基础结果 | 保持基础成功状态 | 原成功回复 |

## 21. State Transition Matrix

| 处理前已确认编号 | 基础处理后已确认编号 | 是否展示 | 是否查询 |
| --- | --- | --- | --- |
| 空 | 空 | 否 | 否 |
| 空 | `DEMO_SS_001` | 是 | 是 |
| `DEMO_SS_001` | `DEMO_SS_001` | 否 | 否 |
| 非空 | 另一个非空 | 否 | 否 |

## 22. Response Matrix

| 场景 | 状态 | 回复 | 异常 |
| --- | --- | --- | --- |
| A. 有公开材料 | 等于基础结果 | 原回复加空行，再加事项名称和材料列表 | 无 |
| B. 公开材料为空 | 等于基础结果 | 原回复加空行，再加事项名称和空材料提示 | 无 |
| C. Preview 失败 | 等于基础结果 | 精确等于原回复 | 不向外抛出 |
| D. 基础失败 | 无成功状态 | 不构造材料回复 | 原异常向外传播 |

## 23. Security / Privacy

Preview 不需要用户身份证号、接口密钥或模型凭证。公开回复只出现事项规范名称和公开材料的 `source_text`。

日志不写用户原文、完整状态或来源明细。材料名称“身份证”是办事材料事实，不是个人证件号码。

## 24. Performance / External Resources

材料读取是进程内仓库查询。不新增模型调用、向量加载、语义检索、网络访问或数据库往返。不规定毫秒时限。

F13-Preview 自己的测试保持 0 次真实模型调用、0 次真实 Redis 命令、0 次真实 PostgreSQL 连接、0 次向量加载、0 次外网访问。

## 25. Non-Scope

不包含办理地点、渠道、条件、法律依据、时限、费用、咨询电话、大厅导航、导航图、业务知识图谱、政策百科、通用问答、同一会话改办事项、语音识别、前端、微信、自动填表和 RPA。

不改需求文档、F12 文档、F12 代码和 F12 测试。

## 26. Open Design Decisions

OPEN_BLOCKING_DESIGN_DECISIONS = 0。

规范名称和公开材料都有现有仓库接口。`AgentTurnResult` 可以用 `dataclasses.replace` 只替换回复。幂等发生在处理器之前。没有需要 Owner 另行决定的设计缺口。

## 27. Implementation Order

后续编码阶段按这个顺序，本文件不执行：

1. 新增 Preview Wrapper 和只读确认编号读取。
2. 完成首次确认判断。
3. 接入 `get_business` 与 `get_materials`。
4. 使用仓库默认公开过滤，不复制规则。
5. 完成确定性渲染和原回复追加。
6. 完成退让边界和安全日志。
7. 在组合根包装 F12 处理器，并复用同一仓库实例。
8. 新增单元测试。
9. 新增会话集成测试。
10. 新增激活测试。
11. 运行安全的 F12 回归和业务数据回归。

## 28. Technical Design Acceptance Criteria

| 编号 | 标准 |
| --- | --- |
| AC-F13P-TD01 | F12 处理器零修改 |
| AC-F13P-TD02 | Preview 实现现有 `AgentTurnProcessor.process_turn` 签名 |
| AC-F13P-TD03 | 基础处理器每次调用恰好一次 |
| AC-F13P-TD04 | 基础调用在退让捕获之外 |
| AC-F13P-TD05 | 处理前编号只读 |
| AC-F13P-TD06 | 处理后编号只读 |
| AC-F13P-TD07 | 仅空到非空触发 |
| AC-F13P-TD08 | 已经确认不查询 |
| AC-F13P-TD09 | 只有候选时不查询 |
| AC-F13P-TD10 | 查询键只能是已确认编号 |
| AC-F13P-TD11 | 规范名称来自 `get_business(...).canonical_name` |
| AC-F13P-TD12 | 复用现有仓库接口 |
| AC-F13P-TD13 | 复用默认公开材料过滤 |
| AC-F13P-TD14 | 不复制核验逻辑 |
| AC-F13P-TD15 | 保持仓库返回顺序 |
| AC-F13P-TD16 | 展示字段是 `source_text` |
| AC-F13P-TD17 | 确定性渲染，不调用模型 |
| AC-F13P-TD18 | 原 F12 回复作为精确前缀 |
| AC-F13P-TD19 | 成功时只改 `response_text` |
| AC-F13P-TD20 | `state` 内容不变 |
| AC-F13P-TD21 | `requires_user_input` 不变 |
| AC-F13P-TD22 | `public_status` 不变 |
| AC-F13P-TD23 | 空公开材料是受控成功 |
| AC-F13P-TD24 | 未知业务退让 |
| AC-F13P-TD25 | 仓库异常退让 |
| AC-F13P-TD26 | 渲染异常退让 |
| AC-F13P-TD27 | 不编造材料 |
| AC-F13P-TD28 | 无模型依赖 |
| AC-F13P-TD29 | 无检索依赖 |
| AC-F13P-TD30 | 无向量依赖 |
| AC-F13P-TD31 | 无新数据库结构 |
| AC-F13P-TD32 | 无新网络依赖 |
| AC-F13P-TD33 | 复用同一个仓库实例 |
| AC-F13P-TD34 | F11 仍拥有会话 |
| AC-F13P-TD35 | 无新检查点结构 |
| AC-F13P-TD36 | 无第二套幂等 |
| AC-F13P-TD37 | 公开接口字段不变 |
| AC-F13P-TD38 | `main.py` 不改 |
| AC-F13P-TD39 | 业务数据不改 |
| AC-F13P-TD40 | 决策图不改 |
| AC-F13P-TD41 | F10 实现不改 |
| AC-F13P-TD42 | 组合根只做接线 |
| AC-F13P-TD43 | 构造和导入时不查材料 |
| AC-F13P-TD44 | 健康检查不受影响 |
| AC-F13P-TD45 | 16 个需求场景全部映射 |
| AC-F13P-TD46 | 要求 F12 回归 |
| AC-F13P-TD47 | F13P 测试不使用真实外部资源 |
| AC-F13P-TD48 | 失败日志不含原文、状态和来源 |
| AC-F13P-TD49 | 不输出内部来源元数据 |
| AC-F13P-TD50 | 范围外事项保持排除 |
| AC-F13P-TD51 | 阻塞性设计决策为 0 |

## 29. Current Feature State

- F12：CLOSED
- F13-Preview Resource Gate：PASS / OWNER REVIEW APPROVED
- F13-Preview Requirement：APPROVED / FROZEN / REMOTE-FROZEN
- F13-Preview Technical Design：DRAFT COMPLETE / READY FOR OWNER REVIEW
- Code：NOT STARTED
- Test：NOT STARTED
- Commit：NOT STARTED
- Push：NOT STARTED

本技术设计尚未批准，也尚未冻结。
