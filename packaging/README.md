# Packaging and releases

This folder builds the release files for IR Remote: for Arch, Debian 13,
Ubuntu 24.04, Fedora 44 and openSUSE Tumbleweed, two packages each, plus
the checksums. GitHub builds them for you when you push a version tag
(see `.github/workflows/release.yml`). You can run the same build on your own
PC with `build-all.sh`.

The two packages per distribution:

| Package | What it is | Arch | Debian / Ubuntu | Fedora / openSUSE |
|---|---|---|---|---|
| elksmart-comm | the dongle tool from [usb-drivers](https://git.janouch.name/p/usb-drivers) by Přemysl Eric Janouch (0BSD), with our learn patch and the udev rule | `elksmart-comm-git` (x86_64) | `elksmart-comm` (amd64) | `elksmart-comm` (x86_64) |
| irremote | the app (MIT) | `irremote` (any) | `irremote` (all) | `irremote` (noarch) |

`irremote` depends on `elksmart-comm` and on the distro's PyQt6 and
dbus-python packages (Arch `python-pyqt6 python-dbus`, Debian/Ubuntu
`python3-pyqt6 python3-dbus`, Fedora `python3-pyqt6 python3-dbus`, openSUSE
`python3-PyQt6 python3-dbus-python`).

Every distro's packages are built in a fresh Docker container of that distro,
then installed with the distro's own package manager in a second fresh
container and checked by `test.sh`: both programs start (`--help`,
`--version`), the version is right, the Python code imports from
`/usr/lib/irremote`, the window opens and closes on its own (offscreen, no
screen needed), the udev rule and the upstream licence are installed, and the
menu entry is valid. No USB dongle is used: the tests never talk to one.

## Making a release

1. **Set the version.** Change `__version__` in `irremote/__init__.py` (for
   example to `1.2.0`). That is the only place the version is written. The
   Debian changelog and the RPM spec get it automatically at build time.
2. **Update `CHANGELOG.md`.** Add (or rename `## Unreleased` to)
   `## 1.2.0 - YYYY-MM-DD` (the date is used in the package changelogs).
3. **Write the release notes** (optional) in `packaging/release-notes/v1.2.0.md`.
   Its first `# ` line becomes the release title. If there is no such file,
   the `## 1.2.0` section of `CHANGELOG.md` is used instead. When you name the
   `.deb`/`.rpm` files in it, write them as GitHub shows them: with `.`
   instead of `~` and `+`, e.g. `irremote_1.2.0-1.deb13_all.deb`.
4. **Commit and push** to `main`.
5. **Push the tag:**
   ```sh
   git tag v1.2.0
   git push origin v1.2.0
   ```
6. **Watch it run:** on GitHub, open the **Actions** tab and click the
   "Release packages" run (or `gh run watch`). If the tag does not match
   `__version__`, it stops in the first step.
7. **Check the release** on the **Releases** page: 10 packages (2 per distro)
   and `SHA256SUMS`. The release is only created if every build and every
   install test passed.

## Updating elksmart-comm

The elksmart-comm version is pinned in **`elksmart-comm.sh`** (upstream
commit, the liberty submodule commit, version, commit date, and the Arch
package version). To move to a newer upstream commit:

1. Change `_commit` (and `pkgver`/`pkgrel`) in `elksmart-comm-git/PKGBUILD`
   and the same values in `elksmart-comm.sh` (`ELK_COMMIT`,
   `ELK_LIBERTY_COMMIT` = `git rev-parse HEAD:liberty` in usb-drivers,
   `ELK_UPSTREAM`, `ELK_DATE`, `ELK_ARCH_PKGVER`, `ELK_ARCH_PKGREL`).
2. Check that `elksmart-comm-git/0001-learn-skip-0132-ack.patch` still applies.
3. Run `packaging/build-all.sh`. `fetch-elksmart-comm.sh` refuses to go on if
   the commits, version or date don't match what upstream says.

The workflow downloads the upstream source **once** (in the first job) from
git.janouch.name; every build container uses that tarball.

## Test run without a release

On GitHub: **Actions** tab, "Release packages", **Run workflow**, pick a
branch. Or from a terminal:

```sh
gh workflow run release.yml --ref main
gh run watch
```

This builds and tests everything but creates no release. The files are on the
run's page under **Artifacts**: `release-files` holds exactly what a release
would get (with `SHA256SUMS` and the release notes), and `pkg-<distro>` holds
each distro's packages with their build logs (lintian / rpmlint output, file
lists).

## Building on your own PC

Needs Docker and a network connection. From the repository folder:

```sh
packaging/build-all.sh                     # everything, from the committed HEAD
packaging/build-all.sh fedora-44 arch      # only some distros
```

Only **committed** files of the app are built (it uses `git archive HEAD`),
so commit first. Results go to `dist/release-<version>/`:

- `source/` the two source tarballs
- `<distro>/pkg/` the packages, `<distro>/build.log`, `<distro>/test.log`,
  `lintian-*.txt` or `rpmlint-*.txt`, `contents-*.txt` (file lists)
- `release/` all release files plus `SHA256SUMS`
- `release-notes.md` the notes the release would use

The single steps can also be run on their own, exactly as the workflow does:

```sh
packaging/fetch-elksmart-comm.sh src
packaging/build.sh debian-13 src/irremote-1.2.0.tar.gz src/elksmart-comm-1.2.0+git20260821.d48653a.tar.gz out/debian-13
packaging/test-in-container.sh debian-13 out/debian-13/pkg 1.2.0
```

## What is in this folder

| File | What it does |
|---|---|
| `distros.sh` | The list of distros and which Docker images they use |
| `elksmart-comm.sh` | Which elksmart-comm commit/version is packaged |
| `fetch-elksmart-comm.sh` | Downloads that commit (with liberty) and packs it as a tarball |
| `build.sh` | Builds one distro's two packages in a fresh container |
| `build-arch.sh`, `build-deb.sh`, `build-rpm.sh` | The build steps that run inside that container |
| `test-in-container.sh` | Installs the packages in a fresh container and runs `test.sh` |
| `test.sh`, `test-common.sh` | The install checks |
| `release-info.sh` | Reads the version, checks the tag, prints the release notes |
| `lib-version.sh` | Writes the version into the Debian changelogs and the specs |
| `build-all.sh` | Runs all of the above on your PC |
| `elksmart-comm-git/` | The Arch PKGBUILD for elksmart-comm (builds from git), the udev rule, the learn patch, the upstream licence. The rule and the patch are used for every distro. |
| `arch/` | `elksmart-comm-git/PKGBUILD`: CI copy of the one above that builds from the tarball; `makepkg.conf` with generic x86-64 flags. irremote itself is built with the `PKGBUILD` at the repository root. |
| `debian/elksmart-comm/`, `debian/irremote/` | Debian/Ubuntu packaging (two source packages) |
| `rpm/` | Fedora/openSUSE specs |
| `release-notes/` | Release notes per tag |

## Troubleshooting

- **"tag v1.2.0 does not match __version__"**: the tag and
  `irremote/__init__.py` disagree. Delete the tag
  (`git tag -d v1.2.0; git push origin :refs/tags/v1.2.0`), fix the file,
  commit, and tag again.
- **"CHANGELOG.md has no '## 1.2.0 - DATE' section"**: add it (step 2) and re-tag as above.
- **The "Download the elksmart-comm source" step fails**: git.janouch.name
  may be down for a moment. Use "Re-run failed jobs" later. A message about
  commit IDs means `elksmart-comm.sh` and upstream disagree (see "Updating
  elksmart-comm").
- **A build fails**: open the failed job on the Actions page and read the log of
  the "Build" step, or run `packaging/build-all.sh <distro>` locally and read
  `dist/release-<version>/<distro>/build.log`. Distros update their images
  often, so a package name may have changed in `debian/*/control` or
  `rpm/*.spec`.
- **An install test fails**: the log shows lines starting with `FAIL:`. Run it
  locally with `packaging/build-all.sh <distro>` and read `<distro>/test.log`.
- **"release v1.2.0 is already published"**: the workflow never replaces files
  of a published release. Delete the release on GitHub (or `gh release delete
  v1.2.0`, keeping the tag) and re-run the workflow from the Actions page.
  A *draft* left over from a half-finished run is completed automatically.
- **Re-running only the failed jobs** is fine: on the run's page use
  "Re-run failed jobs".
- **Docker permission errors on your PC**: your user must be in the `docker`
  group, or the Docker service is not running (`systemctl start docker`).
