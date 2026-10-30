"""Export a scored run to results/<run_id>/ and print a Markdown summary.
Usage: uv run python -m ragdemo.report --run <run_id>"""
import argparse
import json

from .db import connect
from .settings import ROOT

HEADLINE = ["hit_rate_at_5", "recall_at_5", "recall_at_5_multi_section", "full_coverage_at_5", "mrr_at_10",
            "ndcg_at_10", "answer_correctness", "answer_partially_correct", "faithfulness", "fully_faithful",
            "citation_correctness", "uncited_claim_rate", "correct_abstention_rate", "false_abstention_rate",
            "faithful_but_incorrect", "context_tokens", "latency_p50_ms", "latency_p95_ms", "est_cost_usd"]


def fmt(v, metric):
    if v is None:
        return "n/a"
    if metric.startswith("latency") or metric == "context_tokens":
        return f"{v:,.0f}"
    if metric == "est_cost_usd":
        return f"${v:.5f}"
    return f"{v:.3f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    with connect(dict_rows=True) as conn:
        run = conn.execute("select * from benchmark_runs where run_id=%s", (a.run,)).fetchone()
        ds = conn.execute("select * from eval_datasets where dataset_version=%s", (run["dataset_version"],)).fetchone()
        aggs = conn.execute("select * from run_aggregates where run_id=%s", (a.run,)).fetchall()
        rows = conn.execute("select * from run_results where run_id=%s order by question_id, pipeline_id",
                            (a.run,)).fetchall()
    out = ROOT / "results" / a.run
    out.mkdir(parents=True, exist_ok=True)
    (out / "run.json").write_text(json.dumps({"run": run, "dataset": ds}, default=str, indent=2))
    (out / "aggregates.json").write_text(json.dumps(aggs, default=float, indent=2))
    with (out / "per_question.jsonl").open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r, default=str) + "\n")

    agg = {(x["pipeline_id"], x["metric"]): x for x in aggs}
    lines = [f"# Benchmark {a.run}", "",
             f"Dataset `{ds['dataset_version']}`: {ds['n_questions']} questions, {ds['n_human_reviewed']} human-reviewed. "
             f"Snapshot `{run['snapshot_id']}`. Code `{run['git_sha']}`.", "",
             "| Metric | n | Baseline | Intermediate | Advanced | Int - Base (95% CI) | Adv - Int (95% CI) |",
             "|---|---|---|---|---|---|---|"]
    for m in HEADLINE:
        vals = [agg.get((p, m)) for p in ("baseline", "intermediate", "advanced")]
        if not any(vals):
            continue
        n = next((v["n"] for v in vals if v), "")
        cells = [fmt(float(v["value"]) if v and v["value"] is not None else None, m) for v in vals]
        diffs = []
        for key in ("intermediate-minus-baseline", "advanced-minus-intermediate"):
            d = agg.get((key, m))
            diffs.append(f"{float(d['value']):+.3f} ({float(d['ci_low']):+.3f}, {float(d['ci_high']):+.3f})"
                         if d and d["ci_low"] is not None else "")
        lines.append(f"| {m} | {n} | " + " | ".join(cells) + " | " + " | ".join(diffs) + " |")
    md = "\n".join(lines) + "\n"
    (out / "report.md").write_text(md)
    print(md)
    print(f"exported to {out}")


if __name__ == "__main__":
    main()
