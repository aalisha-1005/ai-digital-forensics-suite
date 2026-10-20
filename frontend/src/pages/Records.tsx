import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, local, q, Row, useApi } from "../api";
import { Badge, Card, Empty, ErrorBox, Field, Loading, Notice, Page, SearchBox, Select, Table } from "../components/ui";
import { FormEvent } from "react";

export function TimelinePage() {
  const [sp, setSp] = useSearchParams(); const cases = useApi<Row[]>("/api/cases");
  const caseId = sp.get("case") ?? cases.data?.[0]?.case_id ?? "";
  const [search, setSearch] = useState(""); const [from, setFrom] = useState(""); const [to, setTo] = useState(""); const [utc, setUtc] = useState(false);
  const tl = useApi<Row>(caseId ? `/api/cases/${caseId}/timeline${q({ q: search, date_from: from, date_to: to })}` : null);
  const [ts, setTs] = useState(""); const [title, setTitle] = useState(""); const [err, setErr] = useState("");
  const add = async (e: FormEvent) => { e.preventDefault(); setErr(""); try { await api(`/api/cases/${caseId}/timeline`, { body: { timestamp: new Date(ts).toISOString(), title } }); setTitle(""); setTs(""); tl.reload(); } catch (x: any) { setErr(x.message); } };
  return (
    <Page title="Forensic timeline" subtitle="Events normalised to UTC with provenance; conflicts and gaps are flagged.">
      <div className="mb-3 flex flex-wrap gap-2">
        <select className="input w-auto" aria-label="Case" value={caseId} onChange={(e) => setSp({ case: e.target.value })}>{(cases.data ?? []).map((c) => <option key={c.id} value={c.case_id}>{c.case_id} · {c.title}</option>)}</select>
        <SearchBox value={search} onChange={setSearch} placeholder="Search events" />
        <input type="date" className="input w-auto" aria-label="From" value={from} onChange={(e) => setFrom(e.target.value)} /><input type="date" className="input w-auto" aria-label="To" value={to} onChange={(e) => setTo(e.target.value)} />
        <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={utc} onChange={(e) => setUtc(e.target.checked)} /> Show UTC</label></div>
      {(tl.data?.notes ?? []).length > 0 && <div className="mb-3 space-y-2">{tl.data!.notes.map((n: string, i: number) => <Notice key={i} tone="warn">⚠ {n}</Notice>)}</div>}
      {caseId && <form onSubmit={add} className="panel mb-3 flex flex-wrap items-end gap-2 p-3"><Field label="Analyst event time (local)"><input className="input" type="datetime-local" required value={ts} onChange={(e) => setTs(e.target.value)} /></Field>
        <div className="min-w-[14rem] flex-1"><Field label="Event description"><input className="input" required minLength={3} value={title} onChange={(e) => setTitle(e.target.value)} /></Field></div><button className="btn-primary">Add event</button>{err && <span className="text-sm text-red-400">{err}</span>}</form>}
      <Card>{!caseId ? <Empty title="No cases available" /> : tl.loading ? <Loading /> : tl.error ? <ErrorBox msg={tl.error} retry={tl.reload} /> : !tl.data?.events.length ? <Empty title="No events match" /> : (
        <Table head={[utc ? "Time (UTC)" : "Local time", "Event", "Evidence", "Source", "Provenance"]}>{tl.data.events.map((e: Row) => (<tr key={e.id}>
          <td className="td whitespace-nowrap font-mono text-xs">{utc ? e.timestamp_utc : local(e.timestamp_utc)}</td><td className="td">{e.title}</td><td className="td font-mono">{e.evidence_id ?? "—"}</td>
          <td className="td"><span className="badge bg-cyan-500/10 text-cyan-500">{e.source}</span></td><td className="td muted text-xs">{e.provenance}</td></tr>))}</Table>)}
        <p className="muted mt-3 text-xs">{tl.data?.note}</p></Card>
    </Page>
  );
}

export function CustodyLedger() {
  const [ev, setEv] = useState(""); const [action, setAction] = useState("");
  const { data, loading, error, reload } = useApi<Row[]>(`/api/custody${q({ evidence_id: ev, action })}`);
  const [ver, setVer] = useState<Row | null>(null); const [xfer, setXfer] = useState({ id: "", to: "", reason: "" }); const [msg, setMsg] = useState("");
  const verify = async () => setVer(await api("/api/custody/verify"));
  const transfer = async (e: FormEvent) => { e.preventDefault(); setMsg(""); try { await api(`/api/evidence/${xfer.id}/transfer`, { body: { to_username: xfer.to, reason: xfer.reason } }); setXfer({ id: "", to: "", reason: "" }); reload(); } catch (x: any) { setMsg(x.message); } };
  return (
    <Page title="Chain-of-custody ledger" subtitle="Append-only, hash-linked history of registration, access, verification, analysis, export and transfer." actions={<button className="btn-primary" onClick={verify}>Verify ledger integrity</button>}>
      {ver && <div className="mb-3">{ver.valid ? <Notice>✔ Chain intact — {ver.total_entries} entries verified.</Notice> : <ErrorBox msg={`✖ Chain BROKEN at entry #${ver.first_broken_seq}: ${ver.reason}`} />}</div>}
      <div className="mb-3"><Notice tone="warn">This ledger is tamper-evident, not tamper-proof. It provides no independent trusted timestamping and does not replace legally mandated chain-of-custody procedures.</Notice></div>
      <form onSubmit={transfer} className="panel mb-3 grid gap-2 p-3 md:grid-cols-4"><input className="input" required placeholder="Evidence ID (EV-0001)" value={xfer.id} onChange={(e) => setXfer({ ...xfer, id: e.target.value })} /><input className="input" required placeholder="Recipient username" value={xfer.to} onChange={(e) => setXfer({ ...xfer, to: e.target.value })} />
        <input className="input" required minLength={3} placeholder="Reason for transfer" value={xfer.reason} onChange={(e) => setXfer({ ...xfer, reason: e.target.value })} /><button className="btn-ghost justify-center">Record transfer</button>{msg && <div className="text-sm text-red-400 md:col-span-4">{msg}</div>}</form>
      <div className="mb-3 flex gap-2"><SearchBox value={ev} onChange={setEv} placeholder="Evidence ID" /><Select label="Action" value={action} onChange={setAction} options={["registered", "accessed", "hash_verified", "hash_MISMATCH", "analyzed", "finding_reviewed", "exported", "transferred", "disposed"]} /></div>
      <Card>{loading ? <Loading /> : error ? <ErrorBox msg={error} retry={reload} /> : !data?.length ? <Empty title="No custody events" /> : (
        <Table head={["#", "UTC time", "Evidence", "Action", "Actor", "Details", "Entry hash"]}>{data.map((r) => (<tr key={r.seq}><td className="td">{r.seq}</td><td className="td whitespace-nowrap text-xs">{r.timestamp_utc}</td><td className="td font-mono">{r.evidence_id}</td>
          <td className="td">{r.action.includes("MISMATCH") ? <Badge v="mismatch" /> : r.action}</td><td className="td">{r.actor}</td><td className="td hash max-w-xs">{JSON.stringify(r.details)}</td><td className="td hash" title={r.entry_hash}>{r.entry_hash.slice(0, 12)}…</td></tr>))}</Table>)}</Card>
    </Page>
  );
}

export function AuditViewer() {
  const [action, setAction] = useState(""); const [actor, setActor] = useState("");
  const { data, loading, error, reload } = useApi<Row[]>(`/api/audit${q({ action, actor })}`); const [ver, setVer] = useState<Row | null>(null);
  return (
    <Page title="Audit log" subtitle="Hash-linked record of authentication, administrative and analytical actions." actions={<button className="btn-primary" onClick={async () => setVer(await api("/api/audit/verify"))}>Verify audit chain</button>}>
      {ver && <div className="mb-3">{ver.valid ? <Notice>✔ Audit chain intact — {ver.total_entries} entries.</Notice> : <ErrorBox msg={`✖ Audit chain BROKEN at #${ver.first_broken_seq}: ${ver.reason}`} />}</div>}
      <div className="mb-3 flex gap-2"><SearchBox value={action} onChange={setAction} placeholder="Action contains…" /><SearchBox value={actor} onChange={setActor} placeholder="Exact actor" /></div>
      <Card>{loading ? <Loading /> : error ? <ErrorBox msg={error} retry={reload} /> : !data?.length ? <Empty title="No entries" /> : (
        <Table head={["#", "UTC time", "Actor", "Action", "IP", "Details"]}>{data.map((r) => (<tr key={r.seq}><td className="td">{r.seq}</td><td className="td whitespace-nowrap text-xs">{r.timestamp_utc}</td><td className="td">{r.actor}</td><td className="td font-mono text-xs">{r.action}</td><td className="td">{r.ip}</td><td className="td hash max-w-sm">{JSON.stringify(r.details)}</td></tr>))}</Table>)}</Card>
    </Page>
  );
}
