# The client side of the interop test: one Debian suite with the built
# python3-paramiko-insecure installed next to the stock python3-paramiko, so
# the two are exercised together in one process.
#
# Build context is the repository root; the .deb comes from built-debs/, and
# python3-cryptography-insecure from bundled-debs/ (what our apt site
# bundles from mithro/cryptography-insecure).
ARG SUITE=trixie
FROM debian:${SUITE}

COPY built-debs/python3-paramiko-insecure_*.deb /debs/
COPY bundled-debs/ /bundled/

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        /bundled/*.deb \
        /debs/python3-paramiko-insecure_*.deb python3-paramiko \
    && rm -rf /var/lib/apt/lists/*

COPY packaging/interop/prepare.py packaging/interop/client.py /interop/
WORKDIR /interop
