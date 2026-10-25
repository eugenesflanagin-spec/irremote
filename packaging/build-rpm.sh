#!/bin/bash
# Runs INSIDE a fresh Fedora/openSUSE container (started by build.sh):
#   build-rpm.sh VER ELKVER [DIST]     e.g.  build-rpm.sh 1.1.0 1.2.0+git20260821.d48653a .tw   ("" = distro default, .fc44)
# Mounts: /in/irremote-VER.tar.gz, /in/elksmart-comm-ELKVER.tar.gz (ro),
#         /pkg = this packaging tree (ro), /out = logs, /out/pkg = finished packages.
# Builds elksmart-comm (x86_64) and irremote (noarch).
set -euo pipefail
VER=$1 ELKVER=$2 DIST=${3:-}
. /pkg/lib-version.sh
. /pkg/elksmart-comm.sh
. /pkg/distros.sh
[ "$ELKVER" = "$ELK_VER" ] || { echo "elksmart-comm tarball is $ELKVER, packaging/elksmart-comm.sh says $ELK_VER"; exit 1; }

echo "### toolchain"
if command -v dnf >/dev/null; then
  dnf -y -q install rpm-build rpmlint rpmdevtools dnf-plugins-core gcc make file tar gzip >/tmp/toolchain.log 2>&1 \
    || { tail -30 /tmp/toolchain.log; exit 1; }
else
  zypper -n -q --gpg-auto-import-keys refresh >/dev/null
  zypper -n -q install --no-recommends rpm-build rpmlint rpmdevtools gcc make file tar gzip >/tmp/toolchain.log 2>&1 \
    || { tail -30 /tmp/toolchain.log; exit 1; }
fi

T=/root/rpmbuild
mkdir -p $T/SOURCES $T/SPECS
cp /in/irremote-$VER.tar.gz "/in/elksmart-comm-$ELKVER.tar.gz" $T/SOURCES/
cp /pkg/elksmart-comm-git/{70-elksmart-ir.rules,0001-learn-skip-0132-ack.patch} $T/SOURCES/
cp /pkg/rpm/elksmart-comm.spec /pkg/rpm/irremote.spec $T/SPECS/
DEF=(--define "_topdir $T"); [ -n "$DIST" ] && DEF+=(--define "dist $DIST")

# version + date: irremote from the CHANGELOG.md heading, elksmart-comm from elksmart-comm.sh
IRDATE=$(release_date "$VER" <(tar xzOf /in/irremote-$VER.tar.gz irremote-$VER/CHANGELOG.md))
stamp_spec $T/SPECS/irremote.spec "$VER" "$IRDATE" "Package of upstream release $VER (see CHANGELOG.md)"
stamp_spec $T/SPECS/elksmart-comm.spec "$ELKVER" "$(elk_date)" "Package of usb-drivers commit ${ELK_COMMIT:0:7} (elksmart-comm only)"

builddep() {  # builddep SPEC
  if command -v dnf >/dev/null; then
    dnf -y -q builddep "${DEF[@]}" "$1" >>/tmp/builddeps.log 2>&1 || { cat /tmp/builddeps.log; exit 1; }
  else
    rpmspec -q --buildrequires "${DEF[@]}" "$1" | xargs -d '\n' zypper -n -q install --no-recommends >>/tmp/builddeps.log 2>&1 \
      || { cat /tmp/builddeps.log; exit 1; }
  fi
}

for name in elksmart-comm irremote; do
  SPEC=$T/SPECS/$name.spec
  echo "### $name: build dependencies"
  builddep "$SPEC"
  echo "$name: $(rpmspec -q --srpm --qf '%{version}-%{release}' "${DEF[@]}" "$SPEC")  _udevrulesdir = $(rpm --eval %_udevrulesdir)"
  echo "### $name: rpmbuild"
  rpmbuild -bb "${DEF[@]}" "$SPEC"
  RPM=$(find $T/RPMS -name "$name-[0-9]*.rpm" ! -name '*-debug*')
  rpmlint "$RPM" "$SPEC" >"/out/rpmlint-$name.txt" 2>&1 || true
  echo "### $name: rpmlint"; cat "/out/rpmlint-$name.txt"
  cp "$RPM" "/out/pkg/$(asset_name "$(basename "$RPM")")"
  rpm -qip --requires "$RPM" >"/out/info-$name.txt"
  rpm -qlvp "$RPM" >"/out/contents-$name.txt"
done
echo "### built: $(ls /out/pkg)"
