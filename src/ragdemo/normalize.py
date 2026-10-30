"""Normalization norm-v1 for Hugo-style Markdown docs (Kubernetes website)."""
import hashlib
import re
import unicodedata

import yaml

NORM_VERSION = "norm-v1"

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_GLOSS = re.compile(r"\{\{<\s*glossary_tooltip\s+(.*?)>\}\}", re.S)
_CODE = re.compile(r"\{\{[<%]\s*code(?:_sample)?\s+(.*?)[>%]\}\}", re.S)
_SHORTCODE = re.compile(r"\{\{[<%].*?[>%]\}\}", re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADING_ID = re.compile(r"[ \t]*\{#[^}\n]*\}[ \t]*$", re.M)


def parse_front_matter(raw: str) -> tuple[dict, str]:
    raw = raw.replace("\r\n", "\n")
    m = _FRONT.match(raw)
    if not m:
        return {}, raw
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), raw[m.end():]


def strip_hugo(body: str) -> str:
    body = _COMMENT.sub("", body)

    def gloss(m):
        attrs = dict(_ATTR.findall(m.group(1)))
        return attrs.get("text") or attrs.get("term_id", "")

    def code(m):
        attrs = dict(_ATTR.findall(m.group(1)))
        f = attrs.get("file", "")
        return f"[code sample: {f}]" if f else ""

    body = _GLOSS.sub(gloss, body)
    body = _CODE.sub(code, body)
    body = _SHORTCODE.sub("", body)
    body = _HEADING_ID.sub("", body)
    return body


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{4,}", "\n\n\n", text)  # 3+ blank lines -> 2 blank lines
    return text.strip()


def doc_version(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
