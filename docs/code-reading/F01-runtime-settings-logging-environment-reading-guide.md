# F01 Code Reading Guide — Runtime Settings + Basic Logging + Environment Foundation

本文档面向正在学习 Python / FastAPI / Agent 工程的开发人员。

**核心问题：**

> 一个 HTTP 请求进入 F01 后，Settings、Logging、ASGI Middleware、ContextVar 和 request_id 到底如何协同工作？

最新验证证据（权威）：

| 项 | 结果 |
|----|------|
| Python | 3.11.16 |
| pytest | **29 passed**, 0 failed, 0 skipped, 1 non-blocking warning |
| pip check | No broken requirements found |
| GET /health | HTTP 200, `{"status":"ok"}` |

---

## 1. F01 解决了什么问题

F00 解决了「工程能跑、能测」。F01 解决的是：

> **同一份应用代码，如何在不同运行环境中安全、明确、可观察地启动？**

| F00 已有 | F01 新增 |
|----------|----------|
| FastAPI + `/health` | Settings（`APP_ENV` / `LOG_LEVEL`） |
| Smoke Test | `.env.example` + fail-fast |
| 无结构化应用日志 | 基础控制台日志 + Access Log |
| 无请求追踪 | `request_id` + `X-Request-ID` |

F01 **仍然不是业务 Feature**。没有 Business Graph、Rule Engine、LLM、Embedding。

---

## 2. 推荐阅读顺序

| 顺序 | 文件 | 为什么现在看 | 重点看什么 | 看完应理解 |
|------|------|-------------|-----------|-----------|
| 1 | `.env.example` | 配置入口最小样本 | 只有两行 | F01 当前真正用哪些环境变量 |
| 2 | `pyproject.toml` | 依赖声明 | `pydantic-settings`、`python-dotenv` | 为什么 dotenv 是 **direct** 依赖 |
| 3 | `settings.py` | 配置核心 | Enum、StrictDotEnv、`get_settings` | 配置如何加载与 fail-fast |
| 4 | `logging_config.py` | 日志核心 | owned Handler、propagate | 日志如何初始化且幂等 |
| 5 | `middleware/request_context.py` | 请求链路核心 | ASGI、`send` 包装、ContextVar | 一次请求如何被追踪 |
| 6 | `main.py` | 组装点 | 初始化顺序 | 各模块如何接在一起 |
| 7 | `tests/test_settings.py` | Settings 契约 | `_env_file=None`、非法值 | 配置测试如何与真实 `.env` 隔离 |
| 8 | `tests/test_logging_and_request_id.py` | HTTP/日志契约 | Header、Access Log、幂等 | Middleware 行为如何被测住 |
| 9 | `tests/test_health.py` | F00 回归 | `/health` 契约未变 | F01 没有破坏基线 |
| 10 | `README.md` | 开发者操作说明 | APP_ENV 语义、Local-First | 如何本地启动 |
| 11 | F01 Feature 文档 | 范围与阶段权威 | Finding、Completion Criteria | F01 完成到哪一步 |

---

## 3. Settings：pydantic-settings 与 BaseSettings

### 3.1 pydantic-settings 是什么

`pydantic-settings` 在 Pydantic 模型之上，增加了从**环境变量 / `.env` 文件**填充字段的能力。

### 3.2 BaseSettings vs BaseModel

| | `BaseModel` | `BaseSettings` |
|--|-------------|----------------|
| 主要用途 | 校验 JSON / API 数据 | 校验**运行时配置** |
| 数据来源 | 构造参数、字典 | 环境变量、`.env`、默认值 |
| 典型场景 | 请求/响应 schema | `APP_ENV`、`LOG_LEVEL` |

### 3.3 为什么不要散落 `os.getenv`

```python
# 不好：到处读，难测、难统一、易写错默认值
env = os.getenv("APP_ENV", "LOCAL")
```

统一入口：

```python
settings = get_settings()
settings.app_env  # AppEnv Enum
```

好处：类型明确、非法值启动失败、测试可注入、后续扩展只改一处。

### 3.4 AppEnv / LogLevel / Settings 关系

```text
AppEnv Enum  ──┐
               ├──> Settings 字段类型
LogLevel Enum ─┘

Settings.app_env: AppEnv = LOCAL
Settings.log_level: LogLevel = INFO
```

---

## 4. APP_ENV 只是运行语义

合法值：`LOCAL` / `DEV` / `TEST` / `DEMO`。

| 正确理解 | 错误理解 |
|----------|----------|
| 「当前以哪种意图运行」 | `LOCAL` = 本机数据库地址 |
| 写在日志里便于排查 | `DEV` = 某台固定开发服务器 IP |
| 未来 Feature 可读该字段做**行为策略** | 根据 `APP_ENV` 自动拼 DB/Redis/LLM URL |

**铁律：** 数据库、Redis、LLM、Embedding 的地址由**各自独立配置项**决定（F05/F06/F07/F11 再引入），**不是**由 `APP_ENV` 推断。

---

## 5. Enum 与 fail-fast

使用 Enum 的好处：

- 合法集合写在类型里；
- 非法字符串在校验阶段直接失败。

例如：

```text
APP_ENV=ABC     → ValidationError → 进程起不来
LOG_LEVEL=INVALID → ValidationError → 进程起不来
```

**不会**静默回退到 `LOCAL` / `INFO`。

原因：带着错误配置继续跑，问题会变成「为什么行为不对」；启动失败则立刻知道「配置写错了」。

大小写会先 `upper()` 再校验：`local` → `LOCAL`（合法）；`prod` 仍非法。

---

## 6. 环境变量与 `.env`

### 6.1 优先级

```text
进程环境变量  >  .env 文件  >  代码默认值
```

### 6.2 `.env.example` vs `.env`

| | `.env.example` | `.env` |
|--|----------------|--------|
| Git | **可以提交** | **必须 ignore** |
| 内容 | 示例：`APP_ENV=LOCAL`、`LOG_LEVEL=INFO` | 本机真实运行值 |
| Secret | 无真实密钥 | 未来可能含密钥，勿提交 |

仓库里的 `.env.example` 只有两行——这就是 F01 **当前真正使用**的全部变量。

---

## 7. StrictDotEnvSettingsSource（重要）

### 7.1 为什么仅 `extra="forbid"` 不够

`extra="forbid"` 约束的是：**已经进入 Settings 模型的多余字段**。

但 DotEnv 加载时，`.env` 里**未声明**的键通常**不会绑定到模型字段**，而是被忽略。于是：

```env
APP_ENV=LOCAL
UNKNOWN=123
```

在只有 `extra="forbid"` 时，可能仍用默认/合法字段悄悄启动——**不符合**「项目 `.env` 未知键 fail-fast」。

### 7.2 `settings_customise_sources` 是什么

pydantic-settings 允许你**替换/包装**配置来源顺序。F01 用它把默认的 `DotEnvSettingsSource` 换成 `StrictDotEnvSettingsSource`。

### 7.3 DotEnvSettingsSource / dotenv_values

- `DotEnvSettingsSource`：官方「从 `.env` 读配置」的来源类。
- `dotenv_values`：`python-dotenv` 的官方解析函数（读文件 → dict），**不是**手写 `line.split("=")`。

`StrictDotEnvSettingsSource` 流程：

```text
若 env_file is None → 直接 super()（测试隔离）
否则读取文件全部键
→ 键必须 ⊆ {APP_ENV, LOG_LEVEL}
→ 否则 ValueError
→ 再 super() 做正常加载
```

### 7.4 两类环境的不同待遇

| 来源 | 未知键 | 行为 |
|------|--------|------|
| 进程环境 `PATH` / `CONDA_*` | 大量存在 | **不报错**（Settings 只绑定已声明字段） |
| 项目 `.env` | `UNKNOWN=1` | **fail-fast** |

这正是自定义 Source 存在的理由。

---

## 8. `get_settings` + `@lru_cache`

```python
@lru_cache
def get_settings() -> Settings:
    return Settings()
```

| 调用 | 行为 |
|------|------|
| 第一次 | 真正构造 `Settings()`，读环境 / `.env`，结果缓存 |
| 第二次起 | 直接返回**同一实例** |

为什么不要每个模块都 `Settings()`：

- 可能读到不同时机的环境；
- 重复解析；
- 测试更难控制。

测试改环境变量后必须：

```python
get_settings.cache_clear()
```

否则仍拿到旧缓存。

---

## 9. `Settings(_env_file=None)`（测试隔离）

开发者本机可能有真实 `.env`（甚至含未知键或 DEMO 配置）。

单元测试若默认读它，结果会随机器变化 → **不稳定**。

因此 Settings 测试统一：

```python
Settings(_env_file=None)   # 显式关闭 env file
+ monkeypatch.setenv / delenv
```

`StrictDotEnvSettingsSource` 在 `env_file is None` 时不做文件键校验、不读磁盘上的 `.env`。

---

## 10. Logging 基础

| 概念 | 作用 |
|------|------|
| **Logger** | 打日志的「名字通道」，如 `gov_service_agent` |
| **Handler** | 日志发到哪里（F01：`StreamHandler(stderr)`） |
| **Formatter** | 一行长什么样（asctime / levelname / name / message） |
| **Level** | DEBUG / INFO / WARNING / ERROR / CRITICAL |

F01 结构：

```text
gov_service_agent
    └── owned StreamHandler(stderr)   # 唯一应用 Handler

gov_service_agent.access
    └── （无独立 Handler）
    └── propagate=True → 父 logger 的 Handler
```

Access 不挂第二套 Handler，避免同一条 access 日志写两遍。

---

## 11. propagate（重点）

```text
gov_service_agent.propagate = False
```

→ 应用日志**不上** root，减少与 Uvicorn root 日志缠在一起、减少重复。

```text
gov_service_agent.access.propagate = True
```

→ Access 日志向上交给父 logger，共用那一个 owned Handler。

完整链：

```text
gov_service_agent.access
  → gov_service_agent（父）
  → owned StreamHandler
  → stderr

gov_service_agent
  ✗ 不再 → root
```

---

## 12. `setup_logging` 幂等

**幂等：** 调用多次，效果与调用一次相同。

```text
setup_logging(settings) × 3
→ 仍然只有 1 个 _gov_service_agent_owned Handler
```

原因：模块 reload、测试重复初始化时，若每次 `addHandler`，stderr 会出现**重复行**。

实现：给 Handler 打 `_gov_service_agent_owned` 标记；已存在则只更新 level/formatter。

自动化契约：`test_setup_logging_is_idempotent`（29 例之一）。

---

## 13. `application_initialized` 不是 `application_started`

`main.py` import 时完成：

```text
get_settings → setup_logging → FastAPI → middleware → /health 定义
→ 打 application_initialized
```

此时 Uvicorn **可能还没**进入「Application startup complete」。

| 日志 | 含义 |
|------|------|
| `application_initialized` | 应用模块已初始化（F01） |
| Uvicorn `Application startup complete` | ASGI server 生命周期就绪 |

F01 **没有** lifespan；不要把两者混为一谈。

---

## 14. 什么是 ASGI

| | WSGI | ASGI |
|--|------|------|
| 时代 | 传统同步 Web | 异步友好 |
| FastAPI | — | **使用 ASGI** |
| 常见 Server | gunicorn+sync | **Uvicorn** |

Middleware 的三个参数：

| 参数 | 含义 |
|------|------|
| `scope` | 连接/请求元信息：`type`、`method`、`path` 等 |
| `receive` | 异步可调用：从客户端取 ASGI message |
| `send` | 异步可调用：把 response message 发给 Server/Client |

`scope["type"] == "http"` 才是普通 HTTP 请求；websocket 等其他 type 在 F01 中直接透传。

---

## 15. 为什么用纯 ASGI Middleware

F01 实现：

```python
async def __call__(self, scope, receive, send): ...
```

**不是** Starlette `BaseHTTPMiddleware` 的 `dispatch` / `call_next`。

| 选择 | 说明 |
|------|------|
| 纯 ASGI | 更贴近请求生命周期；对未来异步/Streaming Agent 更友好 |
| BaseHTTPMiddleware | 不是「错误技术」，但有已知限制；F01 刻意不用 |

---

## 16. 一次 HTTP 请求完整链路

```text
浏览器 / HTTP Client
    ↓
Uvicorn（ASGI Server）
    ↓
FastAPI middleware 栈
    ↓
RequestContextMiddleware
    ├── request_id = uuid4()          # 忽略客户端 X-Request-ID
    ├── ContextVar.set(request_id)
    ├── t0 = perf_counter()
    └── await app(scope, receive, send_wrapper)
            ↓
        路由匹配 GET /health
            ↓
        health() → {"status": "ok"}
            ↓
        FastAPI 生成 ASGI response messages
            ↓
        send_wrapper 看到 http.response.start
            ├── 记录 status_code
            └── 追加 header: x-request-id
            ↓
        响应发回客户端
    ↓
Access Log（五字段）
    ↓
finally: ContextVar.reset(token)
    ↓
客户端收到 Body + X-Request-ID
```

---

## 17. request_id 是什么

| 是 | 不是 |
|----|------|
| **一次 HTTP 请求**的关联 ID | `session_id` |
| 用于串起该请求的多条日志 | `conversation_id` |
| UUID4 字符串 | `business_id` |

每个请求重新生成；两次 `/health` 必然不同。

---

## 18. 为什么忽略客户端 `X-Request-ID`

客户端可发送任意字符串。若直接写入日志/Header：

- 日志注入 / 超长输入 / 非法字符；
- 污染链路追踪语义。

F01 策略：**服务端始终生成 UUID4**；客户端最终从**响应头**拿到权威 ID。

未来若有 API Gateway / 分布式 Trace，可另开 Feature 设计传递规则——不属于 F01。

---

## 19. ContextVar（重点）

普通全局变量：

```text
Request A 写入 global_id = A
Request B 并发写入 global_id = B
→ A 的日志可能读到 B
```

`ContextVar`：每个异步任务/上下文有自己的值副本。

```python
token = request_id_ctx.set(request_id)
try:
    ...
finally:
    request_id_ctx.reset(token)  # 无论成功还是异常
```

`finally` 必须存在，否则上下文泄漏到后续请求。

---

## 20. 为什么要包装 `send`

纯 ASGI 没有现成的 `Response` 对象可改 Header。

响应通过多次 `send(message)` 发出。关键类型：

```text
http.response.start  → 状态码 + 响应头
http.response.body   → 正文（可分块）
```

Middleware 包装 `send`：

1. 拦截 `http.response.start`；
2. 读取 `status`；
3. 向 headers 追加 `(b"x-request-id", uuid_bytes)`（ASGI 要求 **bytes**）；
4. 再调用真正的 `send`。

---

## 21. Access Log

只记：

```text
request_id method path status_code duration_ms
```

`duration_ms` 用 `time.perf_counter()`（单调时钟，适合测间隔）。

```text
GET /health?x=1
→ path=/health     # scope["path"]，不含 query
→ 日志中无 x=1
```

---

## 22. 日志安全

F01 从底层禁止把下列内容写入 Access/Error 常规字段：

- body、完整 query string  
- Authorization、Cookie  
- API Key、Token、数据库密码  
- 明文身份证/手机号/证件全文等敏感政务数据  

当前只有 `/health`，但后续会处理社保材料等敏感信息——**安全原则必须从 F01 建立**。

F01 **没有**完整自动脱敏框架；靠「不记录」实现边界。

---

## 23. 异常链路

```text
handler 抛 RuntimeError
  → middleware except
  → APP_LOGGER.exception(... request_id method path duration_ms ...)
  → raise（原异常继续向外）
  → finally: ContextVar.reset
```

Middleware **不**：

- 吞异常；
- 自己返回 JSONResponse；
- 为 Header 加全局 exception handler。

因此：**不保证**框架最终生成的 500 响应一定带 `X-Request-ID`（若异常发生在 `http.response.start` 之前，Header 还没机会写入）。

---

## 24. `main.py` 初始化链

```text
1. get_settings()          # fail-fast 配置
2. setup_logging(settings) # 依赖 LOG_LEVEL
3. app = FastAPI(...)
4. add_middleware(RequestContextMiddleware)
5. @app.get("/health")
6. info application_initialized
```

没有 Application Factory、lifespan、DB/Redis/LLM 启动——**刻意最小**。

---

## 25. `/health` 为什么保持不变

```json
{"status": "ok"}
```

只表示：**FastAPI 进程内应用可用**。

环境信息看启动日志的 `app_env` / `log_level`，不塞进 health payload。  
不探测数据库、Redis、模型——那些服务 F01 根本没接。

---

## 26. 测试文件如何工作

### `tests/test_settings.py`

| 手段 | 作用 |
|------|------|
| `Settings(_env_file=None)` | 不读真实 `.env` |
| `monkeypatch.setenv` | 注入进程环境 |
| `pytest.raises(ValidationError)` | 验证 fail-fast |
| 临时文件 `.env` + 未知键 | 验证 StrictDotEnv |
| `get_settings.cache_clear()` | 清缓存 |

### `tests/test_logging_and_request_id.py`

| 手段 | 作用 |
|------|------|
| `TestClient(app)` | 进程内跑完整 ASGI 栈（含纯 ASGI middleware） |
| 临时 `_ListHandler` 挂到 `gov_service_agent` | 捕获 access/error（因 `propagate=False`，不宜只靠 root `caplog`） |
| 独立 `boom` app | 测异常路径，不污染生产路由 |

---

## 27. 29 个 Test 的能力分层

| 能力层 | 代表测试 | 保护什么 |
|--------|----------|----------|
| **F00 Regression** | `test_app_importable`、`test_health_returns_ok` | `/health` 契约未破 |
| **Settings 默认/枚举** | defaults、`valid_app_env*`、`valid_log_level*` | 合法配置 |
| **Settings fail-fast** | invalid APP_ENV / LOG_LEVEL | 非法配置起不来 |
| **Environment** | env override、`_env_file=None`、unknown `.env` | 优先级与隔离、未知键 |
| **Request ID** | Header 存在、UUID、两次不同、忽略客户端 | 追踪 ID 策略 |
| **Access Logging** | 五字段、path 无 query | 可观察且不泄 query |
| **ContextVar** | 成功/异常后 `get_request_id() is None` | 无泄漏 |
| **Exception** | boom 路由：日志 + 传播 | 不吞异常 |
| **Logging Idempotence** | `test_setup_logging_is_idempotent` | 不重复 Handler |

---

## 28. 常见问题排查

| 现象 | 排查方向 |
|------|----------|
| `APP_ENV=INVALID` 启动失败 | 预期；看 ValidationError |
| `LOG_LEVEL=INVALID` 启动失败 | 预期 |
| `.env` 多写未知字段失败 | StrictDotEnv；对照 `.env.example` |
| 没有 `.env` 能否启动 | 可以；用默认 LOCAL/INFO 或进程环境 |
| PATH/CONDA_* 为何不报错 | 进程 env 只绑定已声明字段 |
| 日志重复两行 | 是否多次 addHandler；跑幂等测试 |
| `X-Request-ID` 每次不同 | 预期（每请求新 UUID） |
| 客户端传 ID 不生效 | 预期忽略；看响应头服务端值 |
| query 不在日志 | `scope["path"]` 不含 query |
| 请求后 `get_request_id()` 为 None | `finally reset` 正常 |

---

## 29. F01 仍然没有什么

没有：PostgreSQL、pgvector、Redis、LangGraph、Business Graph、Rule Engine、LLM、Embedding、Provider、Agent。

这是 **Scope 控制**，不是遗漏。

---

## 30. F01 为后续打下的基础（仅接口意义）

| 后续 | 可复用什么 |
|------|-----------|
| F02/F03 | Settings / Logging 习惯 |
| F05 | 未来增加 `DATABASE_URL` 等字段（独立配置） |
| F06/F07 | Embedding / LLM 配置字段 |
| F08+ | `request_id` 关联一次 Agent HTTP 请求 |
| F11 | Redis 配置字段 |

再次强调：**新增配置 ≠ 根据 `APP_ENV` 推断地址。**

---

## 31. Debug Guide

| 问题类型 | 推荐断点 |
|----------|----------|
| 配置 / `.env` | `Settings` 构造、`StrictDotEnvSettingsSource.__call__` |
| 日志级别 / 重复 | `setup_logging` |
| request_id / Header | 生成 UUID、`http.response.start` 分支 |
| 异常 / 泄漏 | `except`、`finally reset` |
| `/health` 内容 | `health()` |

---

## 32. F01 学习检查清单

读完后应能回答：

1. BaseSettings 是什么？  
2. `.env` 和 `.env.example` 有什么区别？  
3. 为什么 APP_ENV 不等于服务器地址？  
4. 为什么 Settings 要 fail-fast？  
5. `lru_cache` 在 `get_settings` 中做什么？  
6. Logger / Handler / Formatter 有什么区别？  
7. propagate 是什么？  
8. 什么叫 logging 初始化幂等？  
9. ASGI 是什么？  
10. scope / receive / send 是什么？  
11. 为什么使用纯 ASGI Middleware？  
12. request_id 是什么？  
13. 为什么服务器自己生成 request_id？  
14. ContextVar 为什么比全局变量安全？  
15. 为什么一定 finally reset？  
16. 为什么包装 send？  
17. `http.response.start` 是什么？  
18. 为什么 Access Log 不记录 query/body？  
19. 异常为什么要重新 raise？  
20. `/health` 为什么仍然只有 `status=ok`？  

---

## 相关文档

- Feature：`docs/features/F01-runtime-settings-logging-environment.md`
- F00 Reading Guide：`docs/code-reading/F00-project-minimum-initialization-reading-guide.md`
- 运行说明：`README.md`
