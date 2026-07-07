import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Scale } from "lucide-react";
import { api } from "../api";
import type { User } from "../types";

const APIKEY_MEMO = "moshang_apikey_memo";

export function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const navigate = useNavigate();
  const [apikey, setApikey] = useState(localStorage.getItem(APIKEY_MEMO) ?? "");
  const [remember, setRemember] = useState(Boolean(localStorage.getItem(APIKEY_MEMO)));
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!apikey.trim()) {
      setError("请输入 API Key");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const user = await api.login(apikey.trim());
      if (remember) localStorage.setItem(APIKEY_MEMO, apikey.trim());
      else localStorage.removeItem(APIKEY_MEMO);
      onLogin(user);
      navigate("/cases", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center bg-zinc-50">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600 shadow-lg shadow-indigo-600/20">
            <Scale className="h-6 w-6 text-white" strokeWidth={2.2} />
          </div>
          <h1 className="text-lg font-semibold">摩尚OA</h1>
          <p className="text-xs text-zinc-400">浙江摩尚律师事务所 · 办公系统</p>
        </div>

        <form onSubmit={submit} className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm">
          <label className="mb-1.5 block text-xs font-medium text-zinc-500">Agent API Key</label>
          <div className="relative mb-1">
            <input
              type={show ? "text" : "password"}
              value={apikey}
              onChange={(e) => setApikey(e.target.value)}
              placeholder="请输入您的 API Key"
              autoFocus
              className="w-full rounded-lg border border-zinc-300 px-3 py-2 pr-9 text-sm outline-none transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20"
            />
            <button
              type="button"
              onClick={() => setShow(!show)}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600"
            >
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          <p className="mb-4 text-[11px] text-zinc-400">在 OA 网页端「律师后台」中获取您本人的 API Key</p>

          <label className="mb-5 flex items-center gap-2 text-xs text-zinc-500">
            <input
              type="checkbox"
              checked={remember}
              onChange={(e) => setRemember(e.target.checked)}
              className="h-3.5 w-3.5 rounded border-zinc-300 accent-indigo-600"
            />
            在本机记住 API Key
          </label>

          {error && (
            <div className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">{error}</div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white transition hover:bg-indigo-700 disabled:opacity-60"
          >
            {loading ? "登录中…" : "登 录"}
          </button>
        </form>

        <p className="mt-6 text-center text-[11px] text-zinc-300">© 2026 浙江摩尚律师事务所</p>
      </div>
    </div>
  );
}
