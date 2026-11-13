"""
src/config.py
-------------
Loads config/settings.yaml into a dot-accessible object and resolves the
data directory (outside the repository; override with NEUROSYNC_DATA_DIR).

Usage:
    from src.config import settings, data_dir
    settings.behaviour.window_s
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG = PROJECT_ROOT / "config" / "settings.yaml"


class AttrDict(dict):
    """dict with attribute access; nested dicts are converted once at load time."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for k, v in self.items():
            if isinstance(v, dict):
                super().__setitem__(k, AttrDict(v))

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(f"Config has no attribute '{key}'") from None

    def __setattr__(self, key, value):
        self[key] = AttrDict(value) if isinstance(value, dict) and not isinstance(value, AttrDict) else value


def load_settings(path: str | os.PathLike | None = None) -> AttrDict:
    path = Path(path or os.environ.get("NEUROSYNC_CONFIG") or _DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        return AttrDict(yaml.safe_load(f))


def data_dir(cfg: AttrDict | None = None) -> Path:
    """Directory for sessions, the encryption key and the audit log (created if missing)."""
    cfg = cfg or settings
    raw = os.environ.get("NEUROSYNC_DATA_DIR") or cfg.storage.data_dir
    path = Path(os.path.expanduser(raw)).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve(path: str | os.PathLike) -> Path:
    """Resolve a project-relative path (e.g. the optional LLM file)."""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p


settings = load_settings()
