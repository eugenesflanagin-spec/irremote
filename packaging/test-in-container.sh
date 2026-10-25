#!/bin/bash
# Install the built packages in a FRESH container of their distro and run test.sh.
#   test-in-container.sh DISTRO PKGDIR VER
#     PKGDIR  directory holding both package files (build.sh's OUTDIR/pkg)
#     VER     irremote version (test.sh reads the elksmart-comm version from elksmart-comm.sh)
# Used the same way by build-all.sh and .github/workflows/release.yml.
set -euo pipefail
PKG=$(cd "$(dirname "$0")" && pwd)
. "$PKG/distros.sh"
D=${1:?usage: test-in-container.sh DISTRO PKGDIR VER}; known_distro "$D"
DIR=$(readlink -f "${2:?package dir}")
VER=${3:?version}
name=irremote-pkg-test-${D//./}-$$
echo "### $D: install test in a fresh ${TEST_IMAGE[$D]}"
docker pull -q "${TEST_IMAGE[$D]}" >/dev/null
docker run --rm --name "$name" -e KIND="${KIND[$D]}" -e VER="$VER" \
  -v "$DIR:/pkgs:ro" -v "$PKG:/pkg:ro" "${TEST_IMAGE[$D]}" bash /pkg/test.sh
