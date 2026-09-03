# F06 Code Reading — Embedding + Semantic Retrieval

面向已读过 F01 Settings、F02–F04 业务决策链路、F05 PostgreSQL/pgvector 的开发者。

**核心问题：**

> F06 如何把自然语言变成「方向候选」，却不抢走 Graph / Rule / 用户确认对 `business_id` 的最终决定权？代码里 Provider、Admission、Store、Builder、Service 各守哪条边界？

**功能状态：** F06 **Review CLOSED**；本文为 Explanation 阶段 Code-Reading。实现仍在 working tree，**尚未 Commit**。

最新验证证据（权威，来自 F06 Test / Review Fix）：

| 项 | 结果 |
|----|------|
| Python | 3.11.16（conda `govagent`） |
| sentence-transformers | 6.0.1 |
| torch | 2.7.1+cu118 |
| pgvector (Python) | 0.4.2 |
| CUDA | available |
| GPU | NVIDIA GeForce GTX 1660 Ti |
| Real dim / device | 768 / `cuda` |
| Phase A unit | 84 passed |
| Default full（Review Fix 后） | **206 passed / 12 skipped / 1 warning** |
| DB Integration | 8 / 8 PASS |
| Final DB non-real | 214 passed / 3 deselected / 1 warning |
| Golden Top-1 | `DEMO_SS_001` rank=1，score≈0.6671（≥0.50） |
| Dev DB `gov_service_agent` | 仍 **0001**（故意） |
| Test DB `gov_service_agent_test` | **0002** |

---

## 1. F06 的职责

F06 **不是**「直接判断用户最终办什么」。

它只做：

```
用户自然语言
  → Embedding（Local Provider）
  → PostgreSQL + pgvector 语义检索
  → Top-K candidates + scores
  → direction hint（来自 rank=1 的 category）
```

然后把「找方向」的结果交给后续 **Business Decision Graph（F03/F04）**、Rule、用户确认。

**硬边界：** Embedding score **不能**决定 `final_business_id`。生产结果类型里也**没有** `final_business_id` / `confirmed_business_id` / `next_node`。

---

## 2. 在整体架构中的位置

```
用户自然语言 Query
        ↓
F06  Semantic Retrieval     ← 你在这里（找方向 / candidate recall）
        ↓
   candidates + direction hint
        ↓
F03/F04  Decision Graph + Rule Selection（确定性推进）
        ↓
用户确认 → 才写入最终 business_id
```

| Feature | 回答的问题 |
|---------|------------|
| F02 | 业务事实长什么样？（Demo SoT = JSON Snapshot） |
| F03 | 决策图如何结构化？ |
| F04 | slots / 规则如何确定性推进？ |
| F05 | 本机如何有可复现的 PG + pgvector？ |
| **F06** | **如何做语义候选召回，且不越权定事项？** |

F06 **不取代** F03/F04。概念流：

`Query → F06 candidates → Graph Entry → deterministic graph → Rule → User Confirm`

---

## 3. 推荐阅读顺序

| 顺序 | 文件 | 先搞懂什么 |
|------|------|------------|
| 1 | `src/gov_service_agent/settings.py` | Embedding / Top-K / Min-Score 如何配置且不破坏基础 app |
| 2 | `src/gov_service_agent/embedding/provider.py` | Protocol + Local lazy load / device / dimension |
| 3 | `src/gov_service_agent/retrieval/types.py` | Status / Reason / Candidate / Result |
| 4 | `src/gov_service_agent/retrieval/admission.py` | Policy artifact + ONLINE predicate + corpus/fingerprint/key |
| 5 | `src/gov_service_agent/retrieval/store.py` | meta/document 表映射、cosine search、atomic replace |
| 6 | `src/gov_service_agent/retrieval/builder.py` | fresh-read → encode 事务外 → 短事务写库 |
| 7 | `src/gov_service_agent/retrieval/service.py` | Online query 编排：cheap 检查 → heavy load → candidates |
| 8 | `alembic/versions/0002_semantic_retrieval_projection.py` | `vector(768)` 两张投影表 |
| 9 | `tests/**` | Fake / DB Fake / Real opt-in 三层 |

辅助数据：`data/retrieval/f06_online_eligibility.json`（Admission Policy，不是业务 SoT）。

---

## 4. 目录与模块职责

| 模块 | 职责 |
|------|------|
| `embedding/provider.py` | `EmbeddingProvider` Protocol；`LocalSentenceTransformerProvider` |
| `retrieval/types.py` | `RetrievalStatus` / `NotReadyReason` / `RetrievalCandidate` / `RetrievalResult`；版本常量 |
| `retrieval/admission.py` | Policy 解析、ONLINE predicate、`build_retrieval_text`、fingerprint、`projection_key` |
| `retrieval/store.py` | DB 持久化 + exact cosine search + `replace_projection` |
| `retrieval/builder.py` | `rebuild_projection`：业务+策略→向量→原子替换 |
| `retrieval/service.py` | `SemanticRetrievalService.retrieve`：在线查询语义 |
| `settings.py` | F06 字段 + Two-Stage dotenv 扩展 |
| `0002_…py` | 投影 schema |
| `f06_online_eligibility.json` | Online Admission Policy artifact |

**分工一览：**

| 层 | 做什么 | 不做什么 |
|----|--------|----------|
| Provider | 产生向量 | 不读业务图、不查库 |
| Admission | 谁可进 ONLINE 投影 | 不写 VerificationStatus |
| Store | DB / pgvector | 不加载模型、不解释业务 |
| Builder | source → projection | 不响应用户 Query |
| Service | Query → RetrievalResult | 不定 final business_id |
| Types | 结果契约 | — |

**没有 HTTP endpoint，也未改 `main.py`：** F06 是内部 capability，供后续 Agent/LangGraph 直接调用 Service；`/health` 不依赖 Embedding。

---

## 5. Settings

Application 字段（可选启用 Embedding）：

| Env | Settings 字段 | 默认 | 含义 |
|-----|---------------|------|------|
| `EMBEDDING_PROVIDER` | `embedding_provider` | `None` | 目前仅允许 `LOCAL_SENTENCE_TRANSFORMER` |
| `EMBEDDING_MODEL_ID` | `embedding_model_id` | `None` | 身份 / observability / projection identity |
| `EMBEDDING_MODEL_PATH` | `embedding_model_path` | `None` | 本地权重目录；Settings **不**校验路径是否存在 |
| `EMBEDDING_DEVICE` | `embedding_device` | `auto` | `auto` \| `cpu` \| `cuda` |
| `RETRIEVAL_TOP_K` | `retrieval_top_k` | `5` | `1..50` |
| `RETRIEVAL_MIN_SCORE` | `retrieval_min_score` | `0.50` | `[-1.0, 1.0]` |

要点：

- 三者（provider / model_id / path）要么全空（Embedding 关闭），要么一起出现。
- Embedding 未配置 → 基础 Settings / `/health` 仍可用；检索侧返回 `NOT_READY` / `PROVIDER_NOT_CONFIGURED`。
- `hide_input_in_errors=True`：ValidationError 不应泄露完整 DSN / 模型路径。

### Two-Stage Dotenv（延续 F05）

- `KNOWN_DOTENV_KEYS`：含 F05 的 `POSTGRES_*` / `TEST_DATABASE_URL` + F06 Embedding 键。
- `APPLICATION_DOTENV_KEYS`：真正进入 Settings 的应用键（不含 Compose/Test 专用键）。
- Stage 1：扫描 `.env` 原始键，未知键 fail-fast。
- Stage 2：只把 Application 字段喂给 Settings。

F06 **没有**绕开 F05 配置安全策略。

### 安全配置示例

```env
EMBEDDING_PROVIDER=LOCAL_SENTENCE_TRANSFORMER
EMBEDDING_MODEL_ID=AI-ModelScope/gte-base-zh
EMBEDDING_MODEL_PATH=<local-model-path>
EMBEDDING_DEVICE=auto
RETRIEVAL_TOP_K=5
RETRIEVAL_MIN_SCORE=0.50
```

不要在文档或代码里写本机绝对路径。

---

## 6. Embedding Provider

### Protocol

`EmbeddingProvider`（`typing.Protocol`，`@runtime_checkable`）约定：

- `provider_name` / `model_id` / `dimension` / `actual_device`
- `embed_query(text)` / `embed_documents(texts)`

Retrieval 层（Builder / Service）依赖 **Protocol**，而不是 `SentenceTransformer` 类本身。这样：

- 单测可注入 Fake；
- 未来可换 Remote Provider，而不改检索语义。

### LocalSentenceTransformerProvider

构造只保存配置（`model_id`、`model_path`、`device`、`expected_dimension`），**不** import `sentence_transformers`，**不**加载权重。

受控错误类型：

| 异常 | 含义 |
|------|------|
| `EmbeddingDependencyError` | optional ST 未安装 |
| `EmbeddingModelError` | 路径不可用 / 加载失败 |
| `EmbeddingDeviceError` | 显式 `cuda` 但 CUDA 不可用 |
| `EmbeddingDimensionError` | 维度与 expected 不符 |

### Lazy Import

`from sentence_transformers import SentenceTransformer` 仅在 `_load_model_unlocked` 内执行。

因此：

```text
import gov_service_agent
import gov_service_agent.embedding
import gov_service_agent.retrieval
```

在未装 `embedding-local` 时仍可成功；普通 tests / `/health` 不强制加载模型。

**TF-F06-001：** 先检查 `model_path.exists()`，再 import ST。路径明显无效 → `EmbeddingModelError`（映射为 `MODEL_NOT_AVAILABLE`），而不是先报 `DEPENDENCY_UNAVAILABLE`。

### Lazy Model Load

- 创建 Provider 对象 ≠ 加载模型。
- 访问 `dimension`、调用 `embed_*` 才会 `_ensure_model_loaded()`。
- `encode(..., normalize_embeddings=True)`。

### Model Init Lock

`threading.Lock` + double-check：同进程内避免并发首次加载把模型装两次、重复占 GPU。

这是 **单进程锁**，不是分布式锁。失败时 `_model` 保持 `None`，不会缓存半初始化对象。

### Device Policy

| 配置 | 行为 |
|------|------|
| `cpu` | 强制 CPU |
| `cuda` | 必须 CUDA；不可用 → `EmbeddingDeviceError`（**无** silent CPU fallback） |
| `auto` | CUDA available → `cuda`，否则 `cpu` |

CUDA 探测在 `_cuda_available()` 内 **lazy import torch**，不在模块顶部。

### Expected vs Actual Dimension

- **Expected schema dimension**：常量 `768`（Resource Baseline + DB `vector(768)`）。
- **Actual provider dimension**：模型加载后由 `get_embedding_dimension`（或旧名 `get_sentence_embedding_dimension`）读取；再不行用 probe encode。

必须 `actual == expected`。另：每个 query / document 向量 `len == 768`（defense-in-depth）。**禁止** pad / truncate。

---

## 7. Eligibility Admission

### Artifact 定位

`data/retrieval/f06_online_eligibility.json` 是 **Online Retrieval Admission Policy**，不是业务事实库，也不是 Verification SoT。

当前内容：

- `schema_version = 1`
- `policy_version = f06-online-v1`
- 唯一 ALLOW：`DEMO_SS_001` / reason=`current_demo_online_scope`

不含 `canonical_name`、materials、location、verification 等业务事实。

### 为什么需要 Artifact

F02 Snapshot 没有 business-level「ONLINE RETRIEVAL ELIGIBLE」字段；又禁止在 production Python 硬编码 `DEMO_SS_001`。因此用版本化、fail-closed 的 policy 文件列出可进 ONLINE 投影的 `business_id`。

### 三类 Version

| 常量 | 值 | 含义 |
|------|-----|------|
| `ARTIFACT_SCHEMA_VERSION` / `schema_version` | `1` | JSON 结构版本 |
| `POLICY_VERSION` / `policy_version` | `f06-online-v1` | 准入策略内容版本 |
| `PROJECTION_VERSION` | `business-intent-v1` | 语料构造 / 投影语义版本 |

三者独立，不可混用。

### Fail Closed（`parse_admission_policy` / `draft_online_documents`）

以下都会抬 `AdmissionPolicyError`（Builder 再包成 `ProjectionRebuildError`）：

- parse 失败、非 object
- unsupported `schema_version`
- 缺 / 空 `policy_version`
- duplicate `business_id`
- `decision != ALLOW`
- empty `reason`
- ALLOW 指向 unknown business
- ALLOW 但 ONLINE predicate 失败

未列入 Policy 的事项：**默认不得**进入 online retrieval。

### Eligibility Predicate（`is_online_retrieval_eligible`）

在 Policy ALLOW 之外还要求：

1. Snapshot 存在（`get_snapshot`）
2. `status == ACTIVE`
3. `data_scope != TEST`
4. `primary_source_id` 能在 `sources` 中解析（**数据完整性门禁**，**不是** VERIFIED）

注释写明：`admission safety; not VERIFIED`。

生产 Python **无**硬编码 `DEMO_SS_001`；仅 artifact 可含该 id。

---

## 8. Retrieval Corpus

`build_retrieval_text(snapshot)`：

```text
category.strip() + "\n" + canonical_name.strip()
```

当前 F02 可用字段只有这两项。没有 aliases / examples / summary / keywords，**禁止**为效果自行造语料（未来 curation = deferred RF-F06-R01 / TD-F06-02）。

---

## 9. Projection Identity

### `source_fingerprint`

SHA-256，输入含：`business_id`、`data_version`、category、canonical_name、`projection_version`、`policy_version`、`retrieval_text`。

用于溯源 / 源变化感知。**不是** embedding hash。不含 timestamp、random、model path、向量本身。

### `projection_key`

`compute_projection_key(...)`：SHA-256，canonical 串由

`provider_name | model_id | dimension | projection_version | policy_version`

（代码用 `\0` 连接）组成。

**不含** `model_path`、`device`、timestamp。

### 为什么关键

查询必须：

```text
WHERE projection_key = <当前 Settings 算出的 compatible key>
```

否则旧模型 / 旧 policy 的向量可能「更近」却不该出现。Store.search 强制该过滤。

---

## 10. PostgreSQL / pgvector Schema

Migration `0002`（`down_revision = "0001"`）只建两张 **派生投影** 表：

### `semantic_retrieval_index_meta`

回答：有没有构建？identity 是谁？`document_count`？是否 `READY`？

关键列：`projection_key`（PK）、`provider_name`、`model_id`、`embedding_dimension`（CHECK = 768）、`projection_version`、`policy_version`、`document_count`、`status`（CHECK = `'READY'`）、`built_at`。

### `semantic_retrieval_document`

关键列：`(projection_key, business_id)` PK、`display_name`、`direction`、`retrieval_text`、`eligibility_scope`（CHECK = `'ONLINE'`）、`source_data_version`、`source_fingerprint`、`embedding vector(768)`、`updated_at`。

**为什么两表：** meta 表达 readiness / identity / count；document 存可检索行。两者通过 `projection_key` 关联。

**不建** business / material / location / channel / rule 等业务事实表。
**downgrade** 只 DROP 两表，**不** `DROP EXTENSION vector`。

当前 **Exact Scan**，无 HNSW / IVFFlat（Demo 数据量小；ANN 属未来）。

---

## 11. Index Build / Rebuild（Builder）

`rebuild_projection(...)` 真实顺序：

1. `load_admission_policy`（fresh-read）
2. `policy_version` 与 expected 对齐
3. `draft_online_documents`（F02 `get_snapshot` + predicate + text + fingerprint）
4. `provider.dimension` gate（== 768）
5. `embed_documents`（**DB 事务外**）
6. 每个 vector `len == 768`
7. 计算 `projection_key`
8. `store.replace_projection`（短事务）
9. 日志 `projection_rebuild_ok`（含 provider / model_id / dimension / count / versions；**无**完整 path）

### 为何每次 fresh-read Policy

旧 `semantic_retrieval_document.eligibility_scope` **不能**反推下一轮 admission。SoT 仍是 F02 + Artifact。

### 为何 Embedding 在事务外

GPU encode 可能慢；放进长事务会拖库。先 encode + 校验，再短事务写。

### Atomic Replace（`ProjectionStore.replace_projection`）

同一 `engine.begin()` 事务内：

1. `DELETE` 全部 document
2. `DELETE` 全部 meta
3. 插入新 documents（可空）
4. 插入 READY meta（`document_count = len(documents)`）

失败 → rollback → **旧 READY 仍在**（事务前不会先标坏或先删）。

MVP 策略：库内只维护 **当前一套** online projection（全表替换），查询仍用 `projection_key` 过滤。

连续 rebuild = full replace，**不会** append 翻倍。

并发：设计为 **single-process administrative rebuild**；无 Redis/分布式锁、无后台 worker。

---

## 12. Online Retrieval Flow（Service）

`SemanticRetrievalService.retrieve(query)` 按代码实际步骤：

1. normalize（`strip`；`None` → `""`）
2. empty / whitespace → `INVALID_QUERY`（0 embed / 0 search）
3. Embedding 未配置 → `NOT_READY` / `PROVIDER_NOT_CONFIGURED`
4. Store：无 engine → `UNAVAILABLE`；`check_connectivity` 失败 → `UNAVAILABLE`
5. 用 Settings 的 provider/model_id + 常量 versions/dim 算 `expected_key`
6. `load_ready_meta(expected_key)`：无 → `NOT_READY` / `INDEX_MISSING`（**cheap，未加载模型**）
7. meta 上再核对 provider/model_id / dim / projection_version / policy_version → 各类 `*_MISMATCH`
8. `document_count == 0` → `NO_USABLE_CANDIDATE`（built-empty，**仍不加载模型**）
9. `_resolve_provider()`（Local Provider 构造仍轻量）
10. `provider.dimension` / `embed_query`；捕获 Dependency/Device/Model/Dimension 错误 → 对应 `NOT_READY`
11. `len(query_vector) == 768`
12. `store.search(projection_key=..., limit=max(top_k*3, 20))` — 先宽取，再在 Service 侧 threshold
13. `score = 1.0 - distance`；保留 `score >= min_score`；填满 Top-K；`rank` 从 1 起
14. 无候选 → `NO_USABLE_CANDIDATE`；有 → `CANDIDATES`，`direction = candidates[0].direction`

### Cheap Before Heavy

`INDEX_MISSING`、`MODEL_MISMATCH`、版本 mismatch、built-empty 都尽量在加载 195MB 模型 / CUDA **之前**完成，避免无意义重负载。

### Built-Empty

Meta `READY` + `document_count=0` ≠ `INDEX_MISSING`。
表示：「索引构建成功，只是当前没有 ONLINE document」。Query → `NO_USABLE_CANDIDATE`。

### Deferred INFO：`policy_path`

Service 构造可收 `policy_path`，但 **query 路径不读 Artifact**（准入已冻结进投影 meta）。Policy 由 Builder 消费。
**RF-F06-002**：unused field，INFO / DEFERRED；不影响正确性。后续可删字段减误导。

---

## 13. Retrieval Status

| Status | 何时 |
|--------|------|
| `INVALID_QUERY` | 空 / 纯空白 query |
| `UNAVAILABLE` | 无 DB / 连接失败 / search 基础设施异常 |
| `NOT_READY` | 配置、依赖、模型、device、index、identity 未就绪 |
| `NO_USABLE_CANDIDATE` | READY 且已执行检索（或合法 built-empty），但无达标候选 |
| `CANDIDATES` | 有可用候选列表 |

### `NotReadyReason`（实际 Enum）

`PROVIDER_NOT_CONFIGURED` · `DEPENDENCY_UNAVAILABLE` · `MODEL_NOT_AVAILABLE` · `DEVICE_UNAVAILABLE` · `INDEX_MISSING` · `MODEL_MISMATCH` · `DIMENSION_MISMATCH` · `PROJECTION_VERSION_MISMATCH` · `POLICY_VERSION_MISMATCH` · `POLICY_INVALID`

（`POLICY_INVALID` 主要为契约完备；在线 query 靠 rebuild 时 fail-closed + meta 版本对齐。）

### Candidate 字段

`business_id` · `display_name` · `score` · `rank` · `direction` · `eligibility_scope`

**禁止：** embedding 向量、`final_business_id`、`next_node`。

### Direction Hint

`RetrievalResult.direction` = rank=1 的 `direction`（来自业务 `category`）。
只是 **hint**，不是 confirmed domain / final intent。

---

## 14. Similarity / Top-K / Threshold

- pgvector：`cosine_distance`；`score = 1 - distance`；越大越相关。
- `RETRIEVAL_MIN_SCORE` 默认 **0.50**，合法 **[-1, 1]**。这是 **Demo Initial Threshold**，不是政策规则、不是业务可信度、不是最终确认阈值。入选条件：`score >= min_score`。
- `RETRIEVAL_TOP_K` 默认 **5**，合法 **1..50**。只是 recall 条数上限，不是「最终选 5 个业务」。
- Service：先 `fetch_limit = max(top_k * 3, 20)`，再 threshold + 截断到 Top-K（避免「先 LIMIT Top-K 再滤阈值」丢边界候选）。

---

## 15. Failure Semantics（排查表）

| 情况 | 结果 |
|------|------|
| Embedding 未配置 | `NOT_READY` / `PROVIDER_NOT_CONFIGURED` |
| `sentence-transformers` 未装 | `NOT_READY` / `DEPENDENCY_UNAVAILABLE` |
| 模型路径错误 / 加载失败 | `NOT_READY` / `MODEL_NOT_AVAILABLE` |
| 显式 cuda 不可用 | `NOT_READY` / `DEVICE_UNAVAILABLE` |
| Index 未构建（无 compatible meta） | `NOT_READY` / `INDEX_MISSING` |
| Identity / 版本不兼容 | `NOT_READY` / 对应 `*_MISMATCH` |
| PostgreSQL 挂 | `UNAVAILABLE` |
| READY 但无达标候选 / built-empty | `NO_USABLE_CANDIDATE` |
| `"   "` | `INVALID_QUERY` |

---

## 16. Test Architecture

| 层 | Marker / 条件 | Provider | DB | 真实模型 |
|----|---------------|----------|-----|----------|
| A Unit | 默认 | Fake + `make_test_vector` | 无 | 无 |
| B Integration | `integration` + `TEST_DATABASE_URL` | Fake 768-D | `gov_service_agent_test` + 0002 | 无 |
| C Real | `embedding_real` + `RUN_EMBEDDING_REAL=1` | Local gte-base-zh | Golden 需 Test DB | **Opt-in** |

- Unit：不加载 195MB 模型；用确定性稀疏 768-D 测 rank / threshold / Top-K。
- DB Integration：真 PG、真 pgvector、真 cosine、projection 过滤、rollback、duplicate rebuild；Embedding 仍 Fake。
- 缺 `TEST_DATABASE_URL` → skip；有 URL 但不可达 → **fail**（对齐 F05）。
- Real：默认 skip。**Review Fix（RF-F06-001）后**：`RUN_EMBEDDING_REAL=1` 但 Embedding 配置缺失 → **`pytest.fail`**，禁止 skip 造成假绿色。路径无效 / CUDA / dim 错误让 Provider 自然 FAIL。

---

## 17. Golden Scenario

**Input：** `我辞职了，现在没单位，想自己交社保`

**Result（已测）：**

| 项 | 值 |
|----|-----|
| Status | `CANDIDATES` |
| Top-1 `business_id` | `DEMO_SS_001` |
| rank | 1 |
| score | ≈ **0.6671**（≥ `RETRIEVAL_MIN_SCORE=0.50`） |
| device | `cuda` |
| dim | 768 |

**只验证 Semantic Candidate Recall。**
后续仍需 Decision Graph、Rule、User Confirmation，才能落到最终事项。

CPU fallback smoke：同一 Provider，`device=cpu`，仍返回 768-D（不要求与 GPU score bitwise 相同）。

---

## 18. Environment / Configuration

普通开发：

```bash
pip install -e ".[dev]"
```

需要本地 Embedding：

```bash
pip install -e ".[dev,embedding-local]"
```

GPU PyTorch：按目标机器单独安装合适 CUDA wheel。
**本机已验证** `torch 2.7.1+cu118`，这是当前验证环境，**不是** `pyproject.toml` 统一硬依赖（不要把 `+cu118` 写进通用依赖）。

| 依赖 | 位置 |
|------|------|
| Python `pgvector` | 主依赖 |
| `sentence-transformers` | optional extra `embedding-local` |
| CUDA torch | runtime prerequisite（机器相关） |

### 数据库状态（收尾时故意如此）

| 库 | Alembic | F06 表 |
|----|---------|--------|
| `gov_service_agent`（dev） | **0001** | 无 |
| `gov_service_agent_test` | **0002** | 有 |

F06 尚未 Commit/Push，故 **不提前** 升级长期开发库。需要本地跑 Semantic Retrieval 时，在正式提交后再对 dev 执行正常 migration 到 0002。**不要**在 Explanation 阶段自行升级。

---

## 19. Common Troubleshooting

见第 15 节表。额外：

- 普通 `pytest` 很慢且占显存 → 是否误设了 `RUN_EMBEDDING_REAL=1`？
- Opt-in 立刻 FAIL「requires embedding configuration」→ 补齐 `EMBEDDING_*`（不要靠 skip 装作跑过）。
- Golden 无候选 → 检查是否 rebuild 过、threshold、policy 是否只 ALLOW 了 Demo、projection_key 是否与 Settings 一致。

---

## 20. Current Deferred Item

| ID | Severity | 状态 | 说明 |
|----|----------|------|------|
| **RF-F06-001** | MINOR | **CLOSED** | Opt-in 缺配置：skip→fail |
| **RF-F06-002** | INFO | **DEFERRED** | Service 保存 `policy_path` 但 query 未用；Builder 才消费 Policy。可后续删除字段减误导；不影响正确性/安全 |

---

## 21. F06 与后续 Feature 的边界

F06 **不做**：LLM 定 `business_id`、用 GraphRAG 代替 Decision Graph、用 Embedding 查材料/地点/渠道、Redis vector cache、Kafka embedding pipeline、Celery 并发 rebuild。

合理未来扩展（非当前范围）：更多 retrieval corpus curation、Remote Embedding Provider、ANN/HNSW、多进程 rebuild 协调。

---

## 22. 一句话总结

> F06 用可替换的 Local Embedding Provider 和可重建的 pgvector 投影，把自然语言收成带分数的 ONLINE 候选与方向提示；准入靠 fail-closed Policy + F02 Snapshot，检索靠 `projection_key` 隔离身份，最终事项仍留给 Graph、Rule 与用户确认。

---

## 附录：关键符号速查

| 符号 | 位置 |
|------|------|
| `EmbeddingProvider` / `LocalSentenceTransformerProvider` | `embedding/provider.py` |
| `RetrievalStatus` / `NotReadyReason` / `RetrievalResult` | `retrieval/types.py` |
| `load_admission_policy` / `is_online_retrieval_eligible` / `compute_projection_key` | `retrieval/admission.py` |
| `ProjectionStore` / `replace_projection` / `search` | `retrieval/store.py` |
| `rebuild_projection` | `retrieval/builder.py` |
| `SemanticRetrievalService.retrieve` | `retrieval/service.py` |
| `0002` | `alembic/versions/0002_semantic_retrieval_projection.py` |
| `RUN_EMBEDDING_REAL` | `tests/integration/test_embedding_real.py` |
