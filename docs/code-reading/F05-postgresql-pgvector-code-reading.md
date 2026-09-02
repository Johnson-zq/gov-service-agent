# F05 Code Reading — PostgreSQL + pgvector Minimum Local Docker

面向已读过 F01 Settings / F02–F04 业务决策链路的开发者（懂 Python 基础，不必先精通 SQLAlchemy）。

**核心问题：**

> F05 为什么先接 PostgreSQL + pgvector，却不建业务表、不做语义检索？代码里 Engine、Settings、Alembic、Integration Test 各自守哪道边界？

**功能状态：** F05 **CLOSED**（功能 commit `8ca464a`）。本文是 Documentation Maintenance，不是重新打开 F05 开发。

最新验证证据（权威，来自 F05 Test / Feature 记录）：

| 项 | 结果 |
|----|------|
| Python | 3.11.16（govagent） |
| Settings-only | **31 / 31 PASS** |
| Phase A targeted | **44 / 44 PASS** |
| No-Docker Full | **152 passed / 1 skipped** |
| Integration | **3 / 3 PASS** |
| TF-F05-003 reproducer | **9 / 9 PASS** |
| Final Full | **153 / 153 PASS** |
| PostgreSQL | **16.15** |
| pgvector extension | **0.8.6** |
| Image | `pgvector/pgvector:0.8.6-pg16` |

---

## 1. F05 到底做了什么

F05 的核心任务**不是**做语义检索，而是给后续 **F06 Embedding / Semantic Retrieval** 搭好**数据库基础设施**。

最终完成：

1. Docker Compose：PostgreSQL **16**
2. **pgvector 0.8.6** extension（经由 Alembic baseline）
3. **SQLAlchemy 2.x** 同步栈
4. **psycopg3**（URL 驱动名 `postgresql+psycopg`）
5. **lazy Engine**（无 URL 不创建；同 URL 复用）
6. **SessionFactory**（`sessionmaker`，尚无 Depends/Repository）
7. **DB readiness**：`check_db` 三态
8. **Alembic** schema migration（`0001` 仅 `CREATE EXTENSION vector`）
9. **Dev / Test DB isolation**（`gov_service_agent` vs `gov_service_agent_test`）
10. **Local-First**：无库 / 库挂也能启动应用；`/health` 不绑 DB

**F05 明确没有：**

- business / document / chunk / embedding **table**
- `vector(N)` 列、HNSW / IVFFlat
- Semantic Retrieval、Embedding Provider、LLM、Redis
- Repository / Unit of Work / FastAPI `get_db` Depends
- HTTP DB readiness endpoint（`main.py` 未接 DB）

这些不是“没做完”，而是 **Feature Boundary**：维度、度量、索引策略属于 F06。

---

## 2. F05 在架构中的位置

```
F02  Business Data Contract（JSON Snapshot）
        ↓
F03  Business Graph Domain
        ↓
F04  Deterministic Transition + Rule Selection
        ↓
F05  Database Infrastructure   ← 你在这里
        ↓
F06  Embedding + Semantic Retrieval（未来）
```

| Feature | 回答的问题 |
|---------|------------|
| F02 | 业务事实长什么样？（当前 Demo SoT） |
| F03 | 决策图与知识关系如何结构化？ |
| F04 | 标准 slots 如何确定性推进？规则如何就绪？ |
| **F05** | **本机如何有可复现的 PG + pgvector + 连接地基？** |
| F06 | 如何真正把向量检索接到库与 Agent？ |

**强调：** F05 接入的 PostgreSQL **当前不是** Business Data Source of Truth。
Demo Runtime 业务事实仍来自 **F02 JSON**。PostgreSQL 只是基础设施能力层。

---

## 3. 文字架构图

### 3.1 应用连接路径

```
Application
    |
  Settings  (get_settings)
    |
  DATABASE_URL  (Optional)
    |
  get_engine()  /  get_session_factory()  /  check_db()
    |
  SQLAlchemy Engine  (+ sessionmaker)
    |
  psycopg3
    |
  PostgreSQL 16
    |
  pgvector extension  (via Alembic 0001)
```

### 3.2 Docker 路径

```
Docker Compose (compose.yaml)
    |
  postgres service
    image: pgvector/pgvector:0.8.6-pg16
    |
  Container  ←→  Named Volume: pgdata
    |
  localhost:5432
```

### 3.3 Migration 路径

```
Alembic (CLI or programmatic Config)
    |
  env.py  →  get_url()  (Config 优先于 Settings)
    |
  0001_enable_pgvector
    |
  CREATE EXTENSION IF NOT EXISTS vector
```

---

## 4. 推荐阅读顺序

| 顺序 | 文件 | 为什么现在看 |
|------|------|--------------|
| 1 | `compose.yaml` | 先建立「本机到底跑什么」的心智模型 |
| 2 | `settings.py` | Optional URL、Two-Stage dotenv、驱动校验 |
| 3 | `db/runtime.py` | Engine / SessionFactory 生命周期 |
| 4 | `db/readiness.py` | `check_db` 三态与安全字段 |
| 5 | `db/__init__.py` | 公开 API 边界 |
| 6 | `alembic.ini` | URL 留空、避免把 DSN 写进 Git |
| 7 | `alembic/env.py` | URL precedence、`configure_logger` |
| 8 | `alembic/versions/0001_enable_pgvector.py` | baseline 只做 extension |
| 9 | `tests/test_settings.py` | Settings 契约与 TF-F05-001 |
| 10 | `tests/test_db_runtime.py` | 无 Docker 的 Engine / readiness 行为 |
| 11 | `tests/integration/test_db_integration.py` | Guard + 真实 migration + TF-F05-003 |

**为什么这个顺序：** 先基础设施外形（Compose），再配置契约（Settings），再运行时对象（Engine），再 schema 版本（Alembic），最后用测试锁住边界。`main.py` 只读了解「应用不依赖 DB 启动」即可，F05 未改它。

---

## 5. `compose.yaml`：本机 PostgreSQL 怎么起

```yaml
services:
  postgres:
    image: pgvector/pgvector:0.8.6-pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-gov_service_agent}
      POSTGRES_USER: ${POSTGRES_USER:-govagent}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      ...
volumes:
  pgdata:
```

| 项 | 含义 |
|----|------|
| **image** | 精确 tag：PostgreSQL **16** + 已安装 **pgvector** 的官方扩展镜像。它**仍是 PostgreSQL**，不是独立「向量数据库产品」。 |
| **5432:5432** | 宿主机访问 `localhost:5432` |
| **POSTGRES_*** | 官方镜像初始化用户/库；**不是** Settings 字段 |
| **`:?` 密码** | 未提供 `POSTGRES_PASSWORD` 时 Compose **失败**，禁止空密码静默启动 |
| **healthcheck** | 容器内 `pg_isready`；≠ 应用 `/health`，≠ `check_db` |
| **pgdata** | Compose-managed named volume |
| **无 `container_name`** | 避免多项目固定名冲突；用 service 名 `postgres` |

---

## 6. Container ≠ 数据；Named Volume 的意义

| 概念 | 是什么 |
|------|--------|
| **Container** | 进程 + 可写层；可删可重建 |
| **`pgdata` volume** | PostgreSQL data directory 的持久化存储 |

| 操作 | 对数据的大方向影响 |
|------|-------------------|
| `docker compose stop` / `start` | 停/起进程，**数据通常保留** |
| `docker compose down` | 通常删 container/network，**named volume 常保留** |
| `docker compose down -v` | **删除 volume** → 数据没了 |

**测试阶段禁止默认 `down -v`：** 会毁掉已跑通的 migration / extension / 测试库状态，把「基础设施验收」变成「反复从零初始化」，并可能误伤本地 Demo 数据。

### 为什么用 Named Volume，而不是 Windows bind mount？

本项目开发机常见组合是 **Windows + Docker Desktop + WSL2**。PostgreSQL 对 data directory 的 **Linux 文件系统语义、权限、锁与路径** 敏感。把 `C:\...` 直接 bind 进 `/var/lib/postgresql/data`，容易踩权限与兼容性问题。Compose-managed `pgdata` 落在 Docker/Linux 侧管理的卷上，更稳妥。这里强调的是 **兼容性与运维可预期性**，而不是一句空泛的「性能更好」。

---

## 7. Settings：两类 dotenv 键与两阶段加载

### 7.1 允许出现在 `.env` 的键 ≠ Settings 字段

```python
KNOWN_DOTENV_KEYS = {
    "APP_ENV", "LOG_LEVEL", "DATABASE_URL",
    "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
    "TEST_DATABASE_URL",
}

APPLICATION_DOTENV_KEYS = {
    "APP_ENV", "LOG_LEVEL", "DATABASE_URL",
}
```

| 键 | 谁消费 | Settings 字段？ |
|----|--------|-----------------|
| `APP_ENV` / `LOG_LEVEL` / `DATABASE_URL` | Application Settings | **是** |
| `POSTGRES_*` | Docker Compose 初始化 | **否** |
| `TEST_DATABASE_URL` | Integration：`os.environ` | **否** |

**原因：** Compose 与 Integration 各有配置边界。把所有环境变量塞进 `Settings`，会让「应用配置」与「运维/测试配置」耦合，并迫使 `extra="forbid"` 模型吞下不该成为运行时字段的东西。

### 7.2 StrictDotEnv 两阶段（必须按这个顺序）

```
Stage 1: dotenv_values(真实 .env)
         → 扫描 raw keys
         → key ∉ KNOWN_DOTENV_KEYS → fail-fast

Stage 2: super().__call__() 得到字段映射
         → 只保留 app_env / log_level / database_url
         → 交给 Pydantic Settings
```

**为什么不能「先让 Pydantic 过滤，再查 unknown」？**
若先走普通 dotenv 映射，未知键可能在进入校验前就被丢掉，**永远触发不了**「未知 key fail-fast」。Stage 1 必须基于 **raw** `dotenv_values`。

### 7.3 `DATABASE_URL` 为何 Optional

- 类型：`database_url: str | None = None`
- 空字符串 / 纯空格 → 归一为 `None`（Local-First：未配置 = 不用库）
- 无 URL：应用仍可启动；`get_engine()` 返回 `None`；`check_db` → `NOT_CONFIGURED`

### 7.4 为什么强制 `postgresql+psycopg`

URL 形如：`postgresql+psycopg://user:pass@host:5432/dbname`

| 部分 | 含义 |
|------|------|
| `postgresql` | SQLAlchemy **dialect** |
| `psycopg` | **driver**（psycopg3） |

当前项目只接受该组合，拒绝 sqlite、bare `postgresql`、`psycopg2`、`asyncpg` 等——与 F05 冻结的同步 psycopg3 栈对齐，避免「看起来能解析、运行时驱动不一致」。

### 7.5 `make_url()` 做什么

Settings 校验里：

```python
parsed = make_url(value)  # 只解析
if parsed.drivername != "postgresql+psycopg":
    raise ValueError(...)
```

**只解析 / 结构校验，不连接数据库，不发 TCP，不执行 SQL。**

### 7.6 TF-F05-001：ValidationError 与 `hide_input_in_errors`

自定义 `ValueError` 文案本身不打印 URL，但 Pydantic 默认 `ValidationError` 字符串常带 **`input_value=`**。若输入是真实 DSN，可能泄露密码。

**Fix：** `SettingsConfigDict(hide_input_in_errors=True)`。

安全示例（占位符，非真实凭据）：

```text
# 非法 scheme 时：错误信息应描述规则，而不回显完整
# postgresql://... 或带 password 的整段 URL
```

---

## 8. `runtime.py`：Engine 与 SessionFactory

### 8.1 三个 module-level cache

```python
_engine: Engine | None = None
_engine_bound_url: str | None = None
_session_factory: sessionmaker[Session] | None = None
```

**为什么要 cache：** `Engine` 持有连接池；每次 `get_engine()` 都 `create_engine` 会浪费资源、打散连接生命周期，测试与多入口调用也更难推理。

### 8.2 `get_engine()` 四分支（对照真实代码）

| Case | 条件 | 行为 |
|------|------|------|
| 1 | `database_url is None` | 返回 `None`，不创建 Engine |
| 2 | 首次有 URL | `create_engine(..., pool_pre_ping=True)` 并缓存 |
| 3 | 缓存存在且 URL 相同 | 直接返回 `_engine` |
| 4 | URL 改变 | `dispose` 旧 Engine → 清空 `_engine` / URL / **`_session_factory`** → 再建 |

### 8.3 伪代码（与实现一致）

```text
get_engine(settings):
  url = settings.database_url
  if url is None:
      return None
  if _engine is not None and _engine_bound_url == url:
      return _engine
  if _engine is not None:
      _engine.dispose()
  _engine = None
  _engine_bound_url = None
  _session_factory = None   # 必须失效
  _engine = create_engine(url, pool_pre_ping=True)
  _engine_bound_url = url
  return _engine
```

### 8.4 Engine ≠ Connection

`Engine` 更接近：**数据库访问入口 + Connection Pool 管理器**。
`create_engine()` **通常不会**立刻连上 PostgreSQL。因此：

- `import gov_service_agent.db` / 加载 Settings **不会**自动连库
- 真正连库发生在 `engine.connect()`、Session 使用、`check_db` 等路径

### 8.5 `pool_pre_ping=True`

从池中取出连接前做可用性探测，减轻「PostgreSQL 重启后池里仍是死连接」的问题。

**它不是：** DB healthcheck、connect timeout、也不是「一切自动重连策略」。

### 8.6 SessionFactory：有工厂，无数据访问层

```python
_session_factory = sessionmaker(bind=engine)
```

`sessionmaker` 是「以后按需创建 Session」的工厂。F05 **没有**：

- FastAPI `Depends(get_db)`
- Repository / UoW / DAO

**现在加这些是过度设计：** 尚无业务表与事务用例。等 F06+ 有真实 persistence，再引入。

### 8.7 为什么 URL 变更必须 `_session_factory = None`

反例：

1. 旧 URL → Engine A，SessionFactory 绑定 A
2. 新 URL → 只建 Engine B，却留下旧 Factory
3. 后续 `session()` 仍可能绑在 **已 dispose 的 A** 上

这是 Technical Design 冻结的 invariant：`get_session_factory()` 总是先调 `get_engine()`，保证清缓存路径先执行。

### 8.8 `_reset_db_runtime_for_tests`

Private helper：dispose + 清空三个 cache。
**不**从 `db/__init__.py` 导出——避免应用代码依赖「测试专用重置」。

### 8.9 RF-F05-M01（Deferred MINOR）

模块级缓存**无锁**。理论上两线程同时首次 `get_engine()` 可能 double-create。
Local Demo / 单线程 pytest 场景可 Deferred；多 worker / 正式高并发部署再评估。**不是「系统已不可用」级别的当前故障。**

---

## 9. `readiness.py`：`check_db` 三态

### 9.1 状态与结果

```python
class DbReadinessStatus(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    READY = "READY"

@dataclass(frozen=True, slots=True)
class DbReadinessResult:
    status: DbReadinessStatus
    error_type: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
```

**故意没有：** username、password、完整 `database_url`、`error_message`（`str(exc)` 可能含敏感信息）。失败只留 `type(exc).__name__`。

### 9.2 完整逻辑

```text
database_url is None
  → NOT_CONFIGURED

else:
  get_engine → connect → SELECT 1
    成功 → READY (+ 安全 host/port/database)
    异常 → UNAVAILABLE (+ error_type + 安全字段)
```

### 9.3 为什么只 `SELECT 1`，不查 pgvector？

| 职责 | 谁负责 |
|------|--------|
| **Connectivity readiness** | `check_db` |
| **Schema / extension 正确性** | Alembic + Integration Test |

Connection readiness ≠ schema readiness。

### 9.4 RF-F05-I01（INFO）

生产 `check_db` **未强制** `connect_timeout`。当前只是 INFO：它不在 startup、不在 `/health`、不是 HTTP readiness。若未来做 `/ready` 或 K8s probe，应考虑显式超时。

### 9.5 `/health` 为什么不依赖 DB？

`main.py` 未接入 `check_db`。DB down / 无 URL 时 **`/health` 仍 PASS**——Local-First：基础存活探针不绑可选基础设施。

---

## 10. `db/__init__.py`：公开 API

只导出：

- `DbReadinessStatus` / `DbReadinessResult` / `check_db`
- `get_engine` / `get_session_factory`

不导出：module cache、`_reset_db_runtime_for_tests`。

---

## 11. Alembic：Schema 版本工具

Alembic **不是**「随便执行 SQL 的数据库客户端」，而是 **Schema Migration Tool**。以后加表/索引应走 `0002`、`0003`…，而不是手改库却不进版本历史。

### 11.1 `alembic.ini`：`sqlalchemy.url` 留空

避免把真实 DSN 写进 Git。运行时由：

1. Config 上的非空 `sqlalchemy.url`，或
2. Settings `DATABASE_URL`

决定。

### 11.2 `env.py` URL precedence（高风险边界）

```text
Priority 1: Config sqlalchemy.url（非空）
Priority 2: Settings.database_url
Priority 3: 都没有 → fail-fast RuntimeError
```

Integration 必须用 `cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)`，让 **Config 压过 Settings**。

### 11.3 危险反例

| 来源 | 库 |
|------|-----|
| `.env` `DATABASE_URL` | `gov_service_agent`（dev） |
| process `TEST_DATABASE_URL` | `gov_service_agent_test` |

若 `env.py` **无条件**用 `get_settings().database_url` 覆盖 Config，Integration 的 `downgrade base` 可能打到 **dev DB**——属于高风险数据库安全问题。

### 11.4 Test DB Guard

`_validate_test_database_url` 在 **任何** Alembic upgrade/downgrade **之前**：

- driver 必须 `postgresql+psycopg`
- database 必须 **精确等于** `gov_service_agent_test`

不能用 `contains("test")` / `endswith("_test")` / 「只相信调用者」。

### 11.5 `0001_enable_pgvector.py`

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

def downgrade() -> None:
    # Intentional no-op
    pass
```

- **`IF NOT EXISTS`：** 幂等，重复 upgrade 不炸
- **downgrade 不 `DROP EXTENSION`：** vector 是 **共享基础设施能力**；业务 rollback 不应拆掉可能被多表依赖的 extension（更禁止 CASCADE）

### 11.6 `target_metadata=None`

F05 无 ORM 业务模型；baseline 只用 `op.execute`。与「不提前建业务 schema」一致。

### 11.7 TF-F05-003：programmatic `fileConfig` 污染 pytest

| 现象 | 单独 Integration PASS；单独 Logging PASS；Final Full 中 F01 logging FAIL |
|------|--------------------------------------------------------------------------|
| 根因 | Alembic `fileConfig()` 默认 `disable_existing_loggers=True`，禁用 `gov_service_agent*` |
| Fix | `config.attributes.get("configure_logger", True)`；CLI 默认 True；Integration 设 `False` **跳过** fileConfig |

这是 **source-level isolation**：源头不污染，比「测完再手工恢复 logger」更可靠。

---

## 12. Tests 分层

| 层 | 文件 | 验证什么 | Docker？ |
|----|------|----------|----------|
| Settings unit | `tests/test_settings.py` | dotenv / URL / hide_input | 否 |
| Runtime unit | `tests/test_db_runtime.py` | Engine lifecycle / readiness（mock） | 否 |
| Integration | `tests/integration/test_db_integration.py` | Guard + 真实 migration + extension | **是** + process `TEST_DATABASE_URL` |

### 普通 pytest 为何不依赖 Docker？

无 `TEST_DATABASE_URL` → migration round-trip **skip**；Guard 用例仍跑。日常开发可不启 PostgreSQL。

### 为何 Integration 只认 process env？

`os.environ.get("TEST_DATABASE_URL")`——**不**经 Settings / 不自动读 `.env`。
Integration 应是**显式动作**，避免「本地 `.env` 碰巧有 key 就偷偷对库做 destructive migration」。

---

## 13. 完整调用链（四条）

**Docker path**

```text
docker compose up
  → postgres container
  → pgdata volume
  → PostgreSQL 16
  →（镜像内）pgvector 可用
```

**Migration path**

```text
DATABASE_URL（或 Config URL）
  → Alembic
  → env.py get_url()
  → 0001
  → CREATE EXTENSION IF NOT EXISTS vector
```

**Application path**

```text
.env → StrictDotEnv → Settings.DATABASE_URL
  → get_engine → Engine → psycopg → PostgreSQL
```

**Readiness path**

```text
check_db → get_engine → connect → SELECT 1
  → READY / UNAVAILABLE / NOT_CONFIGURED
```

**Test path**

```text
process TEST_DATABASE_URL
  → guard（driver + exact DB name）
  → Config override + configure_logger=False
  → Alembic on gov_service_agent_test
```

---

## 14. Local-First 三种场景

| 场景 | 应用启动 | `/health` | `check_db` |
|------|----------|-----------|------------|
| 无 `DATABASE_URL` | 可 | PASS | `NOT_CONFIGURED` |
| 有 URL，DB down | 可 | PASS | `UNAVAILABLE` |
| DB ready | 可 | PASS | `READY` |

对当前 Agent Demo：数据库是**可选能力**，不是进程生死开关。

---

## 15. 为什么 F05 不做业务表（再强调）

当前 **F02 JSON** 仍是 Demo Runtime Business Data Source of Truth。
PostgreSQL 现在只是 Infrastructure。

直到 F06 决定：Embedding Provider / Model / **Dimension**、document-chunk schema、`vector(N)`、similarity metric、index 策略之后，才适合建 Semantic Retrieval schema。F05 提前定表会把未确认假设焊进架构。

---

## 16. F05 → F06 交接边界

**F06 可直接复用：**

- PostgreSQL 16、pgvector 0.8.6
- `get_engine` / `get_session_factory`
- Alembic 框架与 revision 链
- `gov_service_agent_test` + `integration` marker

**F06 必须自己决定：**

- Embedding Provider / Model / Dimension
- Vector schema、Similarity Metric、Index、Top-K、Threshold
- 检索 API 与 Agent 编排如何消费结果

---

## 17. Finding 总结

| ID | 类型 | 问题 | 处理 | 状态 |
|----|------|------|------|------|
| **TF-F05-001** | Test Finding | Pydantic error `input_value` 可能泄露 DSN | `hide_input_in_errors=True` | **CLOSED** |
| **TF-F05-002** | Resource Finding | 首次获取精确镜像时网络资源阻塞 | 精确 image 本地就绪后再 Integration | **CLOSED** |
| **TF-F05-003** | Test Finding | Alembic programmatic `fileConfig` 污染 pytest logging | `configure_logger` opt-out | **CLOSED** |
| **RF-F05-M01** | Review MINOR | Engine module cache 无锁 | **Deferred** | Deferred |
| **RF-F05-I01** | Review INFO | `check_db` 无强制 connect timeout | 当前 tradeoff（非 health/startup） | INFO |

---

## 18. 面试中怎么介绍 F05

### 30 秒版

「F05 给政务 Agent 接的是本机 Docker 上的 PostgreSQL 16 和 pgvector，用 SQLAlchemy 懒建 Engine、Alembic 只开 vector 扩展。库是可选的，没配或挂了应用也能起。业务表和向量检索留给 F06，现在业务事实还是 F02 的 JSON。」

### 2 分钟版

「我们按 Feature 推进：F02–F04 做业务契约和图上的确定性推进；F05 只做数据库地基。Compose 起精确镜像 `pgvector/pgvector:0.8.6-pg16`，数据放 named volume。应用侧 `DATABASE_URL` 可选，Settings 两阶段 dotenv，只把应用字段进 Settings，Compose/Test 键允许出现在 `.env` 但不进模型。Engine 按 URL 缓存，换 URL 会 dispose 并失效 sessionmaker。`check_db` 只做连通性三态，`/health` 不绑库。Alembic baseline 只 `CREATE EXTENSION vector`，downgrade 故意不 DROP。集成测试用独立库名 `gov_service_agent_test`，Config URL 优先于 Settings，migration 前精确校验库名，避免误伤开发库。程序化 Alembic 会关掉 fileConfig，避免污染 pytest 日志。」

---

## 19. FAQ（15）

1. **pgvector 是向量数据库吗？**
   不是。它是 PostgreSQL 的扩展；镜像仍是 PostgreSQL 16。

2. **为什么不用 Milvus？**
   F05 目标是最小可复现本地栈 + 与后续 SQL/事务同库能力；未引入额外向量库运维面。

3. **为什么 F05 没有 `vector(N)` 列？**
   Embedding 维度与检索 schema 属 F06；提前固定会架构耦合。

4. **Engine 是 Connection 吗？**
   不是。Engine 是入口 + 连接池；连接在 `connect()` / Session 时取用。

5. **SessionFactory 是什么？**
   `sessionmaker`：按需创建 Session 的工厂；F05 尚未接 FastAPI Depends。

6. **为什么 URL 变了要 dispose？**
   旧 Engine 绑旧库/旧池；不 dispose 会泄漏资源并继续指向错误目标。

7. **为什么 sessionmaker 也要失效？**
   Factory 绑定旧 Engine；只换 Engine 不清 Factory 会继续用旧绑定。

8. **为什么 `check_db` 只 `SELECT 1`？**
   只测连通性；extension/schema 由 migration 与 Integration 验证。

9. **为什么 `/health` 不查数据库？**
   Local-First：存活探针不依赖可选基础设施。

10. **为什么 downgrade 不删 vector？**
    Extension 是共享基础设施；业务回滚不应 DROP（尤其 CASCADE）。

11. **为什么 test DB 必须固定名字？**
    精确 `gov_service_agent_test`，防止误指向开发库或模糊匹配。

12. **为什么 integration 不用 Settings？**
    只认 process env，避免 `.env` 偶然触发 destructive migration。

13. **为什么普通 pytest 不需要 Docker？**
    无 `TEST_DATABASE_URL` 时真实 migration skip；单元与 Guard 仍可跑。

14. **为什么不用 Windows bind mount？**
    PG data directory 依赖 Linux 文件系统语义与权限；Named Volume 在 Docker Desktop/WSL2 上更稳妥。

15. **为什么没有 Repository/UoW？**
    尚无业务表与事务用例；现在加是过度设计。

---

## 20. 最终学习总结

F05 的核心**不是**「装了一个 PostgreSQL」。它建立的是一整套可交接的地基：

- **可选**数据库配置（Local-First）
- **lazy** DB runtime（Engine / SessionFactory）
- **安全**的 credential 处理（驱动校验、`hide_input_in_errors`、readiness 不回显密码）
- **可迁移** schema（Alembic，baseline 仅 extension）
- **Dev/Test isolation**（Config 优先 + 精确库名 Guard）
- **pgvector capability**（扩展就绪，检索 schema 留给 F06）

读完本文后，你应能对照代码回答：谁连库、谁迁库、谁测库、谁故意不碰业务表。

---

## 附录：关键文件索引

| 路径 | 角色 |
|------|------|
| `compose.yaml` | 本地 PG + volume + healthcheck |
| `.env.example` | 三类配置示例（占位符） |
| `src/gov_service_agent/settings.py` | Two-Stage dotenv + DATABASE_URL |
| `src/gov_service_agent/db/runtime.py` | Engine / SessionFactory |
| `src/gov_service_agent/db/readiness.py` | `check_db` |
| `src/gov_service_agent/db/__init__.py` | Public API |
| `alembic.ini` / `alembic/env.py` | Migration 环境与 URL precedence |
| `alembic/versions/0001_enable_pgvector.py` | Baseline extension |
| `tests/test_settings.py` | Settings 契约 |
| `tests/test_db_runtime.py` | Runtime unit |
| `tests/integration/test_db_integration.py` | Docker Integration |
| `docs/features/F05-postgresql-pgvector-minimum-local-docker.md` | Feature 权威范围与证据 |
| `pyproject.toml` | sqlalchemy / alembic / psycopg + `integration` marker |
