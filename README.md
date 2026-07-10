# 办公助手（摩尚OA v2）— 律师事务所办公系统

> 全新重写版（2026-07-08）：React 前端 + FastAPI 本地后端 + pywebview 桌面壳。应用名「办公助手」，项目目录沿用 `摩尚OA`。
> 领域术语见 `CONTEXT.md`，技术决策见 `docs/adr/`。旧版 Tauri 代码已于 2026-07-08 清理（如需找回：废纸篓 `摩尚OA_legacy_20260708`）。

## Windows 便携版（2026-07-10 新增）

**推荐路径：GitHub 检出后在 Windows 上直接装**（免 Mac 侧组装、免 Node）：

1. Windows 上下载本仓库（Code → Download ZIP，或 `git clone`）并解压
2. 双击 `windows\install.bat`（一次性：走华为云/npmmirror 镜像下载内嵌 Python 3.12 + 清华镜像装依赖，约 1-3 分钟）
3. 以后每次双击 `windows\start.bat` 启动

要点：前端产物 `frontend/dist` 已入库（268K），Windows 端零构建；`serve_win.py` 自动识别仓库布局/便携包布局；`.gitattributes` 强制 `.bat` 保持 CRLF（LF 批处理在部分环境双击无反应，此前踩坑）；`start.bat` 改用 `python.exe` 带控制台启动，出错会停住显示原因（旧版 `pythonw.exe` 静默失败无从排查）。

备选路径：Mac 上执行 `windows/build_windows_package.sh` 组装免安装包 `windows/dist/MoshangOA-Win-<日期>.zip`（约 14M，内嵌 Python + win_amd64 wheels，解压双击 `start.bat` 即用）。

运行时用 **Edge 应用模式**（`--app` + 独立 `edge-profile` 保证进程独立可感知窗口关闭、localStorage 持久化记住 API Key）替代 pywebview，免 pythonnet/WebView2 依赖；未装 Edge 时退回默认浏览器。办案助手模块依赖 macOS 工具链，Windows 端自动降级不可用（`assistant.py` 以 `IS_WINDOWS` 分支处理 pwd/reveal/文件选择）。日志在 `logs/moshang_win.log`（GitHub 方式在 `windows/logs/`）。

## 一键启动

- **应用程序 → 办案工具集 → 办公助手**（`/Applications/办案工具集/办公助手.app`，推荐）：启动器强制 `arch -arm64`（LaunchServices 可能用 Rosetta 跑脚本型 app，venv 原生库是 arm64），日志在 `/tmp/moshang_oa_app.log`，图标源文件在 `docs/appicon/`
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
| 案件看板 | ✅ | 表格/看板双视图（含「其他状态」兜底列），关键词/状态/类型筛选，案件详情抽屉，未收金额高亮 |
| 文书下载 | ✅ | 案件详情抽屉内（2026-07-10 接入）：列出本案 OA 可用文书模板 → 勾选下载到 `~/Desktop/文书下载/{案号}/`；委托人为法人/非法人组织时自动附带法定代表身份证明书/负责人证明书（2026-06-17 硬规则），同名加后缀防覆盖，下载后校验 docx 完整性，可在访达中显示 |
| 案件审批 | ✅ | 待审清单 → 自动合规检查（完整性/**案由规范性**/利冲/OA重复立案/低收费/风险收费）→ 检查结论汇总条 → 通过/驳回 → 回读校验；利冲/重复命中显示对方案件当事人+案由+经办；案件已不在待审状态时只读守卫 |
| 结案待审 | 👁 | 只读展示（OA 结案审批接口未攻克，见 skill HANDOFF） |
| 办案助手 | ✅ | 整合「办案材料助手」：材料转换（多引擎OCR/Office/音视频逐字稿/MD转Word）、微信录屏取证、证据整理（汇总+时间线+案件OS输入包），后台任务队列+日志 |
| 立案 | 🚧 | 二期（skill 侧脚本已验证，待接入） |

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
1a. **案由规范性**（2026-07-10 新增）— 案由/罪名必须命中 OA 系统案由库（`GetCaseHeads` 全量 12 棵树约 2009 节点，含刑事罪名/民事案由 2011 版等，进程内缓存 12h）：自由填写文本**硬阻断**并给出相近规范案由建议；顶级分类节点硬阻断；非末级案由仅提示；含顿号罪名（如「拒不执行判决、裁定罪」）整串优先匹配，多案由顿号并列逐一校验；登记案由与字典关联案由不一致时提示
2. **利冲检索** — 对立方向命中须合伙人勾选「已人工复核」并填写结论（写入审批意见）
3. **OA 重复立案** — 同委托人+同对方+同案由的**在办/待处理**案件（status 1/3/4/5）直接阻断；历史「立案未通过」（status 2，常见于驳回后重报）与已结案/已撤销/已归档记录降级为人工复核提示，不误阻断（2026-07-10 修正）
4. **低收费审查** — 委托收费 < ¥5,000 必须有收费说明（OA ChargeMemo），否则阻断；收费说明中记载的金额与登记收费不一致（既非其中一笔也非分期合计）同样阻断
5. **风险代理收费** — 展示收费方案原文+标的额+分段上限计算明细（司发通〔2021〕87号），系统给出初步判断与建议，**不硬阻断**；须合伙人勾选「已审阅确认」后才能通过，复核意见写入审批意见。初步判断除禁止情形/缺方案/缺标的/登记超上限外，还比对**方案文本记载金额 vs 登记收费**（不一致报冲突）及**方案固定金额合计 vs 分段上限**

## 待办提醒

侧栏「案件审批」入口带角标：数字为当前立案待审数量；出现**未查看过的新待审案件**时角标变红并带红点脉冲。每 10 分钟自动轮询一次，进入审批页即视为已读；**审批通过/驳回后立即刷新角标**（`moshang:pending-refresh` 事件），不等下个轮询周期。

驳回时系统按预检结果（缺资料/利冲线索/重复立案/收费冲突等）**自动代拟驳回理由**，合伙人可直接采纳或修改后提交。

## 办案助手（2026-07-08 整合）

复用 `/Applications/办案工具集/办案材料助手.app` 的本机 CLI 能力，摩尚OA 只做界面与任务调度，处理逻辑不重复维护：

- **材料转换**：`droplet.sh --agent --engine <engine>`（PDF/图片 OCR 可选 MinerU本地/VisionOCR/legal-ocr在线；Office→MD；MD/TXT→Word；音视频→逐字稿），输出 `~/Desktop/VisionOCR_Output/`
- **微信录屏取证**：`wechat_evidence.py interval-pdf`（间隔抽帧+智能筛选→取证PDF+截图+复核资料），输出 `~/Desktop/录屏取证输出/`
- **证据整理**：逻辑移植自 GUI 脚本（`backend/app/assistant.py`），扫描输出目录生成案件材料汇总/时间线/materials_manifest/case_os_intake_package，行为与原 APP 一致
- 文件选择用 osascript 原生对话框；任务在后台线程跑，前端 2 秒轮询状态，失败可看日志尾部；点击输出文件在访达中显示
