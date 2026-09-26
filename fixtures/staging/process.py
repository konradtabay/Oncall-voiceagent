#!/usr/bin/env python3
"""Staging health-file process fixture for manual verify targets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def health_path(raw: str | None) -> Path:
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent / "health"


def cmd_start(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("up\n", encoding="utf-8")
    return 0


def cmd_kill(path: Path) -> int:
    if path.exists():
        path.unlink()
    return 0


def cmd_restart(path: Path) -> int:
    return cmd_start(path)


def cmd_status(path: Path) -> int:
    if path.exists() and path.read_text(encoding="utf-8").strip() == "up":
        print("up")
        return 0
    print("down")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Staging process health fixture")
    parser.add_argument(
        "action",
        choices=("start", "kill", "restart", "status"),
    )
    parser.add_argument(
        "--health",
        default=None,
        help="Health file path (default: fixtures/staging/health)",
    )
    args = parser.parse_args(argv)
    path = health_path(args.health)
    if args.action == "start":
        return cmd_start(path)
    if args.action == "kill":
        return cmd_kill(path)
    if args.action == "restart":
        return cmd_restart(path)
    return cmd_status(path)


if __name__ == "__main__":
    sys.exit(main())
