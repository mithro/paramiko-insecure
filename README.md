# paramiko-insecure

Debian's **paramiko 5** with the obsolete SSH algorithms upstream removed put
back, packaged as **`python3-paramiko-insecure`** for bookworm, trixie, forky
and sid, and published as a signed APT repository at
<https://mith.ro/paramiko-insecure/>.

> [!CAUTION]
> **Treat a connection made with this module as no more private than telnet.**
> The algorithms it restores are broken or badly weakened: someone who can see
> or intercept the traffic can be expected to read the session and to
> impersonate either end. The encryption is theatre.
>
> Use it **only on a physically secure or otherwise isolated network** — a lab
> bench, a management VLAN with no route off it, a direct cable. Never across
> the public internet. Assume every password typed into such a session is
> disclosed, and that anything it reports back may have been altered.

## Why this exists

Some equipment is twenty years old or more and installed where replacing it is
not possible — remote sites, sealed enclosures, machinery whose vendor no
longer exists. Its SSH server speaks nothing newer, and modern OpenSSH and
paramiko have quite correctly dropped the algorithms it needs.

For those devices the choice is not between this package and a secure
connection. It is between this package and telnet, or no access at all.

**If a device supports anything better, use `python3-paramiko` instead.**

## What is restored

| Removed upstream in | What | Patch |
|---|---|---|
| 4.0.0 | DSA (`ssh-dss`) host and user keys, `DSSKey` | `0007` |
| 5.0.0 | SHA-1 RSA signatures (`ssh-rsa`) | `0003`–`0006` |
| 5.0.0 | `diffie-hellman-group1-sha1`, `-group14-sha1`, `-group-exchange-sha1` | `0002` |
| 5.0.0 | group-exchange moduli below 2048 bits (back to 1024) | `0001` |

CBC ciphers (`aes*-cbc`, `3des-cbc`) and `hmac-sha1`/`hmac-md5` were never
removed upstream and work in both packages. Modern algorithms are still
preferred: an obsolete one is only negotiated when the device offers nothing
better.

**GSSAPI/Kerberos is not restored.** The scope is core SSH, SFTP and SCP —
what these devices actually need — so there is less obsolete code to keep
working.

## Its own private cryptography

`paramiko_insecure` does not use the system `cryptography`. It uses
**`cryptography_insecure`**, shipped by `python3-cryptography-insecure` and
pulled in automatically, which is the same Debian source renamed the same way.

That is not paranoia about the system copy: upstream cryptography is retiring
exactly what this package needs. Version 49 warns that "SSH DSA key support is
deprecated and will be removed in a future release", and 3DES has already moved
to `hazmat.decrepit`. When those go, `python3-paramiko` should follow the
removal and this package should not — which is only possible if it has its own
copy.

The rename covers the Rust extension too, not just the Python tree. The
extension registers its submodules in `sys.modules` under names compiled into
it, so a half-rename would let the private copy overwrite the system copy's
entries and break `cryptography` for everything else in the process.

## Opting in, explicitly

The package installs the module **`paramiko_insecure`**, never `paramiko`:

| | `python3-paramiko` | `python3-paramiko-insecure` |
|---|---|---|
| import | `import paramiko` | `import paramiko_insecure` |
| crypto | `cryptography` | `cryptography_insecure` |
| files | `…/dist-packages/paramiko/` | `…/dist-packages/paramiko_insecure/` |
| dist-info | `paramiko-5.0.0.dist-info` | `paramiko_insecure-5.0.0.dist-info` |
| loggers | `paramiko.*` | `paramiko_insecure.*` |

The packages share no files and declare no Conflicts, Replaces or Provides
between them. Installing this one changes nothing for existing users of
`paramiko`, and both can be imported in the same process.

**Never alias it.** Aliasing hides which connections are unprotected, which is
exactly what a reader of the code most needs to see:

```python
import paramiko_insecure                       # yes
import paramiko_insecure as paramiko           # NO
```

Keep the name at every call site:

```python
import paramiko_insecure

client = paramiko_insecure.SSHClient()
client.load_host_keys("/path/to/known_hosts")
client.set_missing_host_key_policy(paramiko_insecure.RejectPolicy())
client.connect("old-switch.example", username="admin", password="...")
```

**Passwords.** A key would be better, but equipment this old often supports
password login only, so it is left enabled. Assume any password used over such
a connection is compromised, and never reuse it elsewhere.

**Host keys.** Still check them. Verification is weak (a DSA or SHA-1 RSA host
key can be forged by a capable attacker) but it does catch the ordinary case of
talking to the wrong box.

## Using the APT repository

```console
$ sudo install -d -m0755 /etc/apt/keyrings
$ curl -fsSL https://mith.ro/paramiko-insecure/paramiko-insecure.gpg \
    | sudo tee /etc/apt/keyrings/paramiko-insecure.gpg > /dev/null
$ echo "deb [signed-by=/etc/apt/keyrings/paramiko-insecure.gpg] https://mith.ro/paramiko-insecure/$(. /etc/os-release; echo $VERSION_CODENAME)/ ./" \
    | sudo tee /etc/apt/sources.list.d/paramiko-insecure.list
$ sudo apt update
$ sudo apt install python3-paramiko-insecure
```

Suites: `bookworm`, `trixie`, `forky` (testing) and `sid`. The package is
`Architecture: all`. sid reports `forky` as its codename, so the line above
gives sid systems the `forky` suite; write `sid` in it instead if you prefer.

A Debian package that needs this should declare
`Depends: python3-paramiko-insecure` and `import paramiko_insecure`.

## How it is built

This repository is a fork of Debian's packaging repository
(<https://salsa.debian.org/python-team/packages/paramiko>): `main` is Debian's
`master` plus this fork's commits, and Debian's `upstream` and `pristine-tar`
branches and `debian/*`/`upstream/*` tags are kept, so it works with `gbp`.

1. **`debian/patches/insecure/`**: one DEP-3 patch per upstream commit that
   removed support, each a `git revert` of that commit and naming it in its
   `Origin:` header, applied after Debian's own patches. The DSA revert was
   forward-ported by hand onto 5.0's key-writing redesign; each patch header
   says what had to change.
2. **`debian/insecure/rename-module.py`**: run by `debian/rules` after the
   patches, it renames `paramiko/` to `paramiko_insecure/` and rewrites the
   package's references to itself using Python's tokenizer, so only imports,
   attribute chains and module-path strings are touched. It is an exact
   bijection: `debian/rules clean` reverts it byte for byte.
3. **`packaging/cryptography-insecure/`**: fetches that suite's
   `python-cryptography` source, renames it (Python, Rust module paths and
   Debian packaging) and builds `python3-cryptography-insecure`.
4. **`packaging/build.sh`**: `dpkg-buildpackage` inside `debian:<suite>`, with
   build-dependencies from that suite only. trixie, forky and sid run the full
   upstream test suite during the build; bookworm lacks
   `python3-pytest-relaxed`, so it builds with the `nocheck` profile.
5. **`packaging/e2e_test.py`**: installs the `.deb` next to stock
   `python3-paramiko` and connects to real SSH servers that speak only the
   obsolete algorithms (see below).

## Tested against real obsolete servers

Modern `sshd` cannot be configured back to what this equipment speaks, so CI
tests against genuinely old software as well:

| Target | Software | Why |
|---|---|---|
| `debian/eol:etch` | OpenSSH 4.3p2 (2006), OpenSSL 0.9.8c | Era-correct OpenSSH |
| `debian/eol:etch` | Dropbear 0.48 (2007) | What embedded hardware of that era ships |
| built in CI | OpenSSH 9.8p1, DSA enabled + SHA-1 kex by default | Matches the `insecure-ssh-keyscan` build |
| each suite's own | OpenSSH 9.2 / 10.x restricted by config | Current servers forced down to old algorithms |

Every scenario is checked both ways: `paramiko_insecure` must connect, and
must **fail** when the same obsolete algorithms are disabled, so a pass can
never be vacuous. Stock `paramiko` is run against the same servers to show
what it refuses.

## Rebasing onto a new Debian upload

The weekly workflow run fails its "newer Debian paramiko?" job when sid has a
newer paramiko than this fork's base. To rebase:

```console
$ git remote add salsa https://salsa.debian.org/python-team/packages/paramiko.git
$ git fetch salsa --tags
$ git merge salsa/master                 # debian/control and rules: keep ours
# In a clone of github.com/paramiko/paramiko: start a branch from the new
# release, apply Debian's patches as commits (the "base"), then `git revert`
# each upstream removal commit on top of it (the "insecure" branch). Then:
$ debian/insecure/export-patches.py --repo ../paramiko --base <base> --branch <insecure>
$ dch --newversion <debian-version>+insecure1 "Rebase onto Debian <version>."
```

Put hand-porting notes in an `Insecure-Note:` section of a commit message and
`export-patches.py` copies them into the patch header.

## Known limitations

- **cryptography is deprecating SSH DSA.** Handled by shipping
  `python3-cryptography-insecure` (above), but when upstream removes DSA
  outright, that private copy will have to carry a patch to keep it, or be
  pinned to the last version that had it.
- **RSA user auth against a server that over-advertises.** OpenSSH 9.2 lists
  `rsa-sha2-*` in `server-sig-algs` even when its `PubkeyAcceptedAlgorithms`
  only allows `ssh-rsa`, and paramiko believes it. Pass
  `disabled_algorithms={"pubkeys": ["rsa-sha2-512", "rsa-sha2-256"]}` to force
  SHA-1 signatures. Servers too old to know `rsa-sha2` send no
  `server-sig-algs`, and `ssh-rsa` is then chosen automatically.

## Licence

paramiko, and so this fork as a whole, is LGPL-2.1-or-later. The files this
fork adds (`debian/insecure/`, `packaging/`, `.github/`, this README) are
Apache-2.0; see `debian/copyright`.
