import { backendGet } from "@/lib/backend";
import type { Aggregate, BenchmarkResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

const ROWS: [string, string][] = [
  ["hit_rate_at_5", "Hit Rate@5"], ["recall_at_5", "Recall@5"], ["recall_at_5_multi_section", "Recall@5 (multi-section)"],
  ["full_coverage_at_5", "Full Coverage@5 (multi-section)"], ["mrr_at_10", "MRR@10"], ["ndcg_at_10", "nDCG@10"],
  ["answer_correctness", "Answer Correctness"], ["faithfulness", "Faithfulness"], ["citation_correctness", "Citation Correctness"],
  ["uncited_claim_rate", "Uncited Claim Rate"], ["correct_abstention_rate", "Correct Abstention Rate"],
  ["false_abstention_rate", "False Abstention Rate"], ["faithful_but_incorrect", "Faithful but incorrect"],
  ["context_tokens", "Context tokens (mean)"], ["latency_p50_ms", "Latency p50 (ms)"], ["latency_p95_ms", "Latency p95 (ms)"],
  ["est_cost_usd", "Est. cost per query (USD)"],
];
const PROVISIONAL: Record<string, string> = {
  answer_correctness: "correctness", faithfulness: "faithfulness", citation_correctness: "citation",
};

function fmt(v: number | null | undefined, m: string) {
  if (v == null) return "n/a";
  if (m.startsWith("latency") || m === "context_tokens") return Math.round(v).toLocaleString();
  if (m === "est_cost_usd") return `$${v.toFixed(5)}`;
  return v.toFixed(3);
}

function Chart({ get }: { get: (p: string, m: string) => Aggregate | undefined }) {
  const pts = ["baseline", "intermediate", "advanced"].map((p) => ({
    p, x: get(p, "latency_p50_ms")?.value ?? 0, y: get(p, "recall_at_5")?.value ?? 0,
  }));
  const maxX = Math.max(...pts.map((d) => d.x), 1) * 1.2;
  const W = 420, H = 240, P = 40;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-md" role="img" aria-label="Recall@5 versus p50 latency">
      <line x1={P} y1={H - P} x2={W - 10} y2={H - P} stroke="#999" />
      <line x1={P} y1={10} x2={P} y2={H - P} stroke="#999" />
      <text x={W / 2} y={H - 8} fontSize="11" textAnchor="middle">p50 latency (ms)</text>
      <text x={12} y={H / 2} fontSize="11" textAnchor="middle" transform={`rotate(-90 12 ${H / 2})`}>Recall@5</text>
      {pts.map((d) => {
        const cx = P + (d.x / maxX) * (W - P - 20), cy = H - P - d.y * (H - P - 20);
        return (
          <g key={d.p}>
            <circle cx={cx} cy={cy} r={5} fill="#2563eb" />
            <text x={cx + 8} y={cy + 4} fontSize="11">{d.p}</text>
          </g>
        );
      })}
    </svg>
  );
}

export default async function Benchmark() {
  const b = await backendGet<BenchmarkResponse>("/benchmark");
  const get = (p: string, m: string) => b.aggregates.find((a) => a.pipeline_id === p && a.metric === m);
  const diff = (k: string, m: string) => {
    const d = get(k, m);
    return d && d.value != null && d.ci_low != null && d.ci_high != null
      ? `${d.value >= 0 ? "+" : ""}${d.value.toFixed(3)} (${d.ci_low.toFixed(3)}, ${d.ci_high.toFixed(3)})` : "";
  };
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8">
      <h1 className="text-2xl font-semibold">Benchmark</h1>
      <p className="text-sm text-gray-600">
        <span className="rounded bg-green-100 px-1.5 py-0.5 font-medium text-green-800">Measured</span>{" "}
        Run {b.run_id} · dataset {b.dataset.dataset_version}: {b.dataset.n_questions} questions,{" "}
        {b.dataset.n_human_reviewed} human-reviewed · snapshot {b.snapshot_id} · generation {b.models.generation} ·
        judge {b.models.judge}. Differences show paired bootstrap 95% confidence intervals.
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b text-left">
              <th className="py-2 pr-4">Metric</th><th className="pr-4">n</th><th className="pr-4">Baseline</th>
              <th className="pr-4">Intermediate</th><th className="pr-4">Advanced</th>
              <th className="pr-4">Intermediate − Baseline</th><th>Advanced − Intermediate</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.filter(([m]) => get("baseline", m)).map(([m, label]) => {
              const jv = PROVISIONAL[m] ? b.judge_validation?.[PROVISIONAL[m]] : undefined;
              return (
                <tr key={m} className="border-b">
                  <td className="py-2 pr-4">{label}{jv?.provisional ? " (provisional)" : ""}</td>
                  <td className="pr-4">{get("baseline", m)?.n}</td>
                  {["baseline", "intermediate", "advanced"].map((p) => <td key={p} className="pr-4">{fmt(get(p, m)?.value, m)}</td>)}
                  <td className="pr-4">{diff("intermediate-minus-baseline", m)}</td>
                  <td>{diff("advanced-minus-intermediate", m)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Chart get={get} />
      <p className="text-xs text-gray-500">
        Answer metrics are LLM-judged and validated against human labels on a sample:{" "}
        {Object.entries(b.judge_validation ?? {}).map(([k, v]) => `${k} ${Math.round(v.agreement * 100)}% agreement (n=${v.n})`).join(", ") || "not yet reported"}.
      </p>
    </main>
  );
}

