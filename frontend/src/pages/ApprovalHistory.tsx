import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bell,
  CheckCircle2,
  Loader2,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { api, ApiError } from "../api";
import type { ApprovalEvent } from "../types";
import { Dialog, EmptyState, Spinner } from "../components/ui";

// 可反审的决策类事件：自动/人工的通过、驳回。反审后案件回到“立案待审”。
const REVERSIBLE = new Set(["auto_approve", "auto_reject", "manual_approve", "manual_reject"]);

type Meta = { label: string; tone: string; group: "decisions" | "system"; Icon: typeof Bell };

const KIND_META: Record<string, Meta> = {
  auto_approve: { label: "自动通过", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200", group: "decisions", Icon: CheckCircle2 },
  auto_reject: { label: "自动驳回", tone: "bg-red-50 text-red-700 ring-red-200", group: "decisions", Icon: XCircle },
  manual_approve: { label: "人工通过", tone: "bg-blue-50 text-blue-700 ring-blue-200", group: "decisions", Icon: CheckCircle2 },
  manual_reject: { label: "人工驳回", tone: "bg-red-50 text-red-700 ring-red-200", group: "decisions", Icon: XCircle },
  un_approve: { label: "反审撤回", tone: "bg-amber-50 text-amber-700 ring-amber-200", group: "decisions", Icon: RotateCcw },
  candidate: { label: "待处理", tone: "bg-zinc-100 text-zinc-600", group: "system", Icon: Bell },
  shadow_candidate: { label: "观察期", tone: "bg-zinc-100 text-zinc-500", group: "system", Icon: Bell },
  automation_enabled: { label: "开启值守", tone: "bg-zinc-100 text-zinc-600", group: "system", Icon: ShieldCheck },
  automation_disabled: { label: "关闭值守", tone: "bg-zinc-100 text-zinc-600", group: "system", Icon: ShieldCheck },
  automation_stopped: { label: "值守中断", tone: "bg-zinc-100 text-zinc-500", group: "system", Icon: Bell },
  status_changed: { label: "状态已变", tone: "bg-zinc-100 text-zinc-500", group: "system", Icon: Bell },
  review_changed: { label: "资料变化", tone: "bg-zinc-100 text-zinc-500", group: "system", Icon: Bell },
  action_failed: { label: "写入失败", tone: "bg-red-50 text-red-700 ring-red-200", group: "system", Icon: XCircle },
  check_failed: { label: "检查异常", tone: "bg-red-50 text-red-700 ring-red-200", group: "system", Icon: XCircle },
};

function metaOf(kind: string): Meta {
  return KIND_META[kind] ?? { label: kind, tone: "bg-zinc-100 text-zinc-600", group: "system", Icon: Bell };
}

function fmtTime(at?: string): string {
  if (!at) return "";
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at;
  return d.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

type Filter = "all" | "decisions" | "system";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "decisions", label: "审批决策" },
  { key: "system", label: "值守过程" },
];

export function ApprovalHistory() {
  const [events, setEvents] = useState<ApprovalEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState<string | null>(null);
  const [target, setTarget] = useState<ApprovalEvent | null>(null);
  const [working, setWorking] = useState(false);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    try {
      const { events: list } = await api.approvalHistory();
      setEvents(list);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "加载审批记录失败");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = useMemo(() => {
    let autoApprove = 0;
    let autoReject = 0;
    let manual = 0;
    let unapprove = 0;
    for (const e of events) {
      if (e.kind === "auto_approve") autoApprove += 1;
      else if (e.kind === "auto_reject") autoReject += 1;
      else if (e.kind === "manual_approve" || e.kind === "manual_reject") manual += 1;
      else if (e.kind === "un_approve") unapprove += 1;
    }
    return { autoApprove, autoReject, manual, unapprove };
  }, [events]);

  // 事件最新在前（index 0 最新）。某决策若在其之后（更新）被反审，则标记为已撤回。
  const rows = useMemo(() => {
    return events.map((ev, i) => {
      const reversible = REVERSIBLE.has(ev.kind) && ev.case_id != null;
      let reversed = false;
      if (reversible) {
        for (let j = 0; j < i; j++) {
          const e2 = events[j];
          if (e2.kind === "un_approve" && e2.case_id === ev.case_id) {
            reversed = true;
            break;
          }
        }
      }
      return { ev, reversible: reversible && !reversed, reversed };
    });
  }, [events]);

  const visible = useMemo(() => {
    if (filter === "all") return rows;
    return rows.filter((r) => metaOf(r.ev.kind).group === filter);
  }, [rows, filter]);

  async function doUnapprove() {
    if (!target?.case_id) return;
    setWorking(true);
    try {
      await api.unapprove(target.case_id);
      const { events: list } = await api.approvalHistory();
      setEvents(list);
      setTarget(null);
      setError(null);
      // 反审后案件回到待审，刷新左侧角标
      window.dispatchEvent(new Event("moshang:pending-refresh"));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "反审失败");
    } finally {
      setWorking(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <header className="mb-5 flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-zinc-900">审批记录</h1>
          <p className="mt-1 text-sm text-zinc-500">查看自动与人工审批的全部痕迹，可对已落地的立案决策进行反审。</p>
        </div>
        <button
          onClick={() => void load(true)}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-600 shadow-sm transition-colors hover:bg-zinc-50 disabled:opacity-50"
        >
          {refreshing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          刷新
        </button>
      </header>

      <div className="mb-5 grid grid-cols-4 gap-3">
        <StatCard label="自动通过" value={stats.autoApprove} tone="text-emerald-600" />
        <StatCard label="自动驳回" value={stats.autoReject} tone="text-red-600" />
        <StatCard label="人工处理" value={stats.manual} tone="text-blue-600" />
        <StatCard label="反审撤回" value={stats.unapprove} tone="text-amber-600" />
      </div>

      <div className="mb-4 flex gap-1 rounded-lg bg-zinc-100 p-1">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f.key ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-500 hover:text-zinc-700"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}

      {loading ? (
        <Spinner label="正在加载审批记录…" />
      ) : visible.length === 0 ? (
        <EmptyState title="暂无记录" hint="自动或人工审批后，这里会出现可追溯的事件。" />
      ) : (
        <ul className="space-y-2">
          {visible.map(({ ev, reversible, reversed }) => {
            const meta = metaOf(ev.kind);
            const Icon = meta.Icon;
            return (
              <li
                key={`${ev.at}-${ev.case_id ?? ev.kind}-${ev.message ?? ""}`}
                className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white p-3"
              >
                <div className="mt-0.5 shrink-0">
                  <Icon className="h-4 w-4 text-zinc-400" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-transparent ${meta.tone}`}
                    >
                      {meta.label}
                    </span>
                    {ev.case_no && (
                      <span className="text-sm font-medium text-zinc-700">{ev.case_no}</span>
                    )}
                    {reversed && (
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-400">已反审</span>
                    )}
                    <span className="ml-auto text-xs text-zinc-400">{fmtTime(ev.at)}</span>
                  </div>
                  {(ev.message || (ev.reasons && ev.reasons.length > 0)) && (
                    <div className="mt-1 space-y-0.5 text-sm text-zinc-500">
                      {ev.message && <p>{ev.message}</p>}
                      {ev.reasons && ev.reasons.length > 0 && (
                        <p className="text-xs text-zinc-400">依据：{ev.reasons.join("；")}</p>
                      )}
                    </div>
                  )}
                </div>
                {reversible && (
                  <button
                    onClick={() => setTarget(ev)}
                    className="inline-flex shrink-0 items-center gap-1 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-100"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    反审
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <Dialog
        open={!!target}
        title="确认反审该立案申请？"
        onClose={() => !working && setTarget(null)}
      >
        <p className="text-sm text-zinc-600">
          案件 <span className="font-medium text-zinc-900">{target?.case_no}</span> 将由当前状态退回
          <span className="font-medium text-zinc-900">“立案待审”</span>，左侧待审角标会增加，需要重新审批。
        </p>
        <p className="mt-2 text-xs text-zinc-400">
          说明：若案件已进入后续阶段（如结案），OA 不允许反审，届时会提示具体原因。
        </p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            onClick={() => setTarget(null)}
            disabled={working}
            className="rounded-lg border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={() => void doUnapprove()}
            disabled={working}
            className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
            确认反审
          </button>
        </div>
      </Dialog>
    </div>
  );
}

function StatCard({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-3">
      <div className={`text-2xl font-semibold ${tone}`}>{value}</div>
      <div className="mt-0.5 text-xs text-zinc-500">{label}</div>
    </div>
  );
}
