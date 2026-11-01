"""Config, .env and path helpers."""
from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
PROMPTS = ROOT / "prompts"
ASSETS = ROOT / "assets"


def load_env(path: Path | None = None) -> None:
    """Minimal .env loader (KEY=value per line). Existing env vars win."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: Path | None = None) -> dict:
    path = path or ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def slugify(text: str, max_len: int = 48) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len].strip("-") or "untitled"


def project_dir(slug: str) -> Path:
    d = PROJECTS / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"Lipseste {name}. Pune-l in fisierul .env (vezi .env.example) "
            f"sau ruleaza cu --mock ca sa testezi fara API."
        )
    return value
