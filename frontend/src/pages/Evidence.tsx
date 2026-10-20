import { FormEvent, Fragment, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, local, q, Row, useApi } from "../api";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Notice, Page, SearchBox, Select, Table } from "../components/ui";

function EvidencePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data } = useApi<Row[]>("/api/evidence");
  return (<select className="input max-w-md" aria-label="Evidence" value={value} onChange={(e) => onChange(e.target.value)}><option value="">Select evidence…</option>
    {(data ?? []).map((e) => <option key={e.id} value={e.evidence_id}>{e.evidence_id} · {e.original_filename} ({e.case_id})</option>)}</select>);
}

export function EvidenceUpload() {
  const cases = useApi<Row[]>("/api/cases"); const settings = useApi<Row>("/api/settings");
  const [search, setSearch] = useState(""); const [type, setType] = useState(""); const [integrity, setIntegrity] = useState("");
  const list = useApi<Row[]>(`/api/evidence${q({ q: search, file_type: type, integrity })}`);
  const [caseId, setCaseId] = useState(""); const [file, setFile] = useState<File | null>(null); const [src, setSrc] = useState("");
  const [busy, setBusy] = useState(false); const [msg, setMsg] = useState<{ ok: boolean; t: string } | null>(null);
  const open = (cases.data ?? []).filter((c) => c.status !== "closed");
  const submit = async (e: FormEvent) => {
    e.preventDefault(); if (!file) return; setBusy(true); setMsg(null);
    const fd = new FormData(); fd.append("file", file); fd.append("source_description", src);
    try { const r = await api(`/api/cases/${caseId}/evidence`, { form: fd }); setMsg({ ok: true, t: `Registered ${r.evidence_id} — SHA-256 ${r.sha256}` }); setFile(null); setSrc(""); list.reload(); }
    catch (x: any) { setMsg({ ok: false, t: x.message }); } finally { setBusy(false); }
  };
  return (
    <Page title="Evidence acquisition & registration" subtitle="Originals are stored read-only and hashed on acquisition; analysis uses working copies.">
      <form onSubmit={submit} className="panel mb-4 grid gap-3 p-4 md:grid-cols-2">
        <Field label="Case"><select className="input" required value={caseId} onChange={(e) => setCaseId(e.target.value)}><option value="">Select open case…</option>{open.map((c) => <option key={c.id} value={c.case_id}>{c.case_id} · {c.title}</option>)}</select></Field>
        <Field label={`Evidence file (max ${settings.data?.max_upload_mb ?? "…"} MB)`}><input className="input" type="file" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
        <div className="md:col-span-2"><Field label="Source / acquisition description"><input className="input" required maxLength={2000} placeholder="e.g. Synthetic sample exported from lab workstation" value={src} onChange={(e) => setSrc(e.target.value)} /></Field></div>
        <div className="flex items-center gap-3 md:col-span-2"><button className="btn-primary" disabled={busy || !caseId || !file}>{busy ? "Hashing & registering…" : "Register evidence"}</button>
          <span className="muted text-xs">Allowed: {settings.data?.allowed_formats}</span></div>
        {msg && <div className="md:col-span-2">{msg.ok ? <Notice>{msg.t}</Notice> : <ErrorBox msg={msg.t} />}</div>}
        <div className="md:col-span-2"><Notice tone="warn">Upload only evidence you are authorized to examine. Files are never executed; content stays on this machine.</Notice></div>
      </form>
      <div className="mb-3 flex flex-wrap gap-2"><SearchBox value={search} onChange={setSearch} placeholder="Evidence ID, filename, SHA-256" />
        <Select label="Type" value={type} onChange={setType} options={["txt", "text", "png", "jpg", "pdf", "docx", "xlsx", "pptx", "exe", "zip", "unknown"]} />
        <Select label="Integrity" value={integrity} onChange={setIntegrity} options={["verified", "mismatch", "disposed"]} /></div>
      <Card>{list.loading ? <Loading /> : list.error ? <ErrorBox msg={list.error} retry={list.reload} /> : !list.data?.length ? <Empty title="No evidence found" hint="Register a file above." /> : (
        <Table head={["ID", "Case", "File", "Size", "Type", "Acquired", "SHA-256", "Integrity"]}>{list.data.map((e) => (<tr key={e.id}>
          <td className="td font-mono"><Link className="text-cyan-500 underline" to={`/analysis/${e.evidence_id}`}>{e.evidence_id}</Link></td><td className="td">{e.case_id}</td>
          <td className="td">{e.original_filename}{e.is_synthetic && <span className="badge ml-2 bg-violet-500/15 text-violet-400">synthetic</span>}</td>
          <td className="td">{e.size_bytes.toLocaleString()}</td><td className="td">{e.detected_type}</td><td className="td muted">{local(e.acquired_at)}</td>
          <td className="td hash">{e.sha256.slice(0, 16)}…</td><td className="td"><Badge v={e.integrity_status} /></td></tr>))}</Table>)}</Card>
    </Page>
  );
}

export function AnalysisWorkspace() {
  const { evidenceId } = useParams(); const nav = useNavigate();
  const ev = useApi<Row>(evidenceId ? `/api/evidence/${evidenceId}` : null);
  const [res, setRes] = useState<Row | null>(null); const [busy, setBusy] = useState(false); const [err, setErr] = useState("");
  const run = async () => { setBusy(true); setErr(""); try { setRes(await api(`/api/evidence/${evidenceId}/analyze`, { method: "POST" })); ev.reload(); } catch (x: any) { setErr(x.message); ev.reload(); } finally { setBusy(false); } };
  const a = res ?? ev.data?.last_analysis;
  const pred = a?.prediction; const inds = a?.indicators ?? [];
  return (
    <Page title="Evidence analysis workspace" subtitle="Read-only static inspection of a working copy. Nothing is executed, opened with macros or run as a script.">
      <div className="mb-4 flex flex-wrap items-center gap-2"><EvidencePicker value={evidenceId ?? ""} onChange={(v) => { setRes(null); nav(v ? `/analysis/${v}` : "/analysis"); }} />
        {evidenceId && <button className="btn-primary" onClick={run} disabled={busy}>{busy ? "Analyzing…" : "Run analysis"}</button>}
        {evidenceId && <Link className="btn-ghost" to={`/metadata/${evidenceId}`}>Metadata</Link>}</div>
      {!evidenceId ? <Empty title="Select an evidence item" /> : ev.loading ? <Loading /> : ev.error || !ev.data ? <ErrorBox msg={ev.error ?? ""} retry={ev.reload} /> : (<>
        {err && <div className="mb-3"><ErrorBox msg={err} /></div>}
        <div className="grid gap-4 lg:grid-cols-3">
          <Card title="Evidence"><dl className="space-y-1.5 text-sm"><div className="flex justify-between"><dt className="muted">File</dt><dd>{ev.data.original_filename}</dd></div>
            <div className="flex justify-between"><dt className="muted">Detected type</dt><dd>{ev.data.detected_type} ({ev.data.mime_type})</dd></div>
            <div className="flex justify-between"><dt className="muted">Declared MIME</dt><dd>{ev.data.declared_mime || "—"}</dd></div>
            <div className="flex justify-between"><dt className="muted">Integrity</dt><dd><Badge v={ev.data.integrity_status} /></dd></div>
            <div><dt className="muted">SHA-256</dt><dd className="hash">{ev.data.sha256}</dd></div></dl></Card>
          <Card title="Automated indicators (rule-based)" className="lg:col-span-2">
            {!a ? <Empty title="Not analyzed yet" hint="Run analysis to inspect signatures, metadata and indicators." /> : !inds.length ? <p className="text-sm">No rule-based indicators triggered. This does not prove the file is safe.</p> :
              <ul className="space-y-2">{inds.map((i: Row, n: number) => <li key={n} className="flex items-start gap-2 text-sm"><Badge v={i.severity} /><span><b className="font-mono text-xs">{i.code}</b> — {i.reason}</span></li>)}</ul>}
          </Card></div>
        {pred && <Card title="AI-assisted triage (local model)" className="mt-4">
          <div className="flex flex-wrap items-center gap-3"><Badge v={pred.label} /><span className="text-sm">confidence {(pred.confidence * 100).toFixed(1)}%</span><span className="muted text-xs">model {pred.model_version}</span></div>
          <div className="mt-3 grid gap-4 md:grid-cols-2"><div><h3 className="mb-1 text-xs font-semibold uppercase muted">Most influential features</h3>
            <ul className="space-y-1 text-sm">{pred.top_features.map((f: Row) => <li key={f.feature} className="flex justify-between"><span className="font-mono text-xs">{f.feature} = {f.value}</span><span className={f.contribution > 0 ? "text-amber-500" : "text-emerald-500"}>{f.contribution > 0 ? "+" : ""}{f.contribution} toward {pred.label}</span></li>)}</ul></div>
            <div><h3 className="mb-1 text-xs font-semibold uppercase muted">Limitations</h3><ul className="list-disc pl-4 text-xs muted">{pred.limitations.map((l: string) => <li key={l}>{l}</li>)}</ul></div></div>
          <div className="mt-3"><Notice tone="warn">Human review required. This is a triage aid, not proof of wrongdoing. <Link className="underline" to="/findings">Review findings →</Link></Notice></div></Card>}
        {res && <Card title="Integrity during this run" className="mt-4"><p className="text-sm">Before: {res.pre_integrity.match ? "✔ match" : "✖ MISMATCH"} · After: {res.post_integrity.match ? "✔ match" : "✖ MISMATCH"}</p></Card>}
        {a?.text_excerpt && <Card title="Text excerpt (first 2,000 characters, sanitised)" className="mt-4"><pre className="hash max-h-56 overflow-auto whitespace-pre-wrap">{a.text_excerpt}</pre></Card>}
      </>)}
    </Page>
  );
}

export function MetadataInspector() {
  const { evidenceId } = useParams(); const nav = useNavigate();
  const m = useApi<Row>(evidenceId ? `/api/evidence/${evidenceId}/metadata` : null);
  const groups: Record<string, Row[]> = {}; (m.data?.fields ?? []).forEach((f: Row) => (groups[f.source] ??= []).push(f));
  return (
    <Page title="Metadata inspector" subtitle="Self-reported values extracted from the file and filesystem.">
      <div className="mb-4"><EvidencePicker value={evidenceId ?? ""} onChange={(v) => nav(v ? `/metadata/${v}` : "/metadata")} /></div>
      {!evidenceId ? <Empty title="Select an evidence item" /> : m.loading ? <Loading /> : m.error ? <ErrorBox msg={m.error} retry={m.reload} /> : (<>
        <Notice tone="warn">{m.data?.limitations}</Notice>
        {!m.data?.fields.length ? <Card className="mt-4"><Empty title="No metadata stored" hint="Run analysis on this evidence first." /></Card> :
          <div className="mt-4 grid gap-4 md:grid-cols-2">{Object.entries(groups).map(([src, fs]) => (<Card key={src} title={src.toUpperCase()}><Table head={["Field", "Value"]}>{fs.map((f, i) => <tr key={i}><td className="td font-mono text-xs">{f.key}</td><td className="td break-all">{f.value}</td></tr>)}</Table></Card>))}</div>}
      </>)}
    </Page>
  );
}

export function IntegrityPage() {
  const list = useApi<Row[]>("/api/evidence"); const [out, setOut] = useState<Record<string, Row>>({}); const [busy, setBusy] = useState(""); const [open, setOpen] = useState(""); const detail = useApi<Row>(open ? `/api/evidence/${open}` : null);
  const verify = async (id: string) => { setBusy(id); try { const r = await api(`/api/evidence/${id}/verify`, { method: "POST" }); setOut((o) => ({ ...o, [id]: r })); } catch (x: any) { setOut((o) => ({ ...o, [id]: { error: x.message } })); } finally { setBusy(""); list.reload(); } };
  const all = async () => { for (const e of list.data ?? []) if (e.integrity_status !== "disposed") await verify(e.evidence_id); };
  const bad = (list.data ?? []).filter((e) => e.integrity_status === "mismatch");
  return (
    <Page title="Integrity verification" subtitle="Re-hash stored originals and compare against the acquisition SHA-256." actions={<button className="btn-primary" onClick={all} disabled={!!busy}>Verify all</button>}>
      {bad.length > 0 && <div className="mb-4"><ErrorBox msg={`⚠ ${bad.length} evidence item(s) FAILED integrity verification: ${bad.map((b) => b.evidence_id).join(", ")}. Treat as potentially altered and escalate per your procedures.`} /></div>}
      <Card>{list.loading ? <Loading /> : !list.data?.length ? <Empty title="No evidence registered" /> : (
        <Table head={["Evidence", "File", "Status", "Last check", ""]}>{list.data.map((e) => { const o = out[e.evidence_id]; return (<Fragment key={e.id}>
          <tr><td className="td font-mono">{e.evidence_id}</td><td className="td">{e.original_filename}</td><td className="td"><Badge v={e.integrity_status} /></td>
            <td className="td text-xs">{o ? o.error ? <span className="text-red-400">{o.error}</span> : o.match ? "✔ match" : <b className="text-red-500">✖ MISMATCH</b> : "—"}</td>
            <td className="td space-x-2"><button className="btn-ghost" disabled={busy === e.evidence_id || e.integrity_status === "disposed"} onClick={() => verify(e.evidence_id)}>{busy === e.evidence_id ? "Hashing…" : "Verify"}</button>
              <button className="btn-ghost" onClick={() => setOpen(open === e.evidence_id ? "" : e.evidence_id)}>History</button></td></tr>
          {open === e.evidence_id && <tr><td colSpan={5} className="td">{detail.loading ? <Loading /> : <ul className="space-y-1">{(detail.data?.hash_history ?? []).map((h: Row, i: number) => <li key={i} className="text-xs"><Badge v={h.matches_original ? "verified" : "mismatch"} /> <span className="muted">{local(h.computed_at)} · {h.context}</span> <span className="hash">{h.value}</span></li>)}</ul>}</td></tr>}</Fragment>); })}</Table>)}</Card>
    </Page>
  );
}
