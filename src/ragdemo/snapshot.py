"""Create an immutable corpus snapshot.  Usage: uv run python -m ragdemo.snapshot --corpus k8s"""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

from .db import connect
from .normalize import NORM_VERSION, doc_version, normalize_text, parse_front_matter, strip_hugo
from .settings import ROOT, load_yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    args = ap.parse_args()
    cfg = load_yaml(f"corpora/{args.corpus}.yaml")
    repo = ROOT / cfg["local_path"]
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

    files = set()
    for pattern in cfg["include"]:
        files |= set(repo.glob(pattern))
    for pattern in cfg.get("exclude", []):
        files -= set(repo.glob(pattern))

    docs = []
    for f in sorted(files):
        rel = f.relative_to(repo).as_posix()
        meta, body = parse_front_matter(f.read_text(encoding="utf-8"))
        text = normalize_text(strip_hugo(body))
        if len(text) < cfg["min_chars"]:
            continue
        slug = rel.removeprefix(cfg["docs_root"]).removesuffix(".md").removesuffix("_index")
        docs.append({
            "doc_id": f"{cfg['corpus']}:{rel}",
            "doc_version": doc_version(text),
            "source_url": cfg["url_base"] + slug.rstrip("/") + "/",
            "source_path": rel,
            "title": str(meta.get("title") or f.stem),
            "normalized_text": text,
        })

    listing = "".join(f"{d['doc_id']}\t{d['doc_version']}\n" for d in sorted(docs, key=lambda d: d["doc_id"]))
    content_sha = hashlib.sha256(listing.encode()).hexdigest()
    snapshot_id = f"{cfg['corpus']}-{dt.date.today():%Y%m%d}-{content_sha[:6]}"

    out = ROOT / "data" / "snapshots" / snapshot_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps({
        "snapshot_id": snapshot_id, "source_ref": f"{cfg['repo_url']}@{sha}",
        "normalization_version": NORM_VERSION, "doc_count": len(docs), "content_sha256": content_sha,
        "docs": [{k: d[k] for k in ("doc_id", "doc_version", "source_path")} for d in docs]}, indent=1))
    with (out / "documents.jsonl").open("w") as fh:
        for d in docs:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    with connect() as conn, conn.cursor() as cur:
        cur.execute("insert into corpus_snapshots values (%s,%s,%s,%s,%s,%s,%s) on conflict do nothing",
                    (snapshot_id, cfg["corpus"], cfg["source_type"], f"{cfg['repo_url']}@{sha}",
                     NORM_VERSION, len(docs), content_sha))
        cur.executemany(
            "insert into documents values (%s,%s,%s,%s,%s,%s,%s) on conflict do nothing",
            [(snapshot_id, d["doc_id"], d["doc_version"], d["source_url"], d["source_path"],
              d["title"], d["normalized_text"]) for d in docs])
    print(f"snapshot_id={snapshot_id} docs={len(docs)} source={cfg['repo_url']}@{sha}")


if __name__ == "__main__":
    main()
