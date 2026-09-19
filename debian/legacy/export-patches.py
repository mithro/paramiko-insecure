#!/usr/bin/env python3
"""Regenerate debian/patches/legacy/ from a git branch of upstream paramiko.

The branch must hold one `git revert` commit per upstream commit that removed
legacy SSH support, sitting on top of the upstream release with Debian's own
patches applied (so the exported diffs apply after them, with no fuzz):

    export-patches.py --repo ~/paramiko --base debian-base --branch legacy

The upstream commit each revert undoes is read from the revert's standard
"This reverts commit <sha>" trailer and recorded in the DEP-3 Origin field.
Extra notes for a patch (e.g. what had to be forward-ported by hand) go after
a "Legacy-Note:" line in the revert's commit message.
"""

import argparse
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATCH_DIR = HERE.parent / "patches" / "legacy"
SERIES = HERE.parent / "patches" / "series"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def header(subject, orig, note):
    lines = [
        "From: Tim 'mithro' Ansell <me@mith.ro>",
        f'Subject: Revert "{subject}"',
        "",
        "Restore legacy SSH support removed upstream, for talking to old",
        "devices that cannot be upgraded. Shipped only in the separate",
        "paramiko_legacy module; python3-paramiko is untouched.",
    ]
    if note:
        lines += ["", *note.strip().splitlines()]
    lines += [
        "",
        "Origin: vendor, reverts "
        f"https://github.com/paramiko/paramiko/commit/{orig}",
        "Forwarded: not-needed",
        "---",
    ]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--base", required=True)
    ap.add_argument("--branch", required=True)
    args = ap.parse_args()

    revs = git(args.repo, "rev-list", "--reverse",
               f"{args.base}..{args.branch}").split()
    if not revs:
        raise SystemExit(f"no commits in {args.base}..{args.branch}")

    PATCH_DIR.mkdir(parents=True, exist_ok=True)
    for old in PATCH_DIR.glob("*.patch"):
        old.unlink()

    names = []
    for i, rev in enumerate(revs, 1):
        body = git(args.repo, "log", "-1", "--format=%B", rev)
        m = re.search(r"This reverts commit ([0-9a-f]{40})", body)
        if not m:
            raise SystemExit(f"{rev} is not a git revert commit")
        orig = m.group(1)
        subject = git(args.repo, "log", "-1", "--format=%s", orig).strip()
        note = body.split("Legacy-Note:", 1)[1] if "Legacy-Note:" in body else ""
        slug = re.sub(r"[^A-Za-z0-9]+", "-", subject).strip("-")[:50]
        name = f"{i:04d}-revert-{slug}.patch"
        diff = git(args.repo, "diff", "--no-renames", f"{rev}^", rev)
        (PATCH_DIR / name).write_text(header(subject, orig, note) + diff)
        names.append(f"legacy/{name}")
        print(name)

    # Debian's own patches stay first, in their existing order.
    kept = [
        line for line in SERIES.read_text().splitlines()
        if line.strip() and not line.startswith("legacy/")
    ]
    SERIES.write_text("\n".join(kept + names) + "\n")


if __name__ == "__main__":
    main()
