# F03 Code Reading Guide — Business Graph Domain and JSON Repository

面向第一次阅读本项目 Decision Graph / Repository 的开发者（懂 Python / Pydantic 基础，并已了解 F02 Business Data Contract）。

**核心问题：**

> 「用户要办哪个事项」如何变成确定性、可校验的图？事项确定后，材料/地点/渠道从哪里确定性取回？

最新验证证据：

| 项 | 结果 |
|----|------|
| Python | 3.11.16（govagent） |
| F03 targeted | **45 passed** |
| Full pytest | **89 passed**, 0 failed, 0 skipped |
| compileall | PASS |
| pip check | PASS |
| warning | 1 个已知 StarletteDeprecationWarning（upstream，非 F03 Blocking） |

---

## 1. F03 在整体架构中的位置

```
用户自然语言
        ↓
未来 LLM NLU（槽位抽取 / 受控映射 / confidence）
        ↓
未来 Semantic Retrieval（找方向 → graph_id）
        ↓
F03 Decision Graph 静态定义（Node / Edge / Terminal Candidate）
        ↓
未来 F04 deterministic transition（next_node — 尚未实现）
        ↓
Terminal Candidate（candidate_business_id）
        ↓
未来 F04 Rule Engine + 用户最终确认
        ↓
confirmed business_id
        ↓
F03 JsonBusinessRepository（exact id → 事实）
        ↓
材料 / 地点 / 渠道 / 法律依据 / Condition
        ↓
Runtime Knowledge Relation View（可重建投影）
```

**F03 已经定义：** 图长什么样、怎么校验、怎么按 id 查事实。  
**F03 还没有执行：** `next_node(...)`、会话槽位推进、Rule PASS/FAIL、用户确认。

| Feature | 回答的问题 |
|---------|------------|
| **F02** | 官方到底说了什么？（BusinessSnapshot） |
| **F03** | Decision Graph 怎么组织？事实怎么按 id 查询？ |
| **F04** | 确定性路径推进 + Rule 终审（未启动） |
| **F06** | Semantic Retrieval 如何落到 `graph_id`（未启动） |

---

## 2. 三种「图」不要混

| 概念 | 回答 | F03 是否覆盖 |
|------|------|--------------|
| **Business Decision Graph** | 「办哪个？」路径缩小到候选事项 | **是**（Domain + JSON） |
| **Business Knowledge** | 「怎么办？」材料/地点/渠道/依据 | **是**（Repository + Relation View） |
| **Navigation Graph** | 「怎么走到窗口？」 | **否**（未来到厅引导） |

Decision Graph 例子：

```text
service_action = payment
→ payment_actor = self_payment
→ employment_type = other_flexible_employment
→ candidate_business_id = DEMO_SS_001
```

Knowledge 例子（同一事项）：

```text
DEMO_SS_001 HAS_MATERIAL → mat-id-card（身份证）
DEMO_SS_001 HANDLED_AT → loc-jianguo-south（建国南路办公区）
DEMO_SS_001 AVAILABLE_VIA → ch-alipay 等
DEMO_SS_001 HAS_LEGAL_BASIS → legal-social-insurance-law-60
```

---

## 3. 推荐阅读顺序

| 顺序 | 文件 | 为什么现在看 |
|------|------|--------------|
| 1 | `data/graphs/demo/social_security.json` | 先看 7 Node / 11 Edge 长什么样 |
| 2 | `business_graph/models.py` | 再看字段如何被 Contract 约束 |
| 3 | `business_graph/validation.py` | 结构校验 + 交叉引用校验 |
| 4 | `business_graph/loader.py` | 最短加载链路 |
| 5 | `business_data/repository.py` | exact query / PUBLIC / Relation |
| 6 | `tests/test_business_graph.py` | Graph invariant 怎么被测住 |
| 7 | `tests/test_business_repository.py` | Repository / PUBLIC 怎么被测住 |
| 8 | `docs/features/F03-...md` | Feature 范围与阶段权威 |

**先 JSON、后 Model：** 先理解 Demo 路径，再理解代码为什么这样约束它。

---

## 4. `social_security.json` 看什么

不要逐行背 JSON，抓住顶层：

| 字段 | 含义 |
|------|------|
| `schema_version` | Decision Graph **Contract 格式**版本（当前 `"1"`） |
| `graph_id` | 稳定图标识：`social_security`（未来 F06 可对齐） |
| `graph_version` | **图内容**版本（当前 `1`） |
| `data_scope` | `DEMO` |
| `entry_node_id` | `social_security_entry` |
| `nodes` | **7** |
| `edges` | **11** |

唯一正式 Terminal Candidate：`DEMO_SS_001`。  
**没有**正式 `DEMO_SS_002` Business（转移走 `UNSUPPORTED`）。

### 三个版本不要混

| 版本字段 | 属于 | 含义 |
|----------|------|------|
| Graph `schema_version` | F03 Graph Contract | 图 JSON 字段格式 |
| Graph `graph_version` | F03 Graph 内容 | 节点/边改动 |
| Business `data_version` | F02 Snapshot | 业务事实内容 |

---

## 5. NodeType（通俗版）

| NodeType | 一句话 |
|----------|--------|
| `ENTRY` | 图入口；整图恰好 1 个；无 incoming；有且仅有 1 条 `ENTRY_FORWARD` |
| `SLOT_GATE` | 单标准 slot 门：`slot_name` + `allowed_values` + `question_text` |
| `TERMINAL_CANDIDATE` | 产出 `candidate_business_id`（**候选**，不是确认成功） |
| `UNSUPPORTED` | 方向识别到了，但无正式 Source / 无绑定正式事项 |
| `FALLBACK` | 受控出口（无法继续缩小意图） |

`TERMINAL_CANDIDATE` / `UNSUPPORTED` / `FALLBACK` 都是**终止节点**：不得有 outgoing Edge。  
多个路径可以汇聚到同一个 Terminal（例如三种 `employment_type` 都进 `DEMO_SS_001`）。

---

## 6. 为什么 Single Slot Gate

以 `social_security_action` 为例：

- `slot_name = service_action`
- `allowed_values = payment | transfer | inquiry | other`

**一个 Gate 只负责一个标准 slot。**  
未来 F04：读一个 slot → 找一个合法值 → **唯一** Edge。  
不要理解成「节点里可以写任意复杂条件表达式」。

### `question_text` 是什么

只是：slot **缺失**时，Agent 可用的固定群众问句。

例如：`payment_actor` →「这次社保缴费主要是单位缴，还是您自己缴？」

它**不参与**边匹配本身。若用户一开始就说「我自己交社保」，未来 NLU 已得到 `payment_actor=self_payment`，F04 可直接用已有值，**不必机械重问**。

---

## 7. LLM 边界（固定）

未来 LLM **只**类似输出：

```text
slot_name: payment_actor
normalized_value: self_payment
confidence: 0.93
```

LLM **不**输出：`next_node` / `edge_id` / `candidate_business_id` / `confirmed_business_id`。

下一步由程序根据：

```text
current_node + 合法 slot 值 + 预定义 Edge
```

确定性计算（**F04**，尚未实现）。

---

## 8. EdgeKind：为什么只有两种

| EdgeKind | 用途 |
|----------|------|
| `ENTRY_FORWARD` | 仅 `ENTRY →` 首个 Gate；**无 match** |
| `SLOT_MATCH` | 仅 `SLOT_GATE` 发出；必须带 `SlotMatch` |

`ENTRY_FORWARD` **不是** DEFAULT / ANY / ELSE / wildcard。  
刻意禁止「隐式无条件边」，避免把流程逻辑藏进默认边。

### 为什么 SlotMatch 只有 EQ

一期 `operator` **只有 `EQ`**。

即使三种 `employment_type` 都指向同一 Terminal，也写 **三条明确 EQ Edge**，而不是 `IN`。

原因：更容易审查、更容易测试、不会演化成 Rule DSL。

### allowed_values 全覆盖（核心 invariant）

每个 `SLOT_GATE`：

```text
outgoing SLOT_MATCH.match.value 集合
  ==
allowed_values 集合
```

不是「最多一条」，而是：**每个合法值恰好一条 Edge**。  
于是：合法 slot 值 → 未来 F04 必然找到唯一确定路径。

例：`payment_actor` 的 `self_payment` / `employer_payment` / `other` 必须各有一条边。

---

## 9. design_basis 与 SourceConditionRef

| design_basis | 含义 |
|--------------|------|
| `SYSTEM_DESIGNED` | 对话组织方式（如「缴费还是转移」），不必是指南原文规则 |
| `SOURCE_SUPPORTED` | 分流设计有 F02 Condition 作依据；**仍 ≠ VERIFIED Rule** |
| `TEST_ONLY` | 仅测试夹具，不得混入正式 DEMO 群众路径依据 |

### SourceConditionRef

```text
business_id + condition_id
例：DEMO_SS_001 + cond-applicant-01
```

必须带 `business_id`：未来不同 Business 可能出现相同 `condition_id`，不能全局乱猜。

Graph JSON **只引用** id，不复制 `source_text` / Evidence / Material / Location。

### SOURCE_SUPPORTED ≠ Rule（重点）

`employment_type` Node 与三条 → Terminal Edge 使用 `SOURCE_SUPPORTED`，引用 `cond-applicant-01/02/03`。

这只表示：**对话分流有 Source 语义支撑**。  
当前 `DEMO_SS_001` 仍然：**Executable Rule = 0，VERIFIED Rule = 0**。  
不得把 Decision Edge 当成官方资格校验已通过。

`service_action` / `payment_actor` 多为 `SYSTEM_DESIGNED`：是对话组织，不是办事指南资格条款。

---

## 10. 两层 Validation

### 第一层：`validate_graph_structure(graph)`

**只看 Graph 自己**，不访问 Repository。

主要包括：

1. `node_id` / `edge_id` 唯一  
2. 整图恰好 1 个 `ENTRY`，且等于 `entry_node_id`  
3. ENTRY 无 incoming；有且仅有 1 条 `ENTRY_FORWARD`  
4. from/to 存在；`ENTRY_FORWARD` 只能从 ENTRY；`SLOT_MATCH` 只能从 SLOT_GATE  
5. `match.slot` 对齐；`match.value` ∈ allowed；**全覆盖且无重叠**  
6. Terminal-like 无 outgoing  
7. **无环（DAG）**；**全部节点从 ENTRY reachable**

不合法 → `GraphStructureError` fail-fast。

### 为什么无环 / 必须可达

- **无环：** Intent Switch 不应在图里绕圈；应退出当前 Graph → 重新 Semantic Retrieval → 新 `graph_entry`。UI「返回上一问」优先做 session/runtime action，而不是 Graph cycle。  
- **可达：** 死节点 / 废弃节点直接 fail-fast，不留「永远走不到」的配置。

### 第二层：`validate_graph_business_refs(graph, repository)`

需要 Graph + Repository。**DecisionGraph Model 不 import Repository**；Loader 也不自动做这一层。

校验：

| 项 | 规则 |
|----|------|
| Terminal | `candidate_business_id` 存在且 `Business.status == ACTIVE` |
| SourceConditionRef | `(business_id, condition_id)` 真实存在 |

**不检查** Condition 是否 VERIFIED / executable——Source 支撑 ≠ Rule 执行。

### 为什么 INACTIVE 不能当 Terminal

Business 还在索引里 ≠ 可办。`status=INACTIVE` 时 Cross Validation 失败，避免停用事项继续进入群众候选路径。

---

## 11. Loader 调用链

```text
load_decision_graph(path)
        ↓ UTF-8 read
DecisionGraph.model_validate_json(...)
        ↓ schema_version == "1"
validate_graph_structure(graph)
        ↓
DecisionGraph
```

Loader **不**：创建 Repository、访问 Business Data、做 Cross Validation、修 JSON、fallback。

### 最小示例（真实 API）

```python
from pathlib import Path
from gov_service_agent.business_graph import load_decision_graph

graph = load_decision_graph(
    Path("data/graphs/demo/social_security.json")
)
print(graph.graph_id)  # social_security
```

**不要**调用还不存在的 `next_node(...)`。

完整加载 + 交叉校验：

```python
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.business_graph import (
    load_decision_graph,
    validate_graph_business_refs,
)

graph = load_decision_graph(Path("data/graphs/demo/social_security.json"))
repo = JsonBusinessRepository.from_paths(
    [Path("data/demo/demo_ss_001.json")]
)
validate_graph_business_refs(graph, repo)
```

---

## 12. JsonBusinessRepository

| 层 | 职责 |
|----|------|
| F02 `BusinessSnapshot` | 单个事项事实 Contract |
| F03 Repository | 加载多个 Snapshot，建 `business_id → snapshot` 索引，exact query |

Repository **不做**：语义检索、模糊搜索、LLM、Graph traversal、Rule evaluation。

### 为什么只有 `from_paths`

```python
JsonBusinessRepository.from_paths([
    Path("data/demo/demo_ss_001.json"),
])
```

调用方**明确**知道加载了哪些业务；不会自动把 TEST / DEMO / PRODUCTION 扫进同一索引。

| 错误场景 | 行为 |
|----------|------|
| 未知 `business_id` | `BusinessNotFoundError`（不是 None / {} / fallback） |
| 重复 `business_id` | `DuplicateBusinessError` fail-fast（不是后写覆盖） |

空列表 `[]` 只表示「Business 存在但该类事实为空」——Business 不存在必须抛错。

---

## 13. ConsumptionMode：PUBLIC / INTERNAL

所有群众 fact getter **默认 `PUBLIC`**。

| 模式 | 用途 |
|------|------|
| `PUBLIC` | 可作为面向群众的正式办理信息 |
| `INTERNAL` | 调试 / 复核 / 数据治理（可见 TO_CONFIRM） |

**INTERNAL ≠ VERIFIED ≠ Rule 可执行。**

### 真实 DEMO Condition 数量

| Mode | 数量 | 内容 |
|------|------|------|
| PUBLIC | **3** | SOURCE_EXPLICIT applicant scope |
| INTERNAL | **7** | 另含 4 条 TO_CONFIRM |

TO_CONFIRM 字段名（仅 INTERNAL）：`flex_registration_completed` / `payment_occasion` / `household_registration` / `insurance_enrollment_status`。

### PUBLIC 不是 `!= TO_CONFIRM`

Allowlist + fail-closed：

| 状态 | PUBLIC |
|------|--------|
| `SOURCE_EXPLICIT` | 可 |
| `VERIFIED` | 可 |
| `SYSTEM_DERIVED` | 仅 lineage 完整时可 |
| `TO_CONFIRM` | 不可 |
| 其它未知 | fail-closed |

### SYSTEM_DERIVED lineage（真实例子）

```text
身份证（SOURCE_EXPLICIT + Evidence）
  → requirement_level=REQUIRED（SYSTEM_DERIVED + derivation_note）

支付宝（SOURCE_EXPLICIT + Evidence）
  → channel_type=ONLINE（SYSTEM_DERIVED + channel_type_rule）
```

派生值必须有 normalization/derivation metadata，以及 SOURCE_EXPLICIT 基础事实 + Evidence——不是凭空产生。

### 为什么返回完整 Entity

Repository **不**另造 `PublicMaterial` 等第二套 DTO。  
整实体过 PUBLIC gate → 返回原 F02 Entity；不过 → **整条**不返回。  
若 Raw Fact 合法但 `normalized_status=TO_CONFIRM`，整条 Condition 仍不可 PUBLIC。

### `get_snapshot` 不是群众 API

`get_snapshot()`：原始内部访问，**不做** PUBLIC Filtering；返回的是共享可变对象。  
不要把 `get_snapshot()` 结果原样当作群众响应（RF-F03-008 Deferred 的原因之一）。一期靠开发约束：调用方不要原地改 Snapshot。

---

## 14. Knowledge Relation View

轻量 DTO：

```text
business_id + relation_type + target_type + target_id
例：DEMO_SS_001 / HAS_MATERIAL / MATERIAL / mat-id-card
```

Relation **不内嵌**「身份证」全文；详情仍走 `get_materials` 等。

### 不是第二真相源

每次从当前 `BusinessSnapshot` **运行时投影**。  
没有 `relations.json` / `knowledge_facts.json` / 第二份材料表。  
Business Data 更新后，Relation 可重建。

`list_relations(..., consumption=PUBLIC)` 复用同一套 PUBLIC getters，避免两套过滤逻辑漂移。

### 真实 DEMO Relation 数量

| Mode | Material | Location | Channel | LegalBasis | Condition | **合计** |
|------|----------|----------|---------|------------|-----------|----------|
| PUBLIC | 1 | 1 | 6 | 1 | 3 | **12** |
| INTERNAL | 1 | 1 | 6 | 1 | 7 | **16** |

PUBLIC 不得出现 4 条 TO_CONFIRM 的 `HAS_CONDITION`。

---

## 15. 一条未来路径（仅说明 F04 如何消费）

用户：「我辞职了，现在没单位，想自己继续交社保。」

未来 NLU 可能得到：

```text
service_action = payment
payment_actor = self_payment
employment_type = other_flexible_employment
```

未来 F04 可走（**F03 只存/校验，不执行**）：

```text
social_security_entry
  --ENTRY_FORWARD-->
social_security_action (payment)
  --> payment_actor (self_payment)
  --> employment_type (other_flexible_employment)
  --> terminal_demo_ss_001
```

得到：`candidate_business_id = DEMO_SS_001`。

### Terminal 后还缺什么

```text
Terminal Candidate
    ↓ 未来 F04 Rule Engine
    ↓ 用户最终确认
confirmed business_id
```

当前 DEMO_SS_001 **没有任何 VERIFIED executable Rule**——F04 不得伪造资格校验结果。

Rule Engine 未来只消费：

```text
executable is not None
AND verification_status == VERIFIED
AND usable_by_rule_engine == true
```

与 Decision Edge **物理分离、语义分离**。

---

## 16. 如何调试

### Graph

| 现象 | 先看 |
|------|------|
| JSON 加载失败 | Pydantic `ValidationError`（未知字段 / 条件字段） |
| 结构失败 | `GraphStructureError` |
| allowed_values 问题 | Gate 的 allowed 与 outgoing match values 是否集合相等 |
| cycle | from/to 是否回边 |
| unreachable | 从 `entry_node_id` 向外走是否漏节点 |
| Cross 失败 | `candidate_business_id` 或 `SourceConditionRef` |

推荐断点：`load_decision_graph` → `validate_graph_structure` → `validate_graph_business_refs`。

### Repository

| 现象 | 先看 |
|------|------|
| `BusinessNotFoundError` | `from_paths` 是否加载了该 Snapshot |
| `GraphBusinessRefError` | Terminal / ConditionRef |
| PUBLIC 数据偏少 | VerificationStatus、derived status、lineage、Evidence |

---

## 17. 测试怎么读

| 类 | 例子 |
|----|------|
| **A. Graph Contract / Structural** | 第二 ENTRY、cycle、缺 Edge、重复 value、错误 from type、非 EQ |
| **B. Repository / Public** | PUBLIC=3、INTERNAL=7、unknown/duplicate Business |
| **C. Cross Validation** | unknown candidate、unknown ConditionRef、INACTIVE terminal |

测试里的非法 Graph 只是 fixture，不是正式业务配置。

---

## 18. Review Findings（摘要）

| ID | 状态 |
|----|------|
| RF-F03-001～006 | **CLOSED**（专测 / 文档已补） |
| RF-F03-007 | **Deferred** — SYSTEM_DERIVED 基底策略；未来 VERIFIED+derived 再确认 |
| RF-F03-008 | **Deferred** — `get_snapshot` 共享可变 Snapshot |
| RF-F03-009 | **Deferred** — RelationType/TargetType 配对 validator |

---

## 19. 哪些东西不能随便改

1. 不能给 Graph 加 wildcard / default / ELSE edge  
2. 不能让 LLM 返回 `next_node`  
3. 不能把 `SOURCE_SUPPORTED` 理解成 `VERIFIED`  
4. 不能把 Decision Edge 当 Eligibility Rule  
5. 不能把 Terminal Candidate 当 confirmed business  
6. 不能把 `TO_CONFIRM` 暴露到 PUBLIC  
7. 不能新增 `relations.json` 作为第二事实源  
8. 不能为了图完整伪造 `DEMO_SS_002` Business  
9. 不能写入未确认的政务服务中心地址  
10. 不能把 `get_snapshot()` 直接当群众公开响应  

---

## 20. F04 / F06 如何接（方向，非已实现 API）

### F04 Transition（未实现）

概念输入：`DecisionGraph` + `current_node_id` + session slots + confidence policy。

概念步骤（**不要当成现有函数**）：

```text
若 current 是 SLOT_GATE：
  读 slot_name
  session 已有合法值？ → 找唯一 SLOT_MATCH
  没有？ → Agent 用 question_text 提问
若 current 是 ENTRY：
  走唯一 ENTRY_FORWARD
```

### F04 Rule Engine（未实现）

只消费 VERIFIED + usable executable；与 Graph Edge 分开。当前 DEMO 可执行规则数 = **0**。

### F06 Semantic Retrieval（未实现）

可输出 `graph_id=social_security` → 取 `entry_node_id=social_security_entry`。  
进入 Graph 后，用户每句回答**默认不**重新全局向量检索；仅首次进入或 Intent Switch 再 Retrieval。

---

## 21. 相关文档

| 文档 | 用途 |
|------|------|
| `docs/features/F03-business-graph-domain-and-json-repository.md` | Feature 范围与阶段权威 |
| `docs/code-reading/F02-demo-ss-001-business-data-contract-reading-guide.md` | F02 Contract 基础 |
| `docs/project/open-items.md` | 跨 Feature 待确认项 |
| `AGENTS.md` | 核心架构原则 |
