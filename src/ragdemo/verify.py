"""Acceptance checks.
  uv run python -m ragdemo.verify chunks --snapshot <id>
  uv run python -m ragdemo.verify retrieval --run <run_id> [--n 20]
  uv run python -m ragdemo.verify aggregates --run <run_id>"""
import argparse
import json
import random

from .db import connect
from .retrieval import run_retrieval
from .settings import providers
from .stats import aggregate


def chunks(a):
    with connect() as c:
        bad = c.execute(
            "select count(*) from chunks k join documents d using (snapshot_id, doc_id)"
            " where k.snapshot_id=%s and substr(d.normalized_text, k.char_start + 1, k.char_end - k.char_start)"
            " <> k.content", (a.snapshot,)).fetchone()[0]
        dims = c.execute("select distinct vector_dims(embedding) from chunks where snapshot_id=%s",
                         (a.snapshot,)).fetchall()
        stats = c.execute("select chunking_config_id, count(*), round(avg(token_count)),"
                          " percentile_cont(0.95) within group (order by token_count) from chunks"
                          " where snapshot_id=%s group by 1 order by 1", (a.snapshot,)).fetchall()
    print(f"offset mismatches: {bad}  (must be 0)")
    print(f"embedding dims: {[d[0] for d in dims]}  (must be [{providers()['models']['embedding']['dims']}])")
    for s in stats:
        print(f"{s[0]}: chunks={s[1]} mean_tokens={s[2]} p95_tokens={s[3]:.0f}")


def retrieval(a):
    with connect() as c:
        run = c.execute("select snapshot_id from benchmark_runs where run_id=%s", (a.run,)).fetchone()
        rows = c.execute("select r.question_id, r.pipeline_id, r.retrieval, q.payload->>'question'"
                         " from run_results r join benchmark_runs b using (run_id)"
                         " join eval_questions q on q.dataset_version=b.dataset_version and q.question_id=r.question_id"
                         " where r.run_id=%s", (a.run,)).fetchall()
        sample = random.Random(3).sample(rows, min(a.n, len(rows)))
        diffs = 0
        for qid, pid, stored, question in sample:
            again = run_retrieval(c, pid, run[0], question)
            if again["final"] != stored["final"]:
                diffs += 1
                print(f"DIFF {qid}/{pid}")
    print(f"retrieval reruns: {len(sample)} checked, {diffs} differ "
          "(dense and keyword must be identical; small rerank differences are possible and must be noted)")


def aggregates(a):
    with connect() as c:
        rows = c.execute("select pipeline_id, metrics from run_results where run_id=%s", (a.run,)).fetchall()
        stored = {(p, m): (None if v is None else float(v), n) for p, m, v, n in c.execute(
            "select pipeline_id, metric, value, n from run_aggregates where run_id=%s", (a.run,))}
    per = {}
    for pid, m in rows:
        for k, v in m.items():
            per.setdefault((pid, k), []).append(tuple(v))
    bad = 0
    for key, pairs in per.items():
        value, n = aggregate(pairs)
        s = stored.get(key)
        if s is None or n != s[1] or (value is None) != (s[0] is None) or (value is not None and abs(value - s[0]) > 1e-9):
            bad += 1
            print("MISMATCH", key, value, n, s)
    print(f"aggregates checked: {len(per)}, mismatches: {bad} (must be 0)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("chunks"); s.add_argument("--snapshot", required=True)
    s = sub.add_parser("retrieval"); s.add_argument("--run", required=True); s.add_argument("--n", type=int, default=20)
    s = sub.add_parser("aggregates"); s.add_argument("--run", required=True)
    a = ap.parse_args()
    {"chunks": chunks, "retrieval": retrieval, "aggregates": aggregates}[a.cmd](a)


if __name__ == "__main__":
    main()
