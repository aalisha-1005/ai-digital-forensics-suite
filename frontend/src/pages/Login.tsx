import { FormEvent, useState } from "react";
import { api } from "../api";
import { Notice } from "../components/ui";

export default function Login({ onLogin }: { onLogin: (r: any) => void }) {
  const [u, setU] = useState(""); const [p, setP] = useState(""); const [err, setErr] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { onLogin(await api("/api/auth/login", { body: { username: u, password: p } })); }
    catch (x: any) { setErr(x.message); } finally { setBusy(false); }
  };
  return (
    <div className="grid min-h-full place-items-center p-4" style={{ background: "radial-gradient(1200px 500px at 50% -10%, rgba(6,182,212,.18), transparent)" }}>
      <form onSubmit={submit} className="panel w-full max-w-sm space-y-4 p-6" aria-labelledby="t">
        <div className="flex items-center gap-3"><div className="grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 font-mono font-bold text-slate-950">DF</div>
          <div><h1 id="t" className="text-lg font-semibold leading-tight">Digital Forensics Suite</h1><p className="muted text-xs">Local investigator sign-in</p></div></div>
        <label className="block text-sm"><span className="muted mb-1 block text-xs">Username</span><input className="input" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required /></label>
        <label className="block text-sm"><span className="muted mb-1 block text-xs">Password</span><input className="input" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required /></label>
        {err && <div role="alert" className="text-sm text-red-400">{err}</div>}
        <button className="btn-primary w-full justify-center" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <Notice>Accounts are created locally by an administrator (see README: <span className="font-mono">scripts.init_db</span>). Use only with authorized, lawfully obtained evidence.</Notice>
      </form>
    </div>
  );
}
