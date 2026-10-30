"""Retrieval metrics per Section 8. Each returns a (numerator, denominator) pair per question."""
import math


def overlap(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def covers(chunk: dict, span: dict, threshold: float) -> bool:
    if chunk["doc_id"] != span["doc_id"] or chunk["doc_version"] != span["doc_version"]:
        return False
    length = span["end"] - span["start"]
    return length > 0 and overlap(chunk["char_start"], chunk["char_end"], span["start"], span["end"]) >= threshold * length


def _covered(ranked, spans, k, thr):
    return {s["evidence_id"] for s in spans for c in ranked[:k] if covers(c, s, thr)}


def hit_rate_at_5(ranked, required, thr):
    return (1.0 if _covered(ranked, required, 5, thr) else 0.0, 1)


def recall_at_5(ranked, required, thr):
    return (len(_covered(ranked, required, 5, thr)) / len(required), 1)


def full_coverage_at_5(ranked, required, thr, multi_section: bool):
    if not multi_section:
        return (0.0, 0)
    return (1.0 if len(_covered(ranked, required, 5, thr)) == len(required) else 0.0, 1)


def mrr_at_10(ranked, required, thr):
    for i, c in enumerate(ranked[:10], start=1):
        if any(covers(c, s, thr) for s in required):
            return (1.0 / i, 1)
    return (0.0, 1)


def ndcg_at_10(ranked, required, optional, thr):
    credited, dcg = set(), 0.0
    for i, c in enumerate(ranked[:10], start=1):
        new_req = [s["evidence_id"] for s in required if s["evidence_id"] not in credited and covers(c, s, thr)]
        new_opt = [s["evidence_id"] for s in optional if s["evidence_id"] not in credited and covers(c, s, thr)]
        grade = 2 if new_req else (1 if new_opt else 0)
        credited.update(new_req + new_opt)
        dcg += (2 ** grade - 1) / math.log2(i + 1)
    ideal = ([2] * len(required) + [1] * len(optional))[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 1) for i, g in enumerate(ideal, start=1))
    return (dcg / idcg if idcg > 0 else 0.0, 1)


def retrieval_metrics(ranked, item, thr) -> dict:
    """ranked: list of chunk dicts (final top 10). item: dataset record (answerable only)."""
    req, opt = item["required_evidence"], item["optional_evidence"]
    multi = item["question_type"] == "multi_section"
    return {
        "hit_rate_at_5": hit_rate_at_5(ranked, req, thr),
        "recall_at_5": recall_at_5(ranked, req, thr),
        "recall_at_5_multi_section": recall_at_5(ranked, req, thr) if multi else (0.0, 0),
        "full_coverage_at_5": full_coverage_at_5(ranked, req, thr, multi),
        "mrr_at_10": mrr_at_10(ranked, req, thr),
        "ndcg_at_10": ndcg_at_10(ranked, req, opt, thr),
    }
