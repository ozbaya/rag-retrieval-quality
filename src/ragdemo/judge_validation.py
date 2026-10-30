"""Human validation of the LLM judge.
  export: uv run python -m ragdemo.judge_validation export --run <run_id> --n 30
          -> results/<run_id>/judge_validation.csv  (fill the human_* columns in a spreadsheet, save as CSV)
  score:  uv run python -m ragdemo.judge_validation score --run <run_id>"""
import argparse
import csv
import json
import random

from .db import connect
from .settings import ROOT
from .stats import cohen_kappa

COLS = ["question_id", "pipeline_id", "question", "reference_answer", "answer", "unit", "sentence_index",
        "sentence", "judge_label", "human_label", "context_or_evidence"]


def cmd_export(a):
    rng = random.Random(11)
    with connect() as conn:
        rows = conn.execute(
            "select r.question_id, r.pipeline_id, r.answer, r.judge_outputs, q.payload, r.context_chunk_ids"
            " from run_results r join benchmark_runs b using (run_id)"
            " join eval_questions q on q.dataset_version=b.dataset_version and q.question_id=r.question_id"
            " where r.run_id=%s and not r.abstained and (q.payload->>'answerable')::boolean", (a.run,)).fetchall()
        by_pipe = {}
        for r in rows:
            by_pipe.setdefault(r[1], []).append(r)
        sample = []
        for pid, rs in sorted(by_pipe.items()):
            sample += rng.sample(rs, min(a.n // 3, len(rs)))
        path = ROOT / "results" / a.run / "judge_validation.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as fh:
            w = csv.DictWriter(fh, COLS)
            w.writeheader()
            for qid, pid, answer, j, q, ctx_ids in sample:
                ev = "\n\n".join(e["text"] for e in q["required_evidence"])
                w.writerow({"question_id": qid, "pipeline_id": pid, "question": q["question"],
                            "reference_answer": q["reference_answer"], "answer": answer, "unit": "correctness",
                            "judge_label": j["correctness"]["label"], "human_label": "", "context_or_evidence": ev})
                ctx = "\n\n".join(f"[C{i}] {c}" for i, (c,) in enumerate(conn.execute(
                    "select content from chunks where chunk_id = any(%s) order by array_position(%s, chunk_id)",
                    (ctx_ids, ctx_ids)).fetchall(), start=1))
                for s in j.get("claims", []):
                    if not s["is_claim"]:
                        continue
                    sent = j["sentences"][s["index"]]["text"]
                    for unit, label in (("faithfulness", "yes" if s["supported_by_context"] else "no"),
                                        ("citation", s["supported_by_cited"])):
                        w.writerow({"question_id": qid, "pipeline_id": pid, "question": q["question"],
                                    "answer": answer, "unit": unit, "sentence_index": s["index"], "sentence": sent,
                                    "judge_label": label, "human_label": "", "context_or_evidence": ctx})
    print(f"wrote {path}. Hide the judge_label column while labeling, then fill human_label.")


def cmd_score(a):
    path = ROOT / "results" / a.run / "judge_validation.csv"
    rows = [r for r in csv.DictReader(path.open()) if r["human_label"].strip()]
    report = {}
    for unit in ("correctness", "faithfulness", "citation"):
        rs = [r for r in rows if r["unit"] == unit]
        if not rs:
            continue
        j = [r["judge_label"].strip() for r in rs]
        h = [r["human_label"].strip() for r in rs]
        agree = sum(x == y for x, y in zip(j, h)) / len(rs)
        report[unit] = {"n": len(rs), "agreement": round(agree, 3), "kappa": round(cohen_kappa(j, h), 3),
                        "provisional": agree < 0.8,
                        "disagreements": [{k: r[k] for k in ("question_id", "pipeline_id", "sentence",
                                                             "judge_label", "human_label")}
                                          for r in rs if r["judge_label"].strip() != r["human_label"].strip()]}
    (ROOT / "results" / a.run / "judge_validation.json").write_text(json.dumps(report, indent=2))
    for unit, r in report.items():
        print(f"{unit}: n={r['n']} agreement={r['agreement']} kappa={r['kappa']} provisional={r['provisional']}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export"); e.add_argument("--run", required=True); e.add_argument("--n", type=int, default=30)
    s = sub.add_parser("score"); s.add_argument("--run", required=True)
    a = ap.parse_args()
    {"export": cmd_export, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
