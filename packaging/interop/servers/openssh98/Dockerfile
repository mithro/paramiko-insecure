# OpenSSH 9.8p1 built the way /usr/local/bin/insecure-ssh-keyscan on mithro's
# workstation was built (DWARF comp_dir /tmp/openssh-build-*/openssh-9.8p1):
#
#   * --enable-dsa-keys, because 9.8 is the release that disabled DSA at
#     compile time, and that binary still has ssh-dss;
#   * the three SHA-1 key exchanges added to the DEFAULT proposal in
#     myproposal.h, matching the patch in ~/github/openssh/openssh-portable.
#
# It gives us a server that speaks what that tool can scan, and the matching
# ssh-keyscan/ssh binaries to cross-check paramiko_insecure against.
FROM debian:trixie

ARG OPENSSH_VERSION=9.8p1
# https://www.openssh.com/txt/release-9.8 publishes this as base64:
#   SHA256 (openssh-9.8p1.tar.gz) = 3YvQAqN5tdSZ37BQ3R+pr4Ap6ARh9LtsUjxJlz9aOfM=
ARG OPENSSH_SHA256=dd8bd002a379b5d499dfb050dd1fa9af8029e80461f4bb6c523c49973f5a39f3

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl libssl-dev zlib1g-dev \
        python3-minimal \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fsSLO "https://cdn.openbsd.org/pub/OpenBSD/OpenSSH/portable/openssh-${OPENSSH_VERSION}.tar.gz" \
    && echo "${OPENSSH_SHA256}  openssh-${OPENSSH_VERSION}.tar.gz" | sha256sum -c - \
    && tar xzf "openssh-${OPENSSH_VERSION}.tar.gz"

WORKDIR /build/openssh-9.8p1
# Same edit as the workstation tree: SHA-1 kex in the default proposal, so a
# client needs no explicit KexAlgorithms to reach it.
RUN python3 - <<'PY'
from pathlib import Path
p = Path("myproposal.h")
s = p.read_text()
old = '\t"diffie-hellman-group14-sha256"\n'
assert s.count(old) == 1, "myproposal.h KEX_SERVER_KEX changed upstream"
new = ('\t"diffie-hellman-group14-sha256," \\\n'
       '\t"diffie-hellman-group-exchange-sha1," \\\n'
       '\t"diffie-hellman-group14-sha1," \\\n'
       '\t"diffie-hellman-group1-sha1"\n')
p.write_text(s.replace(old, new))
PY

RUN ./configure --prefix=/opt/openssh98 --enable-dsa-keys --with-privsep-path=/var/empty \
    && make -j"$(nproc)" \
    && make install-nokeys

# Privilege separation needs this user and directory.
RUN useradd --system --home-dir /var/empty --shell /usr/sbin/nologin sshd || true

COPY packaging/interop/servers/openssh98/run.sh /run.sh
ENTRYPOINT ["/bin/sh", "/run.sh"]
