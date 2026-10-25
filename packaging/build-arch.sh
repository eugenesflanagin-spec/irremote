#!/bin/bash
# Runs INSIDE a fresh archlinux:base-devel container (started by build.sh):
#   build-arch.sh VER ELKVER
# Mounts: /in/irremote-VER.tar.gz and /in/elksmart-comm-ELKVER.tar.gz (ro),
#         /pkg = this packaging tree (ro), /out = logs, /out/pkg = finished packages.
# makepkg refuses to run as root, so the packages are built by a throwaway user.
# elksmart-comm-git is built first and installed, because irremote depends on it.
set -euo pipefail
VER=$1 ELKVER=$2
. /pkg/elksmart-comm.sh
. /pkg/distros.sh

echo "### toolchain + build dependencies"
pacman -Syu --noconfirm --needed cmake ninja libusb python python-pyqt6 python-dbus >/tmp/deps.log 2>&1 \
  || { tail -30 /tmp/deps.log; exit 1; }
useradd -m builder
CONF=/pkg/arch/makepkg.conf

echo "### elksmart-comm-git (CI copy of packaging/elksmart-comm-git/PKGBUILD)"
E=/work/elksmart-comm-git; mkdir -p $E
cp /pkg/arch/elksmart-comm-git/PKGBUILD /in/elksmart-comm-$ELKVER.tar.gz $E/
cp /pkg/elksmart-comm-git/{70-elksmart-ir.rules,0001-learn-skip-0132-ack.patch,elksmart-comm.install} $E/
SUM=$(sha256sum $E/elksmart-comm-$ELKVER.tar.gz | cut -d' ' -f1)
sed -i -E "s/^_tarver=.*/_tarver=$ELKVER/; s/^pkgver=.*/pkgver=$ELK_ARCH_PKGVER/; s/^pkgrel=.*/pkgrel=$ELK_ARCH_PKGREL/; s/^sha256sums=\('SKIP'/sha256sums=('$SUM'/" $E/PKGBUILD
grep -E '^(_tarver|pkgver|pkgrel|sha256sums)=' $E/PKGBUILD
chown -R builder: /work
su builder -c "cd $E && makepkg -f --noconfirm --config $CONF"
ELKPKG=$(ls $E/elksmart-comm-git-$ELK_ARCH_PKGVER-$ELK_ARCH_PKGREL-x86_64.pkg.tar.zst)
pacman -U --noconfirm "$ELKPKG" >/tmp/elk-install.log 2>&1 || { cat /tmp/elk-install.log; exit 1; }

echo "### irremote (the PKGBUILD at the root of the source tree)"
cd /work && tar xzf /in/irremote-$VER.tar.gz && chown -R builder: /work
I=/work/irremote-$VER
su builder -c "cd $I && makepkg -f --noconfirm --config $CONF"
IRPKG=$(ls $I/irremote-$VER-*-any.pkg.tar.zst)

for p in "$ELKPKG" "$IRPKG"; do
  n=$(basename "$p")
  cp "$p" "/out/pkg/$(asset_name "$n")"
  bsdtar -tvf "$p" >"/out/contents-${n%%-[0-9]*}.txt"
done
bsdtar -xOf "$ELKPKG" .BUILDINFO >/out/BUILDINFO-elksmart-comm-git.txt
echo "### .BUILDINFO (flags)"; grep -E '^(packager|buildenv|options) ' /out/BUILDINFO-elksmart-comm-git.txt | tr '\n' ' '; echo
echo "### built: $(ls /out/pkg)"
