import json
import re
from pathlib import Path

from openai import OpenAI

WORD = re.compile(r"[a-z0-9]{3,}")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, items: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items))
    tmp.replace(path)


def openai_json(model_id: str, system: str, user: str, schema: dict, name: str) -> dict:
    """Chat completion with strict JSON schema output."""
    resp = OpenAI(timeout=60, max_retries=3).chat.completions.create(
        model=model_id,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}})
    return json.loads(resp.choices[0].message.content)


def verbatim_overlap(question: str, evidence: str) -> float:
    q = set(WORD.findall(question.lower()))
    e = set(WORD.findall(evidence.lower()))
    return len(q & e) / len(q) if q else 0.0
