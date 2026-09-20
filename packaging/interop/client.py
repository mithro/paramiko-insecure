#!/usr/bin/python3
"""Connect to each interop server and report what actually happened.

Runs in the client container, where python3-paramiko-insecure is installed
next to the stock python3-paramiko. For every server and every authentication
method it checks, in one process:

  * stock paramiko is refused -- these servers speak nothing paramiko 5 still
    has, which is what proves the server really is obsolete-only. Only
    paramiko >= 5 is required to fail: bookworm ships 2.12 and trixie 3.5,
    which still have SHA-1 and DSA themselves, so there the result is
    reported but not asserted;
  * paramiko_insecure connects, with the host key pinned, runs a command, and
    (where the server has it) transfers a file over SFTP.

All four modules -- both paramikos and both cryptographys -- are imported
here at once, which is the co-installation claim made concrete.
"""

import json
import logging
import sys
import time
import traceback
from pathlib import Path

import cryptography
import cryptography_insecure
import paramiko
import paramiko_insecure

SHARE = Path("/share")
MARKER = "insecure-ok"


def log_capture(module_name):
    seen = []
    handler = logging.Handler(logging.DEBUG)
    handler.emit = lambda record: seen.append(record.getMessage())
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return seen, logger, handler


def negotiated(transport, seen, key):
    kex = [m.split(": ", 1)[1] for m in seen if m.startswith("Kex: ")]
    auth = [m.split("'")[1] for m in seen if m.startswith("Agreed upon '")]
    return (f"kex={kex[-1] if kex else '?'} "
            f"hostkey={transport.host_key_type} "
            f"cipher={transport.local_cipher} mac={transport.local_mac} "
            f"userauth={auth[-1] if auth else (key.get_name() if key else 'password')}")


def connect(module, server, auth, known_hosts, deadline=None):
    """Try one connection. Returns (ok, detail)."""
    seen, logger, handler = log_capture(module.__name__)
    client = module.SSHClient()
    key = None
    try:
        if auth == "password":
            credentials = {"password": (SHARE / "password").read_text()}
        else:
            key_class = {"rsa": "RSAKey", "dss": "DSSKey"}[auth]
            key = getattr(module, key_class).from_private_key_file(
                str(SHARE / f"user_{auth}")
            )
            credentials = {"pkey": key}
        client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(module.RejectPolicy())
        client.connect(
            server["host"], port=server["port"], username="root",
            allow_agent=False, look_for_keys=False,
            timeout=30, banner_timeout=30, auth_timeout=30,
            # These servers advertise rsa-sha2 in server-sig-algs in some
            # versions while accepting only ssh-rsa; force SHA-1 for RSA, as
            # a user of such a device must.
            disabled_algorithms=(
                {"pubkeys": ["rsa-sha2-512", "rsa-sha2-256"]}
                if auth == "rsa" else None
            ),
            **credentials,
        )
        transport = client.get_transport()
        _, stdout, _ = client.exec_command(f"echo {MARKER}")
        output = stdout.read().decode(errors="replace").strip()
        detail = negotiated(transport, seen, key)
        if output != MARKER:
            return False, f"{detail} -> unexpected output {output!r}"
        if server.get("sftp"):
            with client.open_sftp() as sftp:
                payload = b"paramiko_insecure sftp\n"
                with sftp.open("/tmp/interop.txt", "wb") as fd:
                    fd.write(payload)
                with sftp.open("/tmp/interop.txt", "rb") as fd:
                    if fd.read() != payload:
                        return False, f"{detail} -> sftp round trip differed"
            detail += " sftp=ok"
        return True, detail
    except module.ssh_exception.NoValidConnectionsError as exc:
        # The server container may still be starting up.
        if deadline and time.time() < deadline:
            time.sleep(2)
            return connect(module, server, auth, known_hosts, deadline)
        return False, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        logger.removeHandler(handler)


def main():
    servers = json.loads((SHARE / "servers.json").read_text())
    print(f"stock paramiko {paramiko.__version__} and paramiko_insecure "
          f"{paramiko_insecure.__version__} imported together in one process")
    print(f"stock has DSSKey: {hasattr(paramiko, 'DSSKey')}; "
          f"paramiko_insecure has DSSKey: {hasattr(paramiko_insecure, 'DSSKey')}")
    print(f"system cryptography {cryptography.__version__} at "
          f"{Path(cryptography.__file__).parent}")
    print(f"private cryptography_insecure {cryptography_insecure.__version__} at "
          f"{Path(cryptography_insecure.__file__).parent}")
    # paramiko_insecure must reach the private copy and nothing else: it is
    # what keeps DSA working whatever the system cryptography retires.
    used = {m.split(".")[0] for m in sys.modules if "cryptography" in m}
    assert "cryptography_insecure" in used, used
    # Not just "the name is importable": the objects paramiko_insecure
    # actually holds must come from the private copy.
    serialization = paramiko_insecure.pkey.serialization
    assert serialization.__name__.startswith("cryptography_insecure."), \
        serialization.__name__
    print(f"paramiko_insecure.pkey.serialization is {serialization.__name__}")

    stock_major = int(paramiko.__version__.split(".")[0])
    failures = []
    for server in servers:
        print(f"\n=== {server['name']} on port {server['port']}: {server['why']}")
        known_hosts = SHARE / f"{server['name']}.known_hosts"
        first = True
        for auth in server["auths"]:
            # Allow the first attempt per server to wait for it to come up.
            ok, detail = connect(paramiko_insecure, server, auth, known_hosts,
                                 deadline=time.time() + 60 if first else None)
            first = False
            print(f"  paramiko_insecure {auth:8} {'OK ' if ok else 'FAIL'} {detail}")
            if not ok:
                failures.append(f"{server['name']}/{auth}: {detail}")

            stock_ok, stock_detail = connect(paramiko, server, auth, known_hosts)
            print(f"  stock paramiko    {auth:8} "
                  f"{'CONNECTED' if stock_ok else 'refused  '} {stock_detail}")
            # paramiko 5 removed all of this; older stock versions still
            # have it, so only 5+ connecting would mean the server is not
            # actually obsolete-only.
            if stock_ok and stock_major >= 5:
                failures.append(
                    f"{server['name']}/{auth}: stock paramiko {stock_major}.x "
                    "connected, so this server is not obsolete-only and the "
                    "result above proves nothing"
                )

        # The host keys as scanned by the insecure-ssh-keyscan build itself:
        # a client must be able to use that file as its known_hosts.
        if server.get("keyscan"):
            scanned = SHARE / f"{server['name']}.keyscan"
            ok, detail = connect(paramiko_insecure, server, "rsa", scanned)
            print(f"  paramiko_insecure via ssh-keyscan output "
                  f"{'OK ' if ok else 'FAIL'} {detail}")
            print("    " + scanned.read_text().strip()[:100] + " ...")
            if not ok:
                failures.append(f"{server['name']}/keyscan: {detail}")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nall interop checks passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
