# F14 — 政务 Agent Web 汇报与交互前端 Requirement

Web Demo Frontend。

Feature Status：DRAFT / READY FOR OWNER REVIEW。

## 1. Feature Overview

F14 是真实 Agent Web 汇报与交互前端。它同时承担阶段成果汇报和真实 Agent 多轮交互 Demo。

F14 不是纯 Mock Dashboard，不是静态网页 Demo，不是后台管理系统，也不是 Agent 内部调试器。

浏览器中的用户输入必须调用现有 `POST /api/v1/session/turn`。页面展示的 Agent 回复必须来自真实后端返回的 `response_text`。

## 2. Background

F12 已关闭。F13-Preview 已最终关闭并完成远端冻结。现有后端提供可调用的会话回合接口和健康检查接口。Resource Gate 已确认本机具备 Node.js 与 npm，仓库中尚无前端工程。

当前缺口是：已有 Agent 能力只能通过后端接口验证，还没有面向汇报和演示的浏览器页面。

## 3. Feature Goal

用户打开浏览器后，可以查看当前政务 Agent 的阶段性开发成果和业务架构，进入真实 Agent Demo，输入自然语言问题，调用现有 Session API，完成真实多轮对话。

现有 Agent 继续负责语义理解、事项方向、Decision Graph、F09 缺失信息交互、F10 最终事项确认，以及 F13-Preview 已确认事项材料展示。页面只展示真实 `response_text`。

Golden Demo 示例问题是：“我辞职了，现在没单位，想自己交社保”。如果现有 Agent 按当前 Business Data 成功确认，回复中可以出现规范事项名称“灵活就业人员社会保险费申报缴费”和当前公开材料“身份证”。这些文字必须由后端 Agent 产生。前端不得把它们写成自动回复。

## 4. Business Value

F14 让已完成的办理链路可以被非开发人员在浏览器中查看和试讲。汇报内容与真实对话放在同一页面，避免用一套模拟回答代替已上线的 Agent 合同。

## 5. Existing System Boundary

F12 保持 CLOSED。F13-Preview 保持 FINAL CLOSED / REMOTE-FROZEN。

F14 默认不修改后端生产代码。不得为了前端重写 Session API、F11、F12 或 F13-Preview，也不得新增前端专用业务逻辑。

如果后续 Technical Design 发现必须修改后端，必须记为 Integration Gap，并重新获得 Owner 授权。

业务真相仍由后端拥有。

## 6. Scope

第一版范围：

- 单页纵向汇报与真实 Demo。
- 调用 `GET /health` 和 `POST /api/v1/session/turn`。
- 管理浏览器侧的会话标识、请求标识、加载、错误、重试和刷新恢复。
- 展示已批准的静态成果、架构、路线图、可靠性说明和下一阶段规划。
- 开发环境通过 Vite dev proxy 访问本机后端。

## 7. Out of Scope

第一版不做：

- 用户登录、权限系统、多用户管理后台、管理员后台。
- 文件上传、语音输入、微信小程序、RPA 操作。
- 完整 Business Knowledge Graph。
- 实时 Agent 内部节点追踪、`current_node` 可视化。
- 展示 `candidate_business_id`、`confirmed_business_id`、`AgentState`、checkpoint、audit 详情、F09/F10 artifact、raw LLM output、模型 prompt。
- 移动端专项开发。
- 前端直接调用 LLM、Redis 或 PostgreSQL。
- 新增内部执行轨迹 API。
- 修改后端 CORS。

## 8. Page Structure

第一版是单页纵向滚动，不要求多路由。

固定区域：

1. Hero / 项目总览
2. 当前阶段成果
3. Agent 业务架构
4. 真实 Agent Demo
5. 开发 Roadmap
6. 系统可靠性设计
7. 测试与工程证据
8. 下一阶段规划

顶部使用 Sticky Navigation。导航至少包括：项目总览、业务架构、实时 Demo、开发进度、工程验证、下一阶段。

Hero 主标题为“政务智能 Agent”。副标题为“阶段性成果与实时演示”。项目说明为：面向政务事项识别、信息补全、事项确认与办理信息查询的智能服务系统。

Hero 需要表达：核心业务链路已打通，F13-Preview 已完成，真实 Agent Demo 可交互。Agent 服务连接状态必须来自 `GET /health`，不得写死为“服务正常”。

当前阶段成果展示 4 张卡片：业务闭环、办理信息、测试状态、工程状态。允许静态展示 Final Authorized Safe Regression：77 passed、0 failed、0 skipped；Review 为 PASS；F13-Preview 为 FINAL CLOSED / REMOTE-FROZEN。77 passed 只表示 F13-Preview 最终授权安全回归。不得写成全仓测试全部通过。不得虚构准确率、成功率、SLA 或 99.9% 等未经验证指标。

## 9. Architecture Presentation Requirements

汇报视角按业务顺序展示：

用户自然语言 → 语义理解 → 事项方向检索 → 业务决策图 → 缺失信息询问 → 事项候选 → 最终确认 → 办理信息查询 → 用户回复。

技术标签可以包括：LLM NLU、Semantic RAG、Decision Graph、F09、F10、Business Repository、F11 Session、F13-Preview。

推荐表述：语义检索找方向，业务图谱定事项，规则做确认，受控业务数据查办理信息，Agent 统一编排。

架构图是静态展示数据，不是实时执行轨迹。

## 10. Real Agent Demo Requirements

桌面布局为双栏。左侧是真实 Agent 对话，右侧是当前系统能力说明。

左侧至少包含：聊天消息列表、用户输入框、发送按钮、新建会话按钮、示例问题填入按钮、Session 简写、请求 loading、error UI、request latency。

右侧可以说明：自然语言理解、事项方向检索、业务决策、信息补全、最终确认、办理材料查询。右侧标题使用“当前系统能力”，不得写成“当前实时执行节点”。

示例问题“我辞职了，现在没单位，想自己交社保”只填入输入框，不得自动发送，也不得预置 Agent 回复。

Session 展示为简写，例如 `Session: xxxx…xxxx`，只作为当前对话标识。复制完整标识是可选项。

耗时显示浏览器从请求开始到收到响应的时间，例如 `2.8s`。文案必须是“本次请求耗时”或“端到端 Turn 耗时”，不得写成“LLM 推理耗时”。

## 11. Real Session API Contract

唯一 Agent 业务入口：

| 项 | 值 |
| --- | --- |
| Method | POST |
| Path | `/api/v1/session/turn` |
| Request | `SessionTurnRequest` |
| Success | `SessionTurnSuccess` |
| Error | `SessionTurnError` |

不得新造 `/api/agent/turn`、`/chat` 或 `/create-session`。

### 11.1 Request

公开字段只有三个。`extra` 为禁止。前端不得发送任何额外内部字段。

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `request_id` | `str` | 是 | UUID4 字符串 |
| `session_id` | `str \| None` | 否，默认 `None` | 非空时必须是 UUID4。空字符串不是标准写法 |
| `input_text` | `str` | 是 | 长度 1 到 4000。纯空白无效 |

### 11.2 Success

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | `str` | 服务端签发的会话标识 |
| `request_id` | `str` | 本轮请求标识 |
| `status` | `SessionTurnPublicStatus` | `COMPLETED` 或 `AWAITING_USER_INPUT` |
| `response_text` | `str` | 用户可见回复 |
| `requires_user_input` | `bool` | 与 `status` 成对出现 |

约束：`COMPLETED` 时 `requires_user_input` 为 false；`AWAITING_USER_INPUT` 时 `requires_user_input` 为 true。

成功响应中不存在独立的旧草案状态字段。成功响应中不存在 `candidate_business_id`、`confirmed_business_id`、`AgentState`、checkpoint 和 audit。前端不得依赖这些不存在的字段。

`status` 可以用于公开界面辅助，但不得用于重建 Agent 状态机。`requires_user_input` 可以用于界面提示，下一问的具体内容仍必须来自 `response_text`。

### 11.3 Error

失败体公开字段为：`request_id`、`session_id`、`status = FAILED`、`error.code`、`error.message`。前端只消费这些公开字段，不展示 Python stack trace、内部异常、Redis 内部信息、模型异常、prompt 或原始 traceback。

## 12. Health API Contract

`GET /health` 的预期公开响应是：

```json
{"status": "ok"}
```

前端据此显示：正在检查、Agent 服务正常、Agent 服务不可用。

健康检查成功只表示现有 Health Contract 报告服务可用。不得解释为 Redis、PostgreSQL、LLM、Embedding 或全部业务依赖一定正常。

页面初始化不得依赖健康检查成功才能渲染。后端不可访问时，Hero、架构、Roadmap、可靠性说明、测试成果和下一阶段规划仍必须正常展示。只有真实 Agent Demo 显示“Agent 服务当前不可用”。

## 13. Session Lifecycle

新会话模型是服务端懒创建。

用户点击“新建会话”时，前端清除当前已保存的服务端 `session_id`、聊天界面历史和待重试上下文。此时前端不得自己创建 `session_id`，也不得调用创建会话接口，更不得调用删除后端会话的接口。

下一次发送生成新的 UUID4 `request_id`，省略 `session_id`，只发送 `input_text`。服务端创建会话并在成功响应中返回 `session_id`。前端保存这个服务端签发的值。同一对话的后续回合全部复用它，直到用户再次新建会话。

后续回合必须同时发送 `request_id`、`session_id` 和 `input_text`。前端不得每轮重新创建 `session_id`。

传入一个后端不存在的 `session_id` 会得到会话不存在错误。因此客户端预造标识不是合法的新会话方式。

## 14. Request Lifecycle

每个新的用户业务回合必须生成新的 UUID4 `request_id`。推荐浏览器能力是 `crypto.randomUUID()`，具体实现留给 Technical Design。不得使用时间戳、递增整数或随机短字符串。

同一会话在请求处理期间不得并发提交另一个回合。

## 15. Idempotency / Retry

后端幂等键是 `request_id`。请求指纹由 `session_id` 与 `input_text` 计算 SHA-256。

同一 `request_id` 且指纹相同：返回已缓存的公开结果，不再执行 processor。同一 `request_id` 且指纹不同：返回 409，错误码 `REQUEST_ID_REUSE_CONFLICT`。

同一个失败回合的重试必须复用原来的 `request_id`、`session_id` 和 `input_text`。如果原请求是首次会话请求并省略了 `session_id`，重试也必须继续省略 `session_id`。不得为了重试生成新的 `session_id`，也不得在复用旧 `request_id` 时更换 `input_text`。

用户编辑内容后重新发送，视为新回合，必须使用新的 `request_id`。

第一版重试主要用于网络失败、请求超时、可恢复的服务失败，以及 503 持久化不可用。不得对所有错误自动重试。

默认不自动重试：

- 422 `INVALID_REQUEST`
- 404 `SESSION_NOT_FOUND`
- 410 `SESSION_EXPIRED`
- 409 `REQUEST_ID_REUSE_CONFLICT`

409 `REQUEST_IN_PROGRESS` 在第一版只显示明确状态，不进入高频自动轮询。

## 16. Loading / Error Handling

界面状态至少包括：IDLE、SENDING、PROCESSING、SUCCESS、ERROR。

请求期间发送按钮必须禁用。可以显示“Agent 正在处理当前请求…”。不得伪造“正在执行 F09”“正在查询 Decision Graph”或“正在调用某模型”等内部步骤。

基础错误映射：

| 情况 | 用户可见方向 |
| --- | --- |
| 422 `INVALID_REQUEST` | 输入或请求信息无效 |
| 404 `SESSION_NOT_FOUND` | 当前会话不存在，请新建会话后继续 |
| 410 `SESSION_EXPIRED` | 当前会话已过期，请新建会话后继续 |
| 409 `REQUEST_ID_REUSE_CONFLICT` | 请求状态冲突，不要自动重新提交 |
| 409 `REQUEST_IN_PROGRESS` | 当前请求仍在处理中 |
| 500 Agent 处理失败 | Agent 本次处理失败，请稍后重试 |
| 503 持久化不可用 | 会话服务暂不可用 |
| 网络失败或超时 | 网络请求未成功，允许用户重试 |

最终文案可以在 Technical Design 和界面实现中确定，但语义不得偏离上表。404 和 410 必须提供新建会话路径。

## 17. Refresh / Browser Persistence

第一版可以使用 `sessionStorage` 保存服务端签发的 `session_id`、聊天展示记录，以及待重试所需的最小数据。刷新当前标签页后恢复 `session_id` 和聊天界面历史。

`sessionStorage` 不是业务状态的权威来源。真正的会话状态在 `RedisSessionStore`。恢复后如果后端返回 404 或 410，以后端为准，提示会话不存在或已过期。不得悄悄创建新会话并继续旧界面。

允许保存：服务端签发的 `session_id`、聊天展示记录、待重试最小数据。

不得保存：`AgentState`、artifacts、checkpoint、audit、raw LLM response、Business Repository 内部记录、凭据、API key、数据库密码、Redis 密码。

## 18. Static vs Live Data Model

| 类别 | 内容 |
| --- | --- |
| STATIC | 项目名称、简介、架构、Roadmap、77 passed、0 failed、0 skipped、Review PASS、F13-Preview 状态、可靠性设计说明、下一阶段规划 |
| LIVE | `GET /health` 状态、当前服务端签发的 `session_id`、当前 `request_id`、用户输入、`response_text`、`status`、`requires_user_input`、HTTP Turn 耗时 |
| FORBIDDEN | `candidate_business_id`、`confirmed_business_id`、`AgentState`、F09 artifact、F10 artifact、checkpoint、audit 内部信息、raw LLM output、内部规则结果、内部 prompt |

## 19. Frontend / Backend Responsibility Boundary

前端负责：用户交互、页面展示、session 与 request 生命周期管理、API 调用、loading 与 error 界面、汇报静态内容。

前端不负责：意图识别、槽位抽取、allowed-value 映射、Decision Graph 推进、F09 业务判断、F10 用户确认业务判断、`candidate_business_id` 判断、`confirmed_business_id` 判断、材料事实判断、PUBLIC eligibility、RAG、LLM、Business Repository 查询。

调用链是：Browser → FastAPI Agent Backend → 后端拥有的依赖。真实 Demo 仍可能依赖现有 Redis、PostgreSQL、LLM、Embedding 和 Business Data。前端不管理、不配置、不直接连接这些资源。

`response_text` 必须原样来自 `POST /api/v1/session/turn`。前端可以保留换行、基础列表和安全的轻量富文本展示。前端不得总结、改写、删减或用另一个模型润色回复，也不得根据回复重新判断业务状态。

第一版安全渲染只覆盖纯文本、换行、有序列表、无序列表，以及实现需要时的加粗。禁止直接执行原始 HTML、script、iframe 或不安全的 HTML 注入。具体渲染库由 Technical Design 决定。

开发拓扑：浏览器访问 `http://localhost:5173`，请求同源的 `/api` 与 `/health`，由 Vite proxy 转发到 `http://127.0.0.1:8000`。页面业务代码不得散落硬编码 `http://127.0.0.1:8000`。不得让浏览器从 `localhost:5173` 跨域直连 `127.0.0.1:8000`。具体 proxy 配置留给 Technical Design。

## 20. Visual / UX Requirements

整体视觉使用政务蓝、白色、浅灰背景和适量深色科技元素。方向是专业、可信、现代、清晰。避免赛博朋克、大量霓虹、满屏粒子和复杂 3D。卡片使用 12 到 16 像素圆角、轻阴影、轻边框和足够留白。图标采用 Lucide 风格。

允许轻量页面出现、流程线动画、卡片悬停、Agent 输入指示和按钮过渡。禁止影响阅读的动画、持续高强度背景运动、大量粒子和强闪烁。

第一版优先 Chrome 与 Edge 桌面。重点分辨率是 1920×1080、1440×900、1366×768。移动端专项适配不在范围内，但页面在较小窗口中不应完全不可用。

可访问性最低要求：按钮有清晰文本或 `aria-label`；颜色不能成为唯一状态表达；Enter 发送；Shift+Enter 换行；Loading、Error 和 disabled 都有文字或清晰状态。

## 21. Security Boundary

前端构建产物中不得包含 LLM API key、数据库凭据、Redis 凭据、内部授权密钥或其他服务器密钥。浏览器只访问前端源站，以及通过代理暴露的 Agent 后端公开 API。浏览器不得直接调用 LLM Provider。

前端不得长期把完整 Session API 响应、凭据、内部错误、完整敏感用户输入、后端堆栈或 token 写入控制台。开发期诊断的具体日志策略由 Technical Design 定义。

## 22. Functional Requirements

- F14-FR-001：浏览器可打开完整单页汇报页面。
- F14-FR-002：静态汇报内容不依赖 Agent API 成功。
- F14-FR-003：页面使用 `GET /health` 获取 Agent 服务健康状态。
- F14-FR-004：用户可通过真实 Session API 与现有 Agent 交互。
- F14-FR-005：Agent 业务入口固定为 `POST /api/v1/session/turn`。
- F14-FR-006：新会话首次回合必须省略 `session_id`。
- F14-FR-007：前端必须保存后端返回的 `session_id`。
- F14-FR-008：同一对话后续回合复用相同 `session_id`。
- F14-FR-009：用户点击新建会话后，前端清除旧 `session_id` 和界面历史，但不调用删除后端会话。
- F14-FR-010：每个新的用户回合生成新的 UUID4 `request_id`。
- F14-FR-011：同一失败回合重试复用原 `request_id`。
- F14-FR-012：重试必须保持原 `session_id` 与 `input_text`；首次回合重试继续省略 `session_id`。
- F14-FR-013：用户修改输入后重新发送视为新回合，必须生成新 `request_id`。
- F14-FR-014：`response_text` 必须来自真实 Session API。
- F14-FR-015：前端使用公开字段 `session_id`、`request_id`、`status`、`response_text`、`requires_user_input`。
- F14-FR-016：前端只使用成功响应中的 `status`，不依赖任何未出现在 `SessionTurnSuccess` 中的状态字段。
- F14-FR-017：前端不展示内部 `AgentState`。
- F14-FR-018：前端不展示内部 artifacts。
- F14-FR-019：请求处理中禁止重复提交。
- F14-FR-020：页面提供明确 Loading 状态。
- F14-FR-021：页面处理网络、HTTP 和响应结构错误。
- F14-FR-022：可恢复失败提供重试。
- F14-FR-023：不可恢复的会话错误提供新建会话路径。
- F14-FR-024：新建会话不得由前端生成 `session_id`。
- F14-FR-025：刷新页面后可恢复服务端签发的 `session_id` 与聊天界面历史。
- F14-FR-026：前端只把 `sessionStorage` 作为界面持久化，不作为业务状态权威来源。
- F14-FR-027：Agent 服务不可用时，汇报页面其它区域仍正常展示。
- F14-FR-028：页面展示静态项目架构。
- F14-FR-029：页面展示静态开发 Roadmap。
- F14-FR-030：页面展示真实已验证的测试与 Review 证据。
- F14-FR-031：页面展示系统可靠性设计说明。
- F14-FR-032：页面展示下一阶段规划。
- F14-FR-033：页面提供示例问题填入，但不得自动发送。
- F14-FR-034：前端显示当前 Session 简写。
- F14-FR-035：前端显示 HTTP Turn 端到端耗时。
- F14-FR-036：前端对 `response_text` 进行安全渲染。
- F14-FR-037：前端不预置 Agent 回复。
- F14-FR-038：前端不重新实现候选事项到已确认事项的判断。
- F14-FR-039：前端不重新实现材料公开资格判断。
- F14-FR-040：浏览器不直接调用 LLM。
- F14-FR-041：第一版使用 Vite dev proxy。
- F14-FR-042：F14 第一版不要求修改后端 CORS。
- F14-FR-043：页面静态数据与实时数据必须有明确来源边界。
- F14-FR-044：`status` 可用于公开界面辅助，但不得用于重建 Agent 状态机。
- F14-FR-045：`requires_user_input` 可用于界面提示，但下一问内容仍必须来自 `response_text`。
- F14-FR-046：F12 与 F13-Preview 不得因 F14 改变业务语义。

## 23. Non-Functional Requirements

- F14-NFR-001：Chrome 与 Edge 桌面正常运行。
- F14-NFR-002：1366×768 及以上能够完成正常汇报。
- F14-NFR-003：页面主体不能因健康检查或业务 API 失败而白屏。
- F14-NFR-004：同一会话不支持并行回合。
- F14-NFR-005：会话与请求生命周期行为可预测。
- F14-NFR-006：前端不泄露后端内部状态。
- F14-NFR-007：前端不包含凭据。
- F14-NFR-008：静态数据与实时数据来源明确。
- F14-NFR-009：页面动画不影响阅读。
- F14-NFR-010：错误文案不暴露内部异常。
- F14-NFR-011：前端组件不散落后端绝对地址。
- F14-NFR-012：第一版开发环境不需要修改后端 CORS。
- F14-NFR-013：真实 Agent Demo 可以独立失败，汇报页其它模块保持可用。
- F14-NFR-014：前端架构应允许后续扩展公开 Agent 能力。
- F14-NFR-015：F14 不改变现有 Agent 权限边界。

## 24. Acceptance Criteria

- AC-F14-001：浏览器能加载完整汇报页。
- AC-F14-002：后端不可用时，静态汇报页仍可打开。
- AC-F14-003：`GET /health` 驱动真实服务状态显示。
- AC-F14-004：用户可通过真实 API 完成多轮 Agent 对话。
- AC-F14-005：首次回合不发送 `session_id`。
- AC-F14-006：后端返回 `session_id` 后前端正确保存。
- AC-F14-007：后续回合使用相同的服务端签发 `session_id`。
- AC-F14-008：新建会话不会由客户端生成 `session_id`。
- AC-F14-009：每个新回合生成 UUID4 `request_id`。
- AC-F14-010：同一个失败回合重试复用 `request_id`。
- AC-F14-011：相同重试保持相同 `input_text`。
- AC-F14-012：同一 `request_id` 搭配不同输入不作为合法重试。
- AC-F14-013：`response_text` 真实来自后端。
- AC-F14-014：不存在模拟 Agent 回复。
- AC-F14-015：页面使用 `status` 表达公开处理状态。
- AC-F14-016：`requires_user_input` 与现有公开合同对齐。
- AC-F14-017：最终真实流程可展示 F13-Preview 返回的规范事项名称和公开材料。
- AC-F14-018：前端不判断 `candidate_business_id`。
- AC-F14-019：前端不判断 `confirmed_business_id`。
- AC-F14-020：前端不判断材料公开资格。
- AC-F14-021：前端不展示 `AgentState` 或 artifacts。
- AC-F14-022：请求处理中不能重复提交。
- AC-F14-023：网络和 API 错误有明确界面。
- AC-F14-024：可恢复失败可以使用相同请求重试。
- AC-F14-025：404 与 410 能引导用户新建会话。
- AC-F14-026：刷新当前页面后可恢复界面会话。
- AC-F14-027：后端会话状态仍以 Redis 为权威来源。
- AC-F14-028：77 passed、0 failed、0 skipped 正确显示为 Final Authorized Safe Regression。
- AC-F14-029：页面没有宣称全仓测试已全部通过。
- AC-F14-030：Roadmap 正确区分已完成与未来项。
- AC-F14-031：完整 Business Knowledge 不显示为已完成。
- AC-F14-032：Vite proxy 可以使前端无需后端 CORS 完成开发联调。
- AC-F14-033：浏览器不直接连接 LLM。
- AC-F14-034：前端构建产物不包含凭据。
- AC-F14-035：Agent 服务健康不被描述成所有依赖百分之百健康。
- AC-F14-036：Session API 之外不新增第二套业务入口。
- AC-F14-037：F12 保持 CLOSED。
- AC-F14-038：F13-Preview 保持 FINAL CLOSED / REMOTE-FROZEN。
- AC-F14-039：第一版不新增执行轨迹 API。
- AC-F14-040：桌面 1366×768 及以上可以完成主要汇报和 Demo。

## 25. Frozen Decisions

- D-F14-001：F14 是真实 Agent Web 汇报前端，不是 Mock Dashboard。
- D-F14-002：`POST /api/v1/session/turn` 是唯一 Agent 业务入口。
- D-F14-003：`GET /health` 是第一版服务状态来源。
- D-F14-004：前端不实现 Agent 业务决策。
- D-F14-005：新会话由后端懒创建。
- D-F14-006：首次回合省略 `session_id`。
- D-F14-007：前端保存后端返回的 `session_id`。
- D-F14-008：每个新回合使用新的 UUID4 `request_id`。
- D-F14-009：同一失败回合重试复用 `request_id`、`session_id` 和 `input_text`。
- D-F14-010：首次回合重试继续省略 `session_id`。
- D-F14-011：公开状态字段是 `status`。
- D-F14-012：Agent 回复必须来自真实 API。
- D-F14-013：内部 `AgentState`、artifacts 和 checkpoint 不暴露。
- D-F14-014：项目架构、Roadmap、测试证据和规划属于静态汇报数据。
- D-F14-015：健康检查、会话、请求、回复、`status`、`requires_user_input` 和耗时属于实时数据。
- D-F14-016：F14 第一版使用 Vite dev proxy。
- D-F14-017：F14 第一版不修改后端 CORS。
- D-F14-018：汇报页面主体不依赖后端可用才能渲染。
- D-F14-019：第一版不新增内部执行轨迹。
- D-F14-020：桌面 Chrome 与 Edge 优先。
- D-F14-021：页面使用单页纵向汇报结构。
- D-F14-022：浏览器不直接调用 LLM。
- D-F14-023：前端不保存凭据。
- D-F14-024：F12 保持 CLOSED。
- D-F14-025：F13-Preview 保持 FINAL CLOSED / REMOTE-FROZEN。
- D-F14-026：F14 默认不修改现有后端生产代码。
- D-F14-027：`sessionStorage` 只承担前端界面持久化，不是 Agent 状态权威来源。
- D-F14-028：完整 Business Knowledge 不属于 F14 第一版。

## 26. Integration Gaps Resolution

### GAP-F14-001

问题：后端未配置 CORS。

影响：`localhost:5173` 无法直接跨源访问 `127.0.0.1:8000`。

处理：第一版使用 Vite dev proxy。

后端变更：否。

状态：RESOLVED_BY_FRONTEND_DESIGN。

### GAP-F14-002

问题：不存在客户端自建会话模式。

影响：前端不能自己创建 `session_id`。

处理：首次回合省略 `session_id`；后端懒创建；前端保存响应中的 `session_id`。

后端变更：否。

状态：RESOLVED_BY_REQUIREMENT。

### GAP-F14-003

问题：真实成功响应的状态字段名是 `status`。早期草案使用了未出现在公开成功响应中的另一个状态字段名。

影响：旧术语不能作为实现合同。

处理：正式需求全部使用 `status`。

后端变更：否。

状态：RESOLVED_BY_REQUIREMENT。

OPEN_INTEGRATION_GAPS = 0。

## 27. Resource Gate Evidence

以下是 Resource Gate 检查时的事实，其中端口空闲状态不是永久保证。

| 项 | 结果 |
| --- | --- |
| FastAPI | READY |
| `POST /api/v1/session/turn` | READY |
| `GET /health` | READY |
| Backend | `127.0.0.1:8000` |
| `RedisSessionStore` | 现有后端依赖 |
| CORS | 未配置 |
| Vite proxy | 可行 |
| Node | v22.23.2 |
| npm | 10.9.8 |
| pnpm | 未安装，不阻塞 |
| yarn | 未安装，不阻塞 |
| `frontend/` | 尚不存在 |
| 5173 | 检查时空闲 |
| 浏览器 | Chrome / Edge |

## 28. Technical Design Deferred Decisions

以下留给 Technical Design，不在本需求中实现化：

React 与 Vite 的精确目录结构；npm 包版本；Tailwind、Lucide、Framer Motion 的精确版本；Vite 配置代码；API client 结构；`sessionStorage` 键名；是否使用以及使用哪种 React 状态库；Markdown 渲染选型；超时时长；健康检查轮询间隔；CSS token；组件拆分；测试框架以及 Vitest、React Testing Library、Playwright 的选型；构建输出路径；静态托管方式；生产部署拓扑。

本需求只规定行为、边界和验收标准。

## 29. Open Blocking Decisions

OPEN_BLOCKING_DECISIONS = 0。

## 30. Requirement Status

Feature：F14 — Web Demo Frontend。

Requirement Status：DRAFT / READY FOR OWNER REVIEW。

Resource Gate：PASS_WITH_INTEGRATION_GAPS / OWNER REVIEW APPROVED。

Open Integration Gaps：0。

Open Blocking Decisions：0。

F12：CLOSED。

F13-Preview：FINAL CLOSED / REMOTE-FROZEN。

Technical Design：NOT STARTED。

Implementation：NOT STARTED。

Test：NOT STARTED。

Review：NOT STARTED。

Commit：NOT STARTED。

Push：NOT STARTED。

## 31. Roadmap And Reliability Presentation

Roadmap 按业务阶段展示，而不是 Git 提交列表。至少包括：基础工程、Business Data Contract、Decision Graph、Semantic Retrieval、LLM Provider、Agent State / LangGraph、Missing Slot Interaction、Terminal Confirmation、Session API、E2E Integration、F13-Preview Materials Demo。完整 Business Knowledge 标为未来项。F13-Preview 已完成。完整 F13 不得显示为已完成。

近期规划可以包括：完整 Business Knowledge 能力、办理地点、办理渠道、办理条件、法律依据、真实业务数据扩展、Web 前端持续完善。后续规划可以包括：微信端交互、政务百科、大厅导航、RPA 办理协同。这些都是规划，不得显示为已经支持。

可靠性说明固定四项，且属于静态展示内容：

- 流程可控：Business Decision Graph 与规则负责确定性流程。
- 事实可控：办理信息来自受控 Business Data。
- 状态可追踪：F11 提供 Session、checkpoint、幂等和 audit。
- 异常可退让：展示型增强失败不篡改核心业务成功结果。
