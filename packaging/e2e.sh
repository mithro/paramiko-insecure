#!/bin/sh
# Install the built package into a clean debian:<suite> container, next to the
# stock python3-paramiko, and run packaging/e2e_test.py against real sshd.
#   docker run --rm -v "$PWD:/w" -w /w debian:trixie sh packaging/e2e.sh
set -eux
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ./built-debs/python3-paramiko-legacy_*.deb \
  python3-paramiko openssh-server openssh-client
mkdir -p /run/sshd
python3 packaging/e2e_test.py
