# 摩尚OA v2 — 律师事务所办公系统

> 全新重写版（2026-07-08）：React 前端 + FastAPI 本地后端 + pywebview 桌面壳。
> 领域术语见 `CONTEXT.md`，技术决策见 `docs/adr/`。旧版 Tauri 代码已于 2026-07-08 清理（如需找回：废纸篓 `摩尚OA_legacy_20260708`）。

## 一键启动

双击项目根目录的 **`启动摩尚OA.command`**，会自动拉起本地后端并打开桌面窗口。

开发模式：

```bash
# 后端（端口 8017）
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8017 --reload

# 前端（端口 5173，代理 /api 到 8017）
cd frontend && npm run dev

# 改完前端后打包（后端会直接托管 dist）
cd frontend && npm run build
```

## 功能（MVP）

| 模块 | 状态 | 说明 |
|------|------|------|
| 登录 | ✅ | 每人输入自己的 Agent API Key，本机可记住 |
| 案件看板 | ✅ | 表格/看板双视图，关键词/状态/类型筛选，案件详情抽屉，未收金额高亮 |
| 立案审批 | ✅ | 待审清单 → 自动合规检查（完整性/利冲/OA重复立案/风险收费）→ 通过/驳回 → 回读校验 |
| 结案待审 | 👁 | 只读展示（OA 结案审批接口未攻克，见 skill HANDOFF） |
| 立案 / 文书下载 | 🚧 | 二期（skill 侧脚本已验证，待接入） |

## 架构

```
启动摩尚OA.command
└── backend/desktop.py          # pywebview 桌面窗口 + 拉起 uvicorn
    └── backend/app/            # FastAPI
        ├── main.py             # REST API + 托管 frontend/dist
        ├── oa.py               # OA 客户端（移植自 moshang-oa skill 的 oa_probe.py）
        └── sessions.py         # apikey→token 会话，自动续期
frontend/                       # React 18 + TS + Tailwind v4 + Vite
    └── src/pages/              # Login / CaseBoard / Approvals / ApprovalDetail
```

- OA 实例：`https://moshang2.ycq6.com`（AgentAPI + DataService）
- 审批唯一写接口：`/DataServices/LawcaseSvr/Lianshenpi`，通过前必须过合规门禁，提交后回读校验状态
- 桌面壳曾计划用 Tauri（见 ADR-0001）；因本机 Rust 工具链被清理，先落地 pywebview，Tauri 打包留作分发安装包时的升级路线

## 合规门禁（立案审批，2026-07-08 规则）

1. **资料完整性** — 委托人/对方/律师/案由/阶段/收费缺失即阻断；**案情摘要缺失仅提示，不拦截**
2. **利冲检索** — 对立方向命中须合伙人勾选「已人工复核」并填写结论（写入审批意见）
3. **OA 重复立案** — 同委托人+同对方+同案由的在办案件直接阻断
4. **低收费审查** — 委托收费 < ¥5,000 必须有收费说明（OA ChargeMemo），否则阻断；收费说明中记载的金额与登记收费不一致（既非其中一笔也非分期合计）同样阻断
5. **风险代理收费** — 展示收费方案原文+标的额+分段上限计算明细（司发通〔2021〕87号），系统给出初步判断与建议，**不硬阻断**；须合伙人勾选「已审阅确认」后才能通过，复核意见写入审批意见。初步判断除禁止情形/缺方案/缺标的/登记超上限外，还比对**方案文本记载金额 vs 登记收费**（不一致报冲突）及**方案固定金额合计 vs 分段上限**

## 待办提醒

侧栏「立案审批」入口带角标：数字为当前待审数量；出现**未查看过的新待审案件**时角标变红并带红点脉冲。每 10 分钟自动轮询一次，进入审批页即视为已读。
