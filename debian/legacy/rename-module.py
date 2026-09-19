#!/usr/bin/python3
"""Rename the paramiko package to paramiko_legacy, or undo that rename.

    rename-module.py apply    # paramiko/ -> paramiko_legacy/, rewrite refs
    rename-module.py revert   # exact inverse, for `debian/rules clean`

This is what lets python3-paramiko-legacy be co-installed with the normal
python3-paramiko: it installs a different import package, a different
dist-info, and nothing at all under the name "paramiko". Only code that
explicitly does `import paramiko_legacy` ever gets the legacy algorithms.

Rewrites are done on Python *tokens*, not raw text, so they are precise:

- NAME tokens exactly equal to `paramiko` (imports and attribute chains);
- string literals whose whole content is a dotted module path such as
  "paramiko.transport" (logger names, mock.patch() targets and
  importlib.metadata.version("paramiko")).

Comments, docstrings, URLs, hostnames like "www.paramiko.org" used by the
test suite, and the "SSH-2.0-paramiko_<version>" banner are left untouched.
Because nothing in upstream is spelled `paramiko_legacy`, the rewrite is a
bijection and `revert` restores the tree byte for byte.
"""

import re
import sys
import tokenize
from pathlib import Path

OLD, NEW = "paramiko", "paramiko_legacy"
# (original line, renamed line) -- exact, whole-line matches only.
PYPROJECT_LINES = [
    ('name = "paramiko"', 'name = "paramiko_legacy"'),
    ('packages = ["paramiko"]', 'packages = ["paramiko_legacy"]'),
]
STRING_PREFIX = re.compile(r"^([rRbBuU]{0,2})('''|\"\"\"|'|\")")


def rewrite_python(path, src_name, dst_name):
    module_path = re.compile(
        rf"^{re.escape(src_name)}(\.[A-Za-z_]\w*)*$"
    )
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    edits = []  # (row, col, old_len, replacement)
    with path.open("rb") as f:
        for tok in tokenize.tokenize(f.readline):
            (row, col), (erow, _) = tok.start, tok.end
            if tok.type == tokenize.NAME:
                if tok.string == dst_name:
                    raise SystemExit(f"{path}:{row}: already has {dst_name}")
                if tok.string == src_name:
                    edits.append((row, col, len(src_name), dst_name))
            elif tok.type == tokenize.STRING and row == erow:
                m = STRING_PREFIX.match(tok.string)
                if not m:
                    continue
                quote = m.group(2)
                body = tok.string[m.end():-len(quote)]
                if module_path.match(body):
                    start = col + m.end()
                    edits.append((row, start, len(src_name), dst_name))
    if not edits:
        return 0
    for row, col, n, repl in sorted(edits, reverse=True):
        line = lines[row - 1]
        assert line[col:col + n] == src_name, (path, row, col)
        lines[row - 1] = line[:col] + repl + line[col + n:]
    path.write_text("".join(lines), encoding="utf-8")
    return len(edits)


def rewrite_pyproject(root, forward):
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    for orig, renamed in PYPROJECT_LINES:
        src, dst = (orig, renamed) if forward else (renamed, orig)
        found = [ln for ln in text.splitlines() if ln == src]
        if len(found) != 1:
            raise SystemExit(f"pyproject.toml: expected one line {src!r}")
        text = text.replace(src + "\n", dst + "\n")
    path.write_text(text, encoding="utf-8")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("apply", "revert"):
        raise SystemExit(__doc__)
    forward = sys.argv[1] == "apply"
    root = Path.cwd()
    src_name, dst_name = (OLD, NEW) if forward else (NEW, OLD)

    # Idempotent: a clean tree is not an error for `revert` (dh clean runs
    # before every build), and a renamed tree is not an error for `apply`.
    if not (root / src_name).is_dir():
        if (root / dst_name).is_dir():
            print(f"rename-module: {sys.argv[1]}: already done, nothing to do")
            return
        raise SystemExit(f"rename-module: neither {OLD}/ nor {NEW}/ found")

    total = 0
    for d in (src_name, "tests"):
        for py in sorted((root / d).rglob("*.py")):
            total += rewrite_python(py, src_name, dst_name)
    rewrite_pyproject(root, forward)
    (root / src_name).rename(root / dst_name)
    print(f"rename-module: {sys.argv[1]}: {total} references rewritten")


if __name__ == "__main__":
    main()
