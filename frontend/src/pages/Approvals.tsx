import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, RotateCw } from "lucide-react";
import { api } from "../api";
import type { AutomationStatus, CaseRow, PendingResponse } from "../types";
import { EmptyState, money, Spinner } from "../components/ui";

export function Approvals() {
  const [data, setData] = useState<PendingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [automation, setAutomation] = useState<AutomationStatus | null>(null);
  const [automationBusy, setAutomationBusy] = useState(false);
  const [feishuConfigured, setFeishuConfigured] = useState(false);
  const [feishuWebhook, setFeishuWebhook] = useState("");
  const [transferCode, setTransferCode] = useState("");
  const [importCode, setImportCode] = useState("");
  const [importBundle, setImportBundle] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [pending, automationStatus, notificationStatus] = await Promise.all([
        api.pending(), api.automationStatus(), api.notificationStatus(),
      ]);
      setData(pending);
      setAutomation(automationStatus);
      setFeishuConfigured(notificationStatus.configured);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const updateAutomation = async (enabled: boolean) => {
    setAutomationBusy(true);
    setError("");
    try {
      setAutomation(await api.automationSet(enabled));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAutomationBusy(false);
    }
  };

  const checkNow = async () => {
    setAutomationBusy(true);
    setError("");
    try {
      await api.automationCheckNow();
      setAutomation(await api.automationStatus());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAutomationBusy(false);
    }
  };

  const exportCredentials = async () => {
    setAutomationBusy(true);
    try {
      const result = await api.credentialsExport();
      const url = URL.createObjectURL(new Blob([result.bundle], { type: "text/plain" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setTransferCode(result.code);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAutomationBusy(false);
    }
  };

  const importCredentials = async () => {
    setAutomationBusy(true);
    try {
      await api.credentialsImport(importBundle.trim(), importCode.trim());
      setError("");
      setImportBundle("");
      setImportCode("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAutomationBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
        <div>
          <h2 className="text-base font-semibold">案件审批</h2>
          <p className="text-xs text-zinc-400">
            立案待审 {data?.filing.length ?? "…"} 件 · 仅处理立案审批
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="rounded-lg border border-zinc-300 p-2 text-zinc-500 hover:bg-zinc-50"
          title="刷新"
        >
          <RotateCw className="h-4 w-4" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <Spinner label="加载待审清单…" />
        ) : error ? (
          <EmptyState title="加载失败" hint={error} />
        ) : (
          <div className="space-y-8">
            <section className="rounded-xl border border-indigo-100 bg-indigo-50/50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-indigo-950">自动审批</h3>
                  <p className="mt-1 text-xs text-indigo-700">
                    {automation?.enabled
                      ? automation.paused
                        ? "已紧急暂停：后台仍在运行，但不会写入 OA。"
                        : `已开启：每 ${automation.poll_minutes} 分钟检查，首次发现后等待 ${automation.grace_seconds / 60} 分钟复读；业务异常自动驳回并写明全部理由。`
                      : "关闭状态。开启后直接执行自动审批，不设置观察期。"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {automation?.enabled && (
                    <button
                      disabled={automationBusy}
                      onClick={() => void api.automationPause(!automation.paused).then(setAutomation).catch((err) => setError(String(err)))}
                      className={`rounded-lg border px-3 py-2 text-xs font-medium disabled:opacity-50 ${automation.paused ? "border-emerald-200 bg-white text-emerald-700" : "border-red-200 bg-white text-red-700"}`}
                    >
                      {automation.paused ? "恢复审批" : "紧急暂停"}
                    </button>
                  )}
                  {automation?.enabled && !automation.paused && (
                    <button
                      disabled={automationBusy}
                      onClick={() => void checkNow()}
                      className="rounded-lg border border-indigo-200 bg-white px-3 py-2 text-xs font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                    >
                      立即检查
                    </button>
                  )}
                  <button
                    disabled={automationBusy}
                    onClick={() => void updateAutomation(!automation?.enabled)}
                    className={`rounded-lg px-3 py-2 text-xs font-medium text-white disabled:opacity-50 ${automation?.enabled ? "bg-zinc-600 hover:bg-zinc-700" : "bg-indigo-600 hover:bg-indigo-700"}`}
                  >
                    {automation?.enabled ? "关闭自动审批" : "开启自动审批"}
                  </button>
                </div>
              </div>
              {automation?.last_error && <p className="mt-2 text-xs text-red-600">最近检查失败：{automation.last_error}</p>}
              {automation && (
                <p className="mt-2 text-xs text-indigo-700">
                  当前设备：{automation.device_name}（{automation.platform}） · 规则 {automation.rule_version}
                  {automation.consecutive_failures > 0 ? ` · 连续技术异常 ${automation.consecutive_failures} 轮` : ""}
                </p>
              )}
              {automation?.events?.[0] && (
                <p className="mt-2 truncate text-xs text-indigo-700">
                  最近记录：{automation.events[0].case_no || "系统"} · {automation.events[0].message || automation.events[0].kind}
                </p>
              )}
            </section>

            <section className="rounded-xl border border-zinc-200 bg-white p-4">
              <h3 className="text-sm font-semibold text-zinc-800">飞书通知与电脑迁移</h3>
              <p className="mt-1 text-xs text-zinc-500">飞书机器人为可选项，未配置不影响审批。OA 登录凭据与飞书密钥可加密迁移到 Windows。</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <input
                  value={feishuWebhook}
                  onChange={(event) => setFeishuWebhook(event.target.value)}
                  placeholder={feishuConfigured ? "已配置；输入新地址可替换，留空保存可清除" : "飞书机器人 Webhook（可选）"}
                  className="min-w-[320px] flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-xs"
                />
                <button
                  disabled={automationBusy}
                  onClick={() => void api.notificationSet(feishuWebhook).then((result) => { setFeishuConfigured(result.configured); setFeishuWebhook(""); }).catch((err) => setError(String(err)))}
                  className="rounded-lg bg-zinc-800 px-3 py-2 text-xs font-medium text-white"
                >保存并测试</button>
                <button disabled={automationBusy} onClick={() => void exportCredentials()} className="rounded-lg border border-zinc-300 px-3 py-2 text-xs font-medium">导出加密迁移文件</button>
              </div>
              {transferCode && <p className="mt-2 text-xs font-medium text-amber-700">一次性迁移码：{transferCode}（请与迁移文件分开发送）</p>}
              <div className="mt-3 flex flex-wrap gap-2 border-t border-zinc-100 pt-3">
                <input type="file" accept=".oacred,text/plain" onChange={(event) => { const file = event.target.files?.[0]; if (file) void file.text().then(setImportBundle); }} className="text-xs" />
                <input value={importCode} onChange={(event) => setImportCode(event.target.value)} placeholder="输入一次性迁移码" className="rounded-lg border border-zinc-300 px-3 py-2 text-xs" />
                <button disabled={!importBundle || !importCode || automationBusy} onClick={() => void importCredentials()} className="rounded-lg border border-indigo-200 px-3 py-2 text-xs font-medium text-indigo-700 disabled:opacity-40">导入到本机系统凭据库</button>
              </div>
            </section>
            <section>
              <h3 className="mb-3 text-sm font-medium text-zinc-700">立案待审</h3>
              {data && data.filing.length > 0 ? (
                <div className="space-y-2">
                  {data.filing.map((row) => (
                    <PendingCard key={row.id} row={row} actionable />
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-zinc-200 bg-white py-10 text-center text-sm text-zinc-400">
                  当前没有待审的立案申请
                </div>
              )}
            </section>

          </div>
        )}
      </div>
    </div>
  );
}

function PendingCard({ row, actionable = false }: { row: CaseRow; actionable?: boolean }) {
  const navigate = useNavigate();
  return (
    <div
      onClick={actionable ? () => navigate(`/approvals/${row.id}`) : undefined}
      className={`flex items-center gap-4 rounded-xl border border-zinc-200 bg-white px-5 py-4 shadow-sm ${
        actionable ? "cursor-pointer transition hover:border-indigo-300 hover:shadow" : "opacity-80"
      }`}
    >
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-sm font-semibold text-zinc-900">{row.preNo || row.no || `#${row.id}`}</span>
          <span className="text-xs text-zinc-400">{row.baseTypeName}</span>
        </div>
        <div className="truncate text-sm text-zinc-600">
          {row.wtrNames || row.dsrNames || "—"}
          {row.tosNames && (
            <>
              {" "}
              <span className="text-zinc-300">{row.baseTypeName?.includes("刑事") ? "·" : "诉"}</span>{" "}
              {row.tosNames}
            </>
          )}
          <span className="mx-2 text-zinc-300">·</span>
          {row.causeAction || row.caseHeadName || "（无案由）"}
        </div>
        <div className="mt-1 text-xs text-zinc-400">
          经办：{row.empNames || "—"}
          <span className="mx-2">·</span>
          委托费用 {money(row.chargeAmount)}
          <span className="mx-2">·</span>
          {(row.createTime || "").slice(0, 10)} 提交
        </div>
      </div>
      {actionable && (
        <div className="flex items-center gap-1 text-sm font-medium text-indigo-600">
          开始审查
          <ChevronRight className="h-4 w-4" />
        </div>
      )}
    </div>
  );
}
