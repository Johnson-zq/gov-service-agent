# Project Open Items

跨 Feature 待确认事项。按 `docs/development-playbook.md` 管理。

| ID | 事项 | 优先级 | 状态 | 需要谁确认 | 阻塞哪个 Feature | 最后更新 | 最终结论 |
|----|------|--------|------|------------|------------------|----------|----------|
| OI-F02-01 | DEMO_SS_001 是否可在杭州市上城区政务服务中心办理；若可，确认楼层/窗口/业务区域 | P0 | OPEN | 业务方 | 未来 Navigation / 到场引导 | 2026-08-31 | |
| OI-F02-02 | applicant_scope 三类人员是否可升级为 VERIFIED eligibility Rule | P1 | OPEN | 业务方 | F04 Rule Engine 正式规则 | 2026-08-31 | |
| OI-F02-03 | 公司原始办事指南存储政策与 Git 授权范围（含是否同步个人 GitHub） | P1 | OPEN | 项目负责人 / 公司资料管理 | Provenance 原始文件入库 | 2026-08-31 | |
| OI-F02-04 | DEMO_GA_001（原规划居民身份证到期换领）与《居民身份证换补领（领证未满五年）》映射 | P2 | OPEN | 业务方 | 公安类 Demo | 2026-08-31 | |
| OI-F02-05 | DEMO_SS_002（社会保险关系转移接续）办事指南待获取 | P2 | OPEN | 业务方 | 社保转移 Demo | 2026-08-31 | |

## Notes

- `HandlingLocation.floor` / `window` 为 `null` 表示未知细节，不单独建立 Open Item。
- 政务服务中心地点争议统一由 **OI-F02-01** 跟踪；确认前不得写入 DEMO_SS_001 HandlingLocation。
- 当前默认：原始公司 doc/docx 不进入个人 GitHub；结构化 JSON 进入公司 Git。
