#!/usr/bin/python3
"""Generate the user keys and password the interop servers will accept.

Run in the client container before the servers start. The keys are generated
with paramiko_insecure itself, because a DSA key is wanted and no current
tool will still make one: OpenSSH 10 dropped DSA entirely, and OpenSSH 9.8
only has it when built with --enable-dsa-keys.
"""

import secrets
from pathlib import Path

import paramiko_insecure

SHARE = Path("/share")
# 1024 bits is not a choice: the DSA signature algorithm as used by SSH is
# defined for 1024-bit keys, and servers of this vintage accept nothing else.
KEYS = {
    "rsa": lambda: paramiko_insecure.RSAKey.generate(2048),
    "dss": lambda: paramiko_insecure.DSSKey.generate(1024),
}


def main():
    authorized = []
    for name, generate in KEYS.items():
        key = generate()
        path = SHARE / f"user_{name}"
        key.write_private_key_file(str(path))
        path.chmod(0o600)
        authorized.append(f"{key.get_name()} {key.get_base64()} interop\n")
        print(f"{name}: {key.get_name()} {key.get_bits()} bits -> {path}")

    (SHARE / "authorized_keys").write_text("".join(authorized))
    (SHARE / "password").write_text(secrets.token_urlsafe(12))
    print(f"paramiko_insecure {paramiko_insecure.__version__} generated the keys")


if __name__ == "__main__":
    main()
