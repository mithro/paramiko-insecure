#!/bin/sh
# Start a 2007-vintage SSH server inside debian/eol:etch.
#
#   KIND      openssh (4.3p2) or dropbear (0.48)
#   PORT      port to listen on
#   HOST      hostname the client will use (this container's name)
#   SHARE     directory shared with the client container
#   NAME      name used for this server's files in SHARE
#
# Debian 4.0 "etch" is used rather than building these from source: nothing of
# that era compiles against a current OpenSSL or gcc, and these are the real
# binaries as shipped, against a real OpenSSL 0.9.8.
set -eux

: "${KIND:?}" "${PORT:?}" "${HOST:?}" "${SHARE:?}" "${NAME:=etch}"

# openssh-server and dropbear are installed in the image (see Dockerfile);
# this container has no route off its private network.
mkdir -p /root/.ssh /var/run/sshd /etc/dropbear
chmod 700 /root/.ssh
cp "$SHARE/authorized_keys" /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "root:$(cat "$SHARE/password")" | chpasswd

case "$KIND" in
openssh)
    test -x /usr/sbin/sshd
    /usr/sbin/sshd -\? 2>&1 | sed -n 2p > "$SHARE/$NAME.version" || true
    ssh-keygen -q -t rsa -b 1024 -N "" -f /etc/ssh/host_rsa
    ssh-keygen -q -t dsa -b 1024 -N "" -f /etc/ssh/host_dsa
    cat > /etc/ssh/sshd_config_interop <<EOF
Port $PORT
Protocol 2
HostKey /etc/ssh/host_rsa
HostKey /etc/ssh/host_dsa
PermitRootLogin yes
PasswordAuthentication yes
PubkeyAuthentication yes
AuthorizedKeysFile /root/.ssh/authorized_keys
UsePAM no
UsePrivilegeSeparation no
StrictModes no
Subsystem sftp /usr/lib/openssh/sftp-server
PidFile /var/run/sshd_interop.pid
EOF
    {
        printf '[%s]:%s %s\n' "$HOST" "$PORT" "$(cut -d' ' -f1,2 /etc/ssh/host_rsa.pub)"
        printf '[%s]:%s %s\n' "$HOST" "$PORT" "$(cut -d' ' -f1,2 /etc/ssh/host_dsa.pub)"
    } > "$SHARE/$NAME.known_hosts"
    /usr/sbin/sshd -t -f /etc/ssh/sshd_config_interop
    touch "$SHARE/$NAME.ready"
    exec /usr/sbin/sshd -D -e -f /etc/ssh/sshd_config_interop
    ;;
dropbear)
    test -x /usr/sbin/dropbear
    dropbear -h 2>&1 | head -1 > "$SHARE/$NAME.version" || true
    dropbearkey -t rsa -s 1024 -f /etc/dropbear/host_rsa
    dropbearkey -t dss -f /etc/dropbear/host_dss
    # dropbearkey -y prints "Public key portion is: <type> <base64> <comment>"
    {
        dropbearkey -y -f /etc/dropbear/host_rsa | sed -n "s|^ssh-rsa |[$HOST]:$PORT ssh-rsa |p" | cut -d' ' -f1,2,3
        dropbearkey -y -f /etc/dropbear/host_dss | sed -n "s|^ssh-dss |[$HOST]:$PORT ssh-dss |p" | cut -d' ' -f1,2,3
    } > "$SHARE/$NAME.known_hosts"
    test -s "$SHARE/$NAME.known_hosts"
    touch "$SHARE/$NAME.ready"
    # 0.48 predates the address:port syntax for -p, and names the host keys
    # with -r (RSA) and -d (DSS); a second -r is read as another RSA key.
    # -F foreground, -E log to stderr.
    exec dropbear -F -E -p "$PORT" \
        -r /etc/dropbear/host_rsa -d /etc/dropbear/host_dss
    ;;
*)
    echo "unknown KIND=$KIND" >&2
    exit 1
    ;;
esac
