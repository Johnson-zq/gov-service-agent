# AGENTS.md

本项目长期必须遵守的核心开发规则。所有参与开发的人员与 AI 助手均须遵循。

## 1. 渐进式 Feature 开发

- 每次只进入一个 Feature 的一个阶段。
- Feature 范围以 `docs/features/Fxx-*.md` 为权威。
- 不允许一次性生成完整工程或完整 Architecture Blueprint 目录树。

## 2. 固定开发阶段

每个 Feature 必须按以下顺序推进，**未经明确确认不得自动进入下一阶段**：

```
Requirement
→ Technical Design
→ Confirm
→ Code
→ Test
→ Review
→ Explanation
→ Commit
→ Stop
```

## 3. 范围与架构边界

- Architecture Blueprint 是目标参考，不是初始化清单。
- 不得为未启动的 Feature 提前创建空目录、空 Adapter、空 Repository、空 Provider、空 Service 或占位类。
- 若实现过程中需要修改总体 Architecture Blueprint、核心技术路线、业务决策原则，或大幅扩大 Feature Scope，**必须停止并等待确认**。

## 4. 核心架构原则（不可违反）

- 语义检索只负责找方向，不能直接决定最终 `business_id`。
- Business Graph 负责走合法业务路径。
- LLM 负责自然语言理解、槽位抽取、回答映射；不负责最终 `business_id` 和确定性业务规则。
- Rule Engine 必须是确定性的，禁止 LLM 或 Python eval 执行业务规则。
- Terminal Node 只能产生候选事项，须经 Rule Engine 校验和用户确认后才写入 `business_id`。
- 业务数据必须数据化，运行时不得直接读取 Excel。

## 5. 模型与基础设施原则

- 应用本地优先；Embedding 和 LLM 按远程 API 服务化调用，不要求在开发人员笔记本加载大模型。
- 不得猜测并实现尚未提供的公司模型 API。
- 基础设施地址、模型地址、密钥均须配置化，代码中不得写死。

## 6. Git 规则

当前默认 **PRE_REMOTE** 模式：

**允许：**

- `git init`（经授权）
- `git status`
- `git diff`
- 经明确授权后的本地 commit

**禁止：**

- push
- 自行创建假 remote
- 自行假设公司 main/develop 分支策略
- `rebase`、`reset --hard`、`stash`、`force push`（除非明确授权）

Commit 前须：`git status` → `git diff` → 列出文件与用途 → 等待确认。

Commit message 使用中文概括，例如：`feat(F00): 初始化最小FastAPI工程`

## 7. 未确认规则处理

- 无法确认的业务规则必须标记为 `TO_CONFIRM`。
- 不得将推测直接写成已验证规则。

## 8. 日志与安全

- 日志是项目正式能力，但不得记录明文身份证号、手机号、证件全文、密钥、Token 等敏感信息。

## 9. 工具职责

- 总体规划与架构决策：由项目负责人确认。
- 具体 Feature 设计、代码、测试：在 Feature 文档约束下实施。
- Cursor / AI 助手不得越权扩大范围或自动进入未授权阶段。
