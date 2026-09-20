#!/bin/sh
# Start the OpenSSH 9.8p1 "insecure-ssh-keyscan lookalike" server.
#
#   PORT      port to listen on
#   HOST      hostname the client will use (this container's name)
#   SHARE     directory shared with the client container
#   NAME      name used for this server's files in SHARE
#
# Writes $SHARE/$NAME.known_hosts (host keys, as the client should pin them)
# and $SHARE/$NAME.ready once it is accepting connections.
set -eux

: "${PORT:?}" "${HOST:?}" "${SHARE:?}" "${NAME:=openssh98}"
BIN=/opt/openssh98
ETC=$BIN/etc

mkdir -p "$ETC" /var/empty /root/.ssh
chmod 700 /root/.ssh

# Host keys: RSA (verified with SHA-1 by the client) and DSA, which only a
# DSA-enabled build can generate at all.
"$BIN/bin/ssh-keygen" -q -t rsa -b 2048 -N "" -f "$ETC/ssh_host_rsa_key"
"$BIN/bin/ssh-keygen" -q -t dsa -b 1024 -N "" -f "$ETC/ssh_host_dsa_key"

cp "$SHARE/authorized_keys" /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "root:$(cat "$SHARE/password")" | chpasswd

cat > "$ETC/sshd_config" <<EOF
Port $PORT
HostKey $ETC/ssh_host_rsa_key
HostKey $ETC/ssh_host_dsa_key
# SHA-1 key exchange, SHA-1 RSA and DSA host keys, DSA/ssh-rsa user keys:
# the parts a modern client refuses. Ciphers and MACs keep their stock lists
# plus the old ones, because insecure-ssh-keyscan only patches the KEX
# proposal -- restricting ciphers here would lock out that very tool, which
# offers only CTR/GCM. CBC and hmac-md5 are covered by the Dropbear 0.48 and
# restricted-modern-sshd scenarios instead.
KexAlgorithms diffie-hellman-group1-sha1,diffie-hellman-group14-sha1,diffie-hellman-group-exchange-sha1
HostKeyAlgorithms ssh-rsa,ssh-dss
PubkeyAcceptedAlgorithms ssh-rsa,ssh-dss
Ciphers aes128-cbc,3des-cbc,aes128-ctr,aes256-ctr
MACs hmac-sha1,hmac-md5,hmac-sha2-256
PermitRootLogin yes
PasswordAuthentication yes
KbdInteractiveAuthentication no
StrictModes no
Subsystem sftp $BIN/libexec/sftp-server
PidFile $ETC/sshd.pid
EOF

# known_hosts entries for the client to pin, in [host]:port form.
{
  printf '[%s]:%s %s\n' "$HOST" "$PORT" "$(cut -d' ' -f1,2 "$ETC/ssh_host_rsa_key.pub")"
  printf '[%s]:%s %s\n' "$HOST" "$PORT" "$(cut -d' ' -f1,2 "$ETC/ssh_host_dsa_key.pub")"
} > "$SHARE/$NAME.known_hosts"

"$BIN/sbin/sshd" -t -f "$ETC/sshd_config"
"$BIN/sbin/sshd" -D -e -f "$ETC/sshd_config" &
SSHD_PID=$!

# Ready only once the port answers, so the orchestrator never races it.
i=0
while [ $i -lt 100 ]; do
    if "$BIN/bin/ssh-keyscan" -p "$PORT" -T 2 127.0.0.1 2>>"$SHARE/$NAME.wait.log" | grep -q .; then
        break
    fi
    i=$((i + 1))
    sleep 0.1
done

# This is the interop check for the workstation's insecure-ssh-keyscan: the
# same build scanning this server, with the result handed to the client to
# use as its known_hosts.
"$BIN/bin/ssh-keyscan" -p "$PORT" -t rsa,dsa 127.0.0.1 > "$SHARE/$NAME.keyscan" 2>"$SHARE/$NAME.keyscan.log"
# ssh-keyscan writes "[127.0.0.1]:2222 ssh-dss ..." for a non-default port;
# rewrite the address to the one the client will dial.
sed -i "s|^\[127.0.0.1\]:$PORT |[$HOST]:$PORT |" "$SHARE/$NAME.keyscan"
grep -q 'ssh-dss' "$SHARE/$NAME.keyscan" || {
    echo "ssh-keyscan did not return an ssh-dss key" >&2
    cat "$SHARE/$NAME.keyscan.log" >&2
    exit 1
}
touch "$SHARE/$NAME.ready"

wait $SSHD_PID
