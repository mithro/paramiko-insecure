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
# Everything installed now: ours and their whole run-time closure, as a user
# gets them. The test's tools may add packages, but not change these.
mkdir -p ./e2e-notes
dpkg-query -W -f '${Package} ${Version}\n' | sort > ./e2e-notes/ours-installed

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
fi

# Ours and everything they run with must be exactly as step 1 left them: if
# the tools upgraded one of our run-time dependencies (python3, libssl,
# python3-cffi-backend, ...) from staging, the test would exercise ours
# against libraries a user of the suite doesn't have.
dpkg-query -W -f '${Package} ${Version}\n' | sort > ./e2e-notes/after-tools
changed=$(join ./e2e-notes/ours-installed ./e2e-notes/after-tools | awk '$2 != $3 {print $1 ": " $2 " -> " $3}')
gone=$(join -v 1 ./e2e-notes/ours-installed ./e2e-notes/after-tools | awk '{print $1 " " $2 " (removed)"}')
if [ -n "$changed$gone" ]; then
  echo "installing the test's tools changed what ours run with:"
  printf '%s\n' "$changed" "$gone" | grep .
  exit 1
fi

mkdir -p /run/sshd
python3 packaging/e2e_test.py
