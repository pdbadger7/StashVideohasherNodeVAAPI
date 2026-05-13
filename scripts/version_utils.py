#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path


PROJECT_BLOCK_RE = re.compile(r"(?ms)^\[project\]\n(.*?)(?:^\[|\Z)")
VERSION_LINE_RE = re.compile(r'(?m)^version\s*=\s*"(\d+\.\d+\.\d+)"\s*$')


def bump_minor_version(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version.strip())
    if not match:
        raise ValueError(f"Invalid version format: {version!r}")
    major, minor, _patch = (int(part) for part in match.groups())
    return f"{major}.{minor + 1}.0"


def extract_project_version(content):
    block_match = PROJECT_BLOCK_RE.search(content)
    if not block_match:
        raise ValueError("Missing [project] table in pyproject content")
    project_block = block_match.group(1)
    version_match = VERSION_LINE_RE.search(project_block)
    if not version_match:
        raise ValueError("Missing project version line in pyproject content")
    return version_match.group(1)


def replace_project_version(content, new_version):
    block_match = PROJECT_BLOCK_RE.search(content)
    if not block_match:
        raise ValueError("Missing [project] table in pyproject content")
    start, end = block_match.span(1)
    project_block = content[start:end]
    if not VERSION_LINE_RE.search(project_block):
        raise ValueError("Missing project version line in pyproject content")
    updated_block = VERSION_LINE_RE.sub(f'version = "{new_version}"', project_block, count=1)
    return f"{content[:start]}{updated_block}{content[end:]}"


def bump_file(path):
    original = Path(path).read_text(encoding="utf-8")
    current = extract_project_version(original)
    bumped = bump_minor_version(current)
    updated = replace_project_version(original, bumped)
    Path(path).write_text(updated, encoding="utf-8")
    return current, bumped


def versions_equal(content_old, content_new):
    return extract_project_version(content_old) == extract_project_version(content_new)


def _build_parser():
    parser = argparse.ArgumentParser(description="Utilities for pyproject version detection and bumps.")
    sub = parser.add_subparsers(dest="command", required=True)

    bump = sub.add_parser("bump-minor", help="Bump minor version in a pyproject.toml file")
    bump.add_argument("--file", required=True, help="Path to pyproject.toml")

    equal_cmd = sub.add_parser("equal", help="Check whether two pyproject contents have the same version")
    equal_cmd.add_argument("--old-file", required=True, help="Old pyproject.toml file")
    equal_cmd.add_argument("--new-file", required=True, help="New pyproject.toml file")

    return parser


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "bump-minor":
        previous, bumped = bump_file(args.file)
        print(f"old_version={previous}")
        print(f"new_version={bumped}")
        return 0

    if args.command == "equal":
        old_content = Path(args.old_file).read_text(encoding="utf-8")
        new_content = Path(args.new_file).read_text(encoding="utf-8")
        same = versions_equal(old_content, new_content)
        print("equal=true" if same else "equal=false")
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
