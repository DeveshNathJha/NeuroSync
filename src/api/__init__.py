"""NeuroSync local API (FastAPI). Run with `python -m src.api`."""

from src.api.app import create_app, get_app

__all__ = ["create_app", "get_app"]
