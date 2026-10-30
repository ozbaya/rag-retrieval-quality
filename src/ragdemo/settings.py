"""Central settings: .env plus YAML config files."""
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


@lru_cache
def load_yaml(rel_path: str) -> dict:
    return yaml.safe_load((ROOT / rel_path).read_text())


def providers() -> dict:
    return load_yaml("config/providers.yaml")


def pipelines() -> dict:
    return load_yaml("config/pipelines.yaml")


def model(role: str) -> str:
    return providers()["models"][role]["id"]


def prompt(name: str) -> str:
    return (ROOT / "config" / "prompts" / f"{name}.txt").read_text()
