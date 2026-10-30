"""LLM judge (OpenAI): judge-claims-v1 and judge-correct-v1."""
from .evalset.common import openai_json
from .settings import model, prompt

CLAIMS_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["sentences"],
    "properties": {"sentences": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["index", "is_claim", "supported_by_context", "supported_by_cited", "rationale"],
        "properties": {
            "index": {"type": "integer"},
            "is_claim": {"type": "boolean"},
            "supported_by_context": {"type": "boolean"},
            "supported_by_cited": {"type": "string", "enum": ["yes", "no", "no_citation"]},
            "rationale": {"type": "string"}}}}}}

CORRECT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["label", "rationale"],
    "properties": {"label": {"type": "string", "enum": ["correct", "partially_correct", "incorrect"]},
                   "rationale": {"type": "string"}}}


def judge_claims(question, sentences, context_chunks):
    ctx = "\n\n".join(f"[C{i}]\n{c['content']}" for i, c in enumerate(context_chunks, start=1))
    sents = "\n".join(f"{i}. {s['text']}  (cites: {', '.join(f'C{n}' for n in s['citations']) or 'none'})"
                      for i, s in enumerate(sentences))
    user = f"Question: {question}\n\nContext passages:\n{ctx}\n\nAnswer sentences:\n{sents}"
    return openai_json(model("judge"), prompt("judge-claims-v1"), user, CLAIMS_SCHEMA, "claims")


def judge_correct(question, answer, reference_answer, evidence_texts):
    ev = "\n\n".join(f"Evidence {i}:\n{t}" for i, t in enumerate(evidence_texts, start=1))
    user = (f"Question: {question}\n\nReference answer: {reference_answer}\n\nSource evidence:\n{ev}\n\n"
            f"Answer to grade:\n{answer}")
    return openai_json(model("judge"), prompt("judge-correct-v1"), user, CORRECT_SCHEMA, "correct")
