import type { ReactNode } from "react";
import { Loader2 } from "lucide-react";

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-zinc-400">
      <Loader2 className="h-5 w-5 animate-spin" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}

const STATUS_STYLES: Record<number, string> = {
  0: "bg-zinc-100 text-zinc-600",
  1: "bg-amber-50 text-amber-700 ring-amber-200",
  2: "bg-red-50 text-red-700 ring-red-200",
  3: "bg-blue-50 text-blue-700 ring-blue-200",
  4: "bg-violet-50 text-violet-700 ring-violet-200",
  5: "bg-red-50 text-red-700 ring-red-200",
  6: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  99: "bg-zinc-100 text-zinc-500",
};

export function StatusBadge({ status, name }: { status: number; name: string }) {
  const style = STATUS_STYLES[status] ?? "bg-zinc-100 text-zinc-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-transparent ${style}`}>
      {name}
    </span>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <p className="text-sm font-medium text-zinc-500">{title}</p>
      {hint && <p className="mt-1 text-xs text-zinc-400">{hint}</p>}
    </div>
  );
}

export function Dialog({
  open,
  title,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-zinc-900/40" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <h3 className="mb-4 text-base font-semibold text-zinc-900">{title}</h3>
        {children}
      </div>
    </div>
  );
}

export function money(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `¥${Number(value).toLocaleString("zh-CN")}`;
}
