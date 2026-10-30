"""Aggregation, paired bootstrap CIs and Cohen's kappa."""
import numpy as np


def aggregate(pairs: list[tuple[float, float]]) -> tuple[float | None, int]:
    num = sum(p[0] for p in pairs)
    den = sum(p[1] for p in pairs)
    return (num / den if den else None), int(den)


def paired_bootstrap_diff(a: dict, b: dict, n_boot: int = 10_000, seed: int = 42):
    """a, b: {question_id: (num, den)} for two pipelines. Returns (diff, lo, hi) for ratio(a) - ratio(b)."""
    qids = sorted(set(a) & set(b))
    if not qids:
        return None, None, None
    an = np.array([a[q][0] for q in qids]); ad = np.array([a[q][1] for q in qids])
    bn = np.array([b[q][0] for q in qids]); bd = np.array([b[q][1] for q in qids])
    if ad.sum() == 0 or bd.sum() == 0:
        return None, None, None
    point = an.sum() / ad.sum() - bn.sum() / bd.sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(qids), size=(n_boot, len(qids)))
    with np.errstate(invalid="ignore", divide="ignore"):
        diffs = an[idx].sum(1) / ad[idx].sum(1) - bn[idx].sum(1) / bd[idx].sum(1)
    diffs = diffs[np.isfinite(diffs)]
    return float(point), float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def cohen_kappa(x: list, y: list) -> float:
    labels = sorted(set(x) | set(y))
    n = len(x)
    po = sum(1 for i in range(n) if x[i] == y[i]) / n
    pe = sum((x.count(l) / n) * (y.count(l) / n) for l in labels)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)
