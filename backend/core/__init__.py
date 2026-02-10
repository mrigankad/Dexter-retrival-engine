"""
Core module - Configuration, security, logging, and dependency injection.
"""

from .config import settings
from .logger import get_logger, setup_logging

__all__ = ["settings", "get_logger", "setup_logging"]
