"use client";
import { useState } from "react";
import type { Chunk, PipelineResult } from "@/lib/types";

function rankIn(stages: PipelineResult["stages"], stage: string, id: string) {
  return stages[stage]?.find((s) => s.chunk_id === id)?.rank;
}

function AnswerText({ text, top5, onCite }: { text: string; top5: Chunk[]; onCite: (i: number) => void }) {
  const parts = text.split(/(\[C\d+\])/g);
  return (
    <p className="text-sm leading-6 whitespace-pre-wrap">
      {parts.map((p, i) => {
        const m = p.match(/^\[C(\d+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const n = Number(m[1]);
        return (
          <button key={i} onClick={() => onCite(n - 1)} disabled={!top5[n - 1]}
            className="mx-0.5 rounded bg-blue-100 px-1 text-xs font-medium text-blue-800 hover:bg-blue-200">
            C{n}
          </button>
        );
      })}
    </p>
  );
}

export default function PipelineColumn({ name, desc, r }: { name: string; desc: string; r: PipelineResult }) {
  const [open, setOpen] = useState<number | null>(null);
  const total = r.latency_ms ? Object.values(r.latency_ms).reduce((a, b) => a + b, 0) : 0;
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-gray-200 p-4">
      <header>
        <h3 className="font-semibold">{name}</h3>
        <p className="text-xs text-gray-500">{desc}</p>
      </header>
      <div className="rounded bg-gray-50 p-3">
        <AnswerText text={r.answer} top5={r.top5} onCite={setOpen} />
      </div>
      {r.metrics && (
        <dl className="grid grid-cols-2 gap-x-2 text-xs">
          {r.correctness && (<><dt className="text-gray-500">Answer correctness</dt><dd>{r.correctness}</dd></>)}
          {"hit_rate_at_5" in r.metrics && (<><dt className="text-gray-500">Hit@5</dt><dd>{r.metrics.hit_rate_at_5 ? "yes" : "no"}</dd></>)}
          {"recall_at_5" in r.metrics && (<><dt className="text-gray-500">Recall@5</dt><dd>{r.metrics.recall_at_5.toFixed(2)}</dd></>)}
          {"mrr_at_10" in r.metrics && (<><dt className="text-gray-500">MRR@10</dt><dd>{r.metrics.mrr_at_10.toFixed(2)}</dd></>)}
        </dl>
      )}
      <p className="text-xs text-gray-500">
        {Math.round(total)} ms total
        {r.est_cost_usd != null ? ` · est. $${Number(r.est_cost_usd).toFixed(4)}` : " · cost not priced"}
      </p>
      <ol className="flex flex-col gap-2">
        {r.top5.map((c, i) => {
          const d = rankIn(r.stages, "dense", c.chunk_id);
          const k = rankIn(r.stages, "keyword", c.chunk_id);
          const f = rankIn(r.stages, "fused", c.chunk_id);
          return (
            <li key={c.chunk_id} className={`rounded border p-2 text-xs ${open === i ? "border-blue-400" : "border-gray-200"}`}>
              <button className="w-full text-left" onClick={() => setOpen(open === i ? null : i)}>
                <span className="font-medium">C{i + 1}. {c.title}</span>
                {c.section_path && <span className="text-gray-500"> › {c.section_path}</span>}
                {r.stages.reranked && (
                  <span className="block text-gray-500">
                    dense #{d ?? "–"} · keyword #{k ?? "–"} · fused #{f ?? "–"} · reranked #{i + 1}
                  </span>
                )}
              </button>
              {open === i && (
                <div className="mt-2 border-t pt-2">
                  <p className="whitespace-pre-wrap text-gray-700">{c.content}</p>
                  <a className="text-blue-700 underline" href={c.source_url} target="_blank" rel="noreferrer">Source page</a>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

