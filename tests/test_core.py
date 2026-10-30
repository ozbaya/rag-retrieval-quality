import math
import pytest
from ragdemo.normalize import parse_front_matter, strip_hugo, normalize_text
from ragdemo.chunking import fixed_spans, struct_spans, make_chunks, ntok
from ragdemo.keyword import extract_identifiers
from ragdemo.fusion import rrf
from ragdemo import metrics as M
from ragdemo.stats import aggregate, paired_bootstrap_diff, cohen_kappa

RAW = """---
title: Pods
content_type: concept
weight: 10
---

<!-- overview -->
_Pods_ are the smallest deployable units. A {{< glossary_tooltip text="Pod" term_id="pod" >}} groups containers.
{{< note >}}
Use a {{< glossary_tooltip term_id="deployment" >}} instead.
{{< /note >}}

{{% code_sample file="pods/simple-pod.yaml" %}}



## Using Pods

Pods run on a node. Error: ECONNREFUSED when kubelet is down.

### Pod lifecycle

Phases are Pending, Running, Succeeded.

```
# not a heading
kubectl get pods
```
"""

def test_normalize():
    meta, body = parse_front_matter(RAW)
    assert meta["title"] == "Pods"
    text = normalize_text(strip_hugo(body))
    assert "glossary_tooltip" not in text and "{{" not in text
    assert "A Pod groups containers" in text
    assert "Use a deployment instead" in text
    assert "[code sample: pods/simple-pod.yaml]" in text
    assert "\n\n\n\n" not in text
    assert text == text.strip()

def _doc():
    meta, body = parse_front_matter(RAW)
    return meta["title"], normalize_text(strip_hugo(body))

def test_struct_offsets_and_paths():
    title, text = _doc()
    spans = struct_spans(text, max_tokens=400, min_tokens=5)
    paths = [p for _, _, p in spans]
    assert ("Using Pods", "Pod lifecycle") in paths
    for s, e, _ in spans:
        assert 0 <= s < e <= len(text)
    # code fence comment is not a heading
    assert not any("not a heading" in " ".join(p) for p in paths)

def test_make_chunks_invariant():
    title, text = _doc()
    for cfg, strat, params in [("fixed-v1", "fixed", {"size_chars": 120, "min_back_chars": 40}),
                               ("struct-v1", "structured", {"max_tokens": 30, "min_tokens": 5})]:
        chunks = make_chunks(cfg, strat, params, "snap", "k8s:pods.md", "sha256:x", title, text)
        assert chunks
        for c in chunks:
            assert text[c.char_start:c.char_end] == c.content
            assert c.content == c.content.strip()
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))
        again = make_chunks(cfg, strat, params, "snap", "k8s:pods.md", "sha256:x", title, text)
        assert ids == [c.chunk_id for c in again]
    s = make_chunks("struct-v1", "structured", {"max_tokens": 400, "min_tokens": 5}, "snap", "d", "v", title, text)
    assert any(c.header_prefix == "Pods > Using Pods > Pod lifecycle" for c in s)

def test_struct_split_long_section():
    text = "## Big\n\n" + "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(10))
    spans = struct_spans(text, max_tokens=200, min_tokens=50)
    assert len(spans) > 3
    assert all(ntok(text[s:e]) <= 200 for s, e, _ in spans)

def test_fixed_spans_cover_text():
    text = ("alpha beta gamma " * 400).strip()
    spans = fixed_spans(text, 1600, 800)
    assert all(e - s <= 1600 for s, e in spans)
    joined = "".join(text[s:e] for s, e in spans).replace(" ", "")
    assert joined == text.replace(" ", "")

def test_identifiers():
    q = "Why does my pod show CrashLoopBackOff with spec.containers[].resources.limits and --dry-run=client?"
    ids = extract_identifiers(q)
    assert "CrashLoopBackOff" in ids
    assert "spec.containers[].resources.limits" in ids
    assert "--dry-run=client" in ids
    assert "Why" not in ids and "pod" not in ids
    assert extract_identifiers("ECONNREFUSED on port 6443") == ["ECONNREFUSED", "6443"]

def test_rrf():
    out = rrf([["a", "b", "c"], ["c", "a", "d"]], k=60, top_m=10)
    s = dict(out)
    assert math.isclose(s["a"], 1/61 + 1/62)
    assert math.isclose(s["c"], 1/63 + 1/61)
    assert [x for x, _ in out][:2] == ["a", "c"]
    assert set(s) == {"a", "b", "c", "d"}
    # tie broken by id
    assert [x for x, _ in rrf([["y"], ["x"]])] == ["x", "y"]

def ch(doc, s, e):
    return {"doc_id": doc, "doc_version": "v", "char_start": s, "char_end": e}

def sp(eid, doc, s, e):
    return {"evidence_id": eid, "doc_id": doc, "doc_version": "v", "start": s, "end": e}

def test_coverage_threshold():
    assert M.covers(ch("d", 0, 60), sp("r", "d", 50, 70), 0.5)       # 10/20 = 0.5
    assert not M.covers(ch("d", 0, 59), sp("r", "d", 50, 70), 0.5)   # 9/20
    assert not M.covers(ch("other", 0, 100), sp("r", "d", 50, 70), 0.5)

def test_retrieval_metrics_multi():
    req = [sp("r1", "d1", 100, 200), sp("r2", "d2", 0, 50)]
    opt = [sp("o1", "d3", 0, 40)]
    ranked = [ch("x", 0, 10), ch("d1", 90, 300), ch("d1", 100, 200), ch("d3", 0, 100)] + [ch("x", i, i+1) for i in range(6)] + [ch("d2", 0, 60)]
    item = {"required_evidence": req, "optional_evidence": opt, "question_type": "multi_section"}
    m = M.retrieval_metrics(ranked, item, 0.5)
    assert m["hit_rate_at_5"] == (1.0, 1)
    assert m["recall_at_5"] == (0.5, 1)              # r1 yes, r2 only at rank 11
    assert m["full_coverage_at_5"] == (0.0, 1)
    assert m["mrr_at_10"] == (0.5, 1)
    # nDCG: rank2 grade2 (r1), rank3 dup -> 0, rank4 grade1 (o1); r2 beyond 10
    dcg = 3 / math.log2(3) + 1 / math.log2(5)
    idcg = 3 / math.log2(2) + 3 / math.log2(3) + 1 / math.log2(4)
    assert math.isclose(m["ndcg_at_10"][0], dcg / idcg)

def test_single_section_recall_equals_hit():
    req = [sp("r1", "d1", 0, 10)]
    item = {"required_evidence": req, "optional_evidence": [], "question_type": "single_section"}
    m = M.retrieval_metrics([ch("d1", 0, 10)], item, 0.5)
    assert m["recall_at_5"] == m["hit_rate_at_5"] == (1.0, 1)
    assert m["full_coverage_at_5"] == (0.0, 0)
    assert m["ndcg_at_10"] == (1.0, 1)

def test_stats():
    assert aggregate([(1, 1), (0, 1), (0, 0)]) == (0.5, 2)
    a = {f"q{i}": (1.0, 1) for i in range(50)}
    b = {f"q{i}": (1.0 if i < 25 else 0.0, 1) for i in range(50)}
    d, lo, hi = paired_bootstrap_diff(a, b, n_boot=2000)
    assert math.isclose(d, 0.5) and lo < 0.5 < hi and lo > 0.2
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0
    assert round(cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]), 6) == 0.0

def test_heading_ids_removed():
    from ragdemo.normalize import strip_hugo
    assert strip_hugo("## Liveness probe {#liveness-probe}\ntext") == "## Liveness probe\ntext"
