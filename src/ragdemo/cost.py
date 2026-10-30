from .settings import providers


def estimate(usage: dict) -> float | None:
    """Estimated USD from recorded usage and the dated pricing table. None if any needed price is unset."""
    p = providers()["pricing"]
    parts = []
    if "embed_tokens" in usage:
        parts.append((p["embedding_per_mtok"], usage["embed_tokens"] / 1e6))
    if "input_tokens" in usage:
        parts.append((p["generation_input_per_mtok"], usage["input_tokens"] / 1e6))
        parts.append((p["generation_output_per_mtok"], usage["output_tokens"] / 1e6))
    if usage.get("rerank_search_units"):
        parts.append((p["rerank_per_search_unit"], usage["rerank_search_units"]))
    if any(price is None for price, _ in parts):
        return None
    return round(sum(price * qty for price, qty in parts), 6)
