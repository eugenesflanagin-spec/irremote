#!/bin/bash
# Runs INSIDE a fresh Debian/Ubuntu container (started by build.sh):
#   build-deb.sh VER ELKVER SUFFIX DIST      e.g.  build-deb.sh 1.1.0 1.2.0+git20260821.d48653a '~deb13' trixie
# Mounts: /in/irremote-VER.tar.gz, /in/elksmart-comm-ELKVER.tar.gz (ro),
#         /pkg = this packaging tree (ro), /out = logs, /out/pkg = finished packages.
# Builds two source packages: elksmart-comm (amd64) and irremote (all).
set -euo pipefail
VER=$1 ELKVER=$2 SUFFIX=$3 DIST=$4
export DEBIAN_FRONTEND=noninteractive
. /pkg/lib-version.sh
. /pkg/elksmart-comm.sh
. /pkg/distros.sh
[ "$ELKVER" = "$ELK_VER" ] || { echo "elksmart-comm tarball is $ELKVER, packaging/elksmart-comm.sh says $ELK_VER"; exit 1; }

echo "### toolchain"
apt-get update -qq
apt-get install -y -q --no-install-recommends build-essential devscripts debhelper equivs fakeroot \
  lintian pkgconf ca-certificates file >/tmp/toolchain.log 2>&1 || { tail -30 /tmp/toolchain.log; exit 1; }

# debbuild NAME UPVER DATE MESSAGE: unpack /in/NAME-UPVER.tar.gz (prefix NAME-UPVER/)
# in /work/NAME, add packaging/debian/NAME as debian/, build the binary packages.
debbuild() {
  local name=$1 up=$2 date=$3 msg=$4 src
  mkdir -p "/work/$name" && cd "/work/$name"
  cp "/in/$name-$up.tar.gz" "${name}_$up.orig.tar.gz"
  tar xzf "${name}_$up.orig.tar.gz"
  src=/work/$name/$name-$up; cd "$src"
  cp -a "/pkg/debian/$name" debian
  if [ "$name" = elksmart-comm ]; then
    # the udev rule and the patch live in packaging/elksmart-comm-git/ (one copy for all distros)
    cp /pkg/elksmart-comm-git/70-elksmart-ir.rules debian/
    mkdir -p debian/patches
    cp /pkg/elksmart-comm-git/0001-learn-skip-0132-ack.patch debian/patches/
    echo 0001-learn-skip-0132-ack.patch >debian/patches/series
  fi
  stamp_debian_changelog debian/changelog "$name" "$up" "$date" "$msg"
  sed -i "1s/^$name (\([^)]*\)) [^;]*;/$name (\1$SUFFIX) $DIST;/" debian/changelog
  head -1 debian/changelog
  echo "### $name: build dependencies"
  (cd /tmp && mk-build-deps -i -r -t 'apt-get -y -q --no-install-recommends' "$src/debian/control") >"/tmp/builddeps-$name.log" 2>&1 \
    || { cat "/tmp/builddeps-$name.log"; exit 1; }
  echo "### $name: dpkg-buildpackage"
  dpkg-buildpackage -us -uc -b
  cd "/work/$name"
  lintian -I --show-overrides "${name}"_*.changes >"/out/lintian-$name.txt" 2>&1 || true
  echo "### $name: lintian"; cat "/out/lintian-$name.txt"
  for f in "${name}"_*.deb; do
    cp "$f" "/out/pkg/$(asset_name "$f")"
    dpkg-deb -I "$f" >"/out/control-$name.txt"
    dpkg-deb -c "$f" >"/out/contents-$name.txt"
  done
}

debbuild elksmart-comm "$ELKVER" "$(elk_date)" \
  "Package of usb-drivers commit ${ELK_COMMIT:0:7} (elksmart-comm only)."
IRDATE=$(release_date "$VER" <(tar xzOf "/in/irremote-$VER.tar.gz" "irremote-$VER/CHANGELOG.md"))
debbuild irremote "$VER" "$IRDATE" "Package of upstream release $VER (see CHANGELOG.md)."
echo "### built: $(ls /out/pkg)"
