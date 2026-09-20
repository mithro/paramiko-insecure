#!/usr/bin/python3
"""End-to-end test of the installed python3-paramiko-insecure package.

Runs as root inside a clean debian:<suite> container that has installed
python3-paramiko-insecure, python3-paramiko and openssh-server. It checks:

1. Side by side: both modules import, importing paramiko_insecure loads nothing
   from the stock paramiko, and the two packages share no files.
2. Interop: a real OpenSSH sshd restricted to ONLY obsolete algorithms. Each
   scenario must be refused by stock paramiko (proving the server really is
   obsolete-only, so a pass is not vacuous) and accepted by paramiko_insecure,
   which then runs a command over the connection.
"""

import importlib
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(*cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def check_side_by_side():
    out = run(sys.executable, "-c", (
        "import sys, paramiko_insecure;"
        "bad = [m for m in sys.modules"
        " if m == 'paramiko' or m.startswith('paramiko.')];"
        "assert not bad, bad;"
        "print(paramiko_insecure.__file__, paramiko_insecure.__version__)"
    )).stdout.strip()
    print(f"paramiko_insecure alone: {out}")

    import paramiko
    import paramiko_insecure
    assert Path(paramiko.__file__).parent.name == "paramiko"
    assert Path(paramiko_insecure.__file__).parent.name == "paramiko_insecure"
    assert hasattr(paramiko_insecure, "DSSKey")
    print(f"stock paramiko {paramiko.__version__} and paramiko_insecure "
          f"{paramiko_insecure.__version__} import together")

    def files(pkg):
        listed = run("dpkg", "-L", pkg).stdout.splitlines()
        return {f for f in listed if not os.path.isdir(f)}

    shared = files("python3-paramiko") & files("python3-paramiko-insecure")
    assert not shared, f"packages share files: {sorted(shared)}"
    print("python3-paramiko and python3-paramiko-insecure share no files")


def sshd_supports(kind, name):
    return name in run("ssh", "-Q", kind).stdout.split()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Sshd:
    """A throwaway sshd on 127.0.0.1 with the given algorithm restrictions."""

    def __init__(self, workdir, name, host_key_type, options):
        self.dir = Path(workdir) / name
        self.dir.mkdir()
        self.host_key = self.dir / f"host_{host_key_type}"
        keygen(self.host_key, host_key_type)
        self.port = free_port()
        config = self.dir / "sshd_config"
        lines = [
            f"Port {self.port}",
            "ListenAddress 127.0.0.1",
            f"HostKey {self.host_key}",
            f"PidFile {self.dir / 'sshd.pid'}",
            "PermitRootLogin prohibit-password",
            "PasswordAuthentication no",
            "KbdInteractiveAuthentication no",
            "UsePAM no",
            "StrictModes no",
            f"AuthorizedKeysFile {self.dir / 'authorized_keys'}",
            *options,
        ]
        config.write_text("\n".join(lines) + "\n")
        run("/usr/sbin/sshd", "-t", "-f", str(config))
        self.config = config

    def authorize(self, pubkey_path):
        with open(self.dir / "authorized_keys", "a") as f:
            f.write(Path(pubkey_path).read_text())

    def __enter__(self):
        self.log = open(self.dir / "sshd.log", "w")
        self.proc = subprocess.Popen(
            ["/usr/sbin/sshd", "-D", "-e", "-f", str(self.config)],
            stdout=self.log, stderr=subprocess.STDOUT,
        )
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), 1).close()
                return self
            except OSError:
                time.sleep(0.1)
        raise RuntimeError(f"sshd did not start: {self.dir / 'sshd.log'}")

    def __exit__(self, *exc):
        self.proc.terminate()
        self.proc.wait()
        self.log.close()


def keygen(path, key_type):
    bits = {"rsa": ["-b", "2048"], "dsa": ["-b", "1024"]}.get(key_type, [])
    run("ssh-keygen", "-q", "-N", "", "-t", key_type, *bits, "-f", str(path))


def attempt(module_name, sshd, user_key, key_class, disabled=None):
    """Connect with `module_name`, run a command. Return (ok, detail)."""
    mod = importlib.import_module(module_name)
    client = mod.SSHClient()
    # paramiko clears kex_engine once kex completes, so read what was
    # actually negotiated from its own debug log.
    seen = []
    handler = logging.Handler(logging.DEBUG)
    handler.emit = lambda rec: seen.append(rec.getMessage())
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    # Everything, key loading included, is inside the try: stock paramiko
    # cannot even represent a DSA key, and that counts as refusing.
    try:
        pkey = getattr(mod, key_class).from_private_key_file(str(user_key))
        # Pin the host key exactly: this checks the obsolete host-key algorithm
        # really verified, rather than trusting whatever was offered.
        host_pub = sshd.host_key.with_suffix(".pub").read_text().split()
        host_class = {"ssh-rsa": "RSAKey", "ssh-dss": "DSSKey"}[host_pub[0]]
        client.get_host_keys().add(
            f"[127.0.0.1]:{sshd.port}", host_pub[0],
            getattr(mod, host_class)(data=_b64(host_pub[1])),
        )
        client.set_missing_host_key_policy(mod.RejectPolicy())
        client.connect(
            "127.0.0.1", port=sshd.port, username="root", pkey=pkey,
            allow_agent=False, look_for_keys=False, timeout=10,
            banner_timeout=10, auth_timeout=10,
            disabled_algorithms=disabled,
        )
        t = client.get_transport()
        _, out, _ = client.exec_command("echo insecure-ok")
        result = out.read().decode().strip()
        kex = [m.split(": ", 1)[1] for m in seen if m.startswith("Kex: ")]
        auth = [m.split("'")[1] for m in seen
                if m.startswith("Agreed upon '")]
        detail = (f"kex={kex[-1] if kex else '?'} "
                  f"hostkey={t.host_key_type} "
                  # paramiko only logs the agreed algorithm for RSA keys;
                  # for any other key the algorithm is the key's own type.
                  f"userauth={auth[-1] if auth else pkey.get_name()} "
                  f"cipher={t.local_cipher} mac={t.local_mac} -> {result!r}")
        return result == "insecure-ok", detail
    except Exception as e:  # stock paramiko is *expected* to fail here
        return False, f"{type(e).__name__}: {e}"
    finally:
        client.close()
        logger.removeHandler(handler)


def _b64(s):
    import base64
    return base64.b64decode(s)


SCENARIOS = [
    # name, host key type, user key type, key class, sshd options.
    # The sshd options allow exactly one obsolete algorithm of each kind; the
    # negative control disables that same algorithm in paramiko_insecure.
    ("group1-sha1 kex + ssh-rsa (SHA-1) host key and user auth",
     "rsa", "rsa", "RSAKey", [
         "KexAlgorithms diffie-hellman-group1-sha1",
         "HostKeyAlgorithms ssh-rsa",
         "PubkeyAcceptedAlgorithms ssh-rsa",
     ]),
    ("group14-sha1 kex + 3des-cbc + hmac-md5",
     "rsa", "rsa", "RSAKey", [
         "KexAlgorithms diffie-hellman-group14-sha1",
         "HostKeyAlgorithms ssh-rsa",
         "PubkeyAcceptedAlgorithms ssh-rsa",
         "Ciphers 3des-cbc",
         "MACs hmac-md5",
     ]),
    ("group-exchange-sha1 kex",
     "rsa", "rsa", "RSAKey", [
         "KexAlgorithms diffie-hellman-group-exchange-sha1",
         "HostKeyAlgorithms ssh-rsa",
         "PubkeyAcceptedAlgorithms ssh-rsa",
     ]),
    ("ssh-dss (DSA) host key and user auth",
     "dsa", "dsa", "DSSKey", [
         "KexAlgorithms diffie-hellman-group1-sha1",
         "HostKeyAlgorithms ssh-dss",
         "PubkeyAcceptedAlgorithms ssh-dss",
     ]),
]

# sshd_config keyword -> paramiko disabled_algorithms key.
DISABLE_KEYS = {
    "KexAlgorithms": "kex",
    "HostKeyAlgorithms": "keys",
    "PubkeyAcceptedAlgorithms": "pubkeys",
    "Ciphers": "ciphers",
    "MACs": "macs",
}


def obsolete_only(options):
    """disabled_algorithms turning off exactly what the sshd requires."""
    disabled = {}
    for opt in options:
        word, value = opt.split()
        disabled.setdefault(DISABLE_KEYS[word], []).extend(value.split(","))
    return disabled


# OpenSSH 7.2-9.x advertises rsa-sha2-* in server-sig-algs even when
# PubkeyAcceptedAlgorithms refuses them, and paramiko (like upstream 3.x)
# trusts the advertisement. Servers too old to know rsa-sha2 send no
# server-sig-algs, and then paramiko_insecure picks ssh-rsa by itself. So, as a
# user must for such a server, turn rsa-sha2 off for RSA user auth.
RSA_SHA1_ONLY = {"pubkeys": ["rsa-sha2-512", "rsa-sha2-256"]}


def client_options(key_class):
    return RSA_SHA1_ONLY if key_class == "RSAKey" else None


def stock_major():
    import paramiko
    return int(paramiko.__version__.split(".")[0])


def check_interop():
    failures = []
    ran = 0
    with tempfile.TemporaryDirectory() as workdir:
        for name, host_type, user_type, key_class, options in SCENARIOS:
            needed = [("key", f"ssh-{'dss' if host_type == 'dsa' else 'rsa'}")]
            query = {"KexAlgorithms": "kex", "Ciphers": "cipher",
                     "MACs": "mac"}
            needed += [(query[o.split()[0]], o.split()[1]) for o in options
                       if o.split()[0] in query]
            missing = [n for kind, n in needed if not sshd_supports(kind, n)]
            if missing:
                print(f"SKIP {name}: this sshd lacks {missing}")
                continue
            ran += 1
            slug = name.split()[0]
            sshd = Sshd(workdir, f"{ran}-{slug}", host_type, options)
            user_key = Path(workdir) / f"{ran}-user_{user_type}"
            keygen(user_key, user_type)
            sshd.authorize(user_key.with_suffix(".pub"))
            with sshd:
                control_ok, control = attempt(
                    "paramiko_insecure", sshd, user_key, key_class,
                    disabled=obsolete_only(options))
                stock_ok, stock = attempt("paramiko", sshd, user_key,
                                          key_class,
                                          client_options(key_class))
                insecure_ok, insecure = attempt("paramiko_insecure", sshd,
                                            user_key, key_class,
                                            client_options(key_class))
            print(f"\n== {name}")
            print(f"   paramiko_insecure, obsolete algorithms disabled: {control}")
            print(f"   stock paramiko: {stock}")
            print(f"   paramiko_insecure: {insecure}")
            # Negative control: without its obsolete algorithms paramiko_insecure
            # must be refused, else the server is not obsolete-only and the
            # positive result below would prove nothing.
            if control_ok:
                failures.append(f"{name}: connected with the obsolete "
                                "algorithms disabled; test is vacuous")
            # Paramiko 5 removed every obsolete algorithm used here (4.0 already
            # removed DSA). Older stock versions (bookworm 2.12, trixie 3.5)
            # still have them, so for those this is informational only.
            if stock_ok and stock_major() >= 5:
                failures.append(f"{name}: stock paramiko "
                                f"{stock_major()}.x connected?!")
            if not insecure_ok:
                failures.append(f"{name}: paramiko_insecure failed: {insecure}")
                print((sshd.dir / "sshd.log").read_text())
    if ran == 0:
        failures.append("no scenario could run on this sshd")
    return failures


def main():
    print(f"OpenSSH: {run('ssh', '-V').stderr.strip()}")
    check_side_by_side()
    failures = check_interop()
    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nall end-to-end checks passed")


if __name__ == "__main__":
    main()
