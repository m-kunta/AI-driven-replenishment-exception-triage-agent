#!/usr/bin/env python
"""CLI entry point for the replenishment exception triage pipeline.

Usage:
    python scripts/run_triage.py [OPTIONS]

Options:
    --config PATH           Path to config YAML (default: config/config.yaml)
    --date DATE             Run date YYYY-MM-DD (default: today)
    --dry-run               Layer 1+2 only; print enrichment summary, no AI calls
    --no-alerts             Full pipeline but skip alert dispatch
    --sample                Force sample data path (data/sample/exceptions_sample.csv)
    --verbose               Verbose / DEBUG logging to stderr
    --output-format FORMAT  markdown | json | both  [not yet wired to output layer]

Author: Mohith Kunta <mohith.kunta@gmail.com>
GitHub: https://github.com/m-kunta
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on sys.path when the script is invoked directly
# (e.g. `python scripts/run_triage.py`) from any working directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.main import run_triage_pipeline  # noqa: E402 — must follow sys.path setup
from src.utils.exceptions import ConfigurationError  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_triage.py",
        description="AI-driven replenishment exception triage pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default="config/config.yaml",
        help="Path to config YAML file (default: config/config.yaml)",
    )
    parser.add_argument(
        "--date",
        metavar="DATE",
        default=None,
        help="Run date in YYYY-MM-DD format (default: today)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run ingestion and enrichment only; print summary and exit",
    )
    parser.add_argument(
        "--no-alerts",
        action="store_true",
        default=False,
        help="Skip alert dispatch (useful for testing / CI runs)",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        default=False,
        help="Force sample data path regardless of config setting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable DEBUG-level logging to stderr",
    )
    parser.add_argument(
        "--output-format",
        metavar="FORMAT",
        choices=["markdown", "json", "both"],
        default="markdown",
        help="Output format: markdown | json | both (default: markdown)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and invoke the triage pipeline.

    Returns:
        0 on success, 1 on configuration/runtime error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        run_triage_pipeline(
            config_path=args.config,
            run_date=args.date,
            dry_run=args.dry_run,
            no_alerts=args.no_alerts,
            sample=args.sample,
            verbose=args.verbose,
        )
    except ConfigurationError as exc:
        print(f"\n[ERROR] Configuration problem: {exc}", file=sys.stderr)
        print("Check your config/config.yaml and environment variables.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 1
    except Exception as exc:  # pylint: disable=broad-except
        print(f"\n[ERROR] Unexpected error: {type(exc).__name__}: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
