"""Configuration package.

Export the singleton so ``from core.config import settings`` returns the
Settings object instead of the ``core.config.settings`` module.
"""
from core.config.settings import settings

__all__ = ["settings"]
