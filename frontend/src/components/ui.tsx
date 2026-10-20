import { ReactNode } from "react";

const TONES: Record<string, string> = {
  verified: "bg-emerald-500/15 text-emerald-500", benign: "bg-emerald-500/15 text-emerald-500", accepted: "bg-emerald-500/15 text-emerald-500",
  mismatch: "bg-red-500/15 text-red-500", suspicious: "bg-red-500/15 text-red-500", rejected: "bg-slate-500/20 text-slate-400",
  needs_review: "bg-amber-500/15 text-amber-500", pending: "bg-amber-500/15 text-amber-500", unverified: "bg-amber-500/15 text-amber-500",
  open: "bg-cyan-500/15 text-cyan-500", in_review: "bg-amber-500/15 text-amber-500", closed: "bg-slate-500/20 text-slate-400",
  critical: "bg-red-500/15 text-red-500", high: "bg-orange-500/15 text-orange-500", medium: "bg-cyan-500/15 text-cyan-500",
  low: "bg-slate-500/20 text-slate-400", disposed: "bg-slate-500/20 text-slate-400",
};
export const Badge = ({ v }: { v: string }) => <span className={`badge ${TONES[v] ?? "bg-slate-500/20 text-slate-400"}`}>{v.replace("_", " ")}</span>;

export const Page = ({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: ReactNode; children: ReactNode }) => (
  <div className="mx-auto max-w-7xl p-4 sm:p-6">
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-xl font-semibold tracking-tight">{title}</h1>{subtitle && <p className="muted mt-1 text-sm">{subtitle}</p>}</div>
      <div className="flex gap-2">{actions}</div>
    </div>
    {children}
  </div>
);

export const Card = ({ title, children, className = "" }: { title?: string; children: ReactNode; className?: string }) => (
  <section className={`panel p-4 ${className}`}>{title && <h2 className="mb-3 text-sm font-semibold">{title}</h2>}{children}</section>
);

export const Loading = ({ label = "Loading…" }: { label?: string }) => (
  <div role="status" className="muted flex items-center gap-2 p-6 text-sm"><span className="h-3 w-3 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />{label}</div>
);
export const ErrorBox = ({ msg, retry }: { msg: string; retry?: () => void }) => (
  <div role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-400">{msg} {retry && <button className="ml-2 underline" onClick={retry}>Retry</button>}</div>
);
export const Empty = ({ title, hint }: { title: string; hint?: string }) => (
  <div className="muted flex flex-col items-center gap-1 p-10 text-center"><div className="text-3xl" aria-hidden>🗂</div><p className="font-medium">{title}</p>{hint && <p className="text-sm">{hint}</p>}</div>
);
export const Notice = ({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) => (
  <div role="note" className={`rounded-lg border p-3 text-xs ${tone === "warn" ? "border-amber-500/40 bg-amber-500/10 text-amber-500" : "border-cyan-500/30 bg-cyan-500/10 text-cyan-500"}`}>{children}</div>
);
export const Stat = ({ label, value, tone }: { label: string; value: number | string; tone?: string }) => (
  <div className="panel p-4"><div className="muted text-xs uppercase tracking-wide">{label}</div><div className={`mt-1 text-2xl font-semibold ${tone ?? ""}`}>{value}</div></div>
);
export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <label className="block text-sm"><span className="muted mb-1 block text-xs">{label}</span>{children}</label>
);
export const Table = ({ head, children }: { head: string[]; children: ReactNode }) => (
  <div className="overflow-x-auto"><table className="w-full"><thead><tr>{head.map((h) => <th key={h} className="th">{h}</th>)}</tr></thead><tbody>{children}</tbody></table></div>
);
export const SearchBox = ({ value, onChange, placeholder = "Search…" }: { value: string; onChange: (v: string) => void; placeholder?: string }) => (
  <input className="input max-w-xs" aria-label="Search" placeholder={placeholder} value={value} onChange={(e) => onChange(e.target.value)} />
);
export const Select = ({ value, onChange, options, label }: { value: string; onChange: (v: string) => void; options: string[]; label: string }) => (
  <select className="input w-auto" aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
    <option value="">{label}: all</option>{options.map((o) => <option key={o} value={o}>{o.replace("_", " ")}</option>)}
  </select>
);
