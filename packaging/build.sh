#!/bin/bash
# Build both packages (elksmart-comm, then irremote) in a fresh container of a distro.
#   build.sh DISTRO IRREMOTE_TARBALL ELKSMART_TARBALL OUTDIR
#     DISTRO            arch | debian-13 | ubuntu-24.04 | fedora-44 | opensuse-tumbleweed
#     IRREMOTE_TARBALL  irremote-VER.tar.gz from `git archive --prefix=irremote-VER/`
#     ELKSMART_TARBALL  elksmart-comm-ELKVER.tar.gz from fetch-elksmart-comm.sh
#     OUTDIR            gets pkg/<package files> plus build logs (lintian/rpmlint, file lists)
# Used the same way by build-all.sh (your PC) and .github/workflows/release.yml.
# Needs docker. The container is removed afterwards (--rm).
set -euo pipefail
PKG=$(cd "$(dirname "$0")" && pwd)
. "$PKG/distros.sh"
D=${1:?usage: build.sh DISTRO IRREMOTE_TARBALL ELKSMART_TARBALL OUTDIR}; known_distro "$D"
TARBALL=$(readlink -f "${2:?irremote source tarball}")
ELKTAR=$(readlink -f "${3:?elksmart-comm source tarball}")
OUT=${4:?output dir}
VER=$(basename "$TARBALL" .tar.gz); VER=${VER#irremote-}
[[ $VER =~ ^[0-9]+(\.[0-9]+)+$ ]] || { echo "cannot get the version from $TARBALL" >&2; exit 1; }
ELKVER=$(basename "$ELKTAR" .tar.gz); ELKVER=${ELKVER#elksmart-comm-}
[[ $ELKVER =~ ^[0-9][0-9a-z.+]+$ ]] || { echo "cannot get the version from $ELKTAR" >&2; exit 1; }

rm -rf "$OUT"; mkdir -p "$OUT/pkg"; OUT=$(readlink -f "$OUT")
name=irremote-pkg-build-${D//./}-$$
echo "### $D: building irremote $VER + elksmart-comm $ELKVER in ${BUILD_IMAGE[$D]}"
docker pull -q "${BUILD_IMAGE[$D]}" >/dev/null
# shellcheck disable=SC2086  # BUILD_ARGS is a word list on purpose
docker run --rm --name "$name" \
  -v "$TARBALL:/in/irremote-$VER.tar.gz:ro" -v "$ELKTAR:/in/elksmart-comm-$ELKVER.tar.gz:ro" \
  -v "$PKG:/pkg:ro" -v "$OUT:/out" \
  "${BUILD_IMAGE[$D]}" \
  bash -c "bash /pkg/build-${KIND[$D]}.sh $VER $ELKVER ${BUILD_ARGS[$D]}; rc=\$?; chown -R $(id -u):$(id -g) /out; exit \$rc"
ls "$OUT/pkg"
