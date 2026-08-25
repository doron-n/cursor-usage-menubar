from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATH = ROOT / "VERSION"
CHANGELOG_PATH = ROOT / "docs" / "changelog.json"
PAGES_URL = "https://doron-n.github.io/cursor-usage-menubar/"


def notes_for(version: str, path: Path = CHANGELOG_PATH, *, history: bool = False) -> str:
    fallback = (
        f"Cursor Usage {version} for Apple Silicon.\n\n"
        f"Download and install notes: {PAGES_URL}\n"
    )
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback
    releases = [
        rel
        for rel in (data.get("releases") or [])
        if isinstance(rel, dict) and rel.get("version")
    ]
    if not releases:
        return fallback
    start = next((i for i, rel in enumerate(releases) if rel.get("version") == version), None)
    if start is None:
        return fallback
    chosen = releases[start:] if history else [releases[start]]
    lines = [f"Cursor Usage {version} for Apple Silicon.", ""]
    for index, rel in enumerate(chosen):
        ver = str(rel.get("version") or "").strip()
        title = str(rel.get("title") or "").strip()
        highlights = [
            str(item).strip()
            for item in (rel.get("highlights") or [])
            if str(item).strip()
        ]
        if index == 0:
            if title:
                lines.extend([title, ""])
        else:
            heading = f"{ver} — {title}" if title else ver
            lines.extend(["", f"## {heading}", ""])
        lines.extend(f"- {item}" for item in highlights)
    lines.extend(["", f"Download and install notes: {PAGES_URL}"])
    return "\n".join(lines)


def read_version(path: Path = VERSION_PATH) -> str:
    return path.read_text(encoding="utf-8").strip()


def bump(version: str, part: str = "patch") -> str:
    bits = version.split(".")
    if len(bits) != 3 or not all(b.isdigit() for b in bits):
        raise ValueError(f"invalid version: {version!r}")
    major, minor, patch = (int(b) for b in bits)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"invalid bump part: {part!r}")


def write_version(version: str, path: Path = VERSION_PATH) -> None:
    path.write_text(f"{version}\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Read or bump the app VERSION file")
    parser.add_argument("--current", action="store_true", help="print the current version")
    parser.add_argument(
        "--bump",
        choices=("major", "minor", "patch"),
        help="print the next version (does not write unless --write)",
    )
    parser.add_argument("--write", metavar="VERSION", help="write this version to VERSION")
    parser.add_argument(
        "--notes",
        metavar="VERSION",
        nargs="?",
        const="current",
        help="print GitHub release notes for VERSION (default: current VERSION file)",
    )
    parser.add_argument(
        "--notes-history",
        action="store_true",
        help="with --notes, include every older changelog version after the selected one",
    )
    args = parser.parse_args()
    if args.write:
        write_version(args.write)
        print(args.write)
        return
    if args.notes:
        version = read_version() if args.notes == "current" else args.notes
        print(notes_for(version, history=args.notes_history), end="")
        return
    if args.current:
        print(read_version())
        return
    print(bump(read_version(), args.bump or "patch"))


if __name__ == "__main__":
    main()
