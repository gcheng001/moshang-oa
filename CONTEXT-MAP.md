# Context Map

## Contexts

- [产品工作台](./CONTEXT.md) — 定义办公助手的统一产品语言与用户角色
- [OA 业务](./docs/contexts/oa/CONTEXT.md) — 管理案件、立案审批和 OA 文书
- [本机办案工具](./docs/contexts/local-casework/CONTEXT.md) — 处理本机材料转换、微信录屏取证和证据整理

## Relationships

- **产品工作台 → OA 业务**：为承办律师和审批人提供 OA 业务入口
- **产品工作台 → 本机办案工具**：为律师提供本机材料处理入口
- **OA 业务 ↔ 本机办案工具**：共享案件工作场景，但各自拥有独立规则；本机办案工具不得直接改变 OA 案件状态

## 跨仓上下文

- **案件账簿**：领域与实现归 `get笔记项目` 仓库（见该仓库 `docs/contexts/case-ledger/CONTEXT.md`）。办公助手仅提供操作入口（同步触发、结果展示），不拥有其规则。红线：案件账簿只读 OA，任何改动不写回 OA。
