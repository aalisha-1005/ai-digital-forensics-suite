import { useCallback, useEffect, useState } from "react";

export type Row = Record<string, any>;
let csrf = "";
export const setCsrf = (t: string) => { csrf = t; };

export class ApiError extends Error { constructor(public status: number, msg: string) { super(msg); } }

export async function api<T = any>(path: string, opts: { method?: string; body?: any; form?: FormData } = {}): Promise<T> {
  const method = opts.method ?? (opts.body || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = {};
  if (method !== "GET") headers["X-CSRF-Token"] = csrf;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  const res = await fetch(path, { method, headers, body, credentials: "include" });
  if (!res.ok) {
    let msg = res.statusText;
    try { const j = await res.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* ignore */ }
    throw new ApiError(res.status, msg);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export function useApi<T = any>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(!!path);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    if (!path) return;
    setLoading(true); setError(null);
    api<T>(path).then(setData).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [path]);
  useEffect(load, [load]);
  return { data, loading, error, reload: load };
}

export const q = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") p.set(k, String(v)); });
  const s = p.toString();
  return s ? `?${s}` : "";
};

export const local = (utc?: string | null) => (utc ? new Date(utc).toLocaleString() : "—");
