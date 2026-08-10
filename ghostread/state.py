"""Remembers where you left off.

State lives in a single JSON file under the user's home directory. Each
document gets its own entry keyed by absolute path, so reopening a textbook
drops you back on the page you were reading.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR_NAME = ".ghostread"
STATE_FILE_NAME = "state.json"
MAX_ENTRIES = 200

DEFAULTS = {
    "page": 0,
    "zoom": None,
    "fit": "width",
    "opacity": 0.80,
    "invert": False,
    "geometry": None,
}


def state_dir() -> Path:
    base = os.environ.get("GHOSTREAD_HOME")
    if base:
        return Path(base).expanduser()
    return Path.home() / APP_DIR_NAME


def state_path() -> Path:
    return state_dir() / STATE_FILE_NAME


def _load_all() -> dict:
    path = state_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        # A corrupt state file must never stop the reader from opening.
        return {}


def _save_all(data: dict) -> None:
    try:
        directory = state_dir()
        directory.mkdir(parents=True, exist_ok=True)
        tmp = state_path().with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        tmp.replace(state_path())
    except Exception:
        pass


def _key(pdf_path) -> str:
    return str(Path(pdf_path).expanduser().resolve())


def load(pdf_path) -> dict:
    merged = dict(DEFAULTS)
    entry = _load_all().get("documents", {}).get(_key(pdf_path))
    if isinstance(entry, dict):
        for name in DEFAULTS:
            if name in entry:
                merged[name] = entry[name]
    return merged


def save(pdf_path, values: dict) -> None:
    data = _load_all()
    documents = data.setdefault("documents", {})
    entry = documents.setdefault(_key(pdf_path), {})
    for name in DEFAULTS:
        if name in values:
            entry[name] = values[name]
    entry["_touched"] = __import__("time").time()

    # Trim the oldest entries so the file cannot grow without bound.
    if len(documents) > MAX_ENTRIES:
        ordered = sorted(
            documents.items(), key=lambda kv: kv[1].get("_touched", 0), reverse=True
        )
        data["documents"] = dict(ordered[:MAX_ENTRIES])

    _save_all(data)


def recent(limit: int = 15):
    """Most recently opened documents, newest first."""
    documents = _load_all().get("documents", {})
    ordered = sorted(
        documents.items(), key=lambda kv: kv[1].get("_touched", 0), reverse=True
    )
    return [path for path, _ in ordered[:limit] if Path(path).exists()]


def get_flag(name: str, default=None):
    """Read an app wide setting, as opposed to a per document one."""
    return _load_all().get("flags", {}).get(name, default)


def set_flag(name: str, value) -> None:
    data = _load_all()
    data.setdefault("flags", {})[name] = value
    _save_all(data)
