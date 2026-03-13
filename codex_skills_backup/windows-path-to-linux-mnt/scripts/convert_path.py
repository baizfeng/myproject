#!/usr/bin/env python3
"""Convert Windows absolute paths to Linux /mnt/<drive>/ paths."""

from __future__ import annotations

import argparse
import re

WINDOWS_DRIVE_RE = re.compile(r"^(?P<drive>[A-Za-z]):(?P<rest>.*)$")


def strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1]
    return value


def convert_path(path: str) -> str:
    raw = strip_wrapping_quotes(path.strip())
    match = WINDOWS_DRIVE_RE.match(raw)
    if not match:
        return raw

    drive = match.group("drive").lower()
    rest = match.group("rest").replace("\\", "/")
    while rest.startswith("/"):
        rest = rest[1:]

    if rest:
        return f"/mnt/{drive}/{rest}"
    return f"/mnt/{drive}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Windows absolute paths to Linux /mnt/<drive> paths."
    )
    parser.add_argument("paths", nargs="+", help="One or more input paths")
    args = parser.parse_args()

    for path in args.paths:
        print(convert_path(path))


if __name__ == "__main__":
    main()
