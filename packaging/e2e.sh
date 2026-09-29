#!/bin/sh
# Install the built package into a clean debian:<suite> container, next to the
# stock python3-paramiko, and run packaging/e2e_test.py against real sshd.
#   docker run --rm -v "$PWD:/w" -w /w debian:trixie sh packaging/e2e.sh
#
# python3-cryptography-insecure comes from bundled-debs/: the packages this
# repository's apt site bundles from mithro/cryptography-insecure, as the
# workflow fetched them. No other repository is added (apt-sources-unbundled/
# adds only dependency repositories that aren't bundled), so this proves our
# repository alone is enough.
set -eux
export DEBIAN_FRONTEND=noninteractive
sh ./apt-sources-unbundled/install.sh
apt-get update
apt-get install -y --no-install-recommends \
  ./bundled-debs/*.deb \
  ./built-debs/python3-paramiko-insecure_*.deb \
  python3-paramiko openssh-server openssh-client
mkdir -p /run/sshd
python3 packaging/e2e_test.py
