#!/usr/bin/python3
"""Rename the paramiko package to paramiko_insecure, or undo that rename.

    rename-module.py apply    # paramiko/ -> paramiko_insecure/, rewrite refs
    rename-module.py revert   # exact inverse, for `debian/rules clean`

This is what lets python3-paramiko-insecure be co-installed with the normal
python3-paramiko: it installs a different import package, a different
dist-info, and nothing at all under the name "paramiko". Only code that
explicitly does `import paramiko_insecure` ever reaches the obsolete
algorithms.

REFERENCE_ONLY names are rewritten but not moved: the package they name is
built elsewhere (python3-cryptography-insecure), and pointing at it keeps
paramiko_insecure independent of whatever the system cryptography still
supports.

Rewrites are done on Python *tokens*, not raw text, so they are precise:

- NAME tokens exactly equal to a renamed module (imports, attribute chains);
- string literals whose whole content is a dotted module path such as
  "paramiko.transport" (logger names, mock.patch() targets and
  importlib.metadata.version("paramiko")).

Comments, docstrings, URLs, hostnames like "www.paramiko.org" used by the
test suite, and the "SSH-2.0-paramiko_<version>" banner are left untouched.
Because nothing in upstream is spelled with the _insecure suffix, the
rewrite is a bijection and `revert` restores the tree byte for byte.
"""

import re
import sys
import tokenize
from pathlib import Path

# (original, renamed) for the package this source tree builds.
PACKAGE = ("paramiko", "paramiko_insecure")
# Modules referenced but not contained here; rewritten in place, never moved.
# Filled in once python3-cryptography-insecure exists; see debian/rules.
REFERENCE_ONLY = [
    ("cryptography", "cryptography_insecure"),
] if Path("debian/insecure/use-private-cryptography").exists() else []
# Directories of Python source to rewrite, besides the package itself.
EXTRA_DIRS = ("tests",)
# (original line, renamed line) -- exact, whole-line matches only.
PYPROJECT_LINES = [
    ('name = "paramiko"', 'name = "paramiko_insecure"'),
    ('packages = ["paramiko"]', 'packages = ["paramiko_insecure"]'),
]
# Added to PYPROJECT_LINES when the private cryptography is in use, so the
# built package depends on it rather than on the system one.
PRIVATE_CRYPTO_LINE = (
    '  "cryptography>=3.3",', '  "cryptography_insecure>=3.3",'
)
STRING_PREFIX = re.compile(r"^([rRbBuU]{0,2})('''|\"\"\"|'|\")")


def rewrite_python(path, renames):
    """Apply every (src, dst) rename to one file; return the edit count."""
    patterns = [
        (src, dst, re.compile(rf"^{re.escape(src)}(\.[A-Za-z_]\w*)*$"))
        for src, dst in renames
    ]
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    edits = []  # (row, col, old_len, replacement)
    with path.open("rb") as f:
        for tok in tokenize.tokenize(f.readline):
            (row, col), (erow, _) = tok.start, tok.end
            for src, dst, module_path in patterns:
                if tok.type == tokenize.NAME:
                    if tok.string == dst:
                        raise SystemExit(f"{path}:{row}: already has {dst}")
                    if tok.string == src:
                        edits.append((row, col, src, dst))
                elif tok.type == tokenize.STRING and row == erow:
                    m = STRING_PREFIX.match(tok.string)
                    if not m:
                        continue
                    quote = m.group(2)
                    if module_path.match(tok.string[m.end():-len(quote)]):
                        edits.append((row, col + m.end(), src, dst))
    for row, col, src, dst in sorted(edits, reverse=True):
        line = lines[row - 1]
        assert line[col:col + len(src)] == src, (path, row, col, src)
        lines[row - 1] = line[:col] + dst + line[col + len(src):]
    if edits:
        path.write_text("".join(lines), encoding="utf-8")
    return len(edits)


def rewrite_pyproject(root, forward):
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    wanted = list(PYPROJECT_LINES)
    if REFERENCE_ONLY:
        wanted.append(PRIVATE_CRYPTO_LINE)
    for orig, renamed in wanted:
        src, dst = (orig, renamed) if forward else (renamed, orig)
        if sum(1 for ln in text.splitlines() if ln == src) != 1:
            raise SystemExit(f"pyproject.toml: expected one line {src!r}")
        text = text.replace(src + "\n", dst + "\n")
    path.write_text(text, encoding="utf-8")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("apply", "revert"):
        raise SystemExit(__doc__)
    forward = sys.argv[1] == "apply"
    root = Path.cwd()
    old, new = PACKAGE
    src_name, dst_name = (old, new) if forward else (new, old)
    renames = [(src_name, dst_name)] + [
        (a, b) if forward else (b, a) for a, b in REFERENCE_ONLY
    ]

    # Idempotent: a clean tree is not an error for `revert` (dh clean runs
    # before every build), and a renamed tree is not an error for `apply`.
    if not (root / src_name).is_dir():
        if (root / dst_name).is_dir():
            print(f"rename-module: {sys.argv[1]}: already done, nothing to do")
            return
        raise SystemExit(f"rename-module: neither {old}/ nor {new}/ found")

    total = 0
    for d in (src_name, *EXTRA_DIRS):
        for py in sorted((root / d).rglob("*.py")):
            total += rewrite_python(py, renames)
    rewrite_pyproject(root, forward)
    (root / src_name).rename(root / dst_name)
    print(f"rename-module: {sys.argv[1]}: {total} references rewritten")


if __name__ == "__main__":
    main()
