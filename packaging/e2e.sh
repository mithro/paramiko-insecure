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
#
# Ours are installed first and on their own, from the suite alone: that is
# what a user gets, and it must work. The test's own tools (stock paramiko,
# an SSH server and client) come after. In build-deb's Raspbian root, and
# only when E2E_RASPBIAN_CODENAME names its codename, those tools may fall
# back to Raspbian's <codename>-staging (mithro/apt-repo-action
# build-deb/raspbian/staging.sh: the same pinned archive key), for a testing
# codename Raspbian has only half copied (raspbian forky's perl 5.40 can't
# install openssh-server's ucf chain, which needs perl-base 5.42). What came
# from staging is listed in e2e-notes/from-staging, for the step summary.
set -eux
export DEBIAN_FRONTEND=noninteractive
sh ./apt-sources-unbundled/install.sh
apt-get update

# 1. Ours, from the suite alone.
apt-get install -y --no-install-recommends \
  ./bundled-debs/*.deb \
  ./built-debs/python3-paramiko-insecure_*.deb

# 2. The test's own tools.
harness="python3-paramiko openssh-server openssh-client"
# shellcheck disable=SC2086 # a list of packages
if ! apt-get install -y --no-install-recommends $harness; then
  if [ -z "${E2E_RASPBIAN_CODENAME:-}" ]; then
    echo "the test's own tools don't install from this suite (see apt's message above)"
    exit 1
  fi
  echo "the test's tools don't install from raspbian $E2E_RASPBIAN_CODENAME alone; trying $E2E_RASPBIAN_CODENAME-staging"
  sh ./.apt-repo-action/build-deb/raspbian/staging.sh add "$E2E_RASPBIAN_CODENAME" ./e2e-notes
  # shellcheck disable=SC2086
  apt-get install -y --no-install-recommends $harness
  sh ./.apt-repo-action/build-deb/raspbian/staging.sh report ./e2e-notes
  # Ours must still be the suite's: staging only ever supplies the tools.
  for p in python3-paramiko-insecure python3-cryptography-insecure; do
    if grep -q "^$p " ./e2e-notes/from-staging; then
      echo "$p was replaced from staging: the test would no longer be of what users get"
      exit 1
    fi
  done
fi

mkdir -p /run/sshd
python3 packaging/e2e_test.py
