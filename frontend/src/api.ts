import type {
  ApprovalReview,
  AssistantJob,
  AssistantOverview,
  CaseListResponse,
  CaseRow,
  PendingResponse,
  User,
} from "./types";

const SESSION_KEY = "moshang_session_id";
const USER_KEY = "moshang_user";
const APIKEY_MEMO = "moshang_apikey_memo";

export function savedUser(): User | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(USER_KEY);
}

export class ApiError extends Error {
  status: number;
  gateErrors: string[] | null;

  constructor(status: number, message: string, gateErrors: string[] | null = null) {
    super(message);
    this.status = status;
    this.gateErrors = gateErrors;
  }
}

// 后端会话是内存态，APP 重开后旧 session 必然失效；
// 若本机记住了 API Key，则在 401 时静默重登一次并重试原请求。
let reloginPromise: Promise<boolean> | null = null;

async function silentRelogin(): Promise<boolean> {
  const apikey = localStorage.getItem(APIKEY_MEMO);
  if (!apikey) return false;
  try {
    const resp = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apikey }),
    });
    if (!resp.ok) return false;
    const data = (await resp.json()) as { session_id: string; user: User };
    localStorage.setItem(SESSION_KEY, data.session_id);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    return true;
  } catch {
    return false;
  }
}

async function request<T>(path: string, init?: RequestInit, retried = false): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const sessionId = localStorage.getItem(SESSION_KEY);
  if (sessionId) headers["X-Session-Id"] = sessionId;

  const resp = await fetch(path, { ...init, headers });
  if (!resp.ok) {
    if (resp.status === 401 && !retried && path !== "/api/login" && path !== "/api/logout") {
      if (!reloginPromise) {
        reloginPromise = silentRelogin().finally(() => {
          reloginPromise = null;
        });
      }
      if (await reloginPromise) return request<T>(path, init, true);
      clearSession();
      if (!window.location.hash.startsWith("#/login")) {
        window.location.hash = "#/login";
        window.location.reload();
      }
    }
    let message = `请求失败（${resp.status}）`;
    let gateErrors: string[] | null = null;
    try {
      const body = await resp.json();
      const detail = body?.detail;
      if (typeof detail === "string") message = detail;
      else if (detail?.gate_errors) {
        gateErrors = detail.gate_errors as string[];
        message = "审批前合规检查未通过";
      }
    } catch {
      /* keep default message */
    }
    if (resp.status === 401) clearSession();
    throw new ApiError(resp.status, message, gateErrors);
  }
  return (await resp.json()) as T;
}

export const api = {
  async login(apikey: string): Promise<User> {
    const data = await request<{ session_id: string; user: User }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ apikey }),
    });
    localStorage.setItem(SESSION_KEY, data.session_id);
    localStorage.setItem(USER_KEY, JSON.stringify(data.user));
    return data.user;
  },

  async logout(): Promise<void> {
    try {
      await request("/api/logout", { method: "POST" });
    } finally {
      clearSession();
    }
  },

  cases(params: Record<string, string | number | undefined>): Promise<CaseListResponse> {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") query.set(key, String(value));
    }
    return request(`/api/cases?${query}`);
  },

  caseDetail(id: number): Promise<CaseRow & Record<string, unknown>> {
    return request(`/api/cases/${id}`);
  },

  pending(): Promise<PendingResponse> {
    return request("/api/approvals/pending");
  },

  approvalCheck(id: number): Promise<ApprovalReview> {
    return request(`/api/approvals/${id}/check`);
  },

  approve(
    id: number,
    body: {
      memo: string;
      conflict_reviewed: boolean;
      conflict_memo: string;
      risk_reviewed: boolean;
      risk_memo: string;
    },
  ): Promise<{ ok: boolean; case_no: string; new_status_name: string }> {
    return request(`/api/approvals/${id}/approve`, { method: "POST", body: JSON.stringify(body) });
  },

  reject(id: number, memo: string): Promise<{ ok: boolean; case_no: string; new_status_name: string }> {
    return request(`/api/approvals/${id}/reject`, { method: "POST", body: JSON.stringify({ memo }) });
  },

  // ---------------------------------------------------------- 办案助手
  assistantOverview(): Promise<AssistantOverview> {
    return request("/api/assistant/overview");
  },

  assistantPick(mode: "files" | "folder"): Promise<{ paths: string[] }> {
    return request("/api/assistant/pick", { method: "POST", body: JSON.stringify({ mode }) });
  },

  assistantConvert(paths: string[], engine: string): Promise<AssistantJob> {
    return request("/api/assistant/convert", { method: "POST", body: JSON.stringify({ paths, engine }) });
  },

  assistantWechat(body: {
    paths: string[];
    interval: number;
    smart_filter: boolean;
    preserve_head_sec: number;
  }): Promise<AssistantJob> {
    return request("/api/assistant/wechat", { method: "POST", body: JSON.stringify(body) });
  },

  assistantOrganize(source: "ocr" | "wechat" | "custom", dir?: string): Promise<AssistantJob> {
    return request("/api/assistant/organize", { method: "POST", body: JSON.stringify({ source, dir }) });
  },

  assistantJobs(): Promise<{ jobs: AssistantJob[] }> {
    return request("/api/assistant/jobs");
  },

  assistantReveal(path: string): Promise<{ ok: boolean }> {
    return request("/api/assistant/reveal", { method: "POST", body: JSON.stringify({ path }) });
  },
};
