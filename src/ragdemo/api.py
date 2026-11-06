"""Public API (FastAPI). Phase A: /benchmark and /presets. Phase B: /ask when ASK_ENABLED=1.
Run locally: uv run uvicorn ragdemo.api:app --reload --port 8000"""
import datetime as dt
import hmac
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .cost import estimate
from .db import connect
from .generation import generate
from .retrieval import embed_query, load_chunks, run_retrieval
from .settings import env, load_yaml

app = FastAPI(title="RAG retrieval quality demo", docs_url=None, redoc_url=None, openapi_url=None)
PIPELINE_IDS = ["baseline", "intermediate", "advanced"]
_pool = ThreadPoolExecutor(8)


def require_token(authorization: str = Header(default="")):
    expected = f"Bearer {env('BACKEND_TOKEN')}"
    if not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/healthz")
def healthz():
    return {"ok": True}


def published_run(conn):
    run_id = env("PUBLISHED_RUN_ID")
    run = conn.execute("select * from benchmark_runs where run_id=%s", (run_id,)).fetchone()
    if not run:
        raise HTTPException(500, "published run not found")
    return run


@app.get("/benchmark", dependencies=[Depends(require_token)])
def benchmark():
    with connect(dict_rows=True) as conn:
        run = published_run(conn)
        ds = conn.execute("select dataset_version, n_questions, n_human_reviewed from eval_datasets"
                          " where dataset_version=%s", (run["dataset_version"],)).fetchone()
        aggs = conn.execute("select pipeline_id, metric, value, n, ci_low, ci_high from run_aggregates"
                            " where run_id=%s", (run["run_id"],)).fetchall()
    judge_val = load_yaml("config/presets.yaml").get("judge_validation", {})
    return {"run_id": run["run_id"], "created_at": run["created_at"], "snapshot_id": run["snapshot_id"],
            "models": {"embedding": run["embedding_model"], "rerank": run["rerank_model"],
                       "generation": run["generation_model"], "judge": run["judge_model"]},
            "dataset": ds, "judge_validation": judge_val,
            "aggregates": [{**a, "value": None if a["value"] is None else float(a["value"]),
                            "ci_low": None if a["ci_low"] is None else float(a["ci_low"]),
                            "ci_high": None if a["ci_high"] is None else float(a["ci_high"])} for a in aggs]}


def public_chunk(c):
    return {k: c[k] for k in ("chunk_id", "title", "section_path", "source_url", "content")}


@app.get("/presets", dependencies=[Depends(require_token)])
def presets():
    ids = load_yaml("config/presets.yaml")["question_ids"]
    out = []
    with connect(dict_rows=True) as conn:
        run = published_run(conn)
        for qid in ids:
            q = conn.execute("select payload from eval_questions where dataset_version=%s and question_id=%s",
                             (run["dataset_version"], qid)).fetchone()["payload"]
            rows = conn.execute("select pipeline_id, retrieval, context_chunk_ids, answer, abstained, metrics,"
                                " latency_ms, est_cost_usd, judge_outputs from run_results"
                                " where run_id=%s and question_id=%s", (run["run_id"], qid)).fetchall()
            with connect() as tconn:
                pipes = {}
                for r in rows:
                    final = r["retrieval"]["final"]
                    chunks = load_chunks(tconn, final[:5])
                    pipes[r["pipeline_id"]] = {
                        "stages": r["retrieval"]["stages"], "top5": [public_chunk(c) for c in chunks],
                        "answer": r["answer"], "abstained": r["abstained"],
                        "correctness": (r["judge_outputs"] or {}).get("correctness", {}).get("label"),
                        "metrics": {k: v[0] / v[1] for k, v in r["metrics"].items() if v[1]},
                        "latency_ms": r["latency_ms"], "est_cost_usd": r["est_cost_usd"]}
            out.append({"question_id": qid, "question": q["question"], "question_type": q["question_type"],
                        "answerable": q["answerable"], "human_review_status":
                            q["validation"]["human_review_status"], "pipelines": pipes})
    return {"run_id": run["run_id"], "presets": out, "label": "measured"}


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=300)


def _limits(client_ip: str):
    from upstash_ratelimit import FixedWindow, Ratelimit
    from upstash_redis import Redis
    redis = Redis.from_env()
    per_ip = Ratelimit(redis=redis, limiter=FixedWindow(max_requests=int(os.getenv("RATE_PER_IP_HOUR", "10")),
                                                       window=3600), prefix="rl:ip")
    if not per_ip.limit(client_ip).allowed:
        raise HTTPException(429, "Hourly limit reached. Try a preset question.")
    day = dt.date.today().isoformat()
    if int(redis.incr(f"req:{day}")) > int(os.getenv("DAILY_REQUEST_LIMIT", "300")):
        raise HTTPException(429, "Daily demo capacity reached.")
    spent = float(redis.get(f"spend:{day}") or 0)
    if spent >= float(os.getenv("DAILY_BUDGET_USD", "3")):
        raise HTTPException(429, "Daily demo budget reached.")
    redis.expire(f"req:{day}", 172800)
    return redis, day


def _ask(question: str, snapshot: str):
    out = {}
    with connect() as conn:
        qvec, embed_tokens = embed_query(question)
        for pid in PIPELINE_IDS:
            r = run_retrieval(conn, pid, snapshot, question, qvec=qvec)
            chunks = load_chunks(conn, r["final"][:5])
            g = generate(question, chunks)
            usage = {**r["usage"], **g["usage"], "embed_tokens": embed_tokens}
            out[pid] = {"stages": r["stages"], "top5": [public_chunk(c) for c in chunks], "answer": g["answer"],
                        "abstained": g["abstained"], "latency_ms": {**r["timings_ms"], "generate": g["latency_ms"]},
                        "est_cost_usd": estimate(usage)}
    return out


@app.post("/ask", dependencies=[Depends(require_token)])
def ask(body: AskIn, x_client_ip: str = Header(default="unknown")):
    if os.getenv("ASK_ENABLED") != "1":
        raise HTTPException(404, "not enabled")
    redis, day = _limits(x_client_ip)
    try:
        result = _pool.submit(_ask, body.question.strip(), env("PUBLISHED_SNAPSHOT_ID")).result(
            timeout=float(os.getenv("ASK_TIMEOUT_S", "30")))
    except FutureTimeout:
        raise HTTPException(504, "timed out")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "upstream error")
    total = sum(p["est_cost_usd"] or float(os.getenv("UNPRICED_REQUEST_USD", "0.05")) for p in result.values())
    redis.incrbyfloat(f"spend:{day}", total)
    redis.expire(f"spend:{day}", 172800)
    return {"label": "live", "note": "Live result: no ground truth, quality not scored.", "pipelines": result}
