# F14 Web Demo Frontend 代码阅读指南

政务 Agent Web 汇报与交互前端的业务执行流与代码阅读说明。

## 1. 这份文档解决什么问题

F14 是浏览器里的单页汇报，以及一条通向现有会话接口的真实对话入口。用户输入自然语言，浏览器把它交给 `POST /api/v1/session/turn`，再把公开回复显示出来。事项是否成立、缺哪一项、是否已经确认、可以展示哪些材料，都不在这套前端代码里决定。

前端负责“交互与展示”，后端负责“业务事实与业务决策”。浏览器是现有 Agent 的客户端，不是第二套业务引擎。

读完后应能回答：一次发送从输入框走到公开回复，中间谁生成 `request_id`，谁签发 `session_id`，重试为什么必须沿用同一次请求，以及页面上的架构名词为什么不等于前端已经实现了那些规则。

### 1.1 职责分界

前端负责：收集用户输入、管理一次请求的生命周期、生成 `request_id`、保存服务端发来的 `session_id`、用 `sessionStorage` 记住当前标签页的界面、发起 HTTP、显示加载和错误、显示健康检查、展示静态汇报、渲染公开回复。

后端负责：自然语言理解、槽位对应、置信判断、Decision Graph、F09、F10、F13、业务确认、材料是否可公开、语义检索、模型调用、业务事实、Redis checkpoint，以及规则和业务数据。当前前端源码看不到这些内部步骤。

## 2. 一次真实用户消息是怎样走完整条链路的

```
用户输入
    ↓
ChatInput
    ↓
AgentDemoSection
    ↓
useAgentChat.sendMessage
    ↓
生成 request_id
读取 serverSessionId
    ↓
agentClient.sendTurn
    ↓
/api/v1/session/turn
    ↓
Vite Proxy
    ↓
FastAPI Session API
    ↓
Existing Agent
    ↓
F09 / F10 / F13
    ↓
Public Response
    ↓
validateSuccessPayload
    ↓
useAgentChat 更新状态
    ↓
sessionStorage
    ↓
ChatPanel / MessageBubble
    ↓
用户看到公开回复
```

Redis checkpoint 恢复和 Agent 内部状态属于后端。上图里的 “Existing Agent” 只表示请求已经离开前端。本文不描述未在前端源码或已批准公开证据中出现的 SQL、Redis 内容和模型推理。

### 2.1 用户把问题放进输入框

业务场景：用户在「真实 Agent 交互」中输入「我辞职了，现在没单位，想自己交社保」。

`AgentDemoSection` 用组件自己的 `draft` 保存尚未发送的文字，`setDraft` 更新它。`ChatPanel` 把 `draft` 交给 `ChatInput`。`ChatInput` 的 textarea 标识是 `agent-question`。每次输入通过 `onChange` 把 `event.target.value` 交回 `setDraft`。框下显示 `{value.length}/{INPUT_MAX_LENGTH}`，`INPUT_MAX_LENGTH` 是 4000，textarea 同时设置 `maxLength={4000}`。

发送前，`useAgentChat.sendMessage` 对文本做 `trim`。trim 后长度为 0 的内容被拒绝。长度等于 4000 可以发送。长度大于 4000 被拒绝；浏览器的 `maxLength` 也会挡住继续键入。Enter 且没有按住 Shift 时调用 `onSend`。Shift+Enter 只换行。`chat.isSending` 或 `chat.sessionInvalid` 时，输入框禁用。发送按钮还要在 `draft.trim().length === 0` 时禁用。

`AgentDemoSection` 的 `onSend` 调用 `chat.sendMessage(draft)`。只有返回 `true` 才执行 `setDraft('')`。示例按钮只执行 `setDraft(presentation.exampleQuestion)`，不发送。

这一步只收集自然语言。它不判断社保、灵活就业、槽位或事项。下一跳是 `sendMessage`。

### 2.2 sendMessage 准备一次新的用户发言

`useAgentChat.sendMessage` 先看 `isSendingRef` 和 `sessionInvalidRef`。正在发送或会话已标记失效时直接返回。通过长度检查后，它创建一个 `PendingRequest`：

| 字段 | 来源 |
| --- | --- |
| `requestId` | `createId()`，即 `crypto.randomUUID()` |
| `inputText` | trim 之后的文本 |
| `sessionIdAtDispatch` | 当时的 `serverSessionIdRef.current` |

`PendingRequest` 把这一次发送的身份固定下来。后面的手动重试读取同一份 pending，而不是再生成一次 UUID。随后 `dispatch(pending, true)` 把用户气泡加进 `messages`，并调用 `agentClient.sendTurn`。

### 2.3 request_id 和 session_id 不是同一个身份

| 字段 | 谁创建 | 生命周期 | 用途 |
| --- | --- | --- | --- |
| `request_id` | 前端 `createId()` | 一次新的用户发言一个新值；同一次重试不变 | 标识这一次请求，供后端按同一次请求处理 |
| `session_id` | 后端在首次成功响应里签发 | 同一段多轮对话共用 | 让后续发言回到同一个会话 |

举例：

- 第 1 轮：request A，请求里没有 `session_id`
- 第 2 轮：request B，带上服务端返回的 session S
- 第 3 轮：request C，仍然带 S

### 2.4 第一次为什么省略 session_id

`dispatch` 把 `sessionIdAtDispatch` 交给 `sendTurn`。`sendTurn` 先只放入 `request_id` 和 `input_text`。仅当 `sessionId !== null` 时才添加 `session_id`。第一次 `serverSessionId` 是 `null`，所以 JSON 里没有这个字段。它不是 JSON `null`，不是空字符串，也不是浏览器生成的 UUID。

会话归后端所有。浏览器第一次不知道会话号。服务端创建会话，并在成功响应里返回 `session_id`。若本次派出时 `sessionIdAtDispatch === null`，`dispatch` 把 `result.response.session_id` 写入 `serverSessionId` 和 `serverSessionIdRef`，再经 `saveDemoPersistence` 写入 `sessionStorage`。

### 2.5 会话和界面怎样被记住

存储函数在 `frontend/src/storage/sessionStorage.ts`：

| 键 | 内容 |
| --- | --- |
| `gov-agent-demo:v1:session-id` | 服务端签发的会话号 |
| `gov-agent-demo:v1:messages` | 当前聊天界面 |
| `gov-agent-demo:v1:pending-request` | 尚未确认完成的那一次请求 |

实现只使用 `window.sessionStorage`。测试确认这些函数不读写 `localStorage`。源码没有 Cookie 或 IndexedDB。

`loadDemoPersistence` 在 `useAgentChat` 初始化时恢复会话号、消息和 pending。因此同一标签页刷新后，已保存的聊天气泡也会回来。损坏或形状不符的值会被删掉，页面用空默认值继续。若恢复到 pending，只把 `unconfirmed` 设为真，界面显示「上次请求未确认完成」。源码没有在挂载时调用 `dispatch` 或 `sendMessage`，所以刷新不会自动重发。这是会话延续，不是请求重放。

### 2.6 AgentClient 发出公开请求

`frontend/src/api/agentClient.ts` 是生产代码里唯一发起会话请求和健康检查的地方。生产组件没有第二处 `fetch`。

`sendTurn` 负责 POST、90 秒计时、`AbortController`、读取 JSON、调用 `validateSuccessPayload`，以及用 `mapHttpError` 把 HTTP 状态变成前端错误类别。它不保存聊天气泡，也不解释 F09 或 F10。`checkHealth` 只 GET `/health`。

公开请求类型 `SessionTurnRequest` 只有：

- 必填 `request_id`
- 必填 `input_text`
- 可选 `session_id`

用户说「我想办理社保缴费」时，浏览器只发送这句话。请求体里没有槽位、候选事项、已确认事项、`AgentState`、规则结果或 checkpoint。语义判断发生在现有 Agent。

### 2.7 浏览器为什么不直接写后端地址

浏览器请求的是页面自己的路径 `/api/v1/session/turn` 和 `/health`。`frontend/vite.config.ts` 把 `/api` 和 `/health` 代理到 `http://127.0.0.1:8000`，开发端口是 5173，并且 `strictPort: true`。这样浏览器与页面同源，第一版不需要修改后端 CORS。`127.0.0.1:8000` 只出现在这个开发代理配置中，不出现在对话组件里。

请求离开 Vite 之后，前端职责结束。它只按公开合同等待响应。

### 2.8 公开合同，以及前端不再拥有的部分

成功响应类型 `SessionTurnSuccess` 只有：

- `session_id`
- `request_id`
- `status`：只能是 `COMPLETED` 或 `AWAITING_USER_INPUT`
- `response_text`
- `requires_user_input`

失败响应在合同上是 `status = FAILED`，并带 `error.code` 与 `error.message`。界面不直接展示后端原始异常，而是显示 `mapHttpError` 选出的前端类别所对应的中文提示。

公开合同里没有 `public_status`、`candidate_business_id`、`confirmed_business_id`、`AgentState`、checkpoint、内部审计或原始模型输出。

到达 Session API 之后，现有会话与 Agent 栈负责恢复会话并产生公开结果。Redis checkpoint 属于后端。本文不声称某条 SQL、某个 Redis 键的内容，或模型的内部推理。

### 2.9 F09：前端没有替用户选选项

已批准的真实对话中，用户说「平时接一些零活，没有固定单位」。公开回复表示系统还不能可靠确定，并要求按当前选项再说明。前端没有把这句话本地判断成「其他灵活就业人员」。澄清是后端的公开行为。用户若要选择「其他灵活就业人员」，必须自己再发一轮。这表示前端没有复制允许值映射。

### 2.10 F10：看见候选不等于已经确认

同一段已批准对话里，后端公开写出候选事项「灵活就业人员社会保险费申报缴费」，并要求用户明确确认。前端只显示这段 `response_text`。源码里没有因为出现「候选」而设置本地 `confirmed = true`。候选不等于已确认事项。用户之后输入「确认」，那是一次新的发言，带一个新的 `request_id`，并复用已经保存的 `session_id`。

### 2.11 F13：材料句子来自公开回复

用户明确确认之后，已批准响应的 `status` 为 `COMPLETED`。公开回复包含事项「灵活就业人员社会保险费申报缴费」和材料「身份证」。前端没有查询知识数据，没有计算材料，没有判断材料能否公开，也没有自己拼出「身份证」。它渲染的是后端已经生成的 `response_text`。

### 2.12 为什么不能直接相信返回的 JSON

`validateSuccessPayload` 检查：

- `session_id`、`request_id`、`response_text`、`requires_user_input` 的类型
- `status` 只能是 `COMPLETED` 或 `AWAITING_USER_INPUT`
- 返回的 `request_id` 必须等于本次发出的 `requestId`
- 若本次请求已经带了 `session_id`，返回的 `session_id` 必须相同
- `COMPLETED` 必须配 `requires_user_input === false`
- `AWAITING_USER_INPUT` 必须配 `requires_user_input === true`

任何一项不成立，结果是 `INVALID_RESPONSE`，不会被当成一条成功的 Agent 回复。

### 2.13 成功之后前端改哪些状态

`useAgentChat` 用 `useState` 保存：

- `serverSessionId`
- `messages`
- `pendingRequest`
- `isSending`
- `transportError`
- `sessionInvalid`
- `unconfirmed`

对应的 ref 是 `serverSessionIdRef`、`messagesRef`、`pendingRef`、`isSendingRef`、`sessionInvalidRef`。发送过程中读取 ref，是为了拿到当前最新值，而不是渲染闭包里的旧值。

成功时 `dispatch`：

- 仅当本次是首次、`sessionIdAtDispatch === null` 时写入会话号
- 追加 `role: 'assistant'` 的 `ChatMessage`，`text` 等于 `response_text`
- 保留 `status`、`requires_user_input`
- `latency_ms` 使用 `sendTurn` 返回的 `latencyMs`
- 清空 `pendingRequest` 和 `transportError`
- 把 `unconfirmed` 设为 false
- 调用 `saveDemoPersistence`

这是 Review 中的 NB-001：这里用的是 `useState` 和 ref，不是 `useReducer`。Owner 已接受，不作为待修缺陷。见第 15 节。

### 2.14 回复怎样显示，耗时从哪里来

`ChatPanel` 把 `messages` 交给 `MessageBubble`。用户气泡靠右，Agent 气泡靠左。文本放在带 `agent-text` 类的段落里。`frontend/src/styles/index.css` 中该类使用 `white-space: pre-wrap` 和 `overflow-wrap: anywhere`。源码没有 `dangerouslySetInnerHTML`，也没有 Markdown 渲染器。政务回复按纯文本显示，浏览器不会把回复当成 HTML 执行。

`status === 'AWAITING_USER_INPUT'` 时，`ChatPanel` 显示「等待您补充信息」。`COMPLETED` 时显示「本轮处理完成」。下一句要问什么，仍然只来自 `response_text`，不由这两个提示拼出来。

页面上的「会话」只显示 `serverSessionId.slice(0, 8)`。下一轮请求使用完整的 `serverSessionId`。缩短显示不改变网络上的会话身份。

耗时在 `sendTurn` 内用 `performance.now()` 测量：请求开始记一次，成功返回后再记一次，四舍五入为毫秒。这是浏览器观察到的这一次 HTTP 往返，不是模型生成时间，不是后端自报指标，也不是写死的数字。`ChatPanel` 的 `formatLatency` 把它显示为「本次请求耗时」。

## 3. Health 为什么是一条独立链路

`App` 调用 `useAgentHealth()`，再把结果传给页面。挂载后立刻把状态设为 `CHECKING`，并调用 `checkHealth`。JSON 为 `{ "status": "ok" }` 且 HTTP 成功时得到 `AVAILABLE`，否则得到 `UNAVAILABLE`。之后每 `HEALTH_POLL_INTERVAL_MS`（30000 毫秒）再查一次。卸载时把取消标记设为真，并 `clearInterval`。单次检查超时是 `HEALTH_TIMEOUT_MS`（3000 毫秒）。

`ServiceStatus` 把 `AVAILABLE` 显示为「Agent 服务正常」，把 `UNAVAILABLE` 显示为「Agent 服务当前不可用」。这里的正常只表示 `/health` 可用。它不证明模型、Redis、PostgreSQL 或全部依赖已经确认健康。

健康失败只改变 `HealthState`。`useAgentHealth` 不清聊天、不删会话、不改 `request_id`、不重发。`sendMessage` 也不要求当前健康状态必须先变成 `AVAILABLE`。对话自己的错误留在 `transportError`，与这次轮询无关。

## 4. 会话保存、刷新与新建会话

三个函数是 `loadDemoPersistence`、`saveDemoPersistence`、`clearDemoPersistence`。

刷新时，初始化状态调用 `loadDemoPersistence()`。允许恢复的是当前标签页里的会话号、聊天界面和未完成请求。pending 只触发「上次请求未确认完成」，不自动 `dispatch`。

新建会话按钮调用 `requestNewSession`。若 `messages` 非空，先用 `window.confirm(presentation.newSessionConfirm)` 询问。用户取消则不动。确认后 `reset` 清空 `serverSessionId`、`messages`、`pendingRequest`、`transportError`、`sessionInvalid`、`unconfirmed`，并 `clearDemoPersistence()`。这次点击没有 `fetch`。下一次 `sendMessage` 的 `sessionIdAtDispatch` 又是 `null`，请求再次省略 `session_id`。

这个按钮不删除 Redis 里的服务端会话，也没有调用后端的会话重置接口。当前源码不存在这样的调用。

## 5. 为什么“重试”不能生成新的 request_id

新的用户发言走 `sendMessage`，总会 `createId()`。重试走 `retry`：它读取 `pendingRef.current`，再 `dispatch(pending, false)`。第二个参数为 false，所以不会再追加一条用户气泡。`requestId`、`inputText`、`sessionIdAtDispatch` 都还是失败那一次的值。

若第一次就失败，`sessionIdAtDispatch` 仍是 `null`。重试继续省略 `session_id`，不会临时造一个客户端会话号。

举例：用户点了一次发送，`request_id` 是 A，然后网络超时。再点「重试」时仍然是 A。如果改成 B，后端会把它看成另一次请求，原来的同一次请求身份就对不上。已批准的公开合同用 `request_id` 区分新发言和同一次重试。本文不展开后端内部如何保存这套身份。

用户改了文字再发送，走的是 `sendMessage`，那是新发言，会有新的 `request_id`。

`REQUEST_IN_PROGRESS` 允许稍后对同一个 pending 手动重试。源码没有自动轮询。

## 5.1 九十秒超时怎样被认出来

`TURN_TIMEOUT_MS` 是 90000。计时器先把 `timedOut` 设为 `true`，再调用 `controller.abort()`。`catch` 里若 `timedOut` 为真，类别是 `TIMEOUT`；否则是 `NETWORK_ERROR`。超时和其他中断都可能表现为 abort，所以不能只看 AbortError 的名称。这个旗标把「前端自己设定的 90 秒」和普通传输失败分开。

## 5.2 错误怎样变成用户能看懂的状态

| 条件 | 前端类别 | 能否手动重试 | 用户侧结果 |
| --- | --- | --- | --- |
| 422 | `INVALID_REQUEST` | 否 | 中文提示，不自动重发 |
| 404 | `SESSION_NOT_FOUND` | 否 | 标记会话不可用，保留已有消息 |
| 410 | `SESSION_EXPIRED` | 否 | 同上 |
| 409 且 code 为 `REQUEST_ID_REUSE_CONFLICT` | `REQUEST_ID_REUSE_CONFLICT` | 否 | 中文提示 |
| 409 且 code 为 `REQUEST_IN_PROGRESS` | `REQUEST_IN_PROGRESS` | 是，仍用原 pending | 提示稍后再试 |
| 500 | `AGENT_FAILURE` | 是 | 中文提示和重试 |
| 503 | `PERSISTENCE_UNAVAILABLE` | 是 | 中文提示和重试 |
| 自己的 90 秒计时 | `TIMEOUT` | 是 | 中文提示和重试 |
| 其它传输失败 | `NETWORK_ERROR` | 是 | 中文提示和重试 |
| 成功 JSON 不符合合同 | `INVALID_RESPONSE` | 否 | 不当成成功回复 |
| 其它 HTTP，包括 400 | `UNKNOWN_ERROR` | 否 | 中文提示 |

界面使用各类别对应的固定中文句子，不显示 Python 堆栈、Redis 细节或数据库口令。失败不会变成一条假的 assistant 消息。这些错误停在聊天状态，不会进入一个前端版的 Decision Graph。

404 或 410 时，`sessionInvalid` 设为真，已有 `messages` 保留，pending 因为不可重试而被清掉，发送被禁用。页面同时显示错误句和「当前会话已不可用，请新建会话」。源码不会在这时静默生成新的 `session_id`，也不会清理后端会话。用户需要点「新建会话」。

`ErrorBoundary` 在 `main.tsx` 里包裹整个 `App`。它只处理 React 渲染崩溃，页面变为「页面组件加载异常，请刷新页面」，不输出堆栈。Session API 错误走 `transportError`，不走这个边界。

## 6. 汇报页面中的静态数据与实时数据

`frontend/src/content/presentation.ts` 导出常量 `presentation`。各区块只渲染这些句子：

- `HeroSection` 使用 `presentation.hero`
- `AchievementsSection` 使用 `presentation.achievements`，并注明不是实时运行指标
- `ArchitectureSection` 使用 `presentation.architecture`，声明「这是架构说明，不是实时 Trace」
- `RoadmapSection` 按 `presentation.roadmap.steps` 的顺序显示名称。源码没有给每一步单独标「已完成 / 未来」
- `ReliabilitySection` 使用 `presentation.reliability`
- `ValidationSection` 使用 `presentation.validation`
- `NextStepsSection` 使用 `presentation.next`，并写明这些是后续规划，当前版本尚未实现

| 静态 | 实时 |
| --- | --- |
| 项目介绍 | 健康状态 |
| 当前成果 | 服务端 `session_id` |
| 架构说明 | `request_id` |
| 路线名称 | 用户输入 |
| 可靠性说明 | `response_text` |
| F13-Preview 状态 | `status` |
| 77 / 0 / 0 证据 | `requires_user_input` |
| 后续规划 | 浏览器测到的 HTTP 耗时 |

静态区不依赖某次 Agent 成功。实时回复只能来自通过校验的 Session API。把历史证据画成刚刚测到的运行指标，会把两种来源混在一起。

页面上的「Final Authorized Safe Regression：77 passed / 0 failed / 0 skipped」来自 `presentation`。正文写明这是已授权安全回归，不是全仓测试总量。它也不是 F14 前端自己的 46 项测试。那 46 项是另一份前端自动化证据。F13-Preview 在静态文案中写为 `FINAL CLOSED / REMOTE-FROZEN`。

## 7. 浏览器能知道什么，不能知道什么

浏览器可以持有：`session_id`、`request_id`、`status`、`response_text`、`requires_user_input`、健康状态、HTTP 耗时，以及用户自己输入的文字。

浏览器的公开合同不包含：`candidate_business_id`、`confirmed_business_id`、`AgentState`、checkpoint、内部审计、F09 或 F10 的内部产物、原始模型输出、prompt、规则内部结果。后端内部可以有这些数据，但 F14 不把它们送到浏览器。

架构说明里的「Decision Graph」「F09」「F10」「F13」是 `presentation.architecture.steps` 中的展示句子。这些字符串不执行业务判断。

前端源码和 `frontend/README.md` 没有模型密钥、数据库连接串或 Redis 口令。浏览器不连接模型地址。路径是：浏览器到同源 Session API，再由现有后端访问模型和数据。若讨论运行环境，只使用变量名，不写入密钥值。

## 8. 真实 Golden Flow：逐轮看懂代码为什么这样设计

以下是已批准的公开对话，不是本文编写时重新调用的结果。每一轮浏览器都生成新的 `request_id`。第一轮省略 `session_id`。服务端签发会话号之后，后续轮次复用同一个号。页面显示的是各轮 `response_text`。

1. 用户：「我辞职了，现在没单位，想自己交社保」。公开回复询问主要是社保缴费、社保转移，还是查询或其他业务。
2. 用户：「我想办理社保缴费」。公开回复询问是单位缴还是自己缴。
3. 用户：「我自己缴」。公开回复继续询问灵活就业情况。
4. 用户：「平时接一些零活，没有固定单位」。公开回复表示无法可靠确定，并要求进一步说明。前端没有替用户选择选项。
5. 用户：「其他灵活就业人员」。公开回复给出候选事项，并要求明确确认。前端没有本地确认标志。
6. 用户：「确认」。`status` 为 `COMPLETED`。公开回复包含「灵活就业人员社会保险费申报缴费」和「身份证」。

这段证据支持：浏览器页面可用，Vite 代理可用，Session API 可用，首次省略 `session_id`，服务端签发会话，后续复用，每轮新的 `request_id`，真实 `response_text` 被显示，以及 F09 澄清、F10 显式确认、F13 公开材料和最终 `COMPLETED` 这些公开行为。

它不直接证明：Redis checkpoint 的内部内容、SQL 是否正确、数据库具体行如何变化、模型的思维链或隐藏推理、知识检索的精确路径、F09 的置信度数字、F10 的内部候选 ID。

## 9. 状态到底属于谁

| 状态 | 归属 |
| --- | --- |
| `draft` | `AgentDemoSection` |
| `messages` | `useAgentChat`，并写入 `sessionStorage` |
| `serverSessionId` | `useAgentChat`，并写入 `sessionStorage` |
| `pendingRequest` | `useAgentChat`，并写入 `sessionStorage` |
| `isSending`、`transportError`、`sessionInvalid`、`unconfirmed` | `useAgentChat` |
| `HealthState` | `useAgentHealth` |
| 静态汇报 | `presentation.ts` |
| 业务槽位、候选事项、已确认事项 | 后端，不在前端 |

## 10. 关键字段怎么流动

- `input_text`：`ChatInput` → `draft` → `sendMessage` → `PendingRequest.inputText` → `sendTurn` → 后端
- `request_id`：`createId()` → `PendingRequest.requestId` → 后端 → 响应 → `validateSuccessPayload` 比对
- `session_id`：后端创建 → 响应 → `serverSessionId` → `saveDemoPersistence` → 下一轮 `sessionIdAtDispatch`
- `response_text`：后端 → `validateSuccessPayload` → assistant `ChatMessage.text` → `MessageBubble`
- `status`：后端 → 校验允许值 → 写入 assistant 消息 → `ChatPanel` 选择公开提示
- `requires_user_input`：后端 → 与 `status` 一起校验 → 写入同一条消息
- 耗时：`sendTurn` 的 `performance.now()` → `latencyMs` → `latency_ms` → `formatLatency`

失败时，字段停在 `mapHttpError` 或 `validateSuccessPayload` 产生的 `FrontendError`，进入 `transportError`，不进入一条成功的 `response_text`。

## 11. 文件职责地图

页面启动：`frontend/src/main.tsx` 找到根节点，用 `ErrorBoundary` 包住 `App`。`frontend/src/App.tsx` 把汇报区和实时演示排在同一页，并把健康状态传下去。

交互：`AgentDemoSection.tsx` 持有 `draft` 和 `useAgentChat`。`ChatPanel.tsx` 编排发送、示例、重试、新建会话、耗时和错误。`ChatInput.tsx` 收集文字。`MessageBubble.tsx` 显示一条纯文本。`ServiceStatus.tsx` 显示健康文案。

会话：`useAgentChat.ts` 管请求身份、消息、重试和新建会话。

HTTP：`contracts.ts` 定义公开类型和 4000 字上限。`agentClient.ts` 发请求并校验响应。`vite.config.ts` 提供 5173 和开发代理。

存储：`sessionStorage.ts` 读写三个 `gov-agent-demo:v1:` 键。

健康：`useAgentHealth.ts`。

静态内容：`presentation.ts`，以及 Hero、Achievements、Architecture、Roadmap、Reliability、Validation、NextSteps。样式在 `index.css`。`ErrorBoundary.tsx` 只接渲染崩溃。

测试：见第 14 节。`frontend/README.md` 说明在 `frontend/` 用 npm 安装和 `npm run dev`，浏览器只请求同源的 `/health` 与 `/api/v1/session/turn`。

## 12. 第一次读代码时应该先认哪些函数

对话链路：

- `AgentDemoSection`：持有 `draft`，调用 `useAgentChat`
- `ChatInput`：收集 textarea
- `ChatPanel`：发送、重试、新建会话和展示
- `useAgentChat`
- `sendMessage`：新发言
- `retry`：沿用 pending
- `requestNewSession`：清空前端会话
- `dispatch`：真正调用客户端并更新消息
- `createId`：`crypto.randomUUID()`
- `sendTurn`
- `validateSuccessPayload`
- `mapHttpError`
- `MessageBubble`

健康与存储：

- `useAgentHealth`
- `checkHealth`
- `loadDemoPersistence`
- `saveDemoPersistence`
- `clearDemoPersistence`
- `ServiceStatus`

类型名是 `PendingRequest`、`SessionTurnRequest`、`SessionTurnSuccess`、`ChatMessage`、`FrontendError`。常量是 `INPUT_MAX_LENGTH`、`TURN_TIMEOUT_MS`、`HEALTH_TIMEOUT_MS`、`HEALTH_POLL_INTERVAL_MS`。

## 13. 推荐阅读顺序

先沿一次发送读，再看支撑链路：

1. `AgentDemoSection` 和 `ChatPanel`，看点击怎样进入 hook。
2. `useAgentChat`，看 `request_id`、会话号和重试。
3. `contracts.ts` 和 `agentClient.ts`，看公开字段和校验。
4. `sessionStorage.ts`，看刷新恢复什么。
5. `vite.config.ts`，看浏览器路径怎样转到本机后端。
6. `useAgentHealth`，确认它不参与发言。
7. `MessageBubble` 和 `ServiceStatus`，看最终句子。
8. `presentation.ts` 和各静态区块，区分说明文字和实时回复。
9. 测试，看哪些行为被假客户端固定下来。
10. `main.tsx` 和 `App.tsx` 可以最后看，它们只负责挂载和排列，不生成请求身份。

## 14. 测试在验证什么

已批准的前端自动化结果是 6 个测试文件、46 项测试、0 失败，并且生产构建通过。测试源码路径一共 7 个：6 个会被执行的测试文件，加上支撑文件 `frontend/src/test/setup.ts`。

- `agentClient.test.ts`：健康结果、首次省略 `session_id`、已有会话才带上它、成功约束、错误的 `request_id` 或 `session_id`、HTTP 映射，以及 90 秒超时。
- `useAgentChat.test.tsx`：首轮省略会话号、次轮复用、重试身份、修改输入后使用新 `request_id`、新建会话、发送中的第二次点击被忽略、刷新后不自动发送。
- `useAgentHealth.test.tsx`：立即检查、失败，以及 30 秒后再次检查、卸载后停止。
- `sessionStorage.test.ts`：存取、清空、损坏数据，以及不使用 `localStorage`。
- `AgentDemoSection.test.tsx`：示例只填入、按钮和 Enter 发送、Shift+Enter 不发送、4000 字、加载时禁用、耗时和短会话号。
- `App.test.tsx`：汇报区和验证文案出现。

这些测试使用替身客户端。它们验证前端合同和交互，不验证后端 F09、F10、F13 的内部规则。那些公开行为来自已批准的真实浏览器流程。

单元和组件测试回答「前端是否按合同组请求、校验响应并更新界面」。手工真实集成回答「浏览器经 Vite 代理打到真实 Session API 时，公开行为是否成立」。Golden Flow 回答公开办理对话是否按已批准顺序出现。三者不是同一份证据。

冻结设计选择 Vitest、Testing Library、user-event 和 jsdom。真实浏览器流程由受控的手工集成完成。没有 Playwright 或 Cypress 是这个选择，不是漏测。

## 15. Review 中保留的两个说明项

NB-001：`useAgentChat` 使用 `useState` 和 ref，冻结技术设计的字面写法是 `useReducer`。公开合同、会话、`request_id`、重试、存储、46 项测试、构建和真实对话均已通过。Owner 接受该实现，不重开代码，也不在这里当作缺陷修改。

INFO-001：HTTP 400 进入 `UNKNOWN_ERROR`。冻结映射里，`INVALID_REQUEST` 对应 422。这不违反需求或技术设计，不需要修改。

## 16. 用一句话记住 F14

F14 是现有确定性政务办理 Agent 的浏览器客户端和汇报表面，不是第二套业务引擎。前端掌管交互和公开状态，后端掌管业务事实和业务决策。
