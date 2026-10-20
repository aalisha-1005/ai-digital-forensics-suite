import { FormEvent, useState } from "react";
import { api, local, Row, useApi } from "../api";
import { useAuth } from "../App";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Notice, Page, Table } from "../components/ui";

export function Reports() {
  const cases = useApi<Row[]>("/api/cases"); const reps = useApi<Row[]>("/api/reports");
  const [caseId, setCaseId] = useState(""); const [busy, setBusy] = useState(""); const [err, setErr] = useState("");
  const make = async (format: string) => { setBusy(format); setErr(""); try { await api(`/api/cases/${caseId}/reports`, { body: { format } }); reps.reload(); } catch (x: any) { setErr(x.message); } finally { setBusy(""); } };
  return (
    <Page title="Reports & exports" subtitle="Reports separate observed facts, automated flags and analyst interpretations.">
      <Card><div className="flex flex-wrap items-end gap-2"><Field label="Case"><select className="input" value={caseId} onChange={(e) => setCaseId(e.target.value)}><option value="">Select case…</option>{(cases.data ?? []).map((c) => <option key={c.id} value={c.case_id}>{c.case_id} · {c.title}</option>)}</select></Field>
        <button className="btn-primary" disabled={!caseId || !!busy} onClick={() => make("pdf")}>{busy === "pdf" ? "Building…" : "Generate PDF"}</button><button className="btn-ghost" disabled={!caseId || !!busy} onClick={() => make("csv")}>{busy === "csv" ? "Building…" : "Generate CSV"}</button></div>
        {err && <div className="mt-3"><ErrorBox msg={err} /></div>}<div className="mt-3"><Notice>Each export is hashed and recorded in the custody ledger for every evidence item in the case.</Notice></div></Card>
      <Card title="Previous exports" className="mt-4">{reps.loading ? <Loading /> : !reps.data?.length ? <Empty title="No reports generated yet" /> : (
        <Table head={["Case", "Format", "Generated", "SHA-256", ""]}>{reps.data.map((r) => (<tr key={r.id}><td className="td font-mono">{r.case_id}</td><td className="td uppercase">{r.format}</td><td className="td">{local(r.generated_at)}</td><td className="td hash">{r.sha256.slice(0, 16)}…</td>
          <td className="td"><a className="text-cyan-500 underline" href={`/api/reports/${r.id}/download`}>Download</a></td></tr>))}</Table>)}</Card>
    </Page>
  );
}

export function SettingsPage() {
  const { user } = useAuth(); const admin = user.role === "administrator";
  const s = useApi<Row>("/api/settings"); const users = useApi<Row[]>(admin ? "/api/users" : null); const model = useApi<Row>("/api/model");
  const [form, setForm] = useState<Row | null>(null); const [msg, setMsg] = useState(""); const [nu, setNu] = useState({ username: "", full_name: "", password: "", role: "investigator" });
  const cur = form ?? s.data;
  const save = async (e: FormEvent) => { e.preventDefault(); setMsg(""); try { await api("/api/settings", { method: "PUT", body: { max_upload_mb: Number(cur!.max_upload_mb), allowed_formats: cur!.allowed_formats, retention_days: Number(cur!.retention_days) } }); setForm(null); s.reload(); setMsg("Settings saved."); } catch (x: any) { setMsg(x.message); } };
  const addUser = async (e: FormEvent) => { e.preventDefault(); setMsg(""); try { await api("/api/users", { body: nu }); setNu({ username: "", full_name: "", password: "", role: "investigator" }); users.reload(); } catch (x: any) { setMsg(x.message); } };
  const patch = async (id: number, d: Row) => { setMsg(""); try { await api(`/api/users/${id}`, { method: "PATCH", body: d }); users.reload(); } catch (x: any) { setMsg(x.message); } };
  const train = async () => { setMsg(""); try { await api("/api/model/train", { method: "POST" }); model.reload(); setMsg("Model retrained on synthetic data."); } catch (x: any) { setMsg(x.message); } };
  return (
    <Page title="Users & settings" subtitle="Local accounts, upload limits, supported formats and retention.">
      {msg && <div className="mb-3"><Notice>{msg}</Notice></div>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Application settings">{!cur ? <Loading /> : (<form onSubmit={save} className="space-y-3">
          <Field label="Max upload size (MB)"><input className="input" type="number" min={1} max={500} disabled={!admin} value={cur.max_upload_mb} onChange={(e) => setForm({ ...cur, max_upload_mb: e.target.value })} /></Field>
          <Field label="Supported formats (comma-separated extensions)"><input className="input" disabled={!admin} value={cur.allowed_formats} onChange={(e) => setForm({ ...cur, allowed_formats: e.target.value })} /></Field>
          <Field label="Retention period after case closure (days)"><input className="input" type="number" min={0} disabled={!admin} value={cur.retention_days} onChange={(e) => setForm({ ...cur, retention_days: e.target.value })} /></Field>
          {admin ? <button className="btn-primary">Save settings</button> : <p className="muted text-xs">Only administrators can change settings.</p>}
          <Notice>Evidence disposal is only permitted after the case is closed and the retention period has elapsed; hashes and the ledger are preserved.</Notice></form>)}</Card>
        <Card title="Local AI model">{model.loading ? <Loading /> : (<div className="space-y-2 text-sm"><p>Version: <b>{model.data?.version ?? "not trained"}</b></p>{model.data?.algorithm && <><p>Algorithm: {model.data.algorithm}</p><p>Training data: {model.data.training_data}</p><p>Holdout accuracy (synthetic): {model.data.holdout_accuracy}</p></>}
          <ul className="list-disc pl-4 text-xs muted">{(model.data?.limitations ?? []).map((l: string) => <li key={l}>{l}</li>)}</ul>{admin && <button className="btn-ghost" onClick={train}>Retrain locally</button>}</div>)}</Card>
      </div>
      {admin && <Card title="Users" className="mt-4">
        <form onSubmit={addUser} className="mb-4 grid gap-2 md:grid-cols-5"><input className="input" required placeholder="username" value={nu.username} onChange={(e) => setNu({ ...nu, username: e.target.value })} /><input className="input" required placeholder="Full name" value={nu.full_name} onChange={(e) => setNu({ ...nu, full_name: e.target.value })} />
          <input className="input" required type="password" autoComplete="new-password" placeholder="Password (12+ chars)" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} /><select className="input" value={nu.role} onChange={(e) => setNu({ ...nu, role: e.target.value })}><option>investigator</option><option>administrator</option></select><button className="btn-primary justify-center">Add user</button></form>
        {users.loading ? <Loading /> : <Table head={["User", "Name", "Role", "Active", ""]}>{(users.data ?? []).map((u) => (<tr key={u.id}><td className="td font-mono">{u.username}</td><td className="td">{u.full_name}</td>
          <td className="td"><select className="input w-auto" value={u.role} onChange={(e) => patch(u.id, { role: e.target.value })}><option>investigator</option><option>administrator</option></select></td><td className="td"><Badge v={u.is_active ? "verified" : "closed"} /></td>
          <td className="td"><button className="btn-ghost" onClick={() => patch(u.id, { is_active: !u.is_active })}>{u.is_active ? "Disable" : "Enable"}</button></td></tr>))}</Table>}</Card>}
    </Page>
  );
}
