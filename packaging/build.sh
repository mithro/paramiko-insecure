#!/bin/sh
# Build python3-paramiko-legacy for one Debian suite.
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

dpkg-buildpackage -us -uc -b

mkdir -p "$OUT"
cp ../python3-paramiko-legacy_*.deb "$OUT/"
ls -lh "$OUT"
