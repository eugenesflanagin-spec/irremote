# shellcheck shell=bash
# Which elksmart-comm the release packages are built from. Sourced, not run.
# The one place this is written down for the deb/rpm/CI-Arch builds; the
# commit must match _commit in packaging/elksmart-comm-git/PKGBUILD
# (fetch-elksmart-comm.sh checks that).
#
# elksmart-comm is part of usb-drivers by Přemysl Eric Janouch (0BSD),
# https://git.janouch.name/p/usb-drivers. It needs the "liberty" submodule.
# shellcheck disable=SC2034
ELK_URL=https://git.janouch.name/p/usb-drivers
ELK_COMMIT=d48653a270e1e05a0d17419d07d17a498f4d5c28
ELK_LIBERTY_COMMIT=9268fb8eba4a60499809965b3b69c2eb7e3798e7   # what usb-drivers @ ELK_COMMIT records
ELK_UPSTREAM=1.2.0        # "project (usb-drivers VERSION ...)" in CMakeLists.txt
ELK_DATE=20260821         # commit date of ELK_COMMIT
# deb/rpm version: 1.2.0+git20260821.d48653a
ELK_VER=$ELK_UPSTREAM+git$ELK_DATE.${ELK_COMMIT:0:7}
# Arch package: same name and version as packaging/elksmart-comm-git/PKGBUILD makes
ELK_ARCH_PKGVER=1.2.0.r0.gd48653a
ELK_ARCH_PKGREL=2
