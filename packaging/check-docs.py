#!/usr/bin/env python3
"""Fail if anything here recommends hiding paramiko_insecure behind an alias.

`import paramiko_insecure as paramiko` (or `from paramiko_insecure import ...`
into bare names) makes an unprotected connection look exactly like a protected
one at the call site. Every example in this repository keeps the name, and this
check keeps it that way.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Anything a reader might copy: docs and the scripts that demonstrate usage.
SEARCHED = ["README.md", "debian/README.Debian", "debian/control",
            "packaging", "debian/insecure"]
SKIP_SUFFIXES = {".patch", ".pyc"}
FORBIDDEN = [
    (re.compile(r"import\s+paramiko_insecure\s+as\s+(?!paramiko_insecure)"),
     "aliases paramiko_insecure to another name"),
    (re.compile(r"from\s+paramiko_insecure\s+import\s+(?!\*)"),
     "imports names out of paramiko_insecure, losing the name at the call site"),
]
# The prohibition itself has to be quotable.
ALLOW_MARKER = "# NO"


def main():
    problems = []
    for entry in SEARCHED:
        path = REPO / entry
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if not file.is_file() or file.suffix in SKIP_SUFFIXES:
                continue
            if file.resolve() == Path(__file__).resolve():
                continue
            try:
                text = file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if ALLOW_MARKER in line:
                    continue
                for pattern, why in FORBIDDEN:
                    if pattern.search(line):
                        rel = file.relative_to(REPO)
                        problems.append(f"{rel}:{number}: {why}\n    {line.strip()}")
    if problems:
        print("Documentation or examples hide which connections are insecure:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("no aliased imports of paramiko_insecure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
