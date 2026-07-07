import { useCallback, useEffect, useState } from "react";
import { Columns3, RotateCw, Search, Table2, X } from "lucide-react";
import { api, savedUser } from "../api";
import type { CaseRow } from "../types";
import { EmptyState, money, Spinner, StatusBadge } from "../components/ui";

const STATUS_OPTIONS = [
  { value: "", label: "全部状态" },
  { value: "1", label: "立案待审" },
  { value: "2", label: "立案未通过" },
  { value: "3", label: "办理中" },
  { value: "4", label: "结案待审" },
  { value: "6", label: "已结案" },
];

const TYPE_OPTIONS = [
  { value: "", label: "全部类型" },
  { value: "1", label: "民事" },
  { value: "2", label: "刑事" },
];

const KANBAN_GROUPS = [
  { statuses: [1], title: "立案待审" },
  { statuses: [3], title: "办理中" },
  { statuses: [4], title: "结案待审" },
  { statuses: [6], title: "已结案" },
  { statuses: [2, 5], title: "未通过" },
];

export function CaseBoard() {
  const [rows, setRows] = useState<CaseRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [view, setView] = useState<"table" | "kanban">("table");
  const [scope, setScope] = useState<"firm" | "mine">("firm");
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("");
  const [baseType, setBaseType] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [selected, setSelected] = useState<CaseRow | null>(null);
  const pageSize = 50;
  const employeeId = savedUser()?.employeeId ?? null;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.cases({
        keyword: keyword || undefined,
        status: status || undefined,
        baseTypeId: baseType || undefined,
        employeeId: scope === "mine" && employeeId !== null ? employeeId : undefined,
        pageIndex,
        pageSize,
      });
      setRows(data.rows);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [keyword, status, baseType, scope, employeeId, pageIndex]);

  useEffect(() => {
    void load();
  }, [load]);

  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
        <div className="flex items-center gap-4">
          <div>
            <h2 className="text-base font-semibold">案件看板</h2>
            <p className="text-xs text-zinc-400">共 {total} 件</p>
          </div>
          {employeeId !== null && (
            <div className="flex rounded-lg bg-zinc-100 p-0.5 text-sm">
              {(
                [
                  { key: "firm", label: "所内案件" },
                  { key: "mine", label: "我的案件" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => {
                    setScope(tab.key);
                    setPageIndex(0);
                  }}
                  className={`rounded-md px-3 py-1 font-medium transition ${
                    scope === tab.key ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-500 hover:text-zinc-700"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
            <input
              value={keyword}
              onChange={(e) => {
                setKeyword(e.target.value);
                setPageIndex(0);
              }}
              placeholder="案号 / 当事人 / 案由 / 律师"
              className="w-64 rounded-lg border border-zinc-300 py-1.5 pl-8 pr-3 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            />
          </div>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPageIndex(0);
            }}
            className="rounded-lg border border-zinc-300 py-1.5 pl-2 pr-7 text-sm outline-none focus:border-indigo-500"
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            value={baseType}
            onChange={(e) => {
              setBaseType(e.target.value);
              setPageIndex(0);
            }}
            className="rounded-lg border border-zinc-300 py-1.5 pl-2 pr-7 text-sm outline-none focus:border-indigo-500"
          >
            {TYPE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <div className="flex rounded-lg border border-zinc-300 p-0.5">
            <button
              onClick={() => setView("table")}
              className={`rounded-md p-1.5 ${view === "table" ? "bg-zinc-100 text-zinc-900" : "text-zinc-400"}`}
              title="表格视图"
            >
              <Table2 className="h-4 w-4" />
            </button>
            <button
              onClick={() => setView("kanban")}
              className={`rounded-md p-1.5 ${view === "kanban" ? "bg-zinc-100 text-zinc-900" : "text-zinc-400"}`}
              title="看板视图"
            >
              <Columns3 className="h-4 w-4" />
            </button>
          </div>
          <button
            onClick={() => void load()}
            className="rounded-lg border border-zinc-300 p-2 text-zinc-500 hover:bg-zinc-50"
            title="刷新"
          >
            <RotateCw className="h-4 w-4" />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-6">
        {loading ? (
          <Spinner label="加载案件中…" />
        ) : error ? (
          <EmptyState title="加载失败" hint={error} />
        ) : rows.length === 0 ? (
          <EmptyState title="没有匹配的案件" hint="调整筛选条件试试" />
        ) : view === "table" ? (
          <TableView rows={rows} onSelect={setSelected} />
        ) : (
          <KanbanView rows={rows} onSelect={setSelected} />
        )}
      </div>

      {view === "table" && pageCount > 1 && (
        <footer className="flex items-center justify-end gap-3 border-t border-zinc-200 bg-white px-6 py-3 text-sm">
          <span className="text-zinc-400">
            第 {pageIndex + 1} / {pageCount} 页
          </span>
          <button
            disabled={pageIndex === 0}
            onClick={() => setPageIndex(pageIndex - 1)}
            className="rounded-lg border border-zinc-300 px-3 py-1 disabled:opacity-40"
          >
            上一页
          </button>
          <button
            disabled={pageIndex >= pageCount - 1}
            onClick={() => setPageIndex(pageIndex + 1)}
            className="rounded-lg border border-zinc-300 px-3 py-1 disabled:opacity-40"
          >
            下一页
          </button>
        </footer>
      )}

      {selected && <CaseDrawer row={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function TableView({ rows, onSelect }: { rows: CaseRow[]; onSelect: (row: CaseRow) => void }) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-200 bg-zinc-50 text-left text-xs text-zinc-500">
            <th className="px-4 py-2.5 font-medium">案号</th>
            <th className="px-4 py-2.5 font-medium">状态</th>
            <th className="px-4 py-2.5 font-medium">案由</th>
            <th className="px-4 py-2.5 font-medium">委托人</th>
            <th className="px-4 py-2.5 font-medium">对方</th>
            <th className="px-4 py-2.5 font-medium">经办律师</th>
            <th className="px-4 py-2.5 font-medium">受理日期</th>
            <th className="px-4 py-2.5 text-right font-medium">未收金额</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              onClick={() => onSelect(row)}
              className="cursor-pointer border-b border-zinc-100 last:border-0 hover:bg-indigo-50/40"
            >
              <td className="px-4 py-2.5 font-medium text-zinc-900">{row.no || row.preNo || "—"}</td>
              <td className="px-4 py-2.5">
                <StatusBadge status={row.status} name={row.statusName} />
              </td>
              <td className="max-w-44 truncate px-4 py-2.5 text-zinc-600">{row.causeAction || "—"}</td>
              <td className="max-w-36 truncate px-4 py-2.5 text-zinc-600">{row.wtrNames || row.dsrNames || "—"}</td>
              <td className="max-w-36 truncate px-4 py-2.5 text-zinc-600">{row.tosNames || "—"}</td>
              <td className="px-4 py-2.5 text-zinc-600">{row.empNames || "—"}</td>
              <td className="px-4 py-2.5 text-zinc-500">{(row.shouliDate || "").slice(0, 10) || "—"}</td>
              <td className={`px-4 py-2.5 text-right ${Number(row.weishou) > 0 ? "font-medium text-amber-600" : "text-zinc-400"}`}>
                {money(row.weishou)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KanbanView({ rows, onSelect }: { rows: CaseRow[]; onSelect: (row: CaseRow) => void }) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-2">
      {KANBAN_GROUPS.map((group) => {
        const items = rows.filter((r) => group.statuses.includes(r.status));
        return (
          <div key={group.title} className="w-72 shrink-0">
            <div className="mb-2 flex items-center gap-2 px-1">
              <span className="text-sm font-medium text-zinc-700">{group.title}</span>
              <span className="rounded-full bg-zinc-200 px-1.5 text-xs text-zinc-600">{items.length}</span>
            </div>
            <div className="space-y-2">
              {items.map((row) => (
                <button
                  key={row.id}
                  onClick={() => onSelect(row)}
                  className="w-full rounded-xl border border-zinc-200 bg-white p-3 text-left shadow-sm transition hover:border-indigo-300 hover:shadow"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-xs font-medium text-zinc-900">{row.no || row.preNo || `#${row.id}`}</span>
                    <span className="text-[11px] text-zinc-400">{row.baseTypeName}</span>
                  </div>
                  <div className="mb-1.5 truncate text-sm text-zinc-700">{row.causeAction || "（无案由）"}</div>
                  <div className="truncate text-xs text-zinc-500">
                    {row.wtrNames || row.dsrNames} ↔ {row.tosNames || "—"}
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-zinc-400">
                    <span>{row.empNames}</span>
                    {Number(row.weishou) > 0 && (
                      <span className="font-medium text-amber-600">未收 {money(row.weishou)}</span>
                    )}
                  </div>
                </button>
              ))}
              {items.length === 0 && (
                <div className="rounded-xl border border-dashed border-zinc-200 py-6 text-center text-xs text-zinc-300">
                  空
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CaseDrawer({ row, onClose }: { row: CaseRow; onClose: () => void }) {
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api
      .caseDetail(row.id)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [row.id]);

  const field = (label: string, value: unknown) => (
    <div className="flex justify-between gap-4 border-b border-zinc-100 py-2 text-sm last:border-0">
      <span className="shrink-0 text-zinc-400">{label}</span>
      <span className="text-right text-zinc-800">{String(value ?? "") || "—"}</span>
    </div>
  );

  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-zinc-900/30" onClick={onClose} />
      <div className="absolute right-0 top-0 flex h-full w-[420px] flex-col bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-4">
          <div>
            <div className="text-sm font-semibold">{row.no || row.preNo || `案件 #${row.id}`}</div>
            <div className="mt-0.5">
              <StatusBadge status={row.status} name={row.statusName} />
            </div>
          </div>
          <button onClick={onClose} className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-100">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-3">
          {field("案件类型", row.baseTypeName)}
          {field("案件分类", row.caseCategoryName)}
          {field("案由", row.causeAction)}
          {field("委托人", row.wtrNames || row.dsrNames)}
          {field("对方当事人", row.tosNames)}
          {field("经办律师", row.empNames)}
          {field("受理日期", (row.shouliDate || "").slice(0, 10))}
          {field("委托费用", money(row.chargeAmount))}
          {field("已收", money(row.yishou))}
          {field("未收", money(row.weishou))}
          {detail ? field("案情摘要", (detail as Record<string, unknown>).caseSummary) : null}
        </div>
      </div>
    </div>
  );
}
