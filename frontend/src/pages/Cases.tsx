import { FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, local, q, Row, useApi } from "../api";
import { useAuth } from "../App";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Notice, Page, SearchBox, Select, Table } from "../components/ui";

export function Cases() {
  const { user } = useAuth();
  const [search, setSearch] = useState(""); const [status, setStatus] = useState(""); const [priority, setPriority] = useState(""); const [inv, setInv] = useState("");
  const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const { data, loading, error, reload } = useApi<Row[]>(`/api/cases${q({ q: search, status, priority, investigator_id: inv, date_from: from, date_to: to })}`);
  const users = useApi<Row[]>("/api/users");
  const [show, setShow] = useState(false);
  const [f, setF] = useState({ title: "", description: "", priority: "medium", investigator_id: "" });
  const [err, setErr] = useState("");
  const create = async (e: FormEvent) => {
    e.preventDefault(); setErr("");
    try { await api("/api/cases", { body: { ...f, investigator_id: f.investigator_id ? Number(f.investigator_id) : null } }); setShow(false); setF({ title: "", description: "", priority: "medium", investigator_id: "" }); reload(); }
    catch (x: any) { setErr(x.message); }
  };
  return (
    <Page title="Case management" subtitle="Create, search, assign and close forensic cases." actions={<button className="btn-primary" onClick={() => setShow(!show)}>{show ? "Cancel" : "+ New case"}</button>}>
      {show && (
        <form onSubmit={create} className="panel mb-4 grid gap-3 p-4 md:grid-cols-2">
          <Field label="Title"><input className="input" required minLength={3} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Priority"><select className="input" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>{["low", "medium", "high", "critical"].map((p) => <option key={p}>{p}</option>)}</select></Field>
          <div className="md:col-span-2"><Field label="Description"><textarea className="input" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
          {user.role === "administrator" && <Field label="Assign investigator"><select className="input" value={f.investigator_id} onChange={(e) => setF({ ...f, investigator_id: e.target.value })}><option value="">Me</option>{(users.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select></Field>}
          {err && <div role="alert" className="text-sm text-red-400 md:col-span-2">{err}</div>}
          <div className="md:col-span-2"><button className="btn-primary">Create case</button></div>
        </form>)}
      <div className="mb-3 flex flex-wrap gap-2">
        <SearchBox value={search} onChange={setSearch} placeholder="Case ID, title, description" />
        <Select label="Status" value={status} onChange={setStatus} options={["open", "in_review", "closed"]} />
        <Select label="Priority" value={priority} onChange={setPriority} options={["low", "medium", "high", "critical"]} />
        {user.role === "administrator" && <select className="input w-auto" aria-label="Investigator" value={inv} onChange={(e) => setInv(e.target.value)}><option value="">Investigator: all</option>{(users.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select>}
        <input type="date" className="input w-auto" aria-label="Created from" value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="date" className="input w-auto" aria-label="Created to" value={to} onChange={(e) => setTo(e.target.value)} />
      </div>
      <Card>
        {loading ? <Loading /> : error ? <ErrorBox msg={error} retry={reload} /> : !data?.length ? <Empty title="No cases match" hint="Create a case or adjust the filters." /> : (
          <Table head={["Case", "Title", "Investigator", "Priority", "Status", "Evidence", "Pending", "Updated"]}>
            {data.map((c) => (<tr key={c.id}>
              <td className="td font-mono"><Link className="text-cyan-500 underline" to={`/cases/${c.case_id}`}>{c.case_id}</Link></td>
              <td className="td">{c.title}{c.is_synthetic && <span className="badge ml-2 bg-violet-500/15 text-violet-400">synthetic</span>}</td>
              <td className="td">{c.investigator ?? "Unassigned"}</td><td className="td"><Badge v={c.priority} /></td><td className="td"><Badge v={c.status} /></td>
              <td className="td">{c.evidence_count}</td><td className="td">{c.pending_reviews}</td><td className="td muted">{local(c.updated_at)}</td></tr>))}
          </Table>)}
      </Card>
    </Page>
  );
}

export function CaseDetail() {
  const { caseId } = useParams(); const { user } = useAuth();
  const c = useApi<Row>(`/api/cases/${caseId}`); const ev = useApi<Row[]>(`/api/evidence${q({ case_id: caseId })}`);
  const notes = useApi<Row[]>(`/api/cases/${caseId}/notes`); const users = useApi<Row[]>("/api/users");
  const [body, setBody] = useState(""); const [method, setMethod] = useState(""); const [evRef, setEvRef] = useState(""); const [msg, setMsg] = useState("");
  const patch = async (d: Row) => { setMsg(""); try { await api(`/api/cases/${caseId}`, { method: "PATCH", body: d }); c.reload(); } catch (x: any) { setMsg(x.message); } };
  const addNote = async (e: FormEvent) => { e.preventDefault(); setMsg(""); try { await api(`/api/cases/${caseId}/notes`, { body: { body, method, evidence_id: evRef || null } }); setBody(""); setMethod(""); notes.reload(); } catch (x: any) { setMsg(x.message); } };
  if (c.loading) return <Loading />;
  if (c.error || !c.data) return <Page title="Case"><ErrorBox msg={c.error ?? "Not found"} retry={c.reload} /></Page>;
  const k = c.data; const admin = user.role === "administrator";
  return (
    <Page title={`${k.case_id} · ${k.title}`} subtitle={k.description} actions={<>
      {k.status !== "closed" && <button className="btn-ghost" onClick={() => patch({ status: "in_review" })}>Mark in review</button>}
      {k.status !== "closed" ? <button className="btn-danger" onClick={() => confirm("Close this case? All findings must be reviewed.") && patch({ status: "closed" })}>Close case</button>
        : admin && <button className="btn-ghost" onClick={() => patch({ status: "open" })}>Reopen</button>}</>}>
      {msg && <div className="mb-3"><ErrorBox msg={msg} /></div>}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Details"><dl className="space-y-2 text-sm">
          <div className="flex justify-between"><dt className="muted">Status</dt><dd><Badge v={k.status} /></dd></div>
          <div className="flex justify-between"><dt className="muted">Priority</dt><dd>{admin || k.status !== "closed" ? <select className="input w-auto" value={k.priority} disabled={k.status === "closed"} onChange={(e) => patch({ priority: e.target.value })}>{["low", "medium", "high", "critical"].map((p) => <option key={p}>{p}</option>)}</select> : <Badge v={k.priority} />}</dd></div>
          <div className="flex justify-between"><dt className="muted">Investigator</dt><dd>{admin ? <select className="input w-auto" value={k.investigator_id ?? ""} onChange={(e) => patch({ investigator_id: Number(e.target.value) })}>{(users.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.full_name}</option>)}</select> : k.investigator}</dd></div>
          <div className="flex justify-between"><dt className="muted">Created</dt><dd>{local(k.created_at)}</dd></div>
          {k.closed_at && <div className="flex justify-between"><dt className="muted">Closed</dt><dd>{local(k.closed_at)}</dd></div>}
        </dl>
          <div className="mt-3 flex flex-wrap gap-2"><Link className="btn-ghost" to={`/timeline?case=${k.case_id}`}>Timeline</Link><Link className="btn-ghost" to="/reports">Reports</Link><Link className="btn-ghost" to="/findings">Findings</Link></div></Card>
        <Card title="Evidence" className="lg:col-span-2">
          {ev.loading ? <Loading /> : !ev.data?.length ? <Empty title="No evidence registered" hint="Use Evidence upload to add authorized files." /> : (
            <Table head={["ID", "File", "Type", "Integrity", ""]}>{ev.data.map((e) => (<tr key={e.id}><td className="td font-mono">{e.evidence_id}</td><td className="td">{e.original_filename}</td><td className="td">{e.detected_type}</td><td className="td"><Badge v={e.integrity_status} /></td><td className="td"><Link className="text-cyan-500 underline" to={`/analysis/${e.evidence_id}`}>Analyze</Link></td></tr>))}</Table>)}
        </Card>
      </div>
      <Card title="Investigator notes" className="mt-4">
        {k.status !== "closed" && (
          <form onSubmit={addNote} className="mb-4 grid gap-2 md:grid-cols-3">
            <input className="input" placeholder="Analytical method used (optional)" value={method} onChange={(e) => setMethod(e.target.value)} />
            <select className="input" value={evRef} onChange={(e) => setEvRef(e.target.value)}><option value="">Link evidence (optional)</option>{(ev.data ?? []).map((e) => <option key={e.id} value={e.evidence_id}>{e.evidence_id} · {e.original_filename}</option>)}</select>
            <button className="btn-primary justify-center">Add note</button>
            <textarea className="input md:col-span-3" rows={3} required placeholder="Observation, method, reasoning…" value={body} onChange={(e) => setBody(e.target.value)} />
          </form>)}
        {!notes.data?.length ? <Empty title="No notes yet" /> : <ul className="space-y-3">{notes.data.map((n) => (<li key={n.id} className="rounded-lg border p-3 text-sm" style={{ borderColor: "var(--line)" }}>
          <div className="muted mb-1 text-xs">{n.author} · {local(n.created_at)}{n.evidence_id && ` · ${n.evidence_id}`}{n.method && ` · method: ${n.method}`}</div>{n.body}</li>))}</ul>}
        <div className="mt-3"><Notice>Notes are analyst interpretation. Findings only become conclusions after investigator review on the AI findings page.</Notice></div>
      </Card>
    </Page>
  );
}
