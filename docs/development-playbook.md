# Development Playbook

本文档描述本项目的详细 Feature 开发流程。简明不可违反规则见根目录 `AGENTS.md`。

## 1. 开发模式概览

本项目采用 **Feature 驱动的渐进式开发**：

- 一个 Feature 解决一个明确问题；
- 一个阶段只做一件事；
- 代码、目录、文档随 Feature 实际推进而生长；
- 禁止按 Architecture Blueprint 一次性创建完整工程。

## 2. Feature 文档

每个功能对应一份 Feature 文档：

```
docs/features/Fxx-feature-name.md
```

Feature Requirement 至少应包含：

- Problem
- Goals
- Non-goals
- Functional Requirements
- Technical Design
- Files to Create / Modify
- Test Plan
- Completion Criteria
- Open Questions
- Approval Record
- Current Stage

Feature 文档是当前允许修改范围的权威依据。

## 3. 阶段说明

### 3.1 Requirement

**目标：** 明确这个功能解决什么问题、为什么现在做、输入输出是什么、不做什么、完成标准是什么。

**产出：** Feature Requirement 文档。

**禁止：** 在本阶段进入 Design、Code 或 Test。

### 3.2 Technical Design

**目标：** 明确调用链、数据结构、文件清单、配置、测试方案。

**产出：** Technical Design 内容（写入 Feature 文档或引用）。

**禁止：** 在本阶段写实现代码、安装依赖、执行 Git commit。

### 3.3 Confirm

**目标：** 由项目负责人确认 Requirement 与 Design 是否可以进入实现。

**规则：** 未经 Confirm，不得进入 Code。

### 3.4 Code

**目标：** 只实现当前 Feature 已确认范围内的代码与文档。

**规则：**

- 原则上一次 Feature 不应大量修改核心文件；若预计超过约 5～8 个核心文件，应先报告并考虑拆分 Feature。
- 不得引入当前 Feature Non-goals 中的能力。
- Code 完成后停止，不自动进入 Test，除非明确授权。

### 3.5 Test

**目标：** 运行与当前 Feature 对应的测试，并验证完成标准。

**规则：**

- 必须有与 Feature 范围匹配的测试；
- 测试失败时，在授权范围内修复，不自动扩大到其他 Feature。

### 3.6 Review

**目标：** 检查 Correctness、Architecture、Security、Maintainability、Testing、Scope。

**关注点：**

- 是否越界实现；
- 是否提前创建未来 Feature 目录；
- 是否违反 AGENTS.md 中的核心原则。

### 3.7 Explanation

**目标：** 提供代码阅读说明，帮助项目成员理解当前 Feature。

**产出：** `docs/code-reading/Fxx-xxx-reading-guide.md`

至少说明：

1. 本 Feature 解决什么问题
2. 为什么需要这个 Feature
3. 推荐阅读文件顺序
4. 每个文件职责
5. 核心类和函数
6. 完整调用链
7. 一条真实数据如何流动
8. 业务逻辑 vs 基础设施
9. 如何启动
10. 如何测试
11. 如何查看日志
12. 推荐 Debug 断点
13. 常见 Bug
14. 后续 Feature 扩展点

### 3.8 Commit

**目标：** 在明确授权后提交当前 Feature 变更。

**流程：**

1. `git status`
2. `git diff`
3. 列出准备提交的文件及用途
4. 等待确认
5. 使用中文 commit message 提交

**禁止：** 未经授权自动 commit 或 push。

### 3.9 Stop

**目标：** 当前 Feature 阶段工作结束，等待下一指令。

不得自动开始下一个 Feature 或下一阶段。

## 4. 目录与代码生长原则

- 目录必须随 Feature 实际开发逐渐创建；
- 不为 OCR、预约、导航、语音、AR 等未启动能力创建空目录；
- 不为 Provider、Repository、Adapter 等未来抽象提前创建占位实现。

## 5. Open Items 管理

尚未确认的问题统一记录到：

```
docs/project/open-items.md
```

至少包含：ID、事项、优先级、状态、负责人、需要谁确认、阻塞哪个 Feature、最后更新时间、最终结论。

优先级：

- **P0：** 直接阻塞近期 Feature
- **P1：** 需尽快确认，但不阻塞当前核心开发
- **P2：** 后续模块再确认

## 6. Git 模式

### PRE_REMOTE（当前默认）

- 可本地 init、status、diff、经授权 commit
- 不可 push、不可擅自添加 remote

### COMPANY_REMOTE

远程仓库就绪后：

- 每次 Feature 开始前检查 git status、branch、remote、工作树状态
- 工作区干净后再同步远程
- 遇到冲突、detached HEAD 等异常必须停止并报告
- 不得擅自 stash、hard reset、rebase、force push

## 7. 一期 Feature 路线（参考）

```
F00  Project Minimum Initialization
F01  Runtime Settings + Basic Logging + Environment Foundation
F02  DEMO_SS_001 Requirement and Data Contract
F03  Business Graph Domain and JSON Repository
...
```

具体以 Feature 文档为准；未启动的 Feature 不得提前实现。

## 8. 与 Architecture Blueprint 的关系

Architecture Blueprint 描述长期目标结构，**不是**项目初始化清单。

Playbook 与 Feature 文档优先于“为了对齐 Blueprint 而提前建目录”的做法。
