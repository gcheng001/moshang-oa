import { useState } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { savedUser } from "./api";
import type { User } from "./types";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { CaseBoard } from "./pages/CaseBoard";
import { Approvals } from "./pages/Approvals";
import { ApprovalDetail } from "./pages/ApprovalDetail";
import { Assistant } from "./pages/Assistant";

export default function App() {
  const [user, setUser] = useState<User | null>(savedUser());

  return (
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Login onLogin={setUser} />} />
        {user ? (
          <Route element={<Layout user={user} onLogout={() => setUser(null)} />}>
            <Route path="/cases" element={<CaseBoard />} />
            <Route path="/approvals" element={<Approvals />} />
            <Route path="/approvals/:id" element={<ApprovalDetail />} />
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
