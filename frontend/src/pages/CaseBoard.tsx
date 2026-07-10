import { useCallback, useEffect, useRef, useState } from "react";
import { Columns3, FileDown, FolderOpen, RotateCw, Search, Table2, X } from "lucide-react";
import { api, savedUser } from "../api";
import type { CaseRow, DocDownloadResponse, DocTemplatesResponse } from "../types";
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
  const [keyword, setKeyword] = useState(""); // 输入框即时值
  const [query, setQuery] = useState(""); // 防抖后的实际检索词
  const [status, setStatus] = useState("");
  const [baseType, setBaseType] = useState("");
  const [pageIndex, setPageIndex] = useState(0);
  const [selected, setSelected] = useState<CaseRow | null>(null);
  const pageSize = 50;
  const employeeId = savedUser()?.employeeId ?? null;
  // 中文输入法组词中不触发检索（composing 用 state 参与依赖：组词结束即使文本未变也要重新触发防抖）；
  // 请求带序号，过期响应直接丢弃（防止先发后至覆盖新结果）
  const [composing, setComposing] = useState(false);
  const seqRef = useRef(0);

  useEffect(() => {
    if (composing) return;
    const timer = setTimeout(() => {
      const value = keyword.trim();
      if (value !== query) {
        setQuery(value);
        setPageIndex(0);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [keyword, composing, query]);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setError("");
    try {
      const data = await api.cases({
        keyword: query || undefined,
        status: status || undefined,
        baseTypeId: baseType || undefined,
        employeeId: scope === "mine" && employeeId !== null ? employeeId : undefined,
        pageIndex,
        pageSize,
      });
      if (seq !== seqRef.current) return;
      setRows(data.rows);
      setTotal(data.total);
    } catch (err) {
      if (seq !== seqRef.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, [query, status, baseType, scope, employeeId, pageIndex]);

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
              onChange={(e) => setKeyword(e.target.value)}
              onCompositionStart={() => setComposing(true)}
              onCompositionEnd={(e) => {
                setComposing(false);
                setKeyword(e.currentTarget.value);
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
  // 兜底列：草稿/撤销系列/已归档等未在固定分组中的状态，避免案件在看板视图静默消失
  const groupedStatuses = new Set(KANBAN_GROUPS.flatMap((g) => g.statuses));
  const leftoverStatuses = [...new Set(rows.map((r) => r.status).filter((s) => !groupedStatuses.has(s)))];
  const groups =
    leftoverStatuses.length > 0
      ? [...KANBAN_GROUPS, { statuses: leftoverStatuses, title: "其他状态" }]
      : KANBAN_GROUPS;
  return (
    <div className="flex gap-4 overflow-x-auto pb-2">
      {groups.map((group) => {
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
          <DocDownloadSection lawcaseId={row.id} />
        </div>
      </div>
    </div>
  );
}

function DocDownloadSection({ lawcaseId }: { lawcaseId: number }) {
  const [expanded, setExpanded] = useState(false);
  const [meta, setMeta] = useState<DocTemplatesResponse | null>(null);
  const [loadError, setLoadError] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [downloading, setDownloading] = useState(false);
  const [result, setResult] = useState<DocDownloadResponse | null>(null);
  const [downloadError, setDownloadError] = useState("");

  const openSection = async () => {
    setExpanded(true);
    if (meta) return;
    setLoadError("");
    try {
      setMeta(await api.caseDocTemplates(lawcaseId));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : String(err));
    }
  };

  const toggle = (name: string) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const download = async () => {
    setDownloading(true);
    setDownloadError("");
    setResult(null);
    try {
      setResult(await api.caseDocDownload(lawcaseId, [...checked]));
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : String(err));
    } finally {
      setDownloading(false);
    }
  };

  const hasCorporateClient =
    (meta?.principal_legal_persons.length ?? 0) > 0 || (meta?.principal_orgs.length ?? 0) > 0;

  return (
    <div className="mt-4 border-t border-zinc-200 pt-4">
      {!expanded ? (
        <button
          onClick={() => void openSection()}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-100"
        >
          <FileDown className="h-4 w-4" />
          文书下载
        </button>
      ) : (
        <div>
          <div className="mb-2 flex items-center gap-2">
            <FileDown className="h-4 w-4 text-indigo-600" />
            <h4 className="text-sm font-semibold text-zinc-800">文书下载</h4>
          </div>

          {loadError ? (
            <p className="rounded-lg bg-red-50 p-3 text-xs text-red-600">加载模板失败：{loadError}</p>
          ) : !meta ? (
            <Spinner label="加载本案可用文书模板…" />
          ) : (
            <>
              {hasCorporateClient && (
                <p className="mb-2 rounded-lg bg-amber-50 p-2.5 text-[11px] leading-relaxed text-amber-800">
                  委托人含{meta.principal_legal_persons.length > 0 ? "法人" : ""}
                  {meta.principal_legal_persons.length > 0 && meta.principal_orgs.length > 0 ? "、" : ""}
                  {meta.principal_orgs.length > 0 ? "非法人组织" : ""}（
                  {[...meta.principal_legal_persons, ...meta.principal_orgs].join("、")}
                  ）。下载委托类文书时将自动附带对应身份证明文书。
                </p>
              )}
              <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-zinc-200 p-2">
                {meta.templates.length === 0 ? (
                  <p className="py-3 text-center text-xs text-zinc-400">本案暂无可用文书模板</p>
                ) : (
                  meta.templates.map((t) => (
                    <label
                      key={t.name}
                      className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
                    >
                      <input
                        type="checkbox"
                        checked={checked.has(t.name)}
                        onChange={() => toggle(t.name)}
                        className="h-3.5 w-3.5 accent-indigo-600"
                      />
                      <span className="truncate">{t.name}</span>
                    </label>
                  ))
                )}
              </div>
              <button
                disabled={checked.size === 0 || downloading}
                onClick={() => void download()}
                className="mt-2 w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {downloading ? "正在从 OA 导出下载…" : `下载所选文书（${checked.size}）`}
              </button>

              {downloadError && (
                <p className="mt-2 rounded-lg bg-red-50 p-2.5 text-xs text-red-600">下载失败：{downloadError}</p>
              )}

              {result && (
                <div className="mt-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
                  <div className="mb-1.5 flex items-center justify-between">
                    <span className="text-xs font-medium text-emerald-800">
                      已保存 {result.saved.length} 份文书
                    </span>
                    <button
                      onClick={() => void api.assistantReveal(result.dir).catch(() => undefined)}
                      className="flex items-center gap-1 text-xs text-emerald-700 underline-offset-2 hover:underline"
                    >
                      <FolderOpen className="h-3.5 w-3.5" />
                      打开所在文件夹
                    </button>
                  </div>
                  <ul className="space-y-0.5 text-[11px] text-emerald-700">
                    {result.saved.map((s) => (
                      <li key={s.path}>
                        {s.template}
                        {s.auto_added && <span className="ml-1 text-amber-600">（自动附带）</span>}
                        {!s.valid_docx && <span className="ml-1 text-red-600">（文件校验异常，请打开确认）</span>}
                        <span className="ml-1 text-emerald-500">{(s.size / 1024).toFixed(0)} KB</span>
                      </li>
                    ))}
                  </ul>
                  {result.notes.length > 0 && (
                    <ul className="mt-1.5 space-y-0.5 text-[11px] text-amber-700">
                      {result.notes.map((n) => (
                        <li key={n}>· {n}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
