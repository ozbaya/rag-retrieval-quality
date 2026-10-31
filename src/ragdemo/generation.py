"""Answer generation (prompt gen-v1) with [C#] citations and NOT_IN_DOCS abstention."""
import re
import time

from openai import OpenAI

from .settings import model, pipelines, prompt
from .tracing import span

ABSTAIN = "NOT_IN_DOCS:"
_CITE = re.compile(r"\[C(\d+)\]")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z`\"'(\[*-])|\n+")
_client = None


def format_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        parts.append(f"[C{i}] Source: {c['title']}\nSection: {c['section_path'] or '-'}\n{c['content']}")
    return "\n\n---\n\n".join(parts)


def generate(question: str, chunks: list[dict]) -> dict:
    global _client
    _client = _client or OpenAI(timeout=30, max_retries=2)
    g = pipelines()["generation"]
    user = prompt("gen-v1-user").format(context=format_context(chunks), question=question)
    t0 = time.perf_counter()
    with span("generate", model=model("generation")):
        resp = _client.chat.completions.create(
            model=model("generation"), max_completion_tokens=g["max_tokens"],
            messages=[{"role": "system", "content": prompt("gen-v1-system")}, {"role": "user", "content": user}])
    text = (resp.choices[0].message.content or "").strip()
    return {"answer": text, "abstained": text.startswith(ABSTAIN),
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "usage": {"input_tokens": resp.usage.prompt_tokens, "output_tokens": resp.usage.completion_tokens}}


def split_sentences(answer: str) -> list[dict]:
    """Deterministic sentence splitter (version split-v1). Returns sentences with cited chunk numbers."""
    out = []
    for s in (x.strip() for x in _SENT.split(answer)):
        if s:
            out.append({"text": s, "citations": sorted({int(n) for n in _CITE.findall(s)})})
    return out
