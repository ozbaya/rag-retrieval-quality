"""Chunk and embed a snapshot for both chunking configs.
Usage: uv run python -m ragdemo.index --snapshot <snapshot_id>"""
import argparse
import json
import statistics

from openai import OpenAI

from .chunking import make_chunks
from .db import connect
from .settings import model, pipelines, providers


def embed(texts: list[str], batch: int = 100) -> list[list[float]]:
    client, out = OpenAI(), []
    for i in range(0, len(texts), batch):
        resp = client.embeddings.create(model=model("embedding"), input=texts[i:i + batch])
        out.extend(d.embedding for d in resp.data)
        print(f"  embedded {min(i + batch, len(texts))}/{len(texts)}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--config", choices=["fixed-v1", "struct-v1"], help="default: both")
    args = ap.parse_args()
    dims = providers()["models"]["embedding"]["dims"]
    configs = pipelines()["chunking"]
    with connect() as conn:
        docs = conn.execute("select doc_id, doc_version, title, normalized_text from documents "
                            "where snapshot_id=%s order by doc_id", (args.snapshot,)).fetchall()
        for cfg_id in [args.config] if args.config else list(configs):
            cfg = configs[cfg_id]
            conn.execute("insert into chunking_configs values (%s,%s,%s) on conflict (chunking_config_id) do nothing",
                         (cfg_id, cfg["strategy"], json.dumps(cfg["params"])))
            done = conn.execute("select count(*) from chunks where snapshot_id=%s and chunking_config_id=%s",
                                (args.snapshot, cfg_id)).fetchone()[0]
            if done:
                print(f"{cfg_id}: {done} chunks already indexed, skipping (delete them to rebuild)")
                continue
            chunks = []
            for doc_id, ver, title, text in docs:
                for c in make_chunks(cfg_id, cfg["strategy"], cfg["params"], args.snapshot, doc_id, ver, title, text):
                    assert text[c.char_start:c.char_end] == c.content
                    chunks.append((doc_id, ver, c))
            print(f"{cfg_id}: {len(chunks)} chunks, mean tokens "
                  f"{statistics.mean(c.token_count for *_, c in chunks):.0f}")
            vectors = embed([c.index_text for *_, c in chunks])
            assert all(len(v) == dims for v in vectors)
            with conn.cursor() as cur:
                cur.executemany(
                    "insert into chunks (chunk_id, snapshot_id, doc_id, doc_version, chunking_config_id, ordinal,"
                    " char_start, char_end, section_path, header_prefix, content, index_text, token_count,"
                    " embedding_model, embedding) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                    [(c.chunk_id, args.snapshot, d, v, cfg_id, c.ordinal, c.char_start, c.char_end, c.section_path,
                      c.header_prefix, c.content, c.index_text, c.token_count, model("embedding"), vec)
                     for (d, v, c), vec in zip(chunks, vectors)])
            print(f"{cfg_id}: inserted")


if __name__ == "__main__":
    main()
