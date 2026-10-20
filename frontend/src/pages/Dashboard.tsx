import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { local, Row, useApi } from "../api";
import { Card, Empty, ErrorBox, Loading, Page, Stat } from "../components/ui";

const COLORS = ["#22d3ee", "#3b82f6", "#a78bfa", "#34d399", "#f59e0b", "#f87171", "#94a3b8"];
const toData = (o: Row) => Object.entries(o ?? {}).map(([name, value]) => ({ name, value }));

export default function Dashboard() {
  const { data, loading, error, reload } = useApi<Row>("/api/dashboard");
  if (loading) return <Loading />;
  if (error || !data) return <Page title="Overview"><ErrorBox msg={error ?? "No data"} retry={reload} /></Page>;
  const t = data.totals;
  const charts: [string, Row[], "bar" | "pie"][] = [["Case status", toData(data.case_status), "bar"], ["Evidence categories", toData(data.evidence_categories), "pie"], ["Flagged findings", toData(data.flagged_findings), "bar"]];
  return (
    <Page title="Investigation overview" subtitle="All figures are computed live from the local database.">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Cases" value={t.cases} /><Stat label="Evidence items" value={t.evidence} /><Stat label="Verified" value={t.verified} tone="text-emerald-500" />
        <Stat label="Integrity mismatches" value={t.mismatches} tone={t.mismatches ? "text-red-500" : ""} /><Stat label="Pending reviews" value={t.pending_reviews} tone={t.pending_reviews ? "text-amber-500" : ""} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {charts.map(([title, d, kind]) => (
          <Card key={title} title={title}>
            {d.length === 0 ? <Empty title="No data yet" /> : (
              <div className="h-56"><ResponsiveContainer>
                {kind === "pie" ? (
                  <PieChart><Pie data={d} dataKey="value" nameKey="name" outerRadius={80} label>{d.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart>
                ) : (
                  <BarChart data={d}><CartesianGrid strokeDasharray="3 3" stroke="#8884" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="value" radius={[4, 4, 0, 0]}>{d.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar></BarChart>
                )}
              </ResponsiveContainer></div>)}
          </Card>))}
        <Card title="Investigation activity (14 days, custody events)">
          <div className="h-56"><ResponsiveContainer><LineChart data={data.activity}><CartesianGrid strokeDasharray="3 3" stroke="#8884" /><XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} /><YAxis allowDecimals={false} /><Tooltip /><Line dataKey="events" stroke="#22d3ee" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
        </Card>
      </div>
      <Card title="Recent activity" className="mt-4">
        {data.recent_activity.length === 0 ? <Empty title="No activity recorded" /> : (
          <ul className="divide-y" style={{ borderColor: "var(--line)" }}>{data.recent_activity.map((r: Row) => (
            <li key={r.seq} className="flex flex-wrap justify-between gap-2 py-2 text-sm"><span><b>{r.action}</b> · {r.evidence_id} · {r.actor}</span><span className="muted">{local(r.timestamp_utc)}</span></li>))}</ul>)}
      </Card>
    </Page>
  );
}
