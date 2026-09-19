#!/usr/bin/env python3
"""Fail if Debian has uploaded a newer paramiko than this fork is based on.

The fork's base is the newest `paramiko (<version>)` entry in
debian/changelog (entries above it are this fork's own, under the
paramiko-legacy source name). Debian's current version comes from
sources.debian.org for the given suite (default: sid).

Exit status 1 means "rebase the fork": merge Debian's new packaging and
refresh debian/patches/legacy/ (see README.md).
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

SUITE = sys.argv[1] if len(sys.argv) > 1 else "sid"
CHANGELOG = Path(__file__).resolve().parent.parent / "debian" / "changelog"


def base_version():
    for line in CHANGELOG.read_text().splitlines():
        m = re.match(r"^paramiko \(([^)]+)\) ", line)
        if m:
            return m.group(1)
    raise SystemExit("no 'paramiko (...)' entry in debian/changelog")


def debian_version():
    url = "https://sources.debian.org/api/src/paramiko/"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    for v in data["versions"]:
        if SUITE in v["suites"]:
            return v["version"]
    raise SystemExit(f"paramiko not found in {SUITE} at {url}")


def newer(a, b):
    """True if Debian version a > b, per dpkg's own comparison."""
    return subprocess.run(
        ["dpkg", "--compare-versions", a, "gt", b]
    ).returncode == 0


def main():
    ours, theirs = base_version(), debian_version()
    print(f"fork is based on Debian paramiko {ours}; {SUITE} has {theirs}")
    if newer(theirs, ours):
        print(f"::error::Debian {SUITE} has paramiko {theirs}, newer than "
              f"this fork's base {ours}. Rebase the fork (see README.md).")
        sys.exit(1)


if __name__ == "__main__":
    main()
