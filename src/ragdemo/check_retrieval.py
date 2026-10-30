"""Day 1 retrieval tests: does the expected page appear in the top 10 for dense and keyword search?
Usage: uv run python -m ragdemo.check_retrieval --snapshot <id> [--file config/retrieval_tests.yaml]"""
import argparse
import time

import numpy as np

from .db import connect
from .keyword import extract_identifiers
from .retrieval import dense, embed_query, keyword
from .settings import load_yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--file", default="config/retrieval_tests.yaml")
    a = ap.parse_args()
    tests = load_yaml(a.file)["tests"]
    hits = {"dense": 0, "keyword": 0}
    kw_ms, dense_ms, by_kind = [], [], {}
    with connect() as c:
        def doc_of(ids):
            if not ids:
                return []
            rows = dict(c.execute("select chunk_id, doc_id from chunks where chunk_id = any(%s)", (ids,)).fetchall())
            return [rows[i] for i in ids]
        for t in tests:
            qvec, _ = embed_query(t["query"])
            t0 = time.perf_counter()
            d = doc_of([x["chunk_id"] for x in dense(c, a.snapshot, "struct-v1", qvec, 10)])
            dense_ms.append((time.perf_counter() - t0) * 1000)
            t0 = time.perf_counter()
            k = doc_of([x["chunk_id"] for x in keyword(c, a.snapshot, "struct-v1", t["query"], 10)])
            kw_ms.append((time.perf_counter() - t0) * 1000)
            ok_d = any(x.endswith(t["expect"]) for x in d)
            ok_k = any(x.endswith(t["expect"]) for x in k)
            hits["dense"] += ok_d
            hits["keyword"] += ok_k
            b = by_kind.setdefault(t["kind"], [0, 0])
            b[0] += ok_k
            b[1] += 1
            print(f"[{t['kind']:<10}] dense={'Y' if ok_d else '-'} keyword={'Y' if ok_k else '-'} "
                  f"ids={extract_identifiers(t['query'])}  {t['query']}")
    n = len(tests)
    print(f"\ndense top-10: {hits['dense']}/{n}   keyword top-10: {hits['keyword']}/{n}")
    print("keyword by kind: " + ", ".join(f"{k} {v[0]}/{v[1]}" for k, v in by_kind.items()))
    print(f"dense latency   p50={np.percentile(dense_ms, 50):.0f} ms p95={np.percentile(dense_ms, 95):.0f} ms")
    print(f"keyword latency p50={np.percentile(kw_ms, 50):.0f} ms p95={np.percentile(kw_ms, 95):.0f} ms")


if __name__ == "__main__":
    main()
