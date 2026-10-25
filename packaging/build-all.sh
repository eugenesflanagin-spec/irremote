#!/bin/bash
# Build + install-test every release file on your own PC, the same way the
# GitHub workflow (.github/workflows/release.yml) does: same images, same scripts.
#
#   packaging/build-all.sh [-o OUTDIR] [DISTRO...]
#     DISTRO   any of: arch debian-13 ubuntu-24.04 fedora-44 opensuse-tumbleweed (default: all)
#     OUTDIR   default: dist/release-VER in the repo (dist/ is git-ignored)
# The irremote source is a `git archive` of the current HEAD (committed files
# only); the elksmart-comm source is downloaded once by fetch-elksmart-comm.sh.
#
# Result:
#   OUTDIR/<distro>/pkg/<packages>  OUTDIR/<distro>/{build.log,test.log,lintian-*|rpmlint-*,contents-*,...}
#   OUTDIR/release/                 exactly the files a release gets, plus SHA256SUMS
#   OUTDIR/release-notes.md         the notes the release would use
# Needs docker and network. Containers are --rm and named irremote-pkg-*;
# nothing is pushed or uploaded.
set -euo pipefail
PKG=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$PKG")
. "$PKG/distros.sh"
. "$PKG/elksmart-comm.sh"
OUT=
if [ "${1:-}" = -o ]; then OUT=$2; shift 2; fi

VER=$("$PKG/release-info.sh" version)
[[ $VER =~ ^[0-9]+(\.[0-9]+)+$ ]] || { echo "cannot get the version (got '$VER')"; exit 1; }
OUT=$(mkdir -p "${OUT:-$ROOT/dist/release-$VER}" && readlink -f "${OUT:-$ROOT/dist/release-$VER}")
[ -n "$(git -C "$ROOT" status --porcelain --untracked-files=no)" ] && echo "note: uncommitted changes are NOT in the build (git archive uses HEAD)"
TARBALL=$OUT/source/irremote-$VER.tar.gz
mkdir -p "$OUT/source"
git -C "$ROOT" archive --format=tar.gz --prefix="irremote-$VER/" -o "$TARBALL" HEAD
echo "source: git archive of $(git -C "$ROOT" rev-parse --short HEAD) -> $TARBALL"
ELKTAR=$OUT/source/elksmart-comm-$ELK_VER.tar.gz
"$PKG/fetch-elksmart-comm.sh" "$OUT/source"

DISTROS=("$@"); [ ${#DISTROS[@]} -eq 0 ] && DISTROS=("${ALL_DISTROS[@]}")
for d in "${DISTROS[@]}"; do known_distro "$d"; done

declare -A RESULT
for d in "${DISTROS[@]}"; do
  echo "===== $d"
  if "$PKG/build.sh" "$d" "$TARBALL" "$ELKTAR" "$OUT/$d" >"$OUT/$d.build.log" 2>&1; then
    mv "$OUT/$d.build.log" "$OUT/$d/build.log"
    echo "build OK: $(ls "$OUT/$d/pkg" | tr '\n' ' ')"
  else
    mkdir -p "$OUT/$d"; mv "$OUT/$d.build.log" "$OUT/$d/build.log"
    echo "BUILD FAILED ($d), tail of $OUT/$d/build.log:"; tail -25 "$OUT/$d/build.log"; RESULT[$d]="build FAIL"; continue
  fi
  if "$PKG/test-in-container.sh" "$d" "$OUT/$d/pkg" "$VER" >"$OUT/$d/test.log" 2>&1; then
    RESULT[$d]="build OK, test PASS"
  else
    RESULT[$d]="build OK, test FAIL"
    grep '^FAIL' "$OUT/$d/test.log" || true
  fi
  tail -1 "$OUT/$d/test.log"
done

# release folder: every package that was built, SHA256SUMS and the notes
REL=$OUT/release
rm -rf "$REL"; mkdir -p "$REL"
for d in "${DISTROS[@]}"; do [ -d "$OUT/$d/pkg" ] && cp "$OUT/$d"/pkg/* "$REL/"; done
(cd "$REL" && sha256sum -- * >SHA256SUMS)
"$PKG/release-info.sh" notes "v$VER" >"$OUT/release-notes.md"
echo "release files in $REL:"; (cd "$REL" && ls -l)

echo "===== summary (irremote $VER, elksmart-comm $ELK_VER)"
for d in "${DISTROS[@]}"; do printf '%-22s %s\n' "$d" "${RESULT[$d]}"; done
for d in "${DISTROS[@]}"; do [[ ${RESULT[$d]} == *PASS ]] || exit 1; done
