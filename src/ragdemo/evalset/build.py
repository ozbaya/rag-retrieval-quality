"""Generate a draft eval set (prompt qgen-v1).
Usage: uv run python -m ragdemo.evalset.build --snapshot <id> --name k8s-eval --scale 1.6"""
import argparse
import random

import numpy as np

from ..db import connect
from ..keyword import extract_identifiers
from ..settings import ROOT, model, prompt
from .common import openai_json, write_jsonl

TARGET_V0 = {"single_section": 20, "near_duplicate": 12, "exact_term": 10, "multi_section": 10, "unanswerable": 8}

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["question", "reference_answer", "evidence_quotes"],
    "properties": {
        "question": {"type": "string"},
        "reference_answer": {"type": "string"},
        "evidence_quotes": {"type": "array", "items": {"type": "string"}},
    },
}


def load_struct_chunks(conn, snapshot):
    rows = conn.execute(
        "select c.chunk_id, c.doc_id, c.doc_version, c.char_start, c.char_end, c.section_path, c.content,"
        " c.token_count, c.embedding, d.title from chunks c join documents d using (snapshot_id, doc_id)"
        " where c.snapshot_id=%s and c.chunking_config_id='struct-v1' order by c.chunk_id", (snapshot,)).fetchall()
    keys = ["chunk_id", "doc_id", "doc_version", "char_start", "char_end", "section_path", "content",
            "token_count", "embedding", "title"]
    chunks = [dict(zip(keys, r)) for r in rows]
    emb = np.array([np.asarray(c["embedding"], dtype=np.float32) for c in chunks])
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    return chunks, emb


def pools(chunks, emb, rng):
    sims = emb @ emb.T
    doc = np.array([c["doc_id"] for c in chunks])
    other_doc = doc[:, None] != doc[None, :]
    best_other = np.where(other_doc, sims, -1).max(axis=1)
    usable = [i for i, c in enumerate(chunks) if c["token_count"] >= 120]
    near = [i for i in usable if best_other[i] >= 0.88]
    exact = [i for i in usable if len(extract_identifiers(chunks[i]["content"])) >= 2]
    pairs = []
    for i in rng.sample(usable, min(400, len(usable))):
        cand = [j for j in usable if j != i and 0.60 <= sims[i, j] <= 0.85
                and (chunks[j]["doc_id"] != chunks[i]["doc_id"] or chunks[j]["section_path"] != chunks[i]["section_path"])]
        if cand:
            pairs.append((i, rng.choice(cand)))
    sibling = {i: int(np.argmax(np.where(other_doc[i], sims[i], -1))) for i in near}
    return usable, near, exact, pairs, sibling


def passage(c):
    return f"Page: {c['title']}\nSection: {c['section_path'] or '-'}\n{c['content']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--name", default="k8s-eval")
    ap.add_argument("--scale", type=float, default=1.6, help="oversample to allow for rejections")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start-id", type=int, default=1, help="first question number, to merge batches without ID clashes")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    gen_model = model("question_generator")
    system = prompt("qgen-v1-system")
    with connect() as conn:
        chunks, emb = load_struct_chunks(conn, args.snapshot)
    usable, near, exact, pairs, sibling = pools(chunks, emb, rng)
    print(f"pools: usable={len(usable)} near_duplicate={len(near)} exact_term={len(exact)} pairs={len(pairs)}")

    items, n = [], args.start_id - 1
    plan = {k: round(v * args.scale) for k, v in TARGET_V0.items()}
    for qtype, count in plan.items():
        for _ in range(count):
            if qtype == "multi_section":
                i, j = rng.choice(pairs)
                srcs = [chunks[i], chunks[j]]
                task = ("Write ONE question whose complete answer requires information from BOTH passages A and B. "
                        "Quote evidence from each passage.\n\nPassage A:\n" + passage(srcs[0]) +
                        "\n\nPassage B:\n" + passage(srcs[1]))
            elif qtype == "near_duplicate":
                i = rng.choice(near)
                srcs = [chunks[i]]
                task = ("Passage A and passage B look similar. Write ONE question that passage A answers and "
                        "passage B does not. Quote evidence only from passage A.\n\nPassage A:\n" + passage(chunks[i]) +
                        "\n\nPassage B:\n" + passage(chunks[sibling[i]]))
            elif qtype == "exact_term":
                i = rng.choice(exact)
                srcs = [chunks[i]]
                task = ("Write ONE question that hinges on an exact identifier, field name, flag, command or error "
                        "message that appears in the passage, and include that exact string in the question.\n\n"
                        "Passage:\n" + passage(chunks[i]))
            elif qtype == "single_section":
                i = rng.choice(usable)
                srcs = [chunks[i]]
                task = "Write ONE question that this passage answers.\n\nPassage:\n" + passage(chunks[i])
            else:  # unanswerable
                i = rng.choice(usable)
                srcs = []
                task = ("Write ONE realistic question a Kubernetes user might ask about the same topic as this page "
                        "that the page does NOT answer and that is unlikely to be answered elsewhere in the "
                        "Kubernetes concepts or tasks docs. Set reference_answer to NOT_IN_DOCS and "
                        "evidence_quotes to an empty list.\n\nPage topic: " + chunks[i]["title"])
            out = openai_json(gen_model, system, task, SCHEMA, "qgen")
            n += 1
            items.append({
                "question_id": f"q{n:04d}", "question": out["question"], "question_type": qtype,
                "answerable": qtype != "unanswerable",
                "reference_answer": "NOT_IN_DOCS" if qtype == "unanswerable" else out["reference_answer"],
                "draft_quotes": [] if qtype == "unanswerable" else out["evidence_quotes"],
                "draft_sources": [{"doc_id": c["doc_id"], "doc_version": c["doc_version"],
                                   "start": c["char_start"], "end": c["char_end"]} for c in srcs],
                "provenance": {"generated_by": "llm", "generator_model": gen_model,
                               "generator_prompt_version": "qgen-v1",
                               "source_chunks": [c["chunk_id"] for c in srcs]},
            })
            print(f"{n}: [{qtype}] {out['question'][:90]}")
    path = ROOT / "data" / "evalsets" / f"{args.name}-draft.jsonl"
    write_jsonl(path, items)
    print(f"wrote {len(items)} draft items to {path}")


if __name__ == "__main__":
    main()
