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
# an SSH server and client) come after, also from the suite alone, and must
# not change anything ours run with. In build-deb's Raspbian root, when
# E2E_RASPBIAN_CODENAME names its codename and the suite is a testing
# codename Raspbian has only half copied, openssh-server's own files are
# unpacked without its maintainer scripts (see below); that is listed in
# e2e-notes/unpacked, for the step summary.
set -eux
export DEBIAN_FRONTEND=noninteractive
sh ./apt-sources-unbundled/install.sh
apt-get update
# The suite as it is now: a debian:<suite> image can lag its archive
# (debian:sid shipped libsystemd0 262~rc3-1 against the archive's 262-1), and
# the tools below would otherwise upgrade such packages, which isn't what the
# check after step 2 is looking for. From the suite alone: no staging yet.
apt-get -y dist-upgrade

# 1. Ours, from the suite alone.
apt-get install -y --no-install-recommends \
  ./bundled-debs/*.deb \
  ./built-debs/python3-paramiko-insecure_*.deb
# Everything installed now: ours and their whole run-time closure, as a user
# gets them. The test's tools may add packages, but not change these.
mkdir -p ./e2e-notes
dpkg-query -W -f '${Package} ${Version}\n' | sort > ./e2e-notes/ours-installed

# 2. The test's own tools, from the suite alone too.
harness="python3-paramiko openssh-server openssh-client"
# shellcheck disable=SC2086 # a list of packages
if ! apt-get install -y --no-install-recommends $harness; then
  if [ -z "${E2E_RASPBIAN_CODENAME:-}" ]; then
    echo "the test's own tools don't install from this suite (see apt's message above)"
    exit 1
  fi
  # A half-copied Raspbian testing codename: openssh-server's ucf ->
  # libtext-wrapi18n-perl -> libtext-charwidth-perl needs perl-base 5.42,
  # which only <codename>-staging has, and taking it from there would change
  # the perl-base ours run with (python3 -> tzdata -> debconf -> perl-base).
  # The test only needs the suite's own sshd binary: install what it runs
  # with (its libraries, openssh-common, openssh-sftp-server) from the suite,
  # and unpack openssh-server itself without its maintainer scripts
  # (dpkg --unpack checks no Depends), so ucf is never needed.
  echo "openssh-server doesn't install from raspbian $E2E_RASPBIAN_CODENAME alone; unpacking the suite's sshd without its maintainer scripts"
  deps=$(apt-cache show --no-all-versions openssh-server | sed -n 's/^Depends: //p' | tr ',' '\n' \
         | sed 's/|.*//; s/(.*)//; s/[[:space:]]//g' \
         | grep -E '^(lib|openssh-)' )
  # shellcheck disable=SC2086
  apt-get install -y --no-install-recommends python3-paramiko openssh-client $deps
  (cd /tmp && apt-get download openssh-server)
  dpkg --unpack /tmp/openssh-server_*.deb
  # What its postinst would have made: the privilege separation user.
  id sshd > /dev/null 2>&1 || useradd --system --home-dir /run/sshd --shell /usr/sbin/nologin sshd
  missing=$(ldd /usr/sbin/sshd /usr/lib/openssh/sshd-* | grep 'not found' || true)
  if [ -n "$missing" ]; then
    echo "the unpacked sshd lacks libraries: $missing"
    exit 1
  fi
  mkdir -p ./e2e-notes
  {
    echo "openssh-server $(dpkg-deb -f /tmp/openssh-server_*.deb Version): unpacked without its maintainer scripts (ucf needs perl 5.42, which raspbian $E2E_RASPBIAN_CODENAME doesn't have yet)"
  } > ./e2e-notes/unpacked
  cat ./e2e-notes/unpacked
fi

# Ours and everything they run with must be exactly as step 1 left them: if
# the tools upgraded one of our run-time dependencies (python3, libssl,
# python3-cffi-backend, ...) from outside the suite, the test would exercise ours
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
