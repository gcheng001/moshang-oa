import type {
  ApprovalReview,
  AutomationStatus,
  AssistantJob,
  AssistantOverview,
  CaseListResponse,
  CaseRow,
  DocDownloadResponse,
  DocTemplatesResponse,
  PendingResponse,
  User,
} from "./types";

const SESSION_KEY = "moshang_session_id";
let currentUser: User | null = null;

export function savedUser(): User | null {
  return currentUser;
}

export function clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
  currentUser = null;
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

function setSession(sessionId: string, user: User) {
  sessionStorage.setItem(SESSION_KEY, sessionId);
  currentUser = user;
}

// 后端会话是内存态；只有用户选择“保持登录”时，后端才能从操作系统凭据库恢复。
let reloginPromise: Promise<boolean> | null = null;

async function silentRelogin(): Promise<boolean> {
  try {
    const resp = await fetch("/api/login/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    if (!resp.ok) return false;
    const data = (await resp.json()) as { session_id: string; user: User };
    setSession(data.session_id, data.user);
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
  const sessionId = sessionStorage.getItem(SESSION_KEY);
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
  async login(username: string, password: string, remember: boolean): Promise<User> {
    const data = await request<{ session_id: string; user: User }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ username, password, remember }),
    });
    setSession(data.session_id, data.user);
    return data.user;
  },

  async restoreLogin(): Promise<User> {
    const resp = await fetch("/api/login/restore", { method: "POST" });
    if (!resp.ok) throw new ApiError(resp.status, "没有可恢复的登录");
    const data = (await resp.json()) as { session_id: string; user: User };
    setSession(data.session_id, data.user);
    return data.user;
  },

  async currentUser(): Promise<User> {
    const user = await request<User>("/api/me");
    currentUser = user;
    return user;
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

  caseDocTemplates(id: number): Promise<DocTemplatesResponse> {
    return request(`/api/cases/${id}/documents/templates`);
  },

  documentPickDirectory(): Promise<{ path: string | null }> {
    return request("/api/cases/documents/pick-directory", { method: "POST" });
  },

  caseDocDownload(id: number, templates: string[], target_dir: string): Promise<DocDownloadResponse> {
    return request(`/api/cases/${id}/documents/download`, {
      method: "POST",
      body: JSON.stringify({ templates, target_dir }),
    });
  },

  pending(): Promise<PendingResponse> {
    return request("/api/approvals/pending");
  },

  approvalCheck(id: number): Promise<ApprovalReview> {
    return request(`/api/approvals/case/${id}/check`);
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

  automationStatus(): Promise<AutomationStatus> {
    return request("/api/approvals/automation");
  },

  automationSet(enabled: boolean): Promise<AutomationStatus> {
    return request("/api/approvals/automation", { method: "POST", body: JSON.stringify({ enabled }) });
  },

  automationPause(paused: boolean): Promise<AutomationStatus> {
    return request("/api/approvals/automation/pause", { method: "POST", body: JSON.stringify({ paused }) });
  },

  automationCheckNow(): Promise<{ shadow: boolean; count: number }> {
    return request("/api/approvals/automation/check-now", { method: "POST" });
  },

  approvalHistory(): Promise<{ events: AutomationStatus["events"] }> {
    return request("/api/approvals/history");
  },

  notificationStatus(): Promise<{ configured: boolean }> {
    return request("/api/approvals/notifications");
  },

  notificationSet(webhook: string): Promise<{ configured: boolean }> {
    return request("/api/approvals/notifications", { method: "POST", body: JSON.stringify({ webhook }) });
  },

  credentialsExport(): Promise<{ code: string; bundle: string; filename: string }> {
    return request("/api/credentials/export", { method: "POST" });
  },

  credentialsImport(bundle: string, code: string): Promise<{ ok: boolean; username: string; feishu_configured: boolean }> {
    return request("/api/credentials/import", { method: "POST", body: JSON.stringify({ bundle, code }) });
  },

  unapprove(
    id: number,
  ): Promise<{ ok: boolean; case_no: string; new_status_name: string }> {
    return request(`/api/approvals/${id}/unapprove`, { method: "POST" });
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
