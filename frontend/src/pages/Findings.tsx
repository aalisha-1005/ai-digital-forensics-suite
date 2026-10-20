import { useState } from "react";
import { api, q, Row, useApi } from "../api";
import { Badge, Card, Empty, ErrorBox, Loading, Notice, Page, Select } from "../components/ui";

export default function Findings() {
  const [category, setCategory] = useState(""); const [review, setReview] = useState("pending"); const [origin, setOrigin] = useState("");
  const { data, loading, error, reload } = useApi<Row[]>(`/api/findings${q({ category, review_status: review, origin })}`);
  const [text, setText] = useState<Record<number, string>>({}); const [msg, setMsg] = useState("");
  const decide = async (id: number, decision: string) => { setMsg(""); try { await api(`/api/findings/${id}/review`, { body: { decision, analyst_interpretation: text[id] ?? "" } }); reload(); } catch (x: any) { setMsg(x.message); } };
  return (
    <Page title="AI findings & analyst review" subtitle="Automated flags are leads. Only findings you accept, with a written interpretation, are treated as analyst conclusions.">
      <div className="mb-3"><Notice tone="warn">AI and rule outputs are not proof of wrongdoing. Document your reasoning and corroborate with independent evidence.</Notice></div>
      <div className="mb-3 flex flex-wrap gap-2"><Select label="Category" value={category} onChange={setCategory} options={["benign", "needs_review", "suspicious"]} />
        <Select label="Review" value={review} onChange={setReview} options={["pending", "accepted", "rejected"]} /><Select label="Origin" value={origin} onChange={setOrigin} options={["ai_model", "automated_rule", "analyst"]} /></div>
      {msg && <div className="mb-3"><ErrorBox msg={msg} /></div>}
      {loading ? <Loading /> : error ? <ErrorBox msg={error} retry={reload} /> : !data?.length ? <Card><Empty title="No findings match" hint="Run analysis on evidence to generate findings." /></Card> :
        <div className="space-y-3">{data.map((f) => (<Card key={f.id}>
          <div className="flex flex-wrap items-center gap-2"><Badge v={f.category} /><b className="text-sm">{f.title}</b><span className="muted text-xs">{f.evidence_id} · {f.case_id} · {f.origin.replace("_", " ")}{f.confidence != null && ` · confidence ${(f.confidence * 100).toFixed(0)}%`}</span><span className="ml-auto"><Badge v={f.review_status} /></span></div>
          <p className="mt-2 text-sm">{f.description}</p>
          {f.details?.top_features && <p className="muted mt-1 text-xs">Drivers: {f.details.top_features.map((t: Row) => `${t.feature} (${t.contribution > 0 ? "+" : ""}${t.contribution})`).join(", ")}</p>}
          {f.review_status === "pending" ? (<div className="mt-3 flex flex-wrap gap-2"><input className="input flex-1" placeholder="Analyst interpretation (required to accept)" value={text[f.id] ?? ""} onChange={(e) => setText({ ...text, [f.id]: e.target.value })} />
            <button className="btn-primary" onClick={() => decide(f.id, "accepted")}>Accept as finding</button><button className="btn-ghost" onClick={() => decide(f.id, "rejected")}>Reject</button></div>)
            : <p className="mt-2 text-xs"><span className="muted">Reviewed by {f.reviewed_by}:</span> {f.analyst_interpretation || "—"}</p>}
        </Card>))}</div>}
    </Page>
  );
}
