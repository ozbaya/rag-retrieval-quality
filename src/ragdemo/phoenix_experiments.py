"""OPTIONAL: log a scored run to Phoenix as three experiments for side-by-side comparison.
Requires local Phoenix running and `arize-phoenix-client` (checked against the client package in October 2026:
datasets.create_dataset(name, examples) and experiments.run_experiment(dataset, task, evaluators, experiment_name);
evaluator arguments are bound by name: input, output, expected, metadata). If the API differs,
skip this script: traces still go to Phoenix and the comparison lives in results/<run_id>/report.md.
Usage: uv run python -m ragdemo.phoenix_experiments --run <run_id>"""
import argparse

from phoenix.client import Client

from .db import connect

METRICS = ["hit_rate_at_5", "recall_at_5", "mrr_at_10", "ndcg_at_10", "answer_correctness", "faithfulness"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    with connect() as c:
        ds_version = c.execute("select dataset_version from benchmark_runs where run_id=%s", (a.run,)).fetchone()[0]
        qs = [r[0] for r in c.execute("select payload from eval_questions where dataset_version=%s"
                                      " order by question_id", (ds_version,)) if r[0]["status"] == "active"]
        rows = {(q, p): (ans, m) for q, p, ans, m in c.execute(
            "select question_id, pipeline_id, answer, metrics from run_results where run_id=%s", (a.run,))}
    px = Client()  # PHOENIX_ENDPOINT, default http://localhost:6006
    dataset = px.datasets.create_dataset(
        name=f"{ds_version}-{a.run}",
        examples=[{"input": {"question_id": q["question_id"], "question": q["question"]},
                   "output": {"reference_answer": q["reference_answer"]}} for q in qs])
    for pid in ("baseline", "intermediate", "advanced"):
        def task(input, pid=pid):
            return rows[(input["question_id"], pid)][0]

        def make_eval(metric, pid=pid):
            def evaluator(input):
                v = rows[(input["question_id"], pid)][1].get(metric)
                return "n/a" if not v or not v[1] else v[0] / v[1]  # string -> label only, no score
            evaluator.__name__ = metric
            return evaluator

        px.experiments.run_experiment(dataset=dataset, task=task, evaluators=[make_eval(m) for m in METRICS],
                                      experiment_name=f"{a.run}-{pid}")
    print("open http://localhost:6006 -> Datasets -> compare the three experiments")


if __name__ == "__main__":
    main()
