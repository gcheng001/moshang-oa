import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronRight, RotateCw } from "lucide-react";
import { api } from "../api";
import type { CaseRow, PendingResponse } from "../types";
import { EmptyState, money, Spinner } from "../components/ui";

export function Approvals() {
  const [data, setData] = useState<PendingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api.pending());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
        <div>
          <h2 className="text-base font-semibold">立案审批</h2>
          <p className="text-xs text-zinc-400">
            立案待审 {data?.filing.length ?? "…"} 件 · 结案待审 {data?.closing.length ?? "…"} 件
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
          {row.wtrNames || row.dsrNames || "—"} <span className="text-zinc-300">诉</span> {row.tosNames || "—"}
          <span className="mx-2 text-zinc-300">·</span>
          {row.causeAction || "（无案由）"}
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
