import { createContext, useContext, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, local, Row, setCsrf, useApi } from "./api";
import { Loading } from "./components/ui";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import { CaseDetail, Cases } from "./pages/Cases";
import { AnalysisWorkspace, EvidenceUpload, IntegrityPage, MetadataInspector } from "./pages/Evidence";
import { AuditViewer, CustodyLedger, TimelinePage } from "./pages/Records";
import Findings from "./pages/Findings";
import { Reports, SettingsPage } from "./pages/Admin";

export const AuthCtx = createContext<{ user: Row; logout: () => void }>(null as any);
export const useAuth = () => useContext(AuthCtx);

const NAV: [string, string, boolean?][] = [
  ["/", "Overview"], ["/cases", "Cases"], ["/evidence", "Evidence upload"], ["/analysis", "Analysis workspace"], ["/metadata", "Metadata inspector"],
  ["/integrity", "Integrity verification"], ["/timeline", "Forensic timeline"], ["/custody", "Chain of custody"], ["/findings", "AI findings & review"],
  ["/reports", "Reports & exports"], ["/settings", "Users & settings"], ["/audit", "Audit log", true],
];

function Shell({ user, logout }: { user: Row; logout: () => void }) {
  const [dark, setDark] = useState(document.documentElement.classList.contains("dark"));
  const [open, setOpen] = useState(false);
  const [bell, setBell] = useState(false);
  const notes = useApi<Row[]>("/api/notifications");
  const nav = useNavigate();
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    try { localStorage.setItem("dfis-theme", dark ? "dark" : "light"); } catch { /* storage unavailable */ }
  }, [dark]);
  useEffect(() => { const t = setInterval(notes.reload, 30000); return () => clearInterval(t); }, [notes.reload]);
  const unread = (notes.data ?? []).filter((n) => !n.is_read).length;
  const admin = user.role === "administrator";
  return (
    <div className="flex h-full">
      <aside className={`fixed inset-y-0 left-0 z-30 w-64 transform border-r p-3 transition-transform lg:static lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
        style={{ background: "var(--panel)", borderColor: "var(--line)" }} aria-label="Primary">
        <div className="mb-4 flex items-center gap-2 px-2 pt-1">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-cyan-400 to-blue-600 font-mono text-sm font-bold text-slate-950">DF</div>
          <div><div className="text-sm font-semibold leading-tight">DFIS Workstation</div><div className="muted text-[11px]">Offline · Defensive · Read-only evidence</div></div>
        </div>
        <nav className="space-y-0.5">
          {NAV.filter((n) => !n[2] || admin).map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}
              className={({ isActive }) => `block rounded-lg px-3 py-2 text-sm transition ${isActive ? "bg-cyan-500/15 font-medium text-cyan-500" : "muted hover:bg-cyan-500/5"}`}>{label}</NavLink>
          ))}
        </nav>
      </aside>
      {open && <div className="fixed inset-0 z-20 bg-black/50 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b px-4 py-2.5" style={{ background: "var(--panel)", borderColor: "var(--line)" }}>
          <button className="btn-ghost lg:hidden" aria-label="Open menu" onClick={() => setOpen(true)}>☰</button>
          <div className="muted hidden text-xs sm:block">Authorized, lawfully obtained evidence only · AI output requires human review</div>
          <div className="ml-auto flex items-center gap-2">
            <div className="relative">
              <button className="btn-ghost" aria-label={`Notifications (${unread} unread)`} onClick={() => setBell(!bell)}>🔔{unread > 0 && <span className="badge bg-red-500 text-white">{unread}</span>}</button>
              {bell && (
                <div className="panel absolute right-0 z-40 mt-2 max-h-96 w-80 overflow-auto p-2 shadow-xl">
                  <div className="flex justify-between px-2 py-1 text-xs"><b>Notifications</b>
                    <button className="underline" onClick={async () => { await api("/api/notifications/read-all", { method: "POST" }); notes.reload(); }}>Mark all read</button></div>
                  {(notes.data ?? []).length === 0 && <p className="muted p-3 text-sm">No notifications.</p>}
                  {(notes.data ?? []).map((n) => (
                    <button key={n.id} onClick={() => { setBell(false); nav(n.kind === "pending_review" ? "/findings" : n.kind === "integrity_mismatch" ? "/integrity" : "/cases"); }}
                      className={`block w-full rounded-lg px-2 py-1.5 text-left text-xs hover:bg-cyan-500/10 ${n.is_read ? "muted" : "font-medium"}`}>
                      {n.kind === "integrity_mismatch" && "⚠ "}{n.message}<div className="muted">{local(n.created_at)}</div></button>
                  ))}
                </div>)}
            </div>
            <button className="btn-ghost" aria-pressed={dark} onClick={() => setDark(!dark)}>{dark ? "☀ Light" : "🌙 Dark"}</button>
            <span className="muted hidden text-xs sm:inline">{user.full_name} · {user.role}</span>
            <button className="btn-ghost" onClick={logout}>Sign out</button>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cases" element={<Cases />} />
            <Route path="/cases/:caseId" element={<CaseDetail />} />
            <Route path="/evidence" element={<EvidenceUpload />} />
            <Route path="/analysis" element={<AnalysisWorkspace />} />
            <Route path="/analysis/:evidenceId" element={<AnalysisWorkspace />} />
            <Route path="/metadata" element={<MetadataInspector />} />
            <Route path="/metadata/:evidenceId" element={<MetadataInspector />} />
            <Route path="/integrity" element={<IntegrityPage />} />
            <Route path="/timeline" element={<TimelinePage />} />
            <Route path="/custody" element={<CustodyLedger />} />
            <Route path="/findings" element={<Findings />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/audit" element={admin ? <AuditViewer /> : <Navigate to="/" />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<Row | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => { api("/api/auth/me").then((r) => { setCsrf(r.csrf_token); setUser(r.user); }).catch(() => {}).finally(() => setReady(true)); }, []);
  if (!ready) return <Loading label="Starting workstation…" />;
  if (!user) return <Login onLogin={(r) => { setCsrf(r.csrf_token); setUser(r.user); }} />;
  const logout = async () => { try { await api("/api/auth/logout", { method: "POST" }); } catch { /* ignore */ } setUser(null); };
  return <AuthCtx.Provider value={{ user, logout }}><Shell user={user} logout={logout} /></AuthCtx.Provider>;
}
