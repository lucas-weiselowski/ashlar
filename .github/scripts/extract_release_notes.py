#!/usr/bin/env python3
"""Pull one version's section out of CHANGELOG.md (Keep a Changelog format) for use as release notes."""

import re
import sys
from pathlib import Path

if len(sys.argv) != 2:
    print("usage: extract_release_notes.py X.Y.Z", file=sys.stderr)
    sys.exit(2)

version = sys.argv[1]
changelog = Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"
text = changelog.read_text()

pattern = re.compile(
    rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)",
    re.MULTILINE | re.DOTALL,
)
match = pattern.search(text)
if not match:
    print(f"no CHANGELOG.md section found for version {version}", file=sys.stderr)
    sys.exit(1)

print(match.group(1).strip())
