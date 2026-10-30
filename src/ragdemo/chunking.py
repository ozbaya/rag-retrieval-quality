"""Chunkers fixed-v1 and struct-v1. All offsets are half-open [start, end) code-point indices."""
import hashlib
import re
from dataclasses import dataclass

import tiktoken

_ENC = tiktoken.get_encoding("cl100k_base")
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def ntok(s: str) -> int:
    return len(_ENC.encode(s, disallowed_special=()))


@dataclass
class Chunk:
    chunk_id: str
    ordinal: int
    char_start: int
    char_end: int
    section_path: str
    header_prefix: str
    content: str
    index_text: str
    token_count: int


def chunk_id(snapshot_id, doc_id, version, config_id, start, end) -> str:
    key = f"{snapshot_id}|{doc_id}|{version}|{config_id}|{start}|{end}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def _trim(text, s, e):
    while s < e and text[s].isspace():
        s += 1
    while e > s and text[e - 1].isspace():
        e -= 1
    return s, e


# ---------- fixed-v1 ----------
def fixed_spans(text: str, size: int = 1600, min_back: int = 800):
    spans, s, n = [], 0, len(text)
    while s < n:
        while s < n and text[s].isspace():
            s += 1
        if s >= n:
            break
        e = min(s + size, n)
        if e < n:
            cut = max(text.rfind(" ", s, e), text.rfind("\n", s, e))
            if cut > s + min_back:
                e = cut
        a, b = _trim(text, s, e)
        if b > a:
            spans.append((a, b))
        s = e
    return spans


# ---------- struct-v1 ----------
def _sections(text: str):
    """Return list of (start, end, path_tuple). Headings H1-H3 outside code fences."""
    heads, pos, in_fence = [], 0, False
    for line in text.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = _HEADING.match(line)
            if m:
                heads.append((pos, len(m.group(1)), m.group(2).strip()))
        pos += len(line) + 1
    bounds, stack = [], []
    first = heads[0][0] if heads else len(text)
    if first > 0:
        bounds.append((0, first, ()))
    for i, (start, level, title) in enumerate(heads):
        stack = [h for h in stack if h[0] < level] + [(level, title)]
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        bounds.append((start, end, tuple(t for _, t in stack)))
    return bounds


def _pack(text, s, e, cuts, max_tokens):
    """Greedily pack [s,e) at the given cut positions into pieces <= max_tokens."""
    pts = [s] + [c for c in cuts if s < c < e] + [e]
    out, cs = [], pts[0]
    for i in range(1, len(pts)):
        if pts[i - 1] > cs and ntok(text[cs:pts[i]]) > max_tokens:
            out.append((cs, pts[i - 1]))
            cs = pts[i - 1]
    out.append((cs, e))
    return out


def _split(text, s, e, max_tokens):
    if ntok(text[s:e]) <= max_tokens:
        return [(s, e)]
    paras = [m.end() for m in re.finditer(r"\n\s*\n", text[s:e])]
    pieces = _pack(text, s, e, [s + p for p in paras], max_tokens)
    result = []
    for a, b in pieces:
        if ntok(text[a:b]) <= max_tokens:
            result.append((a, b))
            continue
        sents = [m.end() for m in re.finditer(r"(?<=[.!?])\s+", text[a:b])]
        for c, d in _pack(text, a, b, [a + x for x in sents], max_tokens):
            if ntok(text[c:d]) <= max_tokens:
                result.append((c, d))
            else:  # e.g. a long code block or table: hard windows sized to fit
                result.extend(_hard_split(text, c, d, max_tokens))
    return result


def _hard_split(text, s, e, max_tokens):
    out = []
    size = max(100, int((e - s) * max_tokens / max(ntok(text[s:e]), 1) * 0.9))
    for x, y in fixed_spans(text[s:e], size, size // 2):
        a, b = s + x, s + y
        if ntok(text[a:b]) <= max_tokens or b - a <= 100:
            out.append((a, b))
        else:
            out.extend(_hard_split(text, a, b, max_tokens))
    return out


def struct_spans(text: str, max_tokens: int = 400, min_tokens: int = 50):
    secs = [(s, e, p) for s, e, p in _sections(text) if text[s:e].strip()]
    merged, i = [], 0
    while i < len(secs):
        s, e, p = secs[i]
        # merge short sections forward into the next section under the same parent
        while (i + 1 < len(secs) and ntok(text[s:e]) < min_tokens
               and secs[i + 1][2][: max(len(p) - 1, 0)] == p[: max(len(p) - 1, 0)]):
            i += 1
            e, p = secs[i][1], secs[i][2]
        merged.append((s, e, p))
        i += 1
    out = []
    for s, e, p in merged:
        for a, b in _split(text, s, e, max_tokens):
            a, b = _trim(text, a, b)
            if b > a:
                out.append((a, b, p))
    return out


def make_chunks(config_id, strategy, params, snapshot_id, doc_id, version, title, text):
    if strategy == "fixed":
        spans = [(s, e, ()) for s, e in fixed_spans(text, params["size_chars"], params["min_back_chars"])]
    else:
        spans = struct_spans(text, params["max_tokens"], params["min_tokens"])
    chunks = []
    for i, (s, e, path) in enumerate(spans):
        content = text[s:e]
        prefix = ""
        if strategy == "structured":
            prefix = " > ".join([title, *[x for x in path if x != title]])
        index_text = f"{prefix}\n\n{content}" if prefix else content
        chunks.append(Chunk(chunk_id(snapshot_id, doc_id, version, config_id, s, e), i, s, e,
                            " > ".join(path), prefix, content, index_text, ntok(index_text)))
    return chunks
