"""The three pipeline configurations: baseline, intermediate, advanced."""
import time

import cohere
from openai import OpenAI

from .fusion import rrf
from .keyword import extract_identifiers
from .settings import model, pipelines
from .tracing import span

_openai = None
_cohere = None


def _clients():
    global _openai, _cohere
    if _openai is None:
        _openai = OpenAI(timeout=10, max_retries=2)
        _cohere = cohere.ClientV2(timeout=10)
    return _openai, _cohere


def _ms(t0):
    return round((time.perf_counter() - t0) * 1000, 1)


def embed_query(question: str) -> tuple[list[float], int]:
    oa, _ = _clients()
    resp = oa.embeddings.create(model=model("embedding"), input=[question])
    return resp.data[0].embedding, resp.usage.total_tokens


def dense(conn, snapshot, config, qvec, k):
    rows = conn.execute("select chunk_id, score, rank from match_dense(%s, %s, %s::vector, %s)",
                        (snapshot, config, qvec, k)).fetchall()
    return [{"chunk_id": r[0], "score": float(r[1]), "rank": r[2]} for r in rows]


def keyword(conn, snapshot, config, question, k):
    rows = conn.execute("select chunk_id, score, rank from match_keyword(%s, %s, %s, %s, %s)",
                        (snapshot, config, question, extract_identifiers(question), k)).fetchall()
    return [{"chunk_id": r[0], "score": float(r[1]), "rank": r[2]} for r in rows]


def load_chunks(conn, ids):
    rows = conn.execute(
        "select c.chunk_id, c.doc_id, c.doc_version, c.char_start, c.char_end, c.section_path,"
        " c.header_prefix, c.content, c.index_text, c.token_count, d.title, d.source_url"
        " from chunks c join documents d on d.snapshot_id = c.snapshot_id and d.doc_id = c.doc_id"
        " where c.chunk_id = any(%s)", (list(ids),)).fetchall()
    keys = ["chunk_id", "doc_id", "doc_version", "char_start", "char_end", "section_path", "header_prefix",
            "content", "index_text", "token_count", "title", "source_url"]
    by_id = {r[0]: dict(zip(keys, r)) for r in rows}
    return [by_id[i] for i in ids]


def run_retrieval(conn, pipeline_id: str, snapshot: str, question: str, qvec=None) -> dict:
    p = pipelines()["pipelines"][pipeline_id]
    timings, stages, usage = {}, {}, {}
    if qvec is None:
        t0 = time.perf_counter()
        with span("embed_query"):
            qvec, usage["embed_tokens"] = embed_query(question)
        timings["embed"] = _ms(t0)

    if p["retrieval"] == "dense":
        t0 = time.perf_counter()
        with span("dense_search", pipeline=pipeline_id):
            stages["dense"] = dense(conn, snapshot, p["chunking"], qvec, p["final_k"])
        timings["dense"] = _ms(t0)
        final = [x["chunk_id"] for x in stages["dense"]]
    else:
        t0 = time.perf_counter()
        with span("dense_search", pipeline=pipeline_id, k=p["n_dense"]):
            stages["dense"] = dense(conn, snapshot, p["chunking"], qvec, p["n_dense"])
        timings["dense"] = _ms(t0)
        t0 = time.perf_counter()
        with span("keyword_search", pipeline=pipeline_id, k=p["n_kw"]):
            stages["keyword"] = keyword(conn, snapshot, p["chunking"], question, p["n_kw"])
        timings["keyword"] = _ms(t0)
        t0 = time.perf_counter()
        with span("rrf_fusion", rrf_k=p["rrf_k"], top_m=p["top_m"]):
            fused = rrf([[x["chunk_id"] for x in stages["dense"]], [x["chunk_id"] for x in stages["keyword"]]],
                        k=p["rrf_k"], top_m=p["top_m"])
        stages["fused"] = [{"chunk_id": c, "score": s, "rank": i} for i, (c, s) in enumerate(fused, start=1)]
        timings["fuse"] = _ms(t0)
        t0 = time.perf_counter()
        cands = load_chunks(conn, [x["chunk_id"] for x in stages["fused"]])
        _, co = _clients()
        with span("rerank", model=model("rerank"), n=len(cands)):
            resp = co.rerank(model=model("rerank"), query=question,
                             documents=[c["index_text"] for c in cands], top_n=p["final_k"])
        fused_rank = {x["chunk_id"]: x["rank"] for x in stages["fused"]}
        ranked = sorted(((cands[r.index]["chunk_id"], float(r.relevance_score)) for r in resp.results),
                        key=lambda x: (-x[1], fused_rank[x[0]], x[0]))
        stages["reranked"] = [{"chunk_id": c, "score": s, "rank": i} for i, (c, s) in enumerate(ranked, start=1)]
        usage["rerank_search_units"] = getattr(getattr(resp.meta, "billed_units", None), "search_units", None)
        timings["rerank"] = _ms(t0)
        final = [x["chunk_id"] for x in stages["reranked"]]

    return {"pipeline_id": pipeline_id, "stages": stages, "final": final,
            "context_ids": final[: p["context_k"]], "timings_ms": timings, "usage": usage}
