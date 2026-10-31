"""Locate evidence offsets, run auto-checks and independent validation (prompt qval-v1).
Usage: uv run python -m ragdemo.evalset.validate --snapshot <id> --name k8s-eval
Progress is saved after each question; rerunning resumes where it stopped (--fresh starts over)."""
import argparse
import json

from ..db import connect
from ..retrieval import load_chunks, run_retrieval
from ..settings import ROOT, model, prompt
from .common import openai_json, read_jsonl, verbatim_overlap, write_jsonl


def locate(text, quote, hint_start, hint_end, strict):
    """Exact match inside the source section (strict) or anywhere in the document. Half-open (start, end)."""
    q = quote.strip().strip('"').strip()
    if not q:
        return None
    pos = text.find(q, max(0, hint_start - 50), hint_end + 50) if strict else text.find(q)
    return (pos, pos + len(q)) if pos >= 0 else None


def _schema(**props):
    return {"type": "object", "additionalProperties": False, "required": list(props),
            "properties": {k: {"type": t} for k, t in props.items()}}


ANSWERABLE_SCHEMA = _schema(evidence_supports_answer="boolean", each_span_necessary="boolean",
                            question_is_clear="boolean", notes="string")
UNANSWERABLE_SCHEMA = _schema(answered_by_any_passage="boolean", question_is_clear="boolean", notes="string")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--name", default="k8s-eval")
    ap.add_argument("--fresh", action="store_true", help="ignore saved progress and validate every question again")
    args = ap.parse_args()
    src = ROOT / "data" / "evalsets" / f"{args.name}-draft.jsonl"
    partial = ROOT / "data" / "evalsets" / f"{args.name}-validated.partial.jsonl"
    items = read_jsonl(src)
    done = {}
    if partial.exists() and not args.fresh:
        for line in partial.read_text().splitlines():
            try:
                i = json.loads(line)
            except json.JSONDecodeError:  # line cut off when the previous run stopped
                continue
            if i["snapshot_id"] == args.snapshot:
                done[i["question_id"]] = i
        print(f"resuming: {len(done)} of {len(items)} questions already validated")
    system = prompt("qval-v1-system")
    with connect() as conn, partial.open("w") as progress:
        progress.writelines(json.dumps(i, ensure_ascii=False) + "\n" for i in done.values())
        docs = {r[0]: (r[1], r[2]) for r in conn.execute(
            "select doc_id, doc_version, normalized_text from documents where snapshot_id=%s", (args.snapshot,))}
        out = []
        for it in items:
            if it["question_id"] in done:
                out.append(done[it["question_id"]])
                continue
            it["snapshot_id"] = args.snapshot
            it.setdefault("optional_evidence", [])
            it["status"], reasons = "active", []
            req = []
            if it["answerable"]:
                for k, quote in enumerate(it["draft_quotes"], start=1):
                    found = None
                    for strict in (True, False):
                        for src_idx, s in enumerate(it["draft_sources"]):
                            version, text = docs[s["doc_id"]]
                            loc = locate(text, quote, s["start"], s["end"], strict)
                            if loc:
                                found = {"evidence_id": f"{it['question_id']}-r{k}", "doc_id": s["doc_id"],
                                         "doc_version": version, "start": loc[0], "end": loc[1],
                                         "text": text[loc[0]:loc[1]], "_src": src_idx}
                                break
                        if found:
                            break
                    if not found:
                        reasons.append(f"quote {k} not found verbatim")
                    else:
                        req.append(found)
                if not req:
                    reasons.append("no evidence located")
                if it["question_type"] == "multi_section" and len({e["_src"] for e in req}) < 2:
                    reasons.append("multi_section needs located evidence from both passages")
            for e in req:
                e.pop("_src", None)
            it["required_evidence"] = req
            ev_text = " ".join(e["text"] for e in req)
            overlap = verbatim_overlap(it["question"], ev_text) if req else 0.0
            if overlap > 0.7:
                reasons.append(f"question copies evidence (overlap {overlap:.2f})")
            auto = {"offsets_valid": all(docs[e["doc_id"]][1][e["start"]:e["end"]] == e["text"] for e in req),
                    "text_match": all(e["text"] for e in req), "verbatim_overlap": round(overlap, 2)}

            if it["answerable"] and not reasons:
                user = (f"Question: {it['question']}\nReference answer: {it['reference_answer']}\n\n" +
                        "\n\n".join(f"Evidence {i}:\n{e['text']}" for i, e in enumerate(req, start=1)) +
                        "\n\nReturn JSON with keys: evidence_supports_answer (bool), "
                        "each_span_necessary (bool), question_is_clear (bool), notes (string).")
                v = openai_json(model("validator"), system, user, ANSWERABLE_SCHEMA, "qval_answerable")
                verdict = "supported" if (v["evidence_supports_answer"] and v["each_span_necessary"]
                                          and v["question_is_clear"]) else "flagged"
            elif not it["answerable"]:
                r1 = run_retrieval(conn, "intermediate", args.snapshot, it["question"])
                r2 = run_retrieval(conn, "advanced", args.snapshot, it["question"])
                ids = list(dict.fromkeys(r1["final"][:5] + r2["final"][:5]))
                passages = load_chunks(conn, ids)
                it["unanswerable_check_chunks"] = ids
                user = (f"Question: {it['question']}\n\n" +
                        "\n\n".join(f"Passage {i}:\n{c['content']}" for i, c in enumerate(passages, start=1)) +
                        "\n\nReturn JSON with keys: answered_by_any_passage (bool), question_is_clear (bool), "
                        "notes (string).")
                v = openai_json(model("validator"), system, user, UNANSWERABLE_SCHEMA, "qval_unanswerable")
                verdict = "supported" if (not v["answered_by_any_passage"] and v["question_is_clear"]) else "flagged"
            else:
                v, verdict = {}, "not_run"
            if reasons:
                it["status"] = "rejected"
            it["validation"] = {"auto_checks": auto, "auto_reject_reasons": reasons,
                                "validator_model": model("validator"), "validator_prompt_version": "qval-v1",
                                "validator_output": v, "validator_verdict": verdict,
                                "human_review_status": "unreviewed", "reviewer": None, "reviewed_at": None,
                                "notes": ""}
            out.append(it)
            progress.write(json.dumps(it, ensure_ascii=False) + "\n")
            progress.flush()
            print(it["question_id"], it["status"], verdict, "; ".join(reasons))
    dst = ROOT / "data" / "evalsets" / f"{args.name}-validated.jsonl"
    write_jsonl(dst, out)
    partial.unlink()
    active = [i for i in out if i["status"] == "active"]
    print(f"active={len(active)} flagged={sum(i['validation']['validator_verdict'] == 'flagged' for i in active)}"
          f" rejected={len(out) - len(active)} -> {dst}")


if __name__ == "__main__":
    main()
