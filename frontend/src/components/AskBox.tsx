"use client";
import { useState } from "react";
import PipelineColumn from "./PipelineColumn";
import { PIPELINES, type PipelineResult, type PipelineId } from "@/lib/types";

export default function AskBox() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [res, setRes] = useState<Record<PipelineId, PipelineResult> | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(""); setRes(null);
    const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) setErr(j.detail ?? "Something went wrong."); else setRes(j.pipelines);
    setBusy(false);
  }
  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={submit} className="flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={300} minLength={3} required
          placeholder="Ask about Kubernetes concepts or tasks" className="flex-1 rounded border px-3 py-2 text-sm" />
        <button disabled={busy} className="rounded bg-blue-600 px-4 py-2 text-sm text-white disabled:opacity-50">
          {busy ? "Running…" : "Ask"}
        </button>
      </form>
      {err && <p className="text-sm text-red-700">{err}</p>}
      {res && (
        <>
          <p className="text-xs text-gray-500">
            <span className="rounded bg-amber-100 px-1.5 py-0.5 font-medium text-amber-800">Live</span>{" "}
            No ground truth for free-text questions, so quality is not scored.
          </p>
          <div className="grid gap-4 md:grid-cols-3">
            {PIPELINES.map((pl) => res[pl.id] && <PipelineColumn key={pl.id} name={pl.name} desc={pl.desc} r={res[pl.id]} />)}
          </div>
        </>
      )}
    </div>
  );
}
