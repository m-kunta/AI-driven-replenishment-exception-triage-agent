"""Structured logging setup using loguru.

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

import sys
from loguru import logger


def setup_logger(verbose: bool = False) -> None:
    """Configure loguru with structured output.

    Args:
        verbose: If True, set level to DEBUG. Otherwise INFO.
    """
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{module}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        level=level,
        colorize=True,
    )


def get_logger():
    """Return the configured loguru logger instance."""
    return logger
