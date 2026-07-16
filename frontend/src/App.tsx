import { useEffect, useState } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import type { User } from "./types";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { CaseBoard } from "./pages/CaseBoard";
import { Approvals } from "./pages/Approvals";
import { ApprovalDetail } from "./pages/ApprovalDetail";
import { Assistant } from "./pages/Assistant";

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    void api
      .currentUser()
      .then(setUser)
      .catch(() => undefined)
      .finally(() => setRestoring(false));
  }, []);

  if (restoring) {
    return <div className="flex h-full items-center justify-center bg-zinc-50 text-sm text-zinc-400">正在恢复登录…</div>;
  }

  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Login onLogin={setUser} />} />
        {user ? (
          <Route element={<Layout user={user} onLogout={() => setUser(null)} />}>
            <Route path="/cases" element={<CaseBoard />} />
            <Route path="/approvals" element={user.canApprove ? <Approvals /> : <NoApprovalAccess />} />
            <Route path="/approvals/:id" element={user.canApprove ? <ApprovalDetail /> : <NoApprovalAccess />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="*" element={<Navigate to="/cases" replace />} />
          </Route>
        ) : (
          <Route path="*" element={<Navigate to="/login" replace />} />
        )}
      </Routes>
    </HashRouter>
  );
}

function NoApprovalAccess() {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center">
      <div>
        <h2 className="text-base font-semibold text-zinc-800">当前账号无审批权限</h2>
        <p className="mt-2 text-sm text-zinc-400">您仍可使用案件列表和办案助手。</p>
      </div>
    </div>
  );
}
