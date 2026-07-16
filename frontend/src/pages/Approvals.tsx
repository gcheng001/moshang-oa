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

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [pending, automationStatus] = await Promise.all([api.pending(), api.automationStatus()]);
      setData(pending);
      setAutomation(automationStatus);
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

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
        <div>
          <h2 className="text-base font-semibold">案件审批</h2>
          <p className="text-xs text-zinc-400">
            立案待审 {data?.filing.length ?? "…"} 件（可在本页审批） · 结案待审 {data?.closing.length ?? "…"} 件（只读）
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
                      ? automation.mode === "shadow"
                        ? `观察期运行中：还剩约 ${Math.ceil(automation.shadow_remaining_seconds / 3600)} 小时，仅模拟不写入 OA。`
                        : `已开启：每 ${automation.poll_minutes} 分钟检查一次。`
                      : "关闭状态。开启后需保持登录；前三天只模拟，手动审批仍会真实写入 OA。"}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {automation?.enabled && (
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
              {automation?.events?.[0] && (
                <p className="mt-2 truncate text-xs text-indigo-700">
                  最近记录：{automation.events[0].case_no || "系统"} · {automation.events[0].message || automation.events[0].kind}
                </p>
              )}
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

            <section>
              <div className="mb-3 flex items-center gap-2">
                <h3 className="text-sm font-medium text-zinc-700">结案待审</h3>
                <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-500">
                  只读 · 结案审批请在 OA 网页端操作
                </span>
              </div>
              {data && data.closing.length > 0 ? (
                <div className="space-y-2">
                  {data.closing.map((row) => (
                    <PendingCard key={row.id} row={row} />
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-zinc-200 bg-white py-10 text-center text-sm text-zinc-400">
                  当前没有待审的结案申请
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
