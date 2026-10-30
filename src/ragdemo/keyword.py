"""Keyword query helper kwq-v1: identifier extraction (the SQL function builds the tsquery)."""
import re

KWQ_VERSION = "kwq-v1"
_TOKEN = re.compile(r"[\w$./:\-\[\]=]+")
_IDENT = re.compile(r"[_.$/:\[\]=]|\d|[a-z][A-Z]|^--|^[A-Z]{3,}$")


def extract_identifiers(question: str, max_terms: int = 8) -> list[str]:
    out = []
    for tok in _TOKEN.findall(question):
        tok = tok.strip(".:,;")
        if len(tok) >= 3 and _IDENT.search(tok) and tok not in out:
            out.append(tok)
    return out[:max_terms]
