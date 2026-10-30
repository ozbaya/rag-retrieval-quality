"""Reciprocal rank fusion with 1-based ranks and deterministic tie-breaking."""


def rrf(ranked_lists: list[list[str]], k: int = 60, top_m: int = 50) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        seen = set()
        for rank, cid in enumerate(lst, start=1):
            if cid in seen:  # defensive: ignore duplicates inside one list
                continue
            seen.add(cid)
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    ordered = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
    return ordered[:top_m]
