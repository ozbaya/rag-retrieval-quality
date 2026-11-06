"use client";
import { useState } from "react";
import PipelineColumn from "./PipelineColumn";
import { PIPELINES, type Preset } from "@/lib/types";

export default function PresetExplorer({ presets, runId }: { presets: Preset[]; runId: string }) {
  const [sel, setSel] = useState(0);
  const p = presets[sel];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {presets.map((x, i) => (
          <button key={x.question_id} onClick={() => setSel(i)}
            className={`rounded-full border px-3 py-1 text-sm ${i === sel ? "border-blue-600 bg-blue-50" : "border-gray-300"}`}>
            {x.question}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-500">
        <span className="rounded bg-green-100 px-1.5 py-0.5 font-medium text-green-800">Measured</span>{" "}
        From benchmark run {runId}. Question type: {p.question_type}
        {p.answerable ? "" : " (not answered by the docs; the correct response is to abstain)"}. Review status: {p.human_review_status}.
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        {PIPELINES.map((pl) => p.pipelines[pl.id] && (
          <PipelineColumn key={pl.id} name={pl.name} desc={pl.desc} r={p.pipelines[pl.id]} />
        ))}
      </div>
    </div>
  );
}

