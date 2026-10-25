#!/bin/bash
# Download the elksmart-comm source once and pack it as a tarball that every
# build container uses (so the builds don't each fetch from git.janouch.name).
#   fetch-elksmart-comm.sh OUTDIR
#     -> OUTDIR/elksmart-comm-VER.tar.gz   (prefix elksmart-comm-VER/, liberty included)
# The commit IDs are checked against packaging/elksmart-comm.sh, so the
# tarball is exactly the pinned upstream source. Needs git, tar, gzip.
set -euo pipefail
PKG=$(cd "$(dirname "$0")" && pwd)
. "$PKG/elksmart-comm.sh"
OUT=$(mkdir -p "${1:?usage: fetch-elksmart-comm.sh OUTDIR}" && readlink -f "$1")

# the hand-built Arch PKGBUILD must pin the same commit
arch_commit=$(sed -n 's/^_commit=//p' "$PKG/elksmart-comm-git/PKGBUILD")
[ "$arch_commit" = "$ELK_COMMIT" ] || { echo "::error::packaging/elksmart-comm-git/PKGBUILD has _commit=$arch_commit, packaging/elksmart-comm.sh has $ELK_COMMIT"; exit 1; }

W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
git -c advice.detachedHead=false clone -q "$ELK_URL" "$W/src"
git -C "$W/src" -c advice.detachedHead=false checkout -q "$ELK_COMMIT"
git -C "$W/src" -c protocol.file.allow=never submodule -q update --init liberty
got=$(git -C "$W/src" rev-parse HEAD); lib=$(git -C "$W/src/liberty" rev-parse HEAD)
[ "$got" = "$ELK_COMMIT" ] || { echo "::error::usb-drivers is at $got, expected $ELK_COMMIT"; exit 1; }
[ "$lib" = "$ELK_LIBERTY_COMMIT" ] || { echo "::error::liberty is at $lib, expected $ELK_LIBERTY_COMMIT"; exit 1; }
date=$(TZ=UTC git -C "$W/src" log -1 --date=format-local:%Y%m%d --format=%cd)
up=$(sed -n 's/^project (usb-drivers VERSION \([0-9.]*\).*/\1/p' "$W/src/CMakeLists.txt")
[ "$date" = "$ELK_DATE" ] && [ "$up" = "$ELK_UPSTREAM" ] \
  || { echo "::error::upstream says version $up, date $date; packaging/elksmart-comm.sh says $ELK_UPSTREAM, $ELK_DATE"; exit 1; }

# pack: usb-drivers + liberty, without .git, reproducibly
D=elksmart-comm-$ELK_VER
mkdir "$W/$D"
git -C "$W/src" archive HEAD | tar -x -C "$W/$D"
git -C "$W/src/liberty" archive HEAD | tar -x -C "$W/$D/liberty"
mtime=$(git -C "$W/src" log -1 --format=%cI)
tar --sort=name --mtime="$mtime" --owner=0 --group=0 --numeric-owner --format=gnu \
  -C "$W" -cf - "$D" | gzip -n -9 >"$OUT/$D.tar.gz"
echo "elksmart-comm $ELK_VER (usb-drivers $ELK_COMMIT, liberty $ELK_LIBERTY_COMMIT)"
(cd "$OUT" && sha256sum "$D.tar.gz")
