"""Interactive human review in the terminal. Saves after every decision; safe to stop and resume.
Usage: uv run python -m ragdemo.evalset.review --name k8s-eval --reviewer And"""
import argparse
import datetime as dt
import textwrap

from ..db import connect
from ..retrieval import load_chunks
from ..settings import ROOT
from .common import read_jsonl, write_jsonl

PRIORITY = {"multi_section": 0, "unanswerable": 1, "near_duplicate": 2, "exact_term": 3, "single_section": 4}


def show_evidence(conn, it):
    for e in it["required_evidence"]:
        text = conn.execute("select normalized_text from documents where snapshot_id=%s and doc_id=%s",
                            (it["snapshot_id"], e["doc_id"])).fetchone()[0]
        before, after = text[max(0, e["start"] - 300):e["start"]], text[e["end"]:e["end"] + 300]
        print(f"\n  [{e['evidence_id']}] {e['doc_id']}  [{e['start']}, {e['end']})")
        print(textwrap.indent(f"...{before}>>>{e['text']}<<<{after}...", "    "))
    if not it["answerable"]:
        print("\n  Top retrieved passages (check none of them answers the question):")
        for c in load_chunks(conn, it.get("unanswerable_check_chunks", [])):
            print(textwrap.indent(f"- {c['title']} > {c['section_path']}\n{c['content'][:500]}", "    "))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="k8s-eval")
    ap.add_argument("--reviewer", required=True)
    args = ap.parse_args()
    path = ROOT / "data" / "evalsets" / f"{args.name}-validated.jsonl"
    items = read_jsonl(path)
    queue = sorted((i for i in items if i["status"] == "active"
                    and i["validation"]["human_review_status"] == "unreviewed"),
                   key=lambda i: (PRIORITY[i["question_type"]], i["question_id"]))
    print(f"{len(queue)} items to review. Keys: a=accept  e=edit text  r=reject  s=skip  q=quit")
    with connect() as conn:
        for it in queue:
            v = it["validation"]
            print("\n" + "=" * 100)
            print(f"{it['question_id']}  type={it['question_type']}  validator={v['validator_verdict']}  "
                  f"notes={v['validator_output'].get('notes', '')}")
            print(f"\nQ: {it['question']}\nReference answer: {it['reference_answer']}")
            show_evidence(conn, it)
            choice = input("\n[a/e/r/s/q] > ").strip().lower()
            if choice == "q":
                break
            if choice == "s":
                continue
            if choice == "e":
                q = input("New question (Enter keeps current): ").strip()
                a = input("New reference answer (Enter keeps current): ").strip()
                it["question"] = q or it["question"]
                it["reference_answer"] = a or it["reference_answer"]
                v["human_review_status"] = "edited"
            elif choice == "r":
                v["human_review_status"] = "rejected"
                it["status"] = "rejected"
            else:
                v["human_review_status"] = "accepted"
            v["reviewer"] = args.reviewer
            v["reviewed_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            v["notes"] = input("Notes (optional): ").strip()
            write_jsonl(path, items)
    reviewed = sum(i["validation"]["human_review_status"] in ("accepted", "edited") for i in items)
    print(f"human-reviewed (accepted or edited): {reviewed}")


if __name__ == "__main__":
    main()
