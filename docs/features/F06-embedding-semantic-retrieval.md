# F06 — Embedding + Semantic Retrieval

## 1. Feature Status

| 字段 | 内容 |
|------|------|
| Feature ID | F06 |
| Feature Name | Embedding + Semantic Retrieval |
| Current Stage | **Explanation Completed — Awaiting Commit Authorization** |
| 前置 Feature | F05 — PostgreSQL + pgvector Minimum Local Docker（functional `8ca464a`；docs `f9d61d4`） |
| Git Baseline | `develop` @ `f9d61d48fee442248fc49551604bd0b5fcf53069` |
| External Resource Gate | **CLOSED** |
| Formal Business Focus | `DEMO_SS_001`（灵活就业人员社会保险费申报缴费） |
| Requirement Document | `docs/features/F06-embedding-semantic-retrieval.md` |
| Code-Reading | `docs/code-reading/F06-embedding-semantic-retrieval-code-reading.md` |

### Stage Status

| 阶段 | 状态 |
|------|------|
| Resource Gate | **CLOSED** |
| Requirement | **CLOSED** |
| Requirement Finalization | **PASS** |
| Technical Design | **CLOSED** |
| Confirm | **DONE** |
| Code | **PASS** |
| Test | **PASS** |
| Review | **CLOSED**（PASS WITH DEFERRED INFO） |
| Explanation | **COMPLETED** |
| Commit | NOT STARTED |
| Push | NOT STARTED |

**本阶段范围：** Explanation — Code-Reading + Feature 状态更新。
**明确禁止自动进入：** Commit、Push。
**未修改：** production / tests / migration / Settings / pyproject。
**未执行：** pytest、Docker、Alembic、真实 Embedding、git add/commit/push。

### Code Implementation Notes

- Builder 通过 policy ALLOW entries + `JsonBusinessRepository.get_snapshot` 解析业务，**未修改** F03 repository（无需 `list_*` API）。
- `DEMO_SS_001` 仅出现在 eligibility artifact JSON，不在 production Python 硬编码。
- Optional `sentence-transformers`：仅 Local Provider 首次 load 时 lazy import。

### Test Evidence（摘要）

| 项 | 结果 |
|----|------|
| Env | Conda `govagent` / Python 3.11.16 |
| Core/dev install | PASS（含 Python `pgvector` 0.4.2） |
| Phase A unit | **84 passed** |
| No-Docker full（Test 阶段） | **205 passed / 12 skipped / 1 warning** |
| F06 DB integration | **8 passed**（仅 `gov_service_agent_test`） |
| F05+F06 DB regression | **11 passed / 3 deselected** |
| Real CUDA smoke | PASS（`actual_device=cuda`，GPU：GTX 1660 Ti） |
| Golden recall | `DEMO_SS_001` rank=1；score≈**0.6671** ≥ 0.50（candidate only） |
| CPU fallback smoke | PASS（dim=768） |
| Final DB non-real | **214 passed / 3 deselected / 1 warning** |
| Default full（**Review Fix 后**） | **206 passed / 12 skipped / 1 warning** |
| compileall / pip check | PASS / PASS |
| Dev DB `gov_service_agent` | **未** migration 0002 / **无** F06 tables（仍 `0001`） |

#### TF-F06 Findings

| ID | Severity | Symptom | Root Cause | Fix | Status |
|----|----------|---------|------------|-----|--------|
| TF-F06-001 | MINOR | `test_model_path_missing` 在未装 ST 时得到 `DEPENDENCY_UNAVAILABLE` | path 检查在 import 之后 | Provider：path gate 先于 ST import | **CLOSED** |
| TF-F06-002 | MINOR | No-Docker full 时 F06 DB tests FAIL（缺 URL） | 缺 URL 误用 fail | 对齐 F05：缺 URL → skip；有 URL 不可达 → fail | **CLOSED** |
| TF-F06-003 | INFO | ST 6.x `get_sentence_embedding_dimension` FutureWarning | API rename | Prefer `get_embedding_dimension` | **CLOSED** |

#### Resource Notes

| ID | Notes | Status |
|----|-------|--------|
| TF-F06-RESOURCE-001 | PyPI/NGC 拉取 `torch` cu118 wheel 超时；从已验证 `embedding-test` 复制 `torch 2.7.1+cu118` 到 `govagent`；随后 `sentence-transformers==6.0.1`；CUDA 仍可用 | **MITIGATED** |

#### Review Findings

| ID | Severity | 内容 | Status |
|----|----------|------|--------|
| RF-F06-001 | MINOR | `RUN_EMBEDDING_REAL=1` 缺 Embedding 配置时曾 skip；已改为 `pytest.fail` | **CLOSED** |
| RF-F06-002 | INFO | `SemanticRetrievalService` 保存 `policy_path` 但 query 未使用（Builder 才读 Policy） | **DEFERRED** |

---

## 2. Resource Gate

F06 Embedding Resource Gate：**CLOSED**。以下不再作为 Open Question。

| 项 | 冻结值 |
|----|--------|
| Provider Type | `LOCAL_SENTENCE_TRANSFORMER` |
| Model Source | ModelScope |
| Model ID | `AI-ModelScope/gte-base-zh` |
| Model Name | `gte-base-zh` |
| Embedding Dimension | **768**（已实测） |
| Runtime | Python 本地进程 + `sentence-transformers` |
| Device Policy | CUDA preferred；CPU fallback |
| Cloud Embedding API | **NOT REQUIRED** |
| Embedding API Key | **NOT REQUIRED** |
| Runtime Internet | **NOT REQUIRED**（首次模型权重准备除外） |
| PostgreSQL | READY（F05） |
| pgvector | READY（F05） |
| Redis | **F06 NOT REQUIRED** |
| LLM | **F06 NOT REQUIRED** |

### 已完成真实资源验证（证据摘要）

| 验证项 | 结果 |
|--------|------|
| Model Load | PASS |
| Device | `cuda:0`（NVIDIA GeForce GTX 1660 Ti） |
| Embedding Dimension | 768 |
| Single Text Encode | PASS；实际 shape `(768,)` |
| 政务中文 Smoke | PASS（见下） |
| 显存（验证时） | allocated ≈ 210 MB；reserved ≈ 218 MB |

政务中文 Smoke Query：`我现在没有单位，想自己继续交社保`

| Score | Candidate |
|------:|-----------|
| 0.7104 | 灵活就业人员社会保险费申报缴费 |
| 0.6763 | 查询社保缴费记录 |
| 0.6436 | 社保关系转移 |
| 0.3806 | 办理不动产权证书 |

结论：当前模型在本 Demo 中文政务短文本意图召回场景具备基础有效性。

### 本地模型路径原则（Resource 层）

负责人机器示例路径 `<local-model-path>` **仅是 Local Configuration**，不得写入 production/business code 硬编码。
其它本机或服务器路径必须仅通过配置注入（示例：`<local-model-path>`），无需改业务代码。

独立验证环境 `embedding-test` 已完成资源验证，**不是**项目 runtime dependency。正式 F06 运行于项目环境（如 `govagent`）；代码不得依赖 `embedding-test` Conda env。

---

## 3. Background

F00–F05 已提供：

- 最小 FastAPI 工程与运行时 Settings / Logging（F00–F01）
- Demo Runtime Business Data Contract 与 JSON Source of Truth（F02）
- Business Decision Graph Domain + JSON Repository（F03）
- Deterministic Graph Transition + Executable Rule Selection / Readiness（F04）
- PostgreSQL 16 + pgvector 0.8.6 本地基础设施、SQLAlchemy/Alembic、Local-First `check_db`（F05）

尚缺：**将用户自然语言语义映射为业务方向与事项候选召回** 的能力层。该能力属于 Canonical Flow 中的 Semantic Retrieval 段，位于 NLU 之后、Business Decision Graph 之前。

Canonical Flow（F06 仅负责加粗段）：

```
用户自然语言
→ NLU
→ Semantic Retrieval（方向 / Top-K candidates / score）   ← F06
→ graph_entry
→ Business Decision Graph
→ missing slots / deterministic transition
→ Terminal Candidate
→ Verified Rule Layer
→ 用户确认事项
→ confirmed business_id
→ Business Knowledge Graph（材料/地点/渠道/依据）
→ Agent 最终表达
```

---

## 4. Problem Statement

用户以自然语言表达办事意图（例如“我辞职了，现在没单位，想自己交社保”）时，系统需要：

1. 在合法业务范围内做**语义方向定位**与**事项候选召回**；
2. 为每个候选提供**可排序的相关性分数**与排序；
3. 将结果交给后续 Graph Entry / Decision Graph，而**不能**仅凭相似度确认最终 `business_id`。

当前项目具备 Embedding 本地模型与 pgvector 基础设施，但尚无统一的 Embedding Provider 能力、无可重建的 Retrieval Projection、无 Semantic Retrieval 业务契约。若缺少明确边界，容易出现：

- Top-1 similarity 直接当作最终事项；
- 办理材料/地点等事实文本被误用作意图语料；
- PostgreSQL 向量存储被误升为业务事实权威源；
- 硬编码开发机模型路径、import-time 加载大模型、普通单测强绑 GPU。

F06 必须先以 Requirement 冻结上述问题与边界。

---

## 5. Goals

1. **Embedding Capability**：通过可替换的 Embedding Provider 抽象，对查询与文档文本产生向量；当前第一实现为本地 `LOCAL_SENTENCE_TRANSFORMER` + `gte-base-zh`（768-D）。
2. **Semantic Retrieval**：将用户自然语言映射为业务方向（如适用）+ Top-K business candidates + relevance/similarity score + rank。
3. **用途覆盖**：Initial Intent、Intent Switch、Fallback Recovery、业务候选召回。
4. **Retrieval Projection**：从 Runtime Business Data 构建可持久化、可重建、可版本识别的检索投影；使用 PostgreSQL + pgvector 作为持久化向量检索基础。
5. **配置化本地模型**：支持 `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL_ID` / `EMBEDDING_MODEL_PATH` / `EMBEDDING_DEVICE` 等配置能力；路径因机器而异，业务代码不硬编码。
6. **Local-First**：模型权重已准备时，无云端 Embedding API、无 LLM、无 Redis、无 Runtime Internet 亦可运行基础检索能力。
7. **失败可表达**：无候选、低相关、分数接近、跨领域歧义时，不得猜最终事项；须能表达 no usable result / ambiguous recall，供后续 Fallback / clarification / graph entry 使用。
8. **可测试**：Provider 可替换/fakeable；普通 unit tests 不强制真实模型或 GPU；真实模型测试有限、显式、可分类。
9. **Golden Scenario**：对“我辞职了，现在没单位，想自己交社保”召回 `DEMO_SS_001` 为高相关候选（仅验证 recall，不验证最终事项判定）。

---

## 6. Non-Goals

F06 **不负责**且本 Feature **不实现**：

| 类别 | 排除项 |
|------|--------|
| LLM / Agent | LLM NLU、LLM Provider、Agent orchestration、LangGraph、Session、Checkpoint |
| Graph / Rules | 修改 F03 Graph semantics、F04 Transition / Rule Selection semantics、Rule Evaluator、决定 `next_node` / edge / slots |
| Knowledge | Business Knowledge Graph 办理事实查询、Navigation Graph、材料/地点/渠道/楼层/窗口/法律依据作为最终答案源 |
| Confirmation | Final business confirmation、直接写入 confirmed `business_id` |
| Infra extras | Redis、Cloud Embedding API、Remote Embedding Provider 实现、分布式向量库、GPU server、消息队列、复杂 background worker |
| Over-design | 百万级向量 ANN 生产级调优、把 F06 做成“最终事项判定器” |
| Data fabrication | 为扩大语料编造 aliases / examples / summary / keywords / 事项；将 inventory / TO_CONFIRM 业务升级为 verified truth |

**F07 边界：** LLM Abstraction + Provider + Data Policy 属于 F07；F06 不得把 Embedding 与 LLM Chat Completion 混为一谈。

---

## 7. Architecture Boundaries

### 7.1 Hard Invariants（长期）

> **语义检索找方向，业务图谱定事项，规则引擎做终审，知识图谱查办理信息，Agent 统一编排。**

| 组件 | 允许 | 禁止 |
|------|------|------|
| Semantic Retrieval | recall / rank / score；产出 direction、candidate list、score | 决定 `next_node`；创建 edge；修改 slots；决定 rule result；确认 `business_id`；直接查询最终办理事实 |
| Decision Graph | 确定性推进；Terminal Candidate | LLM / Similarity 决定流程 |
| Rule Layer | 确定性终审（后续 Feature） | LLM eval 业务规则 |
| Knowledge Graph | confirmed `business_id` 后确定性查材料/地点/渠道/依据 | 作为意图召回主语料 |

### 7.2 禁止 Top-1 直接确认事项（F06 最重要边界之一）

即使 Top-1 score 明显最高，也 **不得**：

```text
final_business_id = top1.business_id
```

返回的 `business_id` 仅为 **candidate identity**。最终事项仍必须：

```text
Semantic Retrieval
→ Business Decision Graph
→ deterministic transition
→ Rule Layer
→ User Confirmation
→ confirmed business_id
```

### 7.3 F03 / F04 边界

- Decision Graph：办哪个事项（确定性）。
- Knowledge Graph：事项怎么办（后续）。
- F06 **禁止修改** Graph semantics、Rule Selection semantics、Decision logic。

### 7.4 PostgreSQL 角色

- F05 提供基础设施；F06 可将 Semantic Retrieval **projection** 持久化于 PostgreSQL + pgvector。
- PostgreSQL **不得**因 F06 成为 Demo Runtime Business Data Source of Truth。

### 7.5 Provider 可替换性

- 上层 Semantic Retrieval **不得**直接依赖 `SentenceTransformer` / ModelScope / 具体 local model class。
- 必须依赖 Embedding Provider **abstraction**（能力级要求，见 §15）。
- 当前第一实现：`LocalSentenceTransformer`。
- 未来若有 Remote Embedding API，应能通过新增 Provider 扩展且不重写核心检索业务逻辑。
- **F06 不实现** remote provider；只要求架构不锁死替换路径。

---

## 8. Source of Truth

| 层级 | 角色 | F06 立场 |
|------|------|----------|
| Authoritative Evidence Source | 政策/指南等权威证据 | **最高**；Similarity 与 Index **不是** policy truth |
| F02 JSON Runtime Business Data | Demo Runtime Business Data Source of Truth | **保持**；F06 不得擅自迁移权威 |
| Derived Retrieval Projection | 可重建的检索投影 / 索引数据 | **派生**；仅服务召回；不可反向编辑以改变业务事实 |

原则：

1. **Business Fact** 与 **Retrieval Projection / Index Data** 必须区分。
2. 若将业务文本投影进检索存储，该存储只能是 **rebuildable retrieval projection**。
3. 源数据变化后应能重新构建 embedding/index。
4. 不得通过直接编辑 retrieval record 反向改变业务事实。
5. 未确认业务（inventory only / mapping TO_CONFIRM / 缺正式 source）不得为 retrieval benchmark 升级为 verified business truth。
6. **Retrieval Eligibility ≠ Business Verification**（完整策略见 §8.1）。Similarity **永远不能**改变 verification status、source status 或 business eligibility。

### 8.1 Retrieval Eligibility Policy（Requirement Frozen）

#### 8.1.1 两个概念必须分离

| 概念 | 含义 |
|------|------|
| **Retrieval Eligibility** | 某业务记录是否允许进入某一层检索/展示/流程入口 |
| **Business Verification** | F02 等既有 verification / source / executable 语义（TO_CONFIRM、SOURCE_EXPLICIT、VERIFIED 等） |

- Similarity score **不得**改变 verification status、source status、business eligibility。
- 即使 inventory / TO_CONFIRM / unsupported 的 similarity = 0.99，也 **不得**因此进入 online candidate、Decision Graph 或 final matter flow。
- Embedding 只负责 **semantic relevance**，不负责 business authorization / verification / eligibility。

#### 8.1.2 必须区分的五个层级（不得混为一谈）

| 层 | 问题 | 说明 |
|----|------|------|
| **A. Internal Retrieval Projection** | 是否允许进入内部检索投影 | 可含 INTERNAL-ONLY 研究/评测数据；**不要求** F06 当前必须全部建索引 |
| **B. Online Retrieval Candidate Result** | 是否允许进入正式在线候选结果 | 在线链路硬边界 |
| **C. User Business Candidate Display** | 是否允许作为用户可办事项候选展示 | 面向普通用户的“可办理”展示 |
| **D. Decision Graph Entry** | 是否允许进入 Business Decision Graph | 仍须经 Graph 确定性逻辑；≠ final |
| **E. Final business_id** | 是否允许成为 confirmed final business_id | Semantic Retrieval **永远不能**直接产生 |

上述 `ALLOWED` / `NOT ALLOWED` / `OPTIONAL / INTERNAL-ONLY` 为 **Requirement semantics**。
**不在本阶段**创建 EligibilityEnum、DB column、boolean field、SQLAlchemy model、filter SQL、Pydantic class（属 Technical Design）。

#### 8.1.3 Internal Retrieval Projection Policy

为不锁死未来 offline evaluation / retrieval research / data curation：

- inventory-only、TO_CONFIRM 等记录 **允许** 作为 **INTERNAL-ONLY** retrieval projection 数据，用于 offline evaluation、debug、retrieval quality analysis、data curation。
- **是否**在 F06 实现此类 internal-only indexing：属 **Technical Design / Data Curation**。
- Requirement **不要求** F06 当前必须把它们全部建索引。

#### 8.1.4 Online Retrieval Candidate Policy（在线硬边界）

在线 Semantic Retrieval **只能**返回 **ONLINE RETRIEVAL ELIGIBLE** 业务候选。

| 当前 Demo | Online Candidate |
|-----------|------------------|
| `DEMO_SS_001` | **ALLOWED**（ONLINE RETRIEVAL ELIGIBLE） |
| `DEMO_YB_001`（inventory only） | **NOT ALLOWED** |
| `DEMO_GJJ_001`（inventory only） | **NOT ALLOWED** |
| `DEMO_GA_001`（mapping TO_CONFIRM） | **NOT ALLOWED** |
| `DEMO_SS_002`（unsupported / no formal source） | **NOT ALLOWED** |

#### 8.1.5 当前 Demo Eligibility Matrix（概念级）

| business_id | Status | A Internal Projection | B Online Candidate | C User Business Candidate | D Decision Graph Entry | E Final business_id |
|-------------|--------|----------------------|--------------------|---------------------------|------------------------|---------------------|
| `DEMO_SS_001` | 核心正式事项 | **ALLOWED** | **ALLOWED** | **ALLOWED** | **ALLOWED**（仍须经 Graph） | **NOT BY RETRIEVAL**（须 Graph → Rule → User Confirmation） |
| `DEMO_YB_001` | inventory only | **OPTIONAL / INTERNAL-ONLY** | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** |
| `DEMO_GJJ_001` | inventory only | **OPTIONAL / INTERNAL-ONLY** | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** |
| `DEMO_GA_001` | TO_CONFIRM | **OPTIONAL / INTERNAL-ONLY** | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** |
| `DEMO_SS_002` | unsupported / no formal source | 默认不得作正式在线数据；若未来 internal offline experiment，须保持 unsupported/internal identity | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** | **NOT ALLOWED** |

#### 8.1.6 Candidate 必须保留业务资格边界

任何 **在线** candidate 必须能够：

- 携带，或通过 source identity **确定性解析出** 原 Business identity；以及
- 其 retrieval / business **eligibility boundary**。

不得出现：embedding 结果只剩 `business_id + score`，完全丢失业务状态边界。
具体 metadata 字段名、schema、join strategy 属 Technical Design。

#### 8.1.7 Fail-Closed Eligibility

若候选的 eligibility / verification / source boundary **无法确定**，在线 Retrieval **不得**默认视为 eligible；必须 **fail closed**（不进入正式在线 candidate flow）。
具体异常类/状态名属 Technical Design。

#### 8.1.8 Decision Graph Entry / User Display / Final Policy

- **Graph Entry：** 仅 **ONLINE RETRIEVAL ELIGIBLE** candidate 可作为 Semantic Retrieval 提供给后续 Graph Entry / Controller 的正式候选；进入 Graph **仍不等于** final `business_id`。
- **User Display：** inventory-only / TO_CONFIRM / unsupported **不得**作为“可办理事项”正式展示给普通用户。若未来需要“可能相关但尚未确认”的内部运营展示，属新的产品 Requirement，**不属于当前 F06**。
- **Final：** Semantic Retrieval **永远不能**直接产生 confirmed final `business_id`。即使 ONLINE RETRIEVAL ELIGIBLE，也必须：Business Decision Graph → deterministic transition → Rule Layer → User Confirmation → confirmed `business_id`。

---

## 9. Embedding Resource Baseline

| 项 | Baseline |
|----|----------|
| Model | `gte-base-zh`（ModelScope：`AI-ModelScope/gte-base-zh`） |
| Provider Type（第一实现） | `LOCAL_SENTENCE_TRANSFORMER` |
| Dimension | **768**（资源实测；runtime 须暴露自身 dimension） |
| Device | CUDA preferred；CPU fallback |
| Cloud / API Key / LLM / Redis | 均 NOT REQUIRED |

### Dimension 原则（Requirement 级）

1. Embedding runtime **应暴露**自己的 `dimension`。
2. Python 业务逻辑 **不得**在多处散落硬编码 `768`。
3. 若未来 Technical Design 采用固定 `vector(768)` schema，则 768 可作为**该 Schema 版本**的确定性定义——**不是**本阶段设计内容。
4. Migration **不得**根据 `.env` 或当前机器动态改变 vector dimension。
5. 未来更换模型维度：须考虑 new migration + new embedding/index version + vector rebuild（方案属 Technical Design）。

---

## 10. Functional Requirements

| ID | 需求 |
|----|------|
| FR-01 | 系统须能对用户自然语言 query 执行 Semantic Retrieval。 |
| FR-02 | 检索结果须包含 ranked candidate list 与每个候选的 relevance/similarity score。 |
| FR-03 | 在适用时须能定位业务方向（direction），例如 `social_security`。 |
| FR-04 | Candidate 须携带可追踪的业务身份（至少 candidate identity，对应 Runtime Business 的 `business_id` 概念）与展示名；**在线 candidate 须保留或可确定性解析 eligibility / business 资格边界**（不得仅剩 `business_id + score`）。 |
| FR-05 | 必须支持可控的 Top-K candidate retrieval；K 不得隐藏为业务代码 magic number（默认数值不在本阶段冻结）。 |
| FR-06 | 必须提供可排序 score，且 higher/lower 含义对调用方一致（具体度量公式不在本阶段冻结）。 |
| FR-07 | Embedding 须可持久化到检索投影，并支持 rebuild / refresh。 |
| FR-08 | 投影须能识别 provider、model identity、dimension、必要的 embedding/index version，防止不同模型向量无意识混用。 |
| FR-09 | 无可用结果 / 低相关 / 歧义时须可表达，且不得猜测最终事项。 |
| FR-10 | Local model 不得在 module import 时无条件加载；须支持 lazy / controlled initialization。 |
| FR-11 | Embedding 未配置 / 路径不存在 / 加载失败时，不得导致 FastAPI import-time 崩溃；优先保持与 F05 Local-First / health 解耦（Retrieval 可 NOT_READY）。 |
| FR-12 | GPU 不可用时可 CPU 运行基础功能；fallback 不得 silent 到无法诊断；须可观察实际 device。 |
| FR-13 | 在线 Semantic Retrieval 只能返回 ONLINE RETRIEVAL ELIGIBLE 候选；inventory / TO_CONFIRM / unsupported 不得进入 online candidate / Graph entry / final matter flow（不受 similarity 影响）。 |
| FR-14 | Empty / whitespace-only query：不得调用 Embedding Provider、不得进行 vector retrieval、不得返回 business candidates；须返回明确的 invalid/empty-query 业务语义。 |
| FR-15 | 必须区分概念语义：`RETRIEVAL UNAVAILABLE`、`RETRIEVAL NOT READY`（含 index/projection 未 build / incompatible）、`NO USABLE CANDIDATE`、`VALID CANDIDATES`；不得将 NOT READY 冒充为正常空召回。 |

---

## 11. Retrieval Input

### 最小输入

- **用户自然语言 query**（中文短文本为主）。

### 约束（Requirement 级）

- 支持中文短文本意图表达。
- 允许 normalize（算法细节属 Technical Design）。
- **Empty / Whitespace Query（冻结）：** 若 query 为 `None`（若输入契约允许）、empty string、或 normalize 后仅含 whitespace，则：
  1. **不得**调用 Embedding Provider；
  2. **不得**访问 vector retrieval；
  3. **不得**产生随机 / 任意 business candidates；
  4. 须返回明确的 **invalid / empty-query** 业务语义，供上层 clarification / fallback。
- 具体 Enum 名、Exception class、HTTP code 属 Technical Design。

### 本阶段不规定

- tokenizer、max_length、batch size、具体 normalization algorithm。

---

## 12. Retrieval Output

业务级输出**至少包含以下概念**（名称与类型属 Technical Design）：

| 概念 | 说明 |
|------|------|
| query | 本次检索使用的查询（或规范化后的查询表示） |
| direction result | 如适用：业务方向定位结果 |
| candidate list | 有序候选列表 |
| candidate identity | 候选业务身份（对应 runtime `business_id` 概念） |
| candidate display name | 面向展示/调试的业务名称 |
| eligibility / business boundary | 在线候选须携带或可确定性解析的资格边界（不得仅 `business_id + score`） |
| relevance / similarity score | 可排序分数 |
| rank | 排序位次 |
| retrieval metadata | 如需要：provider / model / dimension / index version 等追踪信息 |
| outcome signal | 如适用：invalid/empty-query、RETRIEVAL UNAVAILABLE、RETRIEVAL NOT READY、NO USABLE CANDIDATE、ambiguous、VALID CANDIDATES 等**可区分**概念语义 |

**明确：** 输出中的 candidate identity **不是** confirmed / final `business_id`。
**明确：** 在线结果中的 candidate 必须是 ONLINE RETRIEVAL ELIGIBLE；inventory / TO_CONFIRM / unsupported 不得因高分进入该列表。

---

## 13. Retrieval Corpus Scope

### 13.1 主要允许用于意图检索的文本

用于回答用户“想办什么”的语义匹配：

- `category_name`（及等价类别表达）
- `business_name`（canonical / 正式事项名）
- `aliases`
- `examples`
- `summary`
- `keywords`

### 13.2 不得作为主要 Intent Corpus

以下属于 confirmed `business_id` 之后的确定性办理事实，**不得**作为主要意图召回语料主体：

- material list
- location / address
- window / floor
- service hours
- channel
- legal basis
- 电话
- 详细办理步骤

### 13.3 Corpus Data Safety

1. **禁止**为增加 Embedding 数据量而编造 aliases / examples / summary / keywords / 事项。
2. 若 F02 当前数据缺少足够 retrieval text：记录为**数据缺口 / future curation**，而非 F06 直接造业务事实。
3. **允许**由已有权威业务名称产生技术性、可追踪的 projection；具体 projection algorithm 属 Technical Design。

---

## 14. Index / Projection Lifecycle Requirements

概念流水线（必须满足，实现细节属 Technical Design）：

```text
Business Source Data
→ Retrieval Documents
→ Embedding
→ Vector Store（PostgreSQL + pgvector）
```

| 要求 | 说明 |
|------|------|
| Persist | Embedding / projection 必须可持久化 |
| Rebuild | 必须可重复构建；再次运行不得无限插入不可区分 duplicate |
| Refresh | 源数据或模型/index version 改变时支持 rebuild / refresh |
| Source linkage | 投影须与业务源数据可关联 |
| Version identity | 须能识别 provider / model / dimension / embedding-or-index version |
| Non-SoT | 投影不是业务 Source of Truth；不可反向改写业务事实 |

**本阶段不决定：** table/column 名、`vector(N)` migration、HNSW / IVFFlat / exact scan、upsert vs delete+insert、hash、transaction 细节。

---

## 15. Provider Abstraction Requirements

### 15.1 能力要求（Capability，非 API 设计）

上层必须依赖 Embedding Provider 抽象，至少具备业务能力：

| Capability | 说明 |
|------------|------|
| `embed_query(text)` | 对查询文本编码 |
| `embed_documents(texts)` | 对文档集合编码 |
| `dimension` | 暴露向量维度 |
| model / provider identity | 可识别当前实现身份 |

### 15.2 替换策略

- F06 第一实现：Local Sentence Transformer（`gte-base-zh`）。
- 未来 Remote Embedding API：通过**新增 Provider**扩展。
- Semantic Retrieval 核心业务逻辑不应因 Provider 替换而重写。
- F06 **不实现** remote provider。

### 15.3 本阶段不冻结

Python Protocol / ABC、class hierarchy、method signatures、module path、DI 细节——均属 Technical Design。

---

## 16. Configuration Requirements

F06 必须具备以下**配置能力**（键名作为 Requirement 契约概念；Settings 实现属 Technical Design）：

| 配置概念 | 用途 |
|----------|------|
| `EMBEDDING_PROVIDER` | 选择 Provider 类型（当前：本地 Sentence Transformer） |
| `EMBEDDING_MODEL_ID` | 模型身份（如 `AI-ModelScope/gte-base-zh` / `gte-base-zh`） |
| `EMBEDDING_MODEL_PATH` | 本地模型目录；**因机器而异** |
| `EMBEDDING_DEVICE` | 设备策略/选择（与 CUDA preferred / CPU fallback 对齐） |

### 硬性约束

1. **禁止**在 production/business code 硬编码负责人机器路径（如 `<local-model-path>`）。
2. 更换本机路径不得要求修改业务逻辑代码。
3. Top-K 等运行参数须可控，不得散落不可配置 magic number（具体默认值属 Technical Design）。
4. 本阶段不设计：Pydantic Validator、Settings field 实现、Factory、Enum class、依赖注入代码。

---

## 17. Failure / Fallback Requirements

### 17.1 必须可区分的概念语义（非代码 Enum 名）

| 概念语义 | 含义 | 不得混淆为 |
|----------|------|------------|
| **RETRIEVAL UNAVAILABLE** | DB / 连接等资源不可用，检索无法执行 | “无相关业务” |
| **RETRIEVAL NOT READY** | Projection / Index 尚未 build、未 ready，或 model/index identity 不兼容（INCOMPATIBLE）；属 **system/resource state** | `NO USABLE CANDIDATE` |
| **NO USABLE CANDIDATE** | Index READY、Query VALID、检索正常执行，但无满足可用条件的 **online** candidate；属 **valid retrieval outcome** | Index 未构建 |
| **VALID CANDIDATES** | 返回 ONLINE RETRIEVAL ELIGIBLE 的 ranked candidates | final business confirmation |
| **INVALID / EMPTY QUERY** | 空或仅空白 query | 正常空召回 |

**为什么必须区分 NOT READY 与 NO USABLE CANDIDATE：**
若混为一谈，上层会误认为“系统没有这个业务”，而实际可能只是“索引还没构建”。

Model / index mismatch：继续 **不得**执行混合 Retrieval；语义更接近 **NOT READY / INCOMPATIBLE**，而不是 `NO USABLE CANDIDATE`。

### 17.2 场景表

| 场景 | 期望行为 |
|------|----------|
| Empty / whitespace query | **0** Embedding 调用；**0** vector retrieval；**0** business candidates；返回 invalid/empty-query 语义 |
| Embedding 未配置 | 应用不得 import-time 崩溃；Retrieval 可表达不可用 / NOT_READY |
| 模型目录不存在 / 加载失败 | 同上；失败可观察、可诊断 |
| DB unavailable | **RETRIEVAL UNAVAILABLE**；不得猜 candidate；与 Index not ready / No usable candidate **独立** |
| Projection / Index 未 build 或未 ready | **RETRIEVAL NOT READY**；**不得**返回冒充正常空召回的 `NO USABLE CANDIDATE` |
| Model / index mismatch | 拒绝混合检索；**NOT READY / INCOMPATIBLE**（非 NO CANDIDATE） |
| Index READY + valid query + 无可用 online candidate | **NO USABLE CANDIDATE** |
| Low relevance | 不得升格为最终事项；须可被后续 Fallback / clarification 消费 |
| Near-tie / cross-domain ambiguity | `ambiguous candidate recall`（概念级）；不得猜最终事项 |
| Eligibility 无法确定 | **fail closed**；不进入正式 online candidate flow |
| inventory / TO_CONFIRM / unsupported 高分 | **不得**进入 online candidate / Graph / final flow |
| GPU 不可用 | CPU fallback 继续基础功能；**不得 silent**；记录实际 device |

**本阶段不冻结：** 具体 threshold 数值、HTTP status code、精确错误枚举名。

---

## 18. Local-First Requirements

1. Embedding：**本地模型**（权重已准备前提下）。
2. Runtime：**无网络**可运行基础 Embedding + Retrieval（首次权重准备除外）。
3. **不依赖：** Cloud Embedding API、API Key、LLM、Redis。
4. 与 F05 一致：应用健康检查思路与重资源（DB / Embedding）解耦；Embedding 不可用不应导致 import-time 整应用崩溃。
5. `/health` 保持轻量解耦期望（具体 endpoint 集成属后续 Design/Code，本阶段不设计 HTTP）。

---

## 19. Security / Observability

### 允许安全记录（原则）

- provider identity
- model identity（非敏感标识）
- dimension
- actual device
- index / retrieval operation result
- candidate count
- timing（若设计允许）

### 禁止日志记录

- 完整 embedding vector
- 真实本地模型绝对路径（无必要时）
- secret / API key（F06 亦不需要）
- 完整敏感用户输入（未来若涉及隐私字段时尤其禁止）
- 明文身份证号、手机号、证件全文、Token 等（遵循项目全局日志安全规则）

本阶段只冻结原则，不设计 logger API。

---

## 20. Testing Requirements

### 必须覆盖的行为面（本阶段不写测试代码）

| 类别 | 要求 |
|------|------|
| Provider | unit behavior；query/document embedding；dimension consistency |
| Device | CPU fallback 可测试边界 |
| Retrieval | ranking；Top-K；no result / ambiguous；empty query；NOT READY vs NO USABLE CANDIDATE；online eligibility filtering |
| Projection | index build/rebuild；source linkage；model/index mismatch protection |
| Integration | DB integration（在既有 F05 test DB 隔离原则下） |
| Scenario | Golden Scenario smoke（recall only；online eligible candidate） |

### Deterministic / 性能友好测试架构

1. **EmbeddingProvider 必须可替换 / fakeable。**
2. 普通 unit tests **不得**强制加载真实约 195MB 模型或依赖 GPU。
3. 真实模型测试：有限、显式、可分类（具体 pytest marker 属 Technical Design）。
4. 普通测试应尽量快速、CPU/GPU independent。

### Performance 定位

F06 是 **Local Demo**：优先正确性、架构边界、可替换 Provider、可重建 Index、可测试性。
不要求百万向量级优化，不过度设计分布式向量库 / GPU server / MQ / 复杂 cache。

---

## 21. Golden Scenario

### 用户表述

> 我辞职了，现在没单位，想自己交社保

### F06 Semantic Retrieval 预期（本 Feature 范围）

1. 定位方向：`social_security`（direction）。
2. 召回 `DEMO_SS_001`（灵活就业人员社会保险费申报缴费）作为**高相关 online candidate**（ONLINE RETRIEVAL ELIGIBLE）。
3. **此时不能结束办事流程，不得确认最终 `business_id`。**
4. inventory / TO_CONFIRM / unsupported 事项即使语义相近，也 **不得** 作为正式 online candidate 进入后续 Graph / final flow。

### 后续链路（非 F06 实现范围，仅说明边界）

1. 进入 Business Decision Graph。
2. 仍缺 `employment_type` → Agent 后续询问。
3. 用户：“平时接零活，没有固定单位” → NLU：`other_flexible_employment`。
4. Decision Graph deterministic transition → Terminal Candidate → Rule Layer → User Confirmation。

**F06 只负责前面的 Semantic Retrieval（方向 + 候选召回 + 分数）。**

---

## 22. Acceptance Criteria

| ID | 验收标准 |
|----|----------|
| **AC-01** | 本地 `gte-base-zh` 可通过统一 Provider 产生 **768-D** embedding。 |
| **AC-02** | 业务代码不依赖固定开发机模型路径；路径仅由配置注入。 |
| **AC-03** | 无 GPU 时支持 CPU fallback，且实际 device 可观察。 |
| **AC-04** | Semantic Retrieval 能够返回 ranked candidate list + scores。 |
| **AC-05** | Top-1 **不得**自动成为 `final_business_id`。 |
| **AC-06** | Retrieval Projection 可从 Runtime Business Data 重建。 |
| **AC-07** | Retrieval Projection **不得**成为新的业务 Source of Truth。 |
| **AC-08** | 不同 model / index version **不得**无保护混用。 |
| **AC-09** | 普通 unit tests 不强制真实模型 / GPU。 |
| **AC-10** | Golden Query「我辞职了，现在没单位，想自己交社保」能将 `DEMO_SS_001` 召回为高相关 **online** 候选；**只验证 recall，不验证 final business decision**。 |
| **AC-11** | Embedding 不可用时不得发生 import-time 应用崩溃。 |
| **AC-12** | F06 不依赖 LLM、Redis、Cloud Embedding API。 |
| **AC-13** | Empty / whitespace query：**0** Embedding Provider 调用；**0** vector retrieval；**0** business candidates。 |
| **AC-14** | Projection / Index 未 ready 时，必须与「valid query + zero usable online candidate」**可区分**；不得将 NOT READY 冒充为 `NO USABLE CANDIDATE`。 |
| **AC-15** | inventory-only / TO_CONFIRM / unsupported **不得**进入 online candidate flow、Decision Graph entry 或 final business matter flow，**不受** similarity score 影响。 |

**Acceptance Criteria 数量：15**（AC-01～AC-12 保持；Finalization 新增 AC-13～AC-15）

---

## 23. Technical Decisions Still Open

以下内容 **Requirement 明确不冻结**，移交 Technical Design：

| # | Open Technical Decision |
|---|-------------------------|
| TD-01 | PostgreSQL table / column 命名与 SQLAlchemy model |
| TD-02 | Alembic migration（如 0002）内容；`vector(N)` 精确 DDL |
| TD-03 | Similarity metric：cosine / inner product / L2 及 score 归一化 |
| TD-04 | Index 策略：HNSW / IVFFlat / exact scan 及参数；小数据量是否需要 ANN |
| TD-05 | Top-K 默认数值与配置暴露方式 |
| TD-06 | Low-confidence / ambiguity 的 threshold 数值与判定细则 |
| TD-07 | Retrieval Document projection algorithm（字段拼接、去重、hash） |
| TD-08 | Rebuild 策略：upsert / delete+insert / version table / transaction |
| TD-09 | Module 结构、Protocol/ABC、class 名、Pydantic 精确字段 |
| TD-10 | Provider 实现类、模型缓存 / singleton / lock / lifecycle |
| TD-11 | batch size、tokenizer、max_length、normalization 细节 |
| TD-12 | Embedding / Retrieval readiness 与 HTTP 的集成方式（若需要） |
| TD-13 | pytest marker 分层与真实模型测试触发方式 |
| TD-14 | Settings 字段类型、校验器、dotenv known-key 扩展细节 |
| TD-15 | 如何实现 Online Eligibility filtering、metadata 保留 eligibility boundary、unknown eligibility fail-closed（**原则已冻结；仅实现方式 OPEN**） |
| TD-16 | 如何表达并区分 RETRIEVAL UNAVAILABLE / NOT READY / NO USABLE CANDIDATE / INVALID EMPTY QUERY（概念已冻结；类型/枚举名 OPEN） |

**说明：** “inventory / TO_CONFIRM / unsupported 是否可作为 online candidate” **不再 OPEN** — Requirement 已冻结为 **NOT ALLOWED**。Design 只决定如何标记、过滤、存 metadata、fail closed。

**Technical Decisions Still Open 数量：16**

---

## 24. Requirement Findings / Open Items

| ID | 状态 | 说明 | 处理 |
|----|------|------|------|
| RF-F06-R01 | **DEFERRED** | F02 意图语料字段可能不足；**禁止编造**已冻结。后续 Design / Data Curation 决定如何从已有可追踪业务字段生成 projection。 | Technical Design / 数据 curation |
| RF-F06-R02 | **CLOSED AT REQUIREMENT** | Retrieval Eligibility Policy 已冻结（§8.1）：eligibility ≠ verification；五层区分；Online Candidate 硬边界；Demo Matrix；fail closed；Similarity 不可越权。 | — |
| RF-F06-R03 | **CLOSED** | Draft pending review 为 process-only；Finalization 完成后不再作为 Active Finding。 | — |

**Active Requirement-level Findings：** 无（R01 为 Data Gap defer，非未冻结业务策略）。
无其它阻碍 Resource Gate 的 Open Question（Embedding 资源已 CLOSED）。

---

## 25. Requirement-to-Technical-Design Handoff

进入 Technical Design 前，Design 必须承接并回答：

1. **Provider 抽象**如何落地（不破坏可替换性；第一实现 Local Sentence Transformer）。
2. **配置面**如何接入现有 Strict Dotenv / Settings，且不硬编码本机路径。
3. **Projection schema + migration**如何与 dimension=768 baseline 对齐，且禁止动态 dimension migration。
4. **Rebuild / version identity**如何防止跨模型向量混用。
5. **Retrieval API 业务契约**（输入/输出概念 → 具体类型），并强制候选 ≠ final `business_id`。
6. **Corpus projection**仅使用意图语料范围；材料/地点等排除；数据缺口不造假（R01）。
7. **Failure / Local-First**：import-time 不加载模型；区分 UNAVAILABLE / NOT READY / NO USABLE CANDIDATE / EMPTY QUERY。
8. **Online Eligibility filtering / metadata / fail-closed** 如何实现（原则已冻结于 §8.1；不得重新开放“能否 online”）。
9. **测试分层**：fake provider 覆盖主路径；真实模型/GPU 测试显式隔离；覆盖 AC-13～AC-15。
10. **明确不设计进 F06 Code 的内容：** LLM、Redis、Remote Provider 实现、F03/F04 语义变更、最终事项确认。

### Requirement Finalization Self-Check

| # | 自检项 | 结果 |
|---|--------|------|
| 1 | R02 是否真正冻结 | **是**（§8.1；CLOSED AT REQUIREMENT） |
| 2 | eligibility ≠ verification | **是** |
| 3 | 五层区分（internal / online / user display / graph / final） | **是** |
| 4 | inventory-only 不得 online | **是** |
| 5 | TO_CONFIRM 不得 online | **是** |
| 6 | unsupported 不得 online | **是** |
| 7 | Similarity 无法越权 | **是** |
| 8 | unknown eligibility fail closed | **是** |
| 9 | empty/whitespace → 0 embedding call | **是** |
| 10 | index not ready ≠ no candidate | **是** |
| 11 | DB unavailable 仍独立 | **是** |
| 12 | AC 可测试（含 AC-13～15） | **是** |
| 13 | 未进入 Technical Design | **是** |
| — | Retrieval 决定 final `business_id`？ | **否** |
| — | PostgreSQL 成为 Business SoT？ | **否** |
| — | 提前决定 HNSW / cosine / threshold / Top-K 数值？ | **否**（当时属 Requirement；现由下方 Technical Design 冻结） |

---

# Technical Design

## TD-1. Technical Design Status

| 字段 | 内容 |
|------|------|
| Status | **Technical Design Finalization Completed — Awaiting Owner Confirmation** |
| Code Readiness | **CODE READY**（0 Code-blocking Open Items） |
| Based on | Requirement CLOSED + Design Review Finalization |
| Code | NOT STARTED |
| Scope | Embedding Provider、Settings、ONLINE Projection、Eligibility Artifact Contract、Retrieval Flows、Tests、Exact Planned Paths、Code-Reading Plan |

**冻结原则：** Local Demo；清晰、可测试、可替换 Provider、可重建 Projection、Fail Closed。
**明确不做：** Celery、Kafka、分布式向量库、background worker、GPU server、复杂 cache、HTTP `/retrieval`、INTERNAL-ONLY offline projection、多版本在线切换、并发 rebuild。

### Finalization Finding Closure

| Finding | 状态 |
|---------|------|
| MAJOR-1 Artifact Contract | **CLOSED** |
| MAJOR-2 Runtime Dimension Gate | **CLOSED** |
| MINOR-1 Score range | **CLOSED** |
| MINOR-2 Dependency missing | **CLOSED** |
| MINOR-3 Search identity filter | **CLOSED** |
| MINOR-4 Concurrent rebuild | **CLOSED** |
| MINOR-5 Fake helper / test paths | **CLOSED** |

---

## TD-2. Actual Code / Data Compatibility Analysis

### TD-2.1 已核对路径（只读）

`pyproject.toml`、`settings.py`、`db/runtime.py`、`db/readiness.py`、`db/__init__.py`、`alembic/env.py`、`0001_enable_pgvector.py`、F02 `business_data/models.py`、`data/demo/demo_ss_001.json`、F03 `repository.py`、`data/graphs/demo/social_security.json`、F04 transition/selection、`.env.example`、`tests/integration/test_db_integration.py`。

### TD-2.2 F02 `Business` 实际字段（与 Requirement 语料对照）

| Requirement 允许意图语料 | F02 实际 | 结论 |
|--------------------------|----------|------|
| `category_name` | `Business.category`（如 `social_security`） | **AVAILABLE**（字段名是 `category`） |
| `business_name` | `Business.canonical_name` | **AVAILABLE** |
| `aliases` | — | **NOT AVAILABLE** |
| `examples` | — | **NOT AVAILABLE** |
| `summary` | — | **NOT AVAILABLE** |
| `keywords` | — | **NOT AVAILABLE** |

其它存在但 **不得**作为 Intent Corpus 主语料：`materials`、`handling_locations`、`channels`、`legal_basis`、`conditions`。

`SourceRecord.source_title`：对 `DEMO_SS_001` 与 `canonical_name` 相同；**可不纳入** MVP `retrieval_text`（避免无增益重复）。

### TD-2.3 Demo 运行时数据现状

| business_id | 仓库内正式 `BusinessSnapshot` JSON | Requirement Online |
|-------------|-----------------------------------|--------------------|
| `DEMO_SS_001` | **有** `data/demo/demo_ss_001.json` | ALLOWED |
| `DEMO_YB_001` / `DEMO_GJJ_001` / `DEMO_GA_001` / `DEMO_SS_002` | **无**正式 Snapshot 文件 | NOT ALLOWED |

`JsonBusinessRepository`：仅 exact-id 索引；**无** `list_*` API（Builder 需最小扩展，见 Planned Paths）。

### TD-2.4 基础设施兼容

- Alembic `target_metadata = None`；Config URL 优先于 Settings；`configure_logger` 隔离 — **保持**。
- Settings Two-Stage Dotenv — **保持并扩展 keys**。
- `/health` DB-free — **保持**；F06 **不修改** `main.py`，**不新增** HTTP retrieval API。

### TD-2.5 独立环境只读版本（未加载模型）

| 包 | 版本 |
|----|------|
| `sentence-transformers`（embedding-test） | **6.0.1** |
| `torch` | **2.7.1+cu118** |
| CUDA available | True |

---

## TD-3. Architecture

```
JsonBusinessRepository (F02/F03 SoT)
        +
Online Eligibility Policy Artifact
        │
        ▼
CorpusBuilder  →  retrieval_text (category + canonical_name)
        │
        ▼
EmbeddingProvider.embed_documents  (lazy; outside DB txn)
        │
        ▼
ProjectionStore.replace_all + IndexMeta.READY   (short DB txn)
        │
User query → SemanticRetrievalService
        │
        ├─ INVALID_QUERY / UNAVAILABLE / NOT_READY
        └─ vector exact scan → threshold → Top-K → RetrievalResult(CANDIDATES|NO_USABLE_CANDIDATE)
```

Hard boundary：无 `final_business_id` / `next_node` / Rule / 材料地点渠道。

---

## TD-4. Module Responsibilities

| 模块 | 职责 |
|------|------|
| `embedding.provider` | `EmbeddingProvider` Protocol + `LocalSentenceTransformerProvider`（同文件，避免过碎） |
| `retrieval.types` | Status / Reason / Result / Candidate |
| `retrieval.admission` | Eligibility artifact load/validate + ONLINE predicate + corpus/fingerprint |
| `retrieval.store` | meta/document + projection_key readiness/search |
| `retrieval.builder` | Full rebuild orchestration |
| `retrieval.service` | Query flow |
| `settings` | Embedding/Retrieval 配置 |
| Fake provider + 768-D helper | **仅 tests**（`tests/test_embedding.py`） |

---

## TD-5. Embedding Provider Design

### TD-5.1 抽象

- 采用 **`typing.Protocol`**（非 ABC）。
- 能力：`provider_name`、`model_id`、`dimension`、`actual_device`、`embed_query`、`embed_documents`、可选 `ensure_ready()`。
- 上层 **禁止** `from sentence_transformers import SentenceTransformer`。
- `LocalSentenceTransformerProvider` 与 Protocol **同文件** `embedding/provider.py`。

### TD-5.2 Local 实现

- `provider_name = "LOCAL_SENTENCE_TRANSFORMER"`
- 从 `EMBEDDING_MODEL_PATH` 加载；**不**调用 ModelScope API。
- `EMBEDDING_MODEL_ID`：identity / observability / compatibility（推荐值 `AI-ModelScope/gte-base-zh`；Settings 默认仍为 `None`，未配置 → NOT_READY）。
- Lazy import / lazy load / `threading.Lock` double-check。
- `ImportError`（extra 未装）→ 受控 NOT_READY / **`DEPENDENCY_UNAVAILABLE`**；不得在 app/settings/retrieval **模块 import** 时冒泡未处理 `ModuleNotFoundError`。
- 路径缺失/文件损坏/load 失败 → **`MODEL_NOT_AVAILABLE`**（与 dependency 区分）。

### TD-5.3 Fake（测试）

- `FakeEmbeddingProvider` + **deterministic 768-D helper**（见 TD-24）；禁止 random。

---

## TD-6. Settings Design

### TD-6.1 新增 Application 字段

| Env / Field | 类型 | Default | 校验 |
|-------------|------|---------|------|
| `EMBEDDING_PROVIDER` / `embedding_provider` | `str \| None` | **`None`** | 若设则仅 `LOCAL_SENTENCE_TRANSFORMER`；**不**默认猜测 LOCAL |
| `EMBEDDING_MODEL_ID` / `embedding_model_id` | `str \| None` | **`None`** | provider 已设时必须 non-empty |
| `EMBEDDING_MODEL_PATH` / `embedding_model_path` | `str \| None` | **`None`** | provider 已设时必须 non-empty；**不**在 Settings 校验路径存在 |
| `EMBEDDING_DEVICE` / `embedding_device` | `str` | **`auto`** | `auto` \| `cpu` \| `cuda` |
| `RETRIEVAL_TOP_K` / `retrieval_top_k` | `int` | **`5`** | `1 <= x <= 50` |
| `RETRIEVAL_MIN_SCORE` / `retrieval_min_score` | `float` | **`0.50`** | **`-1.0 <= x <= 1.0`**（见下） |

全部 Optional 于“是否启用 Embedding”：`provider`/`model_id`/`path` 为 `None` → Retrieval **NOT_READY**；**不影响** Settings 构造与 `/health`。

**`RETRIEVAL_MIN_SCORE` 范围理由：** score = `1 - cosine_distance` 对应 cosine similarity，**数学范围 [-1, 1]**。不得声称天然属于 [0, 1]。Demo 默认 **0.50** 仅为 **Demo Initial Threshold**（参考 smoke 0.71/0.67/0.64 vs 无关 0.38），**不是**生产标定/政策阈值。

### TD-6.2 Dotenv

- `KNOWN_DOTENV_KEYS` + `APPLICATION_DOTENV_KEYS` / `_APPLICATION_SETTINGS_FIELDS` 增加上表全部应用键。
- 维持 F05 Two-Stage。

### TD-6.3 `.env.example`（Code 阶段修改；本阶段不创建）

```text
# EMBEDDING_PROVIDER=LOCAL_SENTENCE_TRANSFORMER
# EMBEDDING_MODEL_ID=AI-ModelScope/gte-base-zh
# EMBEDDING_MODEL_PATH=
# EMBEDDING_DEVICE=auto
# RETRIEVAL_TOP_K=5
# RETRIEVAL_MIN_SCORE=0.50
```

**禁止**写入负责人真实绝对路径（如 `G:\...`）。`EMBEDDING_MODEL_PATH` 留空或注释占位。

---

## TD-7. Dependency Strategy

### TD-7.1 `sentence-transformers`

- 放入 optional extra：`embedding-local`
- 建议范围：`sentence-transformers>=3.0,<7`（验证环境为 **6.0.1**）
- **不**并入默认 `dependencies`，也 **不**强制塞进 `dev`（避免每个开发者无条件装 ML 栈）。
- Code/Test 文档：本地 Provider / real smoke 需 `pip install -e ".[embedding-local]"`（或等价）。

### TD-7.2 PyTorch / CUDA

- **不**在 `pyproject.toml` 钉死 `torch==…+cu118`。
- **策略：** CUDA 版 torch 为 **developer/runtime environment prerequisite**（如 `embedding-test` / `govagent` 环境自备）；项目声明依赖 `sentence-transformers`，由其拉动兼容 torch，或文档给出 cu118 安装指引。
- Runtime Internet：模型文件已存在时 **NOT REQUIRED**。

### TD-7.3 `pgvector` Python 包

- **需要** 新增依赖：`pgvector>=0.3,<0.5`（精确上限 Code 前再核对 PyPI；Design 冻结“需要该包”）。
- 理由：DB extension ≠ Python type；用官方 `Vector` 与 SQLAlchemy 2.x 集成 `vector(768)`，避免手写 bind。
- 放入 **主 dependencies**（与 SQLAlchemy/psycopg 同级）：体积小，integration 与 store 代码始终需要；**不**放进 embedding-local。

---

## TD-8. Device / Lazy Loading

| 项 | 冻结 |
|----|------|
| Lazy import | `sentence_transformers` **仅在** Local Provider 首次加载时 import |
| Lazy load | Provider 可构造；首次 `embed_*` / `ensure_ready` 加载模型 |
| Init lock | `threading.Lock` + double-checked locking（防并发双载 OOM） |
| `auto` | CUDA available → `cuda`，否则 `cpu` |
| 显式 `cpu` | 强制 CPU |
| 显式 `cuda` | 要求 GPU；不可用 → **NOT_READY**（`DEVICE_UNAVAILABLE`），**禁止** silent 改 CPU |
| 路径检查 | 仅在 load 时；失败 → NOT_READY；日志不打印完整绝对路径 |

---

## TD-9. Corpus Projection Design

### TD-9.1 RF-F06-R01 结论

- **可用：** `category` + `canonical_name`（均 SOURCE 级业务元数据，可追踪）。
- **不可用：** aliases / examples / summary / keywords — **禁止编造**。
- **Golden：** Resource Gate smoke 仅用事项名即可把“灵活就业…”排 Top-1（0.7104）；MVP 语料 **足够**做 DEMO_SS_001 recall。
- **Future curation：** 若召回不足，另开数据治理补 aliases/examples；**非** F06 Code 造数。

### TD-9.2 文档粒度

- **1 Online Business → 1 Retrieval Document**（无 chunking / multi-vector）。

### TD-9.3 `retrieval_text` 算法（确定性）

```text
retrieval_text = strip(category) + "\n" + strip(canonical_name)
```

- 任一为空 → builder fail-closed（该 business 不得入投影）。
- **不**拼接 materials / locations / channels / legal_basis / conditions。

### TD-9.4 Source fingerprint

- **采用** SHA-256（hex）对规范化 payload：

```text
f"{business_id}|{data_version}|{category}|{canonical_name}|{projection_version}|{policy_version}"
```

- 用途：trace / corpus 输入变化；**不** hash embedding 向量；**不** hash 本机 model path。

---

## TD-10. Retrieval Eligibility Implementation

### TD-10.1 正式定位（DESIGN DECISION CONFIRMED）

**Online Retrieval Admission Policy Artifact**
路径（Code 阶段创建）：`data/retrieval/f06_online_eligibility.json`

| 是 | 不是 |
|----|------|
| 在线检索准入策略 | Business Data / Verification SoT |
| Git-reviewed、versioned、deterministic | Evidence / Rule / Knowledge Source |
| 只回答“是否允许进入 online semantic retrieval” | 业务事实副本 |

**禁止**在 artifact 中复制：`canonical_name`、`category`、materials、locations、channels、legal basis、verification/source facts。

**TD-F06-01** → **DESIGN DECISION CONFIRMED**（不再作为 Active Finding）。

### TD-10.2 最小 JSON Contract（冻结）

```json
{
  "schema_version": 1,
  "policy_version": "f06-online-v1",
  "entries": [
    {
      "business_id": "DEMO_SS_001",
      "decision": "ALLOW",
      "reason": "current_demo_online_scope"
    }
  ]
}
```

| 字段 | 语义 |
|------|------|
| `schema_version` | Artifact **文件结构**版本；当前 **1** |
| `policy_version` | Online **admission policy** 版本；当前 **`f06-online-v1`** |
| `business_id` | 仅引用已有 Runtime Business identity |
| `decision` | F06 仅接受 **`ALLOW`**；未列入 = 默认 **DENY**（不维护大量 DENY 行） |
| `reason` | 非空；说明为何进入当前 online scope；**≠** VERIFIED |

**三版本分离（不得混用）：**

| 版本 | 值 | 职责 |
|------|-----|------|
| `schema_version` | `1` | artifact 格式 |
| `policy_version` | `f06-online-v1` | 准入策略 |
| `projection_version` | `business-intent-v1` | corpus/projection 算法 |

### TD-10.3 Fail Closed / Invalid Policy

| 条件 | 行为 |
|------|------|
| 未列入 `entries` | DENY |
| Artifact 无法解析 / `schema_version` 不支持 / `policy_version` 缺失 | **fail closed** → rebuild **NOT_READY / `POLICY_INVALID`**；**不得**改现有 READY projection |
| `entries` 重复 `business_id` | Artifact **INVALID**（禁止 first/last wins）→ 同上 |
| Artifact 中 `business_id` 在 Runtime 不存在 | **不得**创造 Business / document；**整个 rebuild fail closed**（禁止 silently skip 后标 READY） |
| `reason` 空 | INVALID |
| `decision` ≠ `ALLOW` | INVALID（本期） |

### TD-10.4 ONLINE 确定性谓词（AND）

1. Artifact 显式 `ALLOW`
2. Runtime Snapshot 真实存在
3. `status == ACTIVE`
4. `data_scope != TEST`
5. `primary_source_id` 可在当前 Snapshot `sources` 中确定性解析

第 5 条 = **data integrity / admission safety**，**≠ VERIFIED**。

Similarity **永远不能**覆盖 Eligibility（即使 score=0.99）。

### TD-10.5 Rebuild 必须 fresh-read

每次 full rebuild **必须重新读取**：

- F02 Runtime Business Data
- **当前** Eligibility Artifact

**禁止**从 `semantic_retrieval_document.eligibility_scope` 或旧 meta 推断下一轮 eligibility。
Projection 内 eligibility 列仅为 **derived metadata**，不是下一轮 admission truth。

---

## TD-11. Database Schema

**2 表**；无业务主表 FK。MVP **只维护一个 active online projection**（成功 rebuild 替换旧 rows/meta）；search 仍强制 `projection_key` defense-in-depth。

### TD-11.1 `projection_key`

确定性稳定 identity（**无**本机 path / timestamp / random）：

```text
projection_key = SHA256_hex(
  canonical(provider_name) + "\0" +
  canonical(model_id) + "\0" +
  str(768) + "\0" +
  projection_version + "\0" +
  policy_version
)
```

完整 identity 保存在 **meta**；document 只存 `projection_key`（避免每行重复 provider/model/dim/versions）。

### TD-11.2 `semantic_retrieval_index_meta`

| Column | Type | Null | 用途 |
|--------|------|------|------|
| `projection_key` | `TEXT` PK | NO | 当前 projection identity |
| `index_name` | `TEXT` | NO | 固定 `'business_intent'` |
| `provider_name` | `TEXT` | NO | |
| `model_id` | `TEXT` | NO | |
| `embedding_dimension` | `INTEGER` | NO | 768 |
| `projection_version` | `TEXT` | NO | `business-intent-v1` |
| `policy_version` | `TEXT` | NO | `f06-online-v1` |
| `document_count` | `INTEGER` | NO | `>= 0` |
| `status` | `TEXT` | NO | `'READY'` |
| `built_at` | `TIMESTAMPTZ` | NO | |

### TD-11.3 `semantic_retrieval_document`

| Column | Type | Null | 用途 |
|--------|------|------|------|
| `projection_key` | `TEXT` | NO | 绑定 meta（PK 组成部分） |
| `business_id` | `TEXT` | NO | candidate identity |
| `display_name` | `TEXT` | NO | canonical_name |
| `direction` | `TEXT` | NO | category |
| `retrieval_text` | `TEXT` | NO | |
| `eligibility_scope` | `TEXT` | NO | `'ONLINE'` **derived only** |
| `source_data_version` | `INTEGER` | NO | |
| `source_fingerprint` | `TEXT` | NO | |
| `embedding` | `vector(768)` | NO | |
| `updated_at` | `TIMESTAMPTZ` | NO | |

**PK：** `(projection_key, business_id)`。

**Search 硬规则：** `WHERE projection_key = :current_key` **必须**；禁止全表 distance。另保留 `eligibility_scope = 'ONLINE'` 双保险。

---

## TD-12. Migration 0002

| 项 | 冻结 |
|----|------|
| File | `alembic/versions/0002_semantic_retrieval_projection.py` |
| `revision` | `0002` |
| `down_revision` | `0001` |
| upgrade | `CREATE TABLE` meta + document；`embedding vector(768)` **静态**；含 `projection_key`、`policy_version` |
| downgrade | `DROP TABLE semantic_retrieval_document` → `DROP TABLE semantic_retrieval_index_meta`（**不** DROP extension） |

**禁止** 从 `.env` 读 dimension。

---

## TD-13. Projection Metadata / Readiness

| 状态 | 判定 |
|------|------|
| **INDEX_MISSING / NOT BUILT** | 无兼容 `projection_key` 的 READY meta |
| **BUILT + EMPTY** | meta READY + identity 全匹配 + `document_count == 0` |
| **BUILT + DATA** | READY + 匹配 + `document_count > 0` |
| **MISMATCH** | 有投影但 provider/model/dim/projection_version/policy_version 与 runtime 不一致 → **NOT_READY**（不得 fallback 其它 projection） |

Built-empty + valid query → **`NO_USABLE_CANDIDATE`**（不是 INDEX_MISSING）。

---

## TD-14. Embedding Identity

| 常量 | 值 |
|------|-----|
| Expected schema dimension | **768** |
| `PROJECTION_VERSION` | `business-intent-v1` |
| `POLICY_VERSION` | `f06-online-v1` |
| `INDEX_NAME` | `business_intent` |
| Identity inputs | provider + model_id + dimension + projection_version + **policy_version** → `projection_key` |

**不**把本地绝对 model path 写入 identity / DB。

### Dimension 两层门禁

| 层 | 含义 |
|----|------|
| Expected Schema Dimension | Migration `vector(768)` + Resource Gate |
| Actual Provider Dimension | 模型 load 后 `provider.dimension` |

二者必须 **严格相等**；否则 **禁止** 写入 / 查询 `vector(768)`。

---

## TD-15. Similarity Metric

- **冻结：Cosine Similarity**（gte-base-zh / sentence-transformers 语义匹配惯例；与 Resource smoke 一致）。
- pgvector 运算符：`<=>`（cosine **distance**）。
- **Score（higher-is-better）：** `score = 1.0 - cosine_distance`。
- 调用方只消费 score；不暴露 distance 为对外主语义。

---

## TD-16. Normalization

- **冻结：`normalize_embeddings=True`**（query 与 documents **同一策略**）。
- 与 cosine + `1 - distance` 对齐。

---

## TD-17. Exact Scan / ANN Decision

- **冻结：Exact Scan（`ORDER BY embedding <=> :q`）**
- **NO HNSW / NO IVFFlat**（Demo 事项极少；行为简单；测试可控）。
- 未来数据量增长另开 migration 加 ANN。

---

## TD-18. Top-K

- **Default：`5`**
- 理由：广召回交给 Graph 收敛；Demo 体量小；可配置。
- Settings：`RETRIEVAL_TOP_K`；校验 `1..50`。

---

## TD-19. Threshold

- **Default Demo initial：`0.50`**
- 配置合法范围：**`[-1.0, 1.0]`**
- **不是**生产最优/政策/大规模统计标定值。
- Threshold 只过滤 semantic usable candidate，≠ verified / final。

---

## TD-20. Build / Rebuild Lifecycle（最终冻结）

```text
fresh-read Runtime Business Data
→ fresh-read Eligibility Artifact（validate schema/version/duplicates）
→ ONLINE predicate
→ retrieval_text = category + "\n" + canonical_name
→ source fingerprint
→ lazy provider/model
→ assert provider.dimension == 768 else STOP (no DB write)
→ embed_documents(normalize=True)
→ assert every embedding len == 768 else STOP (no DB write)
→ short transaction:
     DELETE documents/meta for previous active online projection
       (MVP: replace current online projection set)
     INSERT documents (projection_key=...)
     UPSERT/INSERT meta READY + document_count + identity
→ COMMIT
```

- Encode **在事务外**；任一 dimension/policy 失败 → **不开启** replace 事务。
- 事务失败 → **ROLLBACK**；旧 READY **保留**。
- **Concurrent rebuild：** F06 = **single-process administrative**；**不支持**两 rebuild 并发；不实现 advisory/Redis/distributed lock。
- **Concurrent retrieval：** 依赖 PostgreSQL 事务原子性；reader 不看到半删除中间 committed 态。

---

## TD-21. Retrieval Query Flow（最终冻结）

1. Deterministic normalize（strip）
2. Empty/whitespace → **`INVALID_QUERY`**（0 embed / 0 search）
3. Light config：provider/model_id/path 未配置 → **`NOT_READY(PROVIDER_NOT_CONFIGURED)`**
4. DB availability → fail **`UNAVAILABLE`**
5. Load projection meta
6. Cheap identity：provider、model_id、expected dim=768、projection_version、policy_version / `projection_key` 兼容性 → fail **`NOT_READY`**（**不加载模型**）
7. Lazy load provider（此处才可能 import ST / load weights）
8. `ImportError` → **`DEPENDENCY_UNAVAILABLE`**
9. Load fail / path → **`MODEL_NOT_AVAILABLE`**；显式 cuda 不可用 → **`DEVICE_UNAVAILABLE`**
10. **`provider.dimension == 768`** else **`DIMENSION_MISMATCH`**（0 vector query）
11. `embed_query`
12. **`len(query_embedding) == 768`** else **`DIMENSION_MISMATCH`**
13. Exact cosine search **`WHERE projection_key = :key`**（+ ONLINE 双保险）
14. `score = 1 - cosine_distance`；`score >= min_score`；sort；Top-K
15. Direction hint = rank-1 `direction`（= category）；无候选则 `None`
16. **`CANDIDATES`** 或 **`NO_USABLE_CANDIDATE`**

Direction = **hint**，不是 final domain truth。

---

## TD-22. Retrieval Status / Result Model

### TD-22.1 `RetrievalStatus`

`INVALID_QUERY` | `UNAVAILABLE` | `NOT_READY` | `NO_USABLE_CANDIDATE` | `CANDIDATES`

### TD-22.2 `NotReadyReason`（最终集合）

`PROVIDER_NOT_CONFIGURED` | `DEPENDENCY_UNAVAILABLE` | `MODEL_NOT_AVAILABLE` | `DEVICE_UNAVAILABLE` | `INDEX_MISSING` | `MODEL_MISMATCH` | `DIMENSION_MISMATCH` | `PROJECTION_VERSION_MISMATCH` | `POLICY_VERSION_MISMATCH` | `POLICY_INVALID`

### TD-22.3 Result / Candidate

Result：`status`、`reason`、`query`、`direction`、`candidates`、`provider_name`/`model_id`/`projection_version`/`policy_version`/`projection_key`、`top_k`/`min_score`。

Candidate：`business_id`、`display_name`、`score`、`rank`、`direction`、`eligibility_scope`（audit；≠ verification）。

**禁止：** `final_business_id`、`confirmed_business_id`、`next_node`、embedding vector。

---

## TD-23. Failure Handling（摘要）

| 场景 | Status / Reason |
|------|-----------------|
| Empty query | `INVALID_QUERY` |
| PG down | `UNAVAILABLE` |
| Provider/path unset | `NOT_READY` / `PROVIDER_NOT_CONFIGURED` |
| ST extra 未安装 | `NOT_READY` / `DEPENDENCY_UNAVAILABLE` |
| Model path/load fail | `NOT_READY` / `MODEL_NOT_AVAILABLE` |
| Explicit cuda unavailable | `NOT_READY` / `DEVICE_UNAVAILABLE` |
| Index missing | `NOT_READY` / `INDEX_MISSING` |
| Identity/policy mismatch | `NOT_READY` / `MODEL_MISMATCH` \| `*_VERSION_MISMATCH` |
| Policy artifact invalid | `NOT_READY` / `POLICY_INVALID` |
| Dimension mismatch | `NOT_READY` / `DIMENSION_MISMATCH` |
| Ready + 0 above threshold | `NO_USABLE_CANDIDATE` |

---

## TD-24. Testing Architecture

| Layer | Marker | Provider | DB | Real model |
|-------|--------|----------|-----|------------|
| A Unit | default | Fake + 768-D helper | No | **No** |
| B Integration | `integration` | Fake 768-D | `gov_service_agent_test` + 0002 | **No** |
| C Real smoke | `embedding_real` | Local gte-base-zh | No（默认） | **Opt-in** |
| D Real+DB | `embedding_real` + `integration` | Local + Test DB | Yes | **Opt-in** |

**Fake 768-D helper（冻结）：** deterministic factory，默认 `dimension=768`；可用 fixed one-hot/sparse 构造可控 cosine ranking；**禁止** random / 真实模型；**禁止**各测试手写 `[0.0]*768` 散落修改。概念：`make_test_vector(primary_index, secondary_index=None, dimension=768)`（最终函数名按 test style）。

**Unit 必测：** ImportError → `DEPENDENCY_UNAVAILABLE`；基础 package import 在无 `embedding-local` 时仍成功。

**Real smoke：** 模型路径仅 env/Settings；**禁止**硬编码 `G:\...`；Golden 只断言 `DEMO_SS_001` 高相关 **candidate**。

保持 F05：`TEST_DATABASE_URL` process env；DB name guard；`configure_logger=False`。

`JsonBusinessRepository`：新增 `list_business_ids()` / `iter_snapshots()`。

---

## TD-25. Security / Observability

**Log：** provider、model_id、dimension、actual_device、status、reason、candidate_count、embed_ms、search_ms。
**禁止：** full vector、secret、完整 model 绝对路径、不必要完整敏感 query。

---

## TD-26. Performance Boundary

Exact scan + 小数据 + Local Demo。不建 micro-benchmark 框架；可记录 embed/search 耗时。

---

## TD-27. Planned File Changes（Exact Paths）

### Production NEW

| Path | 职责 |
|------|------|
| `src/gov_service_agent/embedding/__init__.py` | 导出 Provider |
| `src/gov_service_agent/embedding/provider.py` | Protocol + LocalSentenceTransformerProvider |
| `src/gov_service_agent/retrieval/__init__.py` | 导出 service/types |
| `src/gov_service_agent/retrieval/types.py` | Status / Reason / Result / Candidate |
| `src/gov_service_agent/retrieval/admission.py` | Artifact + ONLINE predicate + corpus/fingerprint |
| `src/gov_service_agent/retrieval/store.py` | meta/document + projection_key search/readiness |
| `src/gov_service_agent/retrieval/builder.py` | Full rebuild |
| `src/gov_service_agent/retrieval/service.py` | Query orchestration |

**新核心 Python（不含 `__init__.py`）：6**

### Production MODIFY

| Path | 职责 |
|------|------|
| `src/gov_service_agent/settings.py` | Embedding/Retrieval fields + dotenv keys |
| `src/gov_service_agent/business_data/repository.py` | `list_business_ids` / `iter_snapshots` |

**不修改：** `main.py`

### Migration NEW

| Path | 职责 |
|------|------|
| `alembic/versions/0002_semantic_retrieval_projection.py` | meta + document + `vector(768)`；downgrade document→meta |

### Data / Config

| Path | 动作 | 职责 |
|------|------|------|
| `data/retrieval/f06_online_eligibility.json` | NEW（Code 阶段） | Admission policy artifact |
| `.env.example` | MODIFY | 安全 placeholders（无真实绝对路径） |
| `pyproject.toml` | MODIFY | `pgvector` dep；`embedding-local` extra；marker `embedding_real` |

### Tests

| Path | 动作 | 职责 |
|------|------|------|
| `tests/test_settings.py` | MODIFY | Embedding/Retrieval settings validation |
| `tests/test_embedding.py` | NEW | Protocol Fake、768-D helper、lazy ImportError→DEPENDENCY_UNAVAILABLE |
| `tests/test_retrieval_service.py` | NEW | Query statuses / Top-K / threshold / empty / identity filter |
| `tests/test_retrieval_builder.py` | NEW | Admission/corpus/fingerprint/rebuild orchestration（无 DB 或 mock store） |
| `tests/integration/test_retrieval_db.py` | NEW | 0002 + Fake rebuild/search/built-empty |
| `tests/integration/test_embedding_real.py` | NEW | Opt-in real model（± DB via `integration` marker） |

**新 test 文件：5**；无“或并入/约/*”。

### Docs

| Path | 阶段 | 职责 |
|------|------|------|
| `docs/features/F06-embedding-semantic-retrieval.md` | 本 Feature | Requirement + Technical Design |
| `docs/code-reading/F06-embedding-semantic-retrieval-code-reading.md` | **Explanation** | Code-Reading（**现不创建**） |

### Path count

| 类别 | 数量 |
|------|------|
| Production NEW（含 `__init__`） | 8 |
| Production MODIFY | 2 |
| Migration | 1 |
| Data/Config | 3 |
| Tests NEW+MODIFY | 6 |
| Docs（Code-Reading planned） | 1 |
| **Total planned（Code+Explanation，不含本已存在 Feature 文档作为“新增”）** | **21** |

**仍 >18 的必要性：** Embedding Provider 与 Retrieval 职责分离 + Eligibility Artifact + Projection Store + F05 风格三层测试（unit / DB / real opt-in）+ Settings/dotenv 扩展；已合并 `local.py`→`provider.py`、`corpus+eligibility`→`admission.py`，测试从 7 压到 5 NEW。不强制再合并不同职责模块。

---

## TD-28. Code-Reading Plan

- Path：`docs/code-reading/F06-embedding-semantic-retrieval-code-reading.md`
- 创建阶段：**Explanation**（非 Code / 非本阶段）

---

## TD-29. Technical Design Decisions / Findings

| ID | 状态 | 说明 |
|----|------|------|
| **TD-F06-01** | **DESIGN DECISION CONFIRMED** | Version-controlled Fail-Closed Online Retrieval Admission Policy Artifact |
| **TD-F06-02** | **INFO / DEFERRED DATA CURATION** | Intent 语料仅 `category`+`canonical_name`；禁止造数 |
| **TD-F06-03** | **INFO / ACCEPTED RUNTIME STRATEGY** | CUDA torch = environment prerequisite；不钉死 cu118 进普通 PyPI dep |

**Active Design Findings：** 无。
**BLOCKING / unresolved MAJOR / unresolved MINOR：** **0**。

---

## TD-30. Technical Design Open Items

**Code-blocking Open Items：0**

Non-blocking future：

- Future corpus curation（aliases/examples 等）
- Remote Embedding Provider
- ANN scaling / multi-worker rebuild locks

---

## TD-31. Technical Design Acceptance Checklist（CODE READY）

- [x] Artifact schema / fail closed / fresh-read / 非 SoT
- [x] schema_version ≠ policy_version ≠ projection_version
- [x] Query + Rebuild actual dimension == 768 强制门禁
- [x] Score validator [-1, 1]；default 0.50 Demo-only
- [x] DEPENDENCY_UNAVAILABLE ≠ MODEL_NOT_AVAILABLE
- [x] projection_key；search 强制 identity filter
- [x] Built-empty → NO_USABLE_CANDIDATE
- [x] Concurrent rebuild = single-process admin only
- [x] Fake 768-D helper；exact planned paths
- [x] No HTTP；no main.py；no final_business_id
- [x] Code-Reading Explanation scope
- [x] 0 Code-blocking open items

---

## Document Control

| 项 | 值 |
|----|-----|
| Requirement | **CLOSED** |
| Technical Design | **CLOSED** |
| Code | **PASS** |
| Test | **PASS** |
| Review | **CLOSED**（PASS WITH DEFERRED INFO） |
| Explanation | **COMPLETED** |
| Code-Reading | `docs/code-reading/F06-embedding-semantic-retrieval-code-reading.md` |
| Commit | NOT STARTED（禁止本阶段） |
| Push | NOT STARTED |
| Next authorized step | Owner 明确授权后 Commit → Push |
