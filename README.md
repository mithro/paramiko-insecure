# paramiko-legacy

Debian's **paramiko 5** with the legacy SSH algorithms upstream removed put
back, packaged as **`python3-paramiko-legacy`** for bookworm, trixie, forky and sid,
and published as a signed APT repository at
<https://mith.ro/paramiko-legacy/>.

> [!WARNING]
> The restored algorithms are broken or badly weakened. This exists only to
> talk to old devices (switches, BMCs, embedded systems) whose SSH servers
> cannot be upgraded. Do not use it for anything else.

## What is restored

| Removed upstream in | What | Patch |
|---|---|---|
| 4.0.0 | DSA (`ssh-dss`) host and user keys, `DSSKey` | `0010` |
| 5.0.0 | SHA-1 RSA signatures (`ssh-rsa`) | `0005`–`0009` |
| 5.0.0 | `diffie-hellman-group1-sha1`, `-group14-sha1`, `-group-exchange-sha1` | `0004` |
| 5.0.0 | group-exchange moduli below 2048 bits (back to 1024) | `0001` |
| 5.0.0 | GSSAPI authentication and key exchange | `0003` |
| 5.0.0 | *(test-only: restores the client tests the later reverts expect)* | `0002` |

CBC ciphers (`aes*-cbc`, `3des-cbc`) and `hmac-sha1`/`hmac-md5` were never
removed and work in both packages. Modern algorithms are still preferred: a
legacy one is only negotiated when the peer offers nothing better.

## Side by side with the normal paramiko

The package installs the module **`paramiko_legacy`**, never `paramiko`:

| | `python3-paramiko` | `python3-paramiko-legacy` |
|---|---|---|
| import | `import paramiko` | `import paramiko_legacy` |
| files | `…/dist-packages/paramiko/` | `…/dist-packages/paramiko_legacy/` |
| dist-info | `paramiko-5.0.0.dist-info` | `paramiko_legacy-5.0.0.dist-info` |
| loggers | `paramiko.*` | `paramiko_legacy.*` |

The packages share no files and have no Conflicts, Replaces or Provides
between them. Installing this one changes nothing for existing users of
`paramiko`. Only code that explicitly opts in gets the legacy algorithms:

```python
import paramiko_legacy as paramiko

client = paramiko.SSHClient()
client.load_host_keys("/path/to/known_hosts")
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect("old-switch.example", username="admin",
               pkey=paramiko.DSSKey.from_private_key_file("id_dsa"))
```

Importing `paramiko_legacy` loads nothing from `paramiko`, and both can be
used in the same process.

## Using the APT repository

```console
$ sudo install -d -m0755 /etc/apt/keyrings
$ curl -fsSL https://mith.ro/paramiko-legacy/paramiko-legacy.gpg \
    | sudo tee /etc/apt/keyrings/paramiko-legacy.gpg > /dev/null
$ echo "deb [signed-by=/etc/apt/keyrings/paramiko-legacy.gpg] https://mith.ro/paramiko-legacy/$(. /etc/os-release; echo $VERSION_CODENAME)/ ./" \
    | sudo tee /etc/apt/sources.list.d/paramiko-legacy.list
$ sudo apt update
$ sudo apt install python3-paramiko-legacy
```

Suites: `bookworm`, `trixie`, `forky` (testing) and `sid`. The package is
`Architecture: all`. sid reports `forky` as its codename, so the line above
gives sid systems the `forky` suite; write `sid` in it instead if you prefer.

A Debian package that needs legacy SSH should declare
`Depends: python3-paramiko-legacy` and `import paramiko_legacy`.

## How it is built

This repository is a fork of Debian's packaging repository
(<https://salsa.debian.org/python-team/packages/paramiko>): `main` is Debian's
`master` plus this fork's commits, and Debian's `upstream` and `pristine-tar`
branches and `debian/*`/`upstream/*` tags are kept, so it works with `gbp`.

1. **`debian/patches/legacy/`**: one DEP-3 patch per upstream commit that
   removed legacy support, each a `git revert` of that commit and naming it
   in its `Origin:` header. They apply after Debian's own patches. The DSA
   revert was forward-ported by hand onto 5.0's key-writing redesign;
   the patch header says what changed.
2. **`debian/legacy/rename-module.py`**: run by `debian/rules` after the
   patches, it renames `paramiko/` to `paramiko_legacy/` and rewrites the
   package's references to itself, using Python's tokenizer so it only
   touches imports, attribute chains and module-path strings. It is an exact
   bijection: `debian/rules clean` reverts it byte for byte.
3. **`packaging/build.sh`**: `dpkg-buildpackage` inside `debian:<suite>`,
   with build-dependencies from that suite only. trixie and sid run the full
   upstream test suite during the build. bookworm lacks
   `python3-pytest-relaxed`, so it builds with the `nocheck` profile.
4. **`packaging/e2e_test.py`**: installs the `.deb` next to stock
   `python3-paramiko` in a clean container, checks the two share no files,
   then connects to a real OpenSSH `sshd` restricted to *only* legacy
   algorithms. Every scenario must fail when `paramiko_legacy` has those
   algorithms disabled, which proves the server really is legacy-only, and
   succeed with them. DSA is tested on bookworm, whose OpenSSH 9.2 still
   supports it; OpenSSH 10 removed it.

## Rebasing onto a new Debian upload

The weekly workflow run fails its "newer Debian paramiko?" job when sid has a
newer paramiko than this fork's base. To rebase:

```console
$ git remote add salsa https://salsa.debian.org/python-team/packages/paramiko.git
$ git fetch salsa --tags
$ git merge salsa/master                 # debian/control and rules: keep ours
# In a clone of github.com/paramiko/paramiko: start a branch from the new
# release, apply Debian's patches as commits (the "base"), then `git revert`
# each upstream removal commit on top of it (the "legacy" branch). Then:
$ debian/legacy/export-patches.py --repo ../paramiko --base <base> --branch <legacy>
$ dch --newversion <debian-version>+legacy1 "Rebase onto Debian <debian-version>."
```

Put hand-porting notes in a `Legacy-Note:` section of a revert's commit
message and `export-patches.py` copies them into the patch header.

## Known limitations

- **cryptography is deprecating SSH DSA.** python3-cryptography 49 (sid)
  warns that "SSH DSA key support is deprecated and will be removed in a
  future release". Once it is removed, loading DSA keys from OpenSSH-format
  files will stop working here too.
- **RSA user auth against a server that over-advertises.** OpenSSH 9.2 lists
  `rsa-sha2-*` in `server-sig-algs` even when its `PubkeyAcceptedAlgorithms`
  only allows `ssh-rsa`, and paramiko believes it. Pass
  `disabled_algorithms={"pubkeys": ["rsa-sha2-512", "rsa-sha2-256"]}` to
  force SHA-1 signatures. Servers too old to know `rsa-sha2` send no
  `server-sig-algs`, and `ssh-rsa` is then picked automatically.
- **GSSAPI is restored but not exercised by CI**, which has no Kerberos
  realm; the upstream GSSAPI tests are skipped.

## Licence

paramiko, and so this fork as a whole, is LGPL-2.1-or-later. The files this
fork adds (`debian/legacy/`, `packaging/`, `.github/`, this README) are
Apache-2.0; see `debian/copyright`.
