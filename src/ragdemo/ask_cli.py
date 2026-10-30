"""Ask one question through all three pipelines and print what each retrieved and answered.
Usage: uv run python -m ragdemo.ask_cli --snapshot <id> "How do I configure a liveness probe?" """
import argparse

from .db import connect
from .generation import generate
from .retrieval import embed_query, load_chunks, run_retrieval
from .tracing import init_tracing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("question")
    a = ap.parse_args()
    init_tracing()
    with connect() as c:
        qvec, _ = embed_query(a.question)
        for pid in ("baseline", "intermediate", "advanced"):
            r = run_retrieval(c, pid, a.snapshot, a.question, qvec=qvec)
            chunks = load_chunks(c, r["final"][:5])
            print(f"\n=== {pid}  timings={r['timings_ms']}")
            for i, ch in enumerate(chunks, start=1):
                print(f"  C{i} {ch['doc_id'].split(':', 1)[1]} > {ch['section_path'][:60]}")
            if not a.no_generate:
                g = generate(a.question, chunks)
                print(f"  ANSWER ({g['latency_ms']} ms): {g['answer']}")


if __name__ == "__main__":
    main()
