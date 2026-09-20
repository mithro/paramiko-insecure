#!/bin/sh
# Build python3-paramiko-insecure for one Debian suite.
#
# Run inside a debian:<suite> container with the repository at /w:
#   docker run --rm -v "$PWD:/w" -w /w debian:trixie sh packaging/build.sh
#
# Build-dependencies must resolve from the container's own suite. The tree is
# copied first so the build never touches the checkout, and the .debs are
# written to $OUT.
set -eux

export DEBIAN_FRONTEND=noninteractive
OUT=${OUT:-/w/built-debs}
. /etc/os-release
SUITE=${VERSION_CODENAME:?no VERSION_CODENAME in /etc/os-release}

# bookworm has no python3-pytest-relaxed, which the upstream test suite
# needs, so bookworm is built without running it (the standard nocheck
# profile, which also drops the <!nocheck> build-dependencies). CI's
# end-to-end test still exercises the bookworm package against bookworm's
# own OpenSSH.
case "$SUITE" in
  bookworm) export DEB_BUILD_OPTIONS=nocheck DEB_BUILD_PROFILES=nocheck ;;
esac

apt-get update
apt-get install -y --no-install-recommends \
  build-essential ca-certificates devscripts dpkg-dev equivs quilt

rm -rf /tmp/src
cp -a /w /tmp/src
cd /tmp/src
rm -rf built-debs tmp

mk-build-deps --install --remove \
  --tool 'apt-get -y --no-install-recommends' debian/control

# bookworm's setuptools (66) predates PEP 639: it rejects an SPDX string for
# project.license and a project.license-files key. Rewrite them to the older
# table form in this throwaway copy only. Exact-match, so a changed upstream
# pyproject.toml fails here loudly instead of building something different.
if [ "$SUITE" = bookworm ]; then
  python3 - <<'PY'
from pathlib import Path
p = Path("pyproject.toml")
s = p.read_text()
old = 'license = "LGPL-2.1"\nlicense-files = ["LICENSE"]\n'
assert s.count(old) == 1, "pyproject.toml license lines changed upstream"
p.write_text(s.replace(old, 'license = {text = "LGPL-2.1"}\n'))
PY
fi

dpkg-buildpackage -us -uc -b

mkdir -p "$OUT"
cp ../python3-paramiko-insecure_*.deb "$OUT/"
ls -lh "$OUT"
