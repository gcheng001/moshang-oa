import { useCallback, useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  FileText,
  FolderOpen,
  FolderSearch,
  Loader2,
  Video,
  XCircle,
} from "lucide-react";
import { api } from "../api";
import type { AssistantJob, AssistantOverview } from "../types";

const ENGINE_OPTIONS = [
  { value: "mineru", label: "MinerU（本地，版面/表格好）" },
  { value: "visionocr", label: "VisionOCR（Apple 本机，快速离线）" },
  { value: "legalocr", label: "legal-ocr（在线自动，法律后处理）" },
  { value: "legalocr-paddle", label: "PaddleOCR-VL（在线）" },
  { value: "legalocr-mineru", label: "MinerU（在线）" },
];

export function Assistant() {
  const [overview, setOverview] = useState<AssistantOverview | null>(null);
  const [jobs, setJobs] = useState<AssistantJob[]>([]);
  const [error, setError] = useState("");

  const [convertPaths, setConvertPaths] = useState<string[]>([]);
  const [engine, setEngine] = useState("mineru");
  const [videoPaths, setVideoPaths] = useState<string[]>([]);
  const [interval_, setInterval_] = useState("1");
  const [smartFilter, setSmartFilter] = useState(true);
  const [organizeSource, setOrganizeSource] = useState<"ocr" | "wechat" | "custom">("ocr");
  const [customDir, setCustomDir] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const timerRef = useRef<number | null>(null);

  const refreshJobs = useCallback(async () => {
    try {
      const data = await api.assistantJobs();
      setJobs(data.jobs);
      return data.jobs;
    } catch {
      return [];
    }
  }, []);

  useEffect(() => {
    api.assistantOverview().then(setOverview).catch((e) => setError(String(e?.message ?? e)));
    void refreshJobs();
  }, [refreshJobs]);

  // 有任务在跑时每2秒刷新一次
  useEffect(() => {
    const anyRunning = jobs.some((j) => j.status === "running");
    if (anyRunning && timerRef.current === null) {
      timerRef.current = window.setInterval(() => void refreshJobs(), 2000);
    }
    if (!anyRunning && timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [jobs, refreshJobs]);

  const pickFiles = async (setter: (paths: string[]) => void) => {
    setBusy("pick");
    try {
      const { paths } = await api.assistantPick("files");
      if (paths.length > 0) setter(paths);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const run = async (key: string, fn: () => Promise<AssistantJob>) => {
    setBusy(key);
    setError("");
    try {
      await fn();
      await refreshJobs();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="p-6">
      <header className="mb-5">
        <h2 className="text-base font-semibold">办案助手</h2>
        <p className="mt-0.5 text-xs text-zinc-400">
          材料转换 · 微信录屏取证 · 证据整理（全部在本机处理；OCR/转写结果须对照原件人工核实）
        </p>
      </header>

      {error && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          {error}
        </div>
      )}

      {overview && !overview.helper_app && (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          未找到办案材料助手（/Applications/办案工具集/办案材料助手.app），请先确认其存在。
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        {/* 材料转换 */}
        <section className="rounded-xl border border-zinc-200 bg-white p-5">
          <div className="mb-1 flex items-center gap-2">
            <FileText className="h-4.5 w-4.5 text-indigo-500" />
            <h3 className="text-sm font-semibold">材料转换</h3>
          </div>
          <p className="mb-3 text-xs leading-relaxed text-zinc-400">
            PDF/图片 → Markdown（OCR）；Word/Excel/PPT → Markdown；MD/TXT → Word；音视频 → 逐字稿
          </p>
          <PathList paths={convertPaths} onClear={() => setConvertPaths([])} />
          <button
            onClick={() => void pickFiles(setConvertPaths)}
            disabled={busy !== null}
            className="mb-3 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            选择文件…
          </button>
          <label className="mb-1 block text-xs text-zinc-500">PDF/图片 OCR 引擎</label>
          <select
            value={engine}
            onChange={(e) => setEngine(e.target.value)}
            className="mb-3 w-full rounded-lg border border-zinc-300 px-2.5 py-2 text-sm outline-none focus:border-indigo-500"
          >
            {ENGINE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <button
            onClick={() => void run("convert", () => api.assistantConvert(convertPaths, engine))}
            disabled={busy !== null || convertPaths.length === 0}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy === "convert" ? "提交中…" : "开始转换"}
          </button>
        </section>

        {/* 微信录屏取证 */}
        <section className="rounded-xl border border-zinc-200 bg-white p-5">
          <div className="mb-1 flex items-center gap-2">
            <Video className="h-4.5 w-4.5 text-indigo-500" />
            <h3 className="text-sm font-semibold">微信录屏取证</h3>
          </div>
          <p className="mb-3 text-xs leading-relaxed text-zinc-400">
            聊天录屏 MP4/MOV → 取证 PDF 初稿 + 截图 + 复核资料（全程本机处理）
          </p>
          <PathList paths={videoPaths} onClear={() => setVideoPaths([])} />
          <button
            onClick={() => void pickFiles(setVideoPaths)}
            disabled={busy !== null}
            className="mb-3 w-full rounded-lg border border-zinc-300 px-3 py-2 text-sm text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
          >
            选择录屏视频…
          </button>
          <div className="mb-3 flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-zinc-600">
              每
              <input
                value={interval_}
                onChange={(e) => setInterval_(e.target.value)}
                className="w-12 rounded-md border border-zinc-300 px-1.5 py-1 text-center text-xs outline-none focus:border-indigo-500"
              />
              秒留 1 张
            </label>
            <label className="flex items-center gap-1.5 text-xs text-zinc-600">
              <input
                type="checkbox"
                checked={smartFilter}
                onChange={(e) => setSmartFilter(e.target.checked)}
                className="h-3.5 w-3.5 accent-indigo-600"
              />
              智能筛选（挑清晰帧、去重复）
            </label>
          </div>
          <button
            onClick={() =>
              void run("wechat", () =>
                api.assistantWechat({
                  paths: videoPaths,
                  interval: Number(interval_) || 1,
                  smart_filter: smartFilter,
                  preserve_head_sec: 8,
                }),
              )
            }
            disabled={busy !== null || videoPaths.length === 0}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy === "wechat" ? "提交中…" : "开始取证"}
          </button>
        </section>

        {/* 证据整理 */}
        <section className="rounded-xl border border-zinc-200 bg-white p-5">
          <div className="mb-1 flex items-center gap-2">
            <FolderSearch className="h-4.5 w-4.5 text-indigo-500" />
            <h3 className="text-sm font-semibold">证据整理</h3>
          </div>
          <p className="mb-3 text-xs leading-relaxed text-zinc-400">
            重新扫描输出目录，生成案件材料汇总、时间线初稿和案件OS输入包
          </p>
          <div className="mb-3 space-y-1.5 text-xs text-zinc-600">
            <label className="flex items-center gap-2">
              <input
                type="radio"
                checked={organizeSource === "ocr"}
                onChange={() => setOrganizeSource("ocr")}
                className="accent-indigo-600"
              />
              材料转换输出目录（VisionOCR_Output）
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                checked={organizeSource === "wechat"}
                onChange={() => setOrganizeSource("wechat")}
                className="accent-indigo-600"
              />
              最近一次录屏取证目录
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                checked={organizeSource === "custom"}
                onChange={() => setOrganizeSource("custom")}
                className="accent-indigo-600"
              />
              自定义目录
            </label>
            {organizeSource === "custom" && (
              <div className="flex items-center gap-2 pl-5">
                <span className="min-w-0 flex-1 truncate rounded-md bg-zinc-50 px-2 py-1 text-[11px] text-zinc-500">
                  {customDir || "未选择"}
                </span>
                <button
                  onClick={async () => {
                    const { paths } = await api.assistantPick("folder").catch(() => ({ paths: [] }));
                    if (paths[0]) setCustomDir(paths[0]);
                  }}
                  className="shrink-0 rounded-md border border-zinc-300 px-2 py-1 text-[11px] text-zinc-600 hover:bg-zinc-50"
                >
                  选择…
                </button>
              </div>
            )}
          </div>
          <button
            onClick={() => void run("organize", () => api.assistantOrganize(organizeSource, customDir))}
            disabled={busy !== null || (organizeSource === "custom" && !customDir)}
            className="w-full rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy === "organize" ? "提交中…" : "开始整理"}
          </button>
        </section>
      </div>

      {/* 任务列表 */}
      <section className="mt-5 rounded-xl border border-zinc-200 bg-white">
        <div className="flex items-center justify-between border-b border-zinc-100 px-5 py-3">
          <h3 className="text-sm font-semibold">任务</h3>
          {overview && (
            <button
              onClick={() => void api.assistantReveal(overview.output_dir)}
              className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-600"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              打开输出文件夹
            </button>
          )}
        </div>
        {jobs.length === 0 ? (
          <p className="px-5 py-6 text-center text-xs text-zinc-400">
            暂无任务。选择文件后点击开始，任务会在这里显示进度。
          </p>
        ) : (
          <ul className="divide-y divide-zinc-100">
            {jobs.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function PathList({ paths, onClear }: { paths: string[]; onClear: () => void }) {
  if (paths.length === 0) {
    return <div className="mb-2 rounded-lg bg-zinc-50 px-3 py-2 text-xs text-zinc-400">未选择文件</div>;
  }
  return (
    <div className="mb-2 max-h-24 overflow-y-auto rounded-lg bg-zinc-50 px-3 py-2">
      {paths.map((p) => (
        <div key={p} className="truncate text-xs text-zinc-600" title={p}>
          {p.split("/").pop()}
        </div>
      ))}
      <button onClick={onClear} className="mt-1 text-[11px] text-zinc-400 underline hover:text-zinc-600">
        清空（共 {paths.length} 个）
      </button>
    </div>
  );
}

function JobRow({ job }: { job: AssistantJob }) {
  const [showLog, setShowLog] = useState(false);
  const icon =
    job.status === "running" ? (
      <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
    ) : job.status === "done" ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    ) : (
      <XCircle className="h-4 w-4 text-red-500" />
    );

  return (
    <li className="px-5 py-3">
      <div className="flex items-center gap-2.5">
        {icon}
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-medium text-zinc-800">{job.title}</span>
            <span className="text-[11px] text-zinc-400">{job.created_at}</span>
          </div>
          <div className="text-xs text-zinc-500">
            {job.status === "failed" ? job.error : job.detail}
          </div>
        </div>
        {job.log_tail && (
          <button
            onClick={() => setShowLog((v) => !v)}
            className="shrink-0 text-[11px] text-zinc-400 underline hover:text-zinc-600"
          >
            {showLog ? "收起日志" : "日志"}
          </button>
        )}
      </div>
      {job.outputs.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1.5 pl-6.5">
          {job.outputs.map((o) => (
            <button
              key={o}
              onClick={() => void api.assistantReveal(o)}
              title={o}
              className="max-w-64 truncate rounded-md bg-indigo-50 px-2 py-0.5 text-[11px] text-indigo-700 hover:bg-indigo-100"
            >
              {o.split("/").pop()}
            </button>
          ))}
        </div>
      )}
      {showLog && (
        <pre className="mt-2 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg bg-zinc-900 p-3 text-[11px] leading-relaxed text-zinc-200">
          {job.log_tail}
        </pre>
      )}
    </li>
  );
}
