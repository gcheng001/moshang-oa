# 办公助手（摩尚OA v2）— 律师事务所办公系统

> 全新重写版（2026-07-08）：React 前端 + FastAPI 本地后端 + pywebview 桌面壳。应用名「办公助手」，项目目录沿用 `摩尚OA`。
> 领域术语见 `CONTEXT.md`，技术决策见 `docs/adr/`。旧版 Tauri 代码已于 2026-07-08 清理（如需找回：废纸篓 `摩尚OA_legacy_20260708`）。

## 一键启动

- **应用程序 → 办公助手**（`/Applications/办公助手.app`，推荐）：启动器强制 `arch -arm64`（LaunchServices 可能用 Rosetta 跑脚本型 app，venv 原生库是 arm64），日志在 `/tmp/moshang_oa_app.log`，图标源文件在 `docs/appicon/`
- 或双击项目根目录的 **`启动办公助手.command`**

两者都会自动拉起本地后端（端口 8017）并打开桌面窗口。

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
| 办案助手 | ✅ | 整合「办案材料助手」：材料转换（多引擎OCR/Office/音视频逐字稿/MD转Word）、微信录屏取证、证据整理（汇总+时间线+案件OS输入包），后台任务队列+日志 |
| 立案 / 文书下载 | 🚧 | 二期（skill 侧脚本已验证，待接入） |

## 架构

```
启动办公助手.command
└── backend/desktop.py          # pywebview 桌面窗口 + 拉起 uvicorn
    └── backend/app/            # FastAPI
        ├── main.py             # REST API + 托管 frontend/dist
        ├── oa.py               # OA 客户端（移植自 moshang-oa skill 的 oa_probe.py）
        ├── assistant.py        # 办案助手：包装办案材料助手 CLI + 移植证据整理，后台任务管理
        └── sessions.py         # apikey→token 会话，自动续期
frontend/                       # React 18 + TS + Tailwind v4 + Vite
    └── src/pages/              # Login / CaseBoard / Approvals / ApprovalDetail / Assistant
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

侧栏「立案审批」入口带角标：数字为当前待审数量；出现**未查看过的新待审案件**时角标变红并带红点脉冲。每 10 分钟自动轮询一次，进入审批页即视为已读；**审批通过/驳回后立即刷新角标**（`moshang:pending-refresh` 事件），不等下个轮询周期。

驳回时系统按预检结果（缺资料/利冲线索/重复立案/收费冲突等）**自动代拟驳回理由**，合伙人可直接采纳或修改后提交。

## 办案助手（2026-07-08 整合）

复用 `/Applications/办案工具集/办案材料助手.app` 的本机 CLI 能力，摩尚OA 只做界面与任务调度，处理逻辑不重复维护：

- **材料转换**：`droplet.sh --agent --engine <engine>`（PDF/图片 OCR 可选 MinerU本地/VisionOCR/legal-ocr在线；Office→MD；MD/TXT→Word；音视频→逐字稿），输出 `~/Desktop/VisionOCR_Output/`
- **微信录屏取证**：`wechat_evidence.py interval-pdf`（间隔抽帧+智能筛选→取证PDF+截图+复核资料），输出 `~/Desktop/录屏取证输出/`
- **证据整理**：逻辑移植自 GUI 脚本（`backend/app/assistant.py`），扫描输出目录生成案件材料汇总/时间线/materials_manifest/case_os_intake_package，行为与原 APP 一致
- 文件选择用 osascript 原生对话框；任务在后台线程跑，前端 2 秒轮询状态，失败可看日志尾部；点击输出文件在访达中显示
