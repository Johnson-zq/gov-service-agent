# F02 Code Reading Guide — DEMO_SS_001 Business Data Contract

面向第一次接触本项目 Business Data Contract 的开发者（懂 Python / FastAPI 基础即可）。

**核心问题：**

> 官方办事指南说了什么，如何变成可校验、可溯源的结构化数据？F03/F04 以后如何消费？

最新验证证据：

| 项 | 结果 |
|----|------|
| Python | 3.11.16（govagent） |
| F02 targeted | **15 passed** |
| Full pytest | **44 passed**, 0 failed, 0 skipped |
| compileall | PASS |
| pip check | PASS |
| warning | 1 个已知 StarletteDeprecationWarning（upstream，非 F02 Blocking） |

---

## 1. F02 在整个项目中的位置

```
官方办事指南（Authoritative Evidence）
        ↓  人工整理 + 确定性标准化（不是 LLM 生成）
demo_ss_001.json（Runtime Source of Truth）
        ↓  Pydantic Contract 校验
BusinessSnapshot（内存中的合法对象）
        ↓  未来 F03
Repository / Graph 投影
        ↓  未来 F04
Rule Engine（仅 VERIFIED Executable Rule）
```

### 1.1 两层真相，不要混

| 层 | 是什么 | 谁读它 |
|----|--------|--------|
| **Authoritative Evidence** | 官方办事指南、授权业务确认 | 人：整理与纠错依据 |
| **Runtime Source of Truth** | 结构化 JSON / `BusinessSnapshot` | 程序：Graph、API、Rule |

程序**运行时不读 Word**。但如果 JSON 与正式指南冲突：

> 以 Authoritative Evidence 为准，**修正**结构化 Business Data——不是反过来认为「JSON 更权威」。

### 1.2 为什么 F02 还没有 Graph

| Feature | 回答的问题 |
|---------|------------|
| **F02** | 官方到底说了什么？（事实 + 溯源 + 校验状态） |
| **F03** | Business Graph 怎么组织、怎么查询？ |
| **F04** | 确定性 Rule 怎么终审？ |

F02 **有意不包含**：Decision Node/Edge、Knowledge Graph runtime、Graph Transition、Rule Engine。  
这是 Feature 边界，不是功能缺失。

---

## 2. 推荐阅读顺序

| 顺序 | 文件 | 为什么现在看 |
|------|------|--------------|
| 1 | `data/demo/demo_ss_001.json` | 先看真实数据长什么样 |
| 2 | `src/gov_service_agent/business_data/models.py` | 再看代码如何约束这些数据 |
| 3 | `src/gov_service_agent/business_data/__init__.py` | 包对外导出什么 |
| 4 | `tests/test_business_data_contract.py` | 契约如何被测住 |
| 5 | `docs/project/open-items.md` | 哪些事还没定，不能写进正式事实 |

**先 JSON、后 Model：** 没有具体数据，抽象字段很难落地。

---

## 3. `demo_ss_001.json` 长什么样

### 3.1 两个「版本」别搞混

| 字段 | 位置 | 含义 |
|------|------|------|
| `schema_version` | Snapshot 顶层 | **Contract 格式**版本（当前 `"1"`） |
| `data_version` | `business` 内 | **业务内容**版本（当前 `1`） |

改 JSON 字段结构 → 可能升 `schema_version`。  
改事项事实内容 → 升 `data_version`（一期在 Business / Snapshot 级维护，子实体不单独版本）。

### 3.2 七个顶层块各自干什么

| 块 | 职责 | 当前 DEMO 规模 |
|----|------|----------------|
| `business` | 事项主档 + Metadata | 1 |
| `sources` | 整份资料级来源 | 1 |
| `materials` | 申请材料 | 1 |
| `handling_locations` | 线下受理地点 | 1 |
| `channels` | 缴费/办理渠道 | 6 |
| `legal_basis` | 法律依据 | 1 |
| `conditions` | 条件描述 / 标准化 /（未来）可执行规则 | 3 SOURCE_EXPLICIT + 4 TO_CONFIRM |

真实例子：

- `business.canonical_name` = `灵活就业人员社会保险费申报缴费`
- `materials[0].source_text` = `身份证`
- `handling_locations[0].name` = `国家税务总局杭州市上城区税务局建国南路办公区`
- **没有**「上城区政务服务中心」

---

## 4. Raw Fact vs Normalized Value

这是 F02 最重要的设计点：**原文事实**与**系统标准化值**必须分开标状态。

| 例子 | 原文层 | 标准化层 |
|------|--------|----------|
| 材料 | `身份证` → **SOURCE_EXPLICIT** | `REQUIRED` → **SYSTEM_DERIVED** |
| 渠道 | `支付宝` → **SOURCE_EXPLICIT** | `ONLINE` → **SYSTEM_DERIVED** |
| 渠道用途 | 指南栏目语义「缴费渠道」 | `PAYMENT` → **SYSTEM_DERIVED** |
| 申请对象 | `无雇工的个体工商户` → **SOURCE_EXPLICIT** | `self_employed_without_employees` → **SYSTEM_DERIVED** |

标准化来自**人工整理 + 确定性规则**（如 `applicant_scope_v1`、`channel_type_v1`），**不是 LLM 推断**。

---

## 5. VerificationStatus（通俗版）

| 状态 | 一句话 |
|------|--------|
| **SOURCE_EXPLICIT** | 官方 Source 明确写了 |
| **SYSTEM_DERIVED** | 系统按明确规则从原文标准化出来（须可回溯） |
| **TO_CONFIRM** | 还没依据 / 有冲突 / 待确认；可内部看，**不能**当面向群众的确定性办理事实 |
| **VERIFIED** | 业务确认后，才可作正式规则 / 高可信事实 |

**关键：**

- `SOURCE_EXPLICIT` ≠ 可执行 Rule  
- `SYSTEM_DERIVED` ≠ 可执行 Rule  
- 当前 **DEMO_SS_001 没有任何 VERIFIED Executable Rule**

---

## 6. Condition 三层（看真实 ID）

### 6.1 `cond-applicant-01`（申请对象）

| 层 | 字段 | 值 |
|----|------|-----|
| Layer 1 Source | `source_text` | `无雇工的个体工商户`（SOURCE_EXPLICIT） |
| Layer 2 Normalized | `field` / `normalized_values` | `employment_type` / `self_employed_without_employees`（SYSTEM_DERIVED） |
| Layer 3 Executable | `executable` | **`null`** |

为什么不能直接进 Rule Engine？因为还没有业务确认把它升级成 **VERIFIED Executable Rule**（见 OI-F02-02）。展示「指南写了什么」可以；自动 PASS/FAIL 不行。

### 6.2 `flex_registration_completed`（旧假设）

- `source_status = TO_CONFIRM`
- `executable = null`
- 指南**没有**证明它是 DEMO_SS_001 必要条件

同类还有：`payment_occasion`、`household_registration`、`insurance_enrollment_status`。

---

## 7. ContractModel 与 `extra="forbid"`

所有 Contract 实体继承内部基类：

```python
class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

（`ContractModel` **不是**业务实体，也不从 `__init__.py` 导出。）

**以前：** 拼错字段可能被静默忽略。  
**现在：** `canonical_nam` 这类未知键 → `ValidationError` → **fail-fast**。

政务业务数据：**宁可加载失败，也不能悄悄丢字段继续跑。**

---

## 8. EvidenceRef：事实级溯源

```text
SourceRecord          = 整份资料（例如某一份办事指南 .doc）
EvidenceRef           = 某一条事实来自哪份资料的哪个栏目/摘录
```

| 字段 | 作用 |
|------|------|
| `source_id` | 指向 `sources[]` |
| `source_section` | 如「申请材料」「受理地点」「缴费渠道」 |
| `source_excerpt` | 可选原文摘录（当前 DEMO 多为 null） |

例：材料「身份证」不仅知道来自 `src-demo-ss-001`，还知道栏目是 **申请材料**。  
`SOURCE_EXPLICIT` 事实必须能挂上有效 `EvidenceRef`（Condition 的 TO_CONFIRM 可为 null）。

原始文件名在 SourceRecord：`灵活就业人员社会保险费申报缴费.doc`（仅文件名，无本机绝对路径；原始 Word **不进**源码仓）。

---

## 9. 为什么 Snapshot 内 ID 必须唯一

同一 Snapshot 内唯一：

`source_id` / `material_id` / `location_id` / `channel_id` / `legal_basis_id` / `condition_id`

若两个 Channel 都叫 `ch-alipay`，未来 F03 `get_channel("ch-alipay")` 会歧义。  
Contract：**重复 → ValidationError（`duplicate channel_id: ...`）**，不去重、不覆盖。

---

## 10. `load_snapshot` 调用链

```
load_snapshot(Path("data/demo/demo_ss_001.json"))
        ↓
Path.read_text(encoding="utf-8")
        ↓
BusinessSnapshot.model_validate_json(...)
        ↓
各子模型字段 / 状态校验（Evidence、SYSTEM_DERIVED lineage、Executable 约束…）
        ↓
BusinessSnapshot 跨实体校验（引用存在 + ID 唯一）
        ↓
成功 → BusinessSnapshot
失败 → ValidationError（fail-fast）
```

**不会：** 自动修数据、fallback、忽略未知字段、偷偷重写 JSON、刷新 `updated_at`。

### 最小可运行示例

```python
from pathlib import Path
from gov_service_agent.business_data import load_snapshot

snapshot = load_snapshot(Path("data/demo/demo_ss_001.json"))
print(snapshot.business.business_id)       # DEMO_SS_001
print(snapshot.materials[0].source_text) # 身份证
```

不要写还不存在的 Repository API。

---

## 11. 当前 DEMO 数据一览

| 项 | 数量 / 值 |
|----|-----------|
| Business | 1（`DEMO_SS_001`） |
| Material | 1（身份证） |
| Location | 1（建国南路办公区；`floor`/`window` = null） |
| Channel | 6 |
| LegalBasis | 1（社会保险法第六十条） |
| SOURCE_EXPLICIT Condition | 3（applicant_scope） |
| TO_CONFIRM Condition | 4 |
| Executable Rule | **0** |
| VERIFIED Rule | **0** |

地点只能说指南里的税务局建国南路办公区，**不能**说成上城区政务服务中心。

---

## 12. Open Items ≠ TO_CONFIRM Condition

| | Open Items（`docs/project/open-items.md`） | TO_CONFIRM Condition |
|--|---------------------------------------------|----------------------|
| 是什么 | **项目级**待确认事项 | **数据模型内**可能未来变字段/规则的假设 |
| 进不进运行时 Contract | 否 | 是（JSON 里可见） |
| 例子 | OI-F02-01 政务服务中心是否可办 | `flex_registration_completed` |

重点 Open Items：

- **OI-F02-01**：是否可在政务服务中心办理（阻塞未来导航/到场）
- **OI-F02-02**：applicant_scope 是否升级 VERIFIED Rule（阻塞 F04 正式规则）
- 另有原始资料 Git 授权、DEMO_GA_001 映射、DEMO_SS_002 待 Source 等

---

## 13. 测试怎么理解

### 第一类：Contract invariant（通用结构）

未知字段失败、重复 ID 失败、SOURCE_EXPLICIT 缺 Evidence、SYSTEM_DERIVED 缺 lineage、TO_CONFIRM 不可 executable、非 VERIFIED executable 失败……

→ 写在 **Pydantic validators** + 对应负向测试。

### 第二类：DEMO acceptance（业务验收）

正式事项名称、身份证、建国南路地点、无政务服务中心、Executable Rule = 0……

→ 写在 **pytest**，**不要**把「身份证」「建国南路」硬编码进通用 Model。

---

## 14. 如何调试

| 现象 | 先看 |
|------|------|
| JSON 加载失败 | `ValidationError` 全文 |
| source 引用错误 | `sources[]` 与各 `EvidenceRef.source_id` |
| SYSTEM_DERIVED 失败 | `normalization_rule` 或 `derivation_note` 是否非空 |
| 重复 ID | 错误里的 `duplicate <id_type>` |

推荐断点（只读调试，勿改代码）：

1. `load_snapshot`
2. `BusinessSnapshot.check_source_references`
3. `Condition.check_layers` / `ConditionExecutable.must_be_verified_executable`

---

## 15. 哪些东西不能随便改

1. 不能把 `TO_CONFIRM` 直接改成 `VERIFIED`
2. 不能为 Demo 方便塞入虚构地点（如未确认的政务服务中心）
3. 不能把 Graph Node/Edge 塞进 F02 JSON
4. 不能让 LLM 自动生成 Materials / Locations / Channels
5. 不能直接物理删除正式业务历史而不留版本语义
6. 不能把公司原始 Word 未经授权推个人 GitHub

---

## 16. 未来 F03 怎么接（只讲方向）

F03 可读 `BusinessSnapshot`，再做类似：

`get_business` / `get_materials` / `get_handling_locations` / `get_channels` / `get_legal_basis` / `get_conditions`

并投影 Knowledge Graph。Decision Graph 只用**预定义** Node/Edge，**不是** LLM 读 Conditions 后自由选路径。

群众查询默认应过滤 `TO_CONFIRM`（过滤逻辑在 F03，不在 F02 Enum）。

---

## 17. 未来 F04 怎么接

只消费：

```text
condition.executable is not None
AND executable.verification_status == VERIFIED
AND executable.usable_by_rule_engine == true
```

当前 DEMO_SS_001：**筛选结果 = 0**。  
F02 已划好 Rule 边界，但**还没有真实可执行规则**——不要为演示把 applicant_scope 擅自升级成 Rule。

---

## 18. LLM 边界（固定）

LLM 未来可以：自然语言理解、槽位提取、受控 `allowed_values` 映射、confidence。

LLM **不可以**：决定 `next_node` / Edge / `business_id` / Material / Location / Channel / Rule result。

**程序**根据确定规则决定是否推进。

---

## 19. Review Findings（摘要）

| ID | 状态 |
|----|------|
| RF-F02-001 extra fields | CLOSED |
| RF-F02-002 ID uniqueness | CLOSED |
| RF-F02-003 Feature stage | CLOSED |
| RF-F02-004 negative executable test | CLOSED |
| RF-F02-005 Material.condition_ref | Deferred |
| RF-F02-006 Open Item owner field | Deferred |
| RF-F02-007 updated_at precision | Accepted / No Action |

---

## 20. 相关文档

| 文档 | 用途 |
|------|------|
| `docs/features/F02-demo-ss-001-requirement-and-data-contract.md` | Feature 范围与阶段权威 |
| `docs/project/open-items.md` | 跨 Feature 待确认项 |
| `AGENTS.md` | 核心架构原则 |
