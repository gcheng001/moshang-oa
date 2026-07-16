import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Briefcase, ClipboardCheck, LayoutGrid, LogOut, Scale } from "lucide-react";
import { api } from "../api";
import type { User } from "../types";

const NAV = [
  { to: "/cases", label: "案件列表", icon: LayoutGrid },
  { to: "/approvals", label: "案件审批", icon: ClipboardCheck, requiresApproval: true },
  { to: "/assistant", label: "办案助手", icon: Briefcase },
];

const SEEN_KEY = "moshang_seen_filing_ids";
const POLL_INTERVAL = 10 * 60 * 1000; // 10 分钟

function seenIds(): Set<number> {
  try {
    return new Set(JSON.parse(localStorage.getItem(SEEN_KEY) || "[]") as number[]);
  } catch {
    return new Set();
  }
}

export function Layout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();

  const [pendingCount, setPendingCount] = useState(0);
  const [hasNew, setHasNew] = useState(false);
  const idsRef = useRef<number[]>([]);
  const onApprovalsRef = useRef(false);
  onApprovalsRef.current = location.pathname.startsWith("/approvals");

  const markSeen = useCallback(() => {
    localStorage.setItem(SEEN_KEY, JSON.stringify(idsRef.current));
    setHasNew(false);
  }, []);

  const poll = useCallback(async () => {
    if (!user.canApprove) return;
    try {
      const data = await api.pending();
      const ids = data.filing.map((row) => row.id);
      idsRef.current = ids;
      setPendingCount(ids.length);
      if (onApprovalsRef.current) {
        markSeen();
      } else {
        const seen = seenIds();
        setHasNew(ids.some((id) => !seen.has(id)));
      }
    } catch {
      /* 会话失效等情况静默跳过，下个周期重试 */
    }
  }, [markSeen, user.canApprove]);

  useEffect(() => {
    void poll();
    const timer = setInterval(() => void poll(), POLL_INTERVAL);
    // 审批通过/驳回后由 ApprovalDetail 广播，立即刷新角标，不等下个轮询周期
    const onRefresh = () => void poll();
    window.addEventListener("moshang:pending-refresh", onRefresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("moshang:pending-refresh", onRefresh);
    };
  }, [poll]);

  // 进入审批页即视为已读，清除红点
  useEffect(() => {
    if (location.pathname.startsWith("/approvals") && idsRef.current.length > 0) markSeen();
  }, [location.pathname, markSeen]);

  const handleLogout = async () => {
    await api.logout().catch(() => undefined);
    onLogout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex h-full">
      <aside className="flex w-52 shrink-0 flex-col border-r border-zinc-200 bg-white">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
            <Scale className="h-4.5 w-4.5 text-white" strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-sm font-semibold leading-tight">办公助手</div>
            <div className="text-[11px] text-zinc-400">律师事务所</div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 pt-2">
          {NAV.filter((item) => !item.requiresApproval || user.canApprove).map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-indigo-50 text-indigo-700"
                    : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900"
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
              {to === "/approvals" && pendingCount > 0 && (
                <span className="relative ml-auto">
                  <span
                    className={`inline-flex min-w-[18px] items-center justify-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none ${
                      hasNew ? "bg-red-500 text-white" : "bg-zinc-200 text-zinc-600"
                    }`}
                  >
                    {pendingCount > 99 ? "99+" : pendingCount}
                  </span>
                  {hasNew && (
                    <>
                      <span className="absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full bg-red-500" />
                      <span className="absolute -right-0.5 -top-0.5 h-2 w-2 animate-ping rounded-full bg-red-400" />
                    </>
                  )}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-zinc-200 p-3">
          <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-zinc-200 text-xs font-semibold text-zinc-600">
              {(user.employeeName || user.userName || "?").slice(0, 1)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{user.employeeName || user.userName}</div>
              <div className="truncate text-[11px] text-zinc-400">{user.lawfirmName}</div>
            </div>
            <button
              onClick={handleLogout}
              title="退出登录"
              className="rounded-md p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
