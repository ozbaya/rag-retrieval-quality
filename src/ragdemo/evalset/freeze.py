"""Freeze a dataset version and register it.
Usage: uv run python -m ragdemo.evalset.freeze --name k8s-eval --version k8s-eval-v0"""
import argparse
import hashlib
import json

from ..db import connect
from ..settings import ROOT
from .common import read_jsonl, write_jsonl

KEEP = ["question_id", "dataset_version", "snapshot_id", "question", "question_type", "answerable",
        "reference_answer", "required_evidence", "optional_evidence", "provenance", "validation", "status", "tags"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="k8s-eval")
    ap.add_argument("--version", required=True)
    ap.add_argument("--require-reviewed-types", default="multi_section,unanswerable")
    args = ap.parse_args()
    items = read_jsonl(ROOT / "data" / "evalsets" / f"{args.name}-validated.jsonl")
    must = set(args.require_reviewed_types.split(","))
    for it in items:
        it["dataset_version"] = args.version
        it.setdefault("tags", [])
        unreviewed_required = (it["question_type"] in must
                               and it["validation"]["human_review_status"] == "unreviewed")
        if it["status"] == "active" and (unreviewed_required or it["validation"]["validator_verdict"] == "flagged"
                                         and it["validation"]["human_review_status"] == "unreviewed"):
            it["status"] = "rejected"
            it["validation"]["notes"] += " [excluded at freeze: needs human review]"
    out = [{k: it.get(k) for k in KEEP} for it in items]
    path = ROOT / "datasets" / f"{args.version}.jsonl"
    write_jsonl(path, out)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    active = [i for i in out if i["status"] == "active"]
    reviewed = sum(i["validation"]["human_review_status"] in ("accepted", "edited") for i in active)
    snapshot = active[0]["snapshot_id"]
    with connect() as conn:
        conn.execute("insert into eval_datasets values (%s,%s,%s,%s,%s)",
                     (args.version, snapshot, sha, len(active), reviewed))
        with conn.cursor() as cur:
            cur.executemany("insert into eval_questions values (%s,%s,%s)",
                            [(args.version, i["question_id"], json.dumps(i)) for i in out])
    by_type = {}
    for i in active:
        by_type[i["question_type"]] = by_type.get(i["question_type"], 0) + 1
    print(f"{args.version}: active={len(active)} human_reviewed={reviewed} by_type={by_type} sha256={sha[:12]}")


if __name__ == "__main__":
    main()
