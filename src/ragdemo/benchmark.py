"""Benchmark runner. Stages: generate -> judge -> score. Each stage is resumable.
Usage:
  uv run python -m ragdemo.benchmark new --snapshot <id> --dataset k8s-eval-v0 --notes "E1 defaults"
  uv run python -m ragdemo.benchmark generate --run <run_id> [--workers 4]
  uv run python -m ragdemo.benchmark judge --run <run_id> [--workers 4]
  uv run python -m ragdemo.benchmark score --run <run_id>
"""
import argparse
import datetime as dt
import hashlib
import json
import secrets
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import metrics as M
from .cost import estimate
from .db import connect
from .generation import generate, split_sentences
from .judge import judge_claims, judge_correct
from .retrieval import embed_query, load_chunks, run_retrieval
from .settings import ROOT, model, pipelines, providers
from .stats import aggregate, paired_bootstrap_diff
from .tracing import init_tracing

PIPELINE_IDS = ["baseline", "intermediate", "advanced"]
PROMPTS = ["gen-v1-system", "gen-v1-user", "judge-claims-v1", "judge-correct-v1"]
_local = threading.local()


def conn():
    if not hasattr(_local, "conn"):
        _local.conn = connect()
    return _local.conn


def file_hash(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:12]


def git_sha():
    sha = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet"]).returncode != 0
    return sha + ("-dirty" if dirty else "")


def questions(run):
    rows = conn().execute("select payload from eval_questions where dataset_version=%s order by question_id",
                          (run["dataset_version"],)).fetchall()
    return [r[0] for r in rows if r[0]["status"] == "active"]


def get_run(run_id):
    row = conn().execute("select run_id, snapshot_id, dataset_version from benchmark_runs where run_id=%s",
                         (run_id,)).fetchone()
    return {"run_id": row[0], "snapshot_id": row[1], "dataset_version": row[2]}


# ---------------- new ----------------
def cmd_new(a):
    sha = git_sha()
    if sha.endswith("-dirty") and not a.allow_dirty:
        raise SystemExit("Commit your changes first (or pass --allow-dirty for a throwaway run).")
    run_id = f"{dt.datetime.now(dt.timezone.utc):%Y%m%d-%H%M}-{secrets.token_hex(2)}"
    cfg = pipelines()
    prompt_versions = {p: file_hash(f"config/prompts/{p}.txt") for p in PROMPTS}
    prompt_versions["kwq"] = file_hash("sql/002_functions.sql")
    prompt_versions["pipelines_yaml"] = file_hash("config/pipelines.yaml")
    conn().execute(
        "insert into benchmark_runs (run_id, git_sha, snapshot_id, dataset_version, pipeline_configs,"
        " embedding_model, embedding_dims, rerank_model, generation_model, judge_model, prompt_versions,"
        " coverage_threshold, pricing_table_version, notes) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (run_id, sha, a.snapshot, a.dataset, json.dumps(cfg), model("embedding"),
         providers()["models"]["embedding"]["dims"], model("rerank"), model("generation"), model("judge"),
         json.dumps(prompt_versions), cfg["coverage_threshold"], providers()["pricing_version"], a.notes))
    print(f"run_id={run_id}")


# ---------------- generate ----------------
def generate_one(run, q):
    c = conn()
    done = {r[0] for r in c.execute("select pipeline_id from run_results where run_id=%s and question_id=%s",
                                    (run["run_id"], q["question_id"]))}
    todo = [p for p in PIPELINE_IDS if p not in done]
    if not todo:
        return
    qvec, embed_tokens = embed_query(q["question"])  # same query embedding for all three pipelines
    thr = pipelines()["coverage_threshold"]
    for pid in todo:
        r = run_retrieval(c, pid, run["snapshot_id"], q["question"], qvec=qvec)
        final_chunks = load_chunks(c, r["final"])
        ctx = final_chunks[: len(r["context_ids"])]
        g = generate(q["question"], ctx)
        usage = {**r["usage"], **g["usage"], "embed_tokens": embed_tokens}
        retrieval_metrics = M.retrieval_metrics(final_chunks, q, thr) if q["answerable"] else {}
        latency = {**r["timings_ms"], "generate": g["latency_ms"]}
        latency["total"] = round(sum(latency.values()), 1)
        c.execute(
            "insert into run_results (run_id, question_id, pipeline_id, retrieval, context_chunk_ids, context_tokens,"
            " answer, abstained, judge_outputs, metrics, usage, latency_ms, est_cost_usd)"
            " values (%s,%s,%s,%s,%s,%s,%s,%s,null,%s,%s,%s,%s) on conflict do nothing",
            (run["run_id"], q["question_id"], pid, json.dumps({"stages": r["stages"], "final": r["final"]}),
             r["context_ids"], sum(x["token_count"] for x in ctx), g["answer"], g["abstained"],
             json.dumps(retrieval_metrics), json.dumps(usage), json.dumps(latency), estimate(usage)))
    print(f"{q['question_id']}: generated {todo}")


def cmd_generate(a):
    init_tracing()
    run = get_run(a.run)
    qs = questions(run)
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda q: generate_one(run, q), qs))


# ---------------- judge ----------------
def judge_one(run, q, pid):
    c = conn()
    answer, abstained, ctx_ids = c.execute(
        "select answer, abstained, context_chunk_ids from run_results where run_id=%s and question_id=%s"
        " and pipeline_id=%s", (run["run_id"], q["question_id"], pid)).fetchone()
    out = {"sentences": split_sentences(answer)}
    if not abstained:
        out["claims"] = judge_claims(q["question"], out["sentences"], load_chunks(c, ctx_ids))["sentences"]
    if q["answerable"]:
        out["correctness"] = ({"label": "incorrect", "rationale": "abstained"} if abstained else
                              judge_correct(q["question"], answer, q["reference_answer"],
                                            [e["text"] for e in q["required_evidence"]]))
    c.execute("update run_results set judge_outputs=%s where run_id=%s and question_id=%s and pipeline_id=%s",
              (json.dumps(out), run["run_id"], q["question_id"], pid))
    print(f"{q['question_id']}/{pid}: judged")


def cmd_judge(a):
    run = get_run(a.run)
    qs = {q["question_id"]: q for q in questions(run)}
    todo = conn().execute("select question_id, pipeline_id from run_results where run_id=%s and judge_outputs is null",
                          (run["run_id"],)).fetchall()
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(lambda t: judge_one(run, qs[t[0]], t[1]), todo))


# ---------------- score ----------------
def answer_metrics(q, abstained, j):
    claims = [s for s in j.get("claims", []) if s["is_claim"]]
    cited = [s for s in claims if s["supported_by_cited"] in ("yes", "no")]
    label = j.get("correctness", {}).get("label")
    faith = (sum(s["supported_by_context"] for s in claims) / len(claims)) if claims else None
    m = {
        "answer_correctness": (1.0 if label == "correct" else 0.0, 1) if q["answerable"] else (0.0, 0),
        "answer_partially_correct": (1.0 if label == "partially_correct" else 0.0, 1) if q["answerable"] else (0.0, 0),
        "faithfulness": (faith, 1) if faith is not None else (0.0, 0),
        "fully_faithful": (1.0 if faith == 1.0 else 0.0, 1) if faith is not None else (0.0, 0),
        "citation_correctness": (sum(s["supported_by_cited"] == "yes" for s in cited), len(cited)),
        "uncited_claim_rate": (sum(s["supported_by_cited"] == "no_citation" for s in claims), len(claims)),
        "correct_abstention_rate": (1.0 if abstained else 0.0, 1) if not q["answerable"] else (0.0, 0),
        "false_abstention_rate": (1.0 if abstained else 0.0, 1) if q["answerable"] else (0.0, 0),
        "faithful_but_incorrect": ((1.0 if faith == 1.0 and label == "incorrect" else 0.0, 1)
                                   if q["answerable"] and not abstained and faith is not None else (0.0, 0)),
    }
    return m


def cmd_score(a):
    run = get_run(a.run)
    qs = {q["question_id"]: q for q in questions(run)}
    rows = conn().execute(
        "select question_id, pipeline_id, abstained, judge_outputs, metrics, latency_ms, est_cost_usd, context_tokens"
        " from run_results where run_id=%s", (run["run_id"],)).fetchall()
    per = {p: {} for p in PIPELINE_IDS}      # pipeline -> metric -> {qid: (num, den)}
    lat = {p: [] for p in PIPELINE_IDS}
    missing_judge = 0
    for qid, pid, abstained, j, rm, latency, cost, ctx_tokens in rows:
        if qid not in qs:
            continue
        if j is None:
            missing_judge += 1
            continue
        m = {k: tuple(v) for k, v in rm.items()}
        m.update(answer_metrics(qs[qid], abstained, j))
        m["context_tokens"] = (float(ctx_tokens), 1)
        if cost is not None:
            m["est_cost_usd"] = (float(cost), 1)
        conn().execute("update run_results set metrics=%s where run_id=%s and question_id=%s and pipeline_id=%s",
                       (json.dumps(m), run["run_id"], qid, pid))
        for k, v in m.items():
            per[pid].setdefault(k, {})[qid] = v
        lat[pid].append(latency["total"])
    if missing_judge:
        raise SystemExit(f"{missing_judge} rows not judged yet; run the judge stage first.")
    conn().execute("delete from run_aggregates where run_id=%s", (run["run_id"],))
    for pid in PIPELINE_IDS:
        for metric, by_q in per[pid].items():
            value, n = aggregate(list(by_q.values()))
            conn().execute("insert into run_aggregates values (%s,%s,%s,%s,%s,null,null)",
                           (run["run_id"], pid, metric, value, n))
        for name, pct in (("latency_p50_ms", 50), ("latency_p95_ms", 95)):
            conn().execute("insert into run_aggregates values (%s,%s,%s,%s,%s,null,null)",
                           (run["run_id"], pid, name, float(np.percentile(lat[pid], pct)), len(lat[pid])))
    for a_id, b_id in (("intermediate", "baseline"), ("advanced", "intermediate"), ("advanced", "baseline")):
        for metric in per[a_id]:
            d, lo, hi = paired_bootstrap_diff(per[a_id][metric], per[b_id].get(metric, {}))
            if d is not None:
                conn().execute("insert into run_aggregates values (%s,%s,%s,%s,%s,%s,%s)",
                               (run["run_id"], f"{a_id}-minus-{b_id}", metric, d,
                                len(set(per[a_id][metric]) & set(per[b_id][metric])), lo, hi))
    print("scored; now run: uv run python -m ragdemo.report --run", run["run_id"])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("--snapshot", required=True); n.add_argument("--dataset", required=True)
    n.add_argument("--notes", default=""); n.add_argument("--allow-dirty", action="store_true")
    for name in ("generate", "judge", "score"):
        s = sub.add_parser(name); s.add_argument("--run", required=True); s.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    {"new": cmd_new, "generate": cmd_generate, "judge": cmd_judge, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
