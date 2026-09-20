# Debian 4.0 "etch" (2007): OpenSSH 4.3p2 against OpenSSL 0.9.8c, and
# Dropbear 0.48. These are the real binaries as shipped in 2007 -- nothing of
# that era builds against a current OpenSSL or gcc, and this is as close to
# the equipment the package exists for as can be had without the equipment.
#
# Built as linux/386: that runs natively on x86-64 CI, and unlike amd64 under
# qemu-aarch64 it is stable when emulated on an arm64 workstation (etch's apt
# http method segfaults there).
#
# Packages are installed at build time so the container itself needs no
# network beyond the private one it shares with the client.
FROM debian/eol:etch

# archive.debian.org still carries etch. Its Release files and signing keys
# expired long ago, which is exactly what a 2007 archive looks like.
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --force-yes openssh-server dropbear < /dev/null \
    || true

# The maintainer scripts of this vintage can fail (they do under emulation);
# the binaries are what matter, so check for those explicitly instead.
RUN test -x /usr/sbin/sshd && test -x /usr/sbin/dropbear \
    && test -x /usr/bin/dropbearkey && test -x /usr/bin/ssh-keygen

COPY packaging/interop/servers/etch/etch.sh /etch.sh
ENTRYPOINT ["/bin/sh", "/etch.sh"]
