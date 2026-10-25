# shellcheck shell=bash
# shared helpers for test.sh (sourced inside a fresh distro container; KIND=arch|deb|rpm)
FAILS=0
fail() { echo "FAIL: $*"; FAILS=$((FAILS+1)); }
# pkg_install PACKAGE...: install extra tools from the distro's repositories (quietly)
pkg_install() {
  if [ "$KIND" = arch ]; then pacman -S --noconfirm --needed "$@" >/dev/null 2>&1
  elif [ "$KIND" = deb ]; then apt-get install -y -q --no-install-recommends "$@" >/dev/null 2>&1
  elif command -v dnf >/dev/null; then dnf -y -q install "$@" >/dev/null 2>&1
  else zypper -n -q install --no-recommends "$@" >/dev/null 2>&1; fi
}
install_pkgs() {
  . /etc/os-release; echo "### $PRETTY_NAME"
  if [ "$KIND" = arch ]; then
    pacman -Syu --noconfirm >/tmp/upgrade.log 2>&1 || { tail -30 /tmp/upgrade.log; fail "pacman -Syu"; finish; }
    pacman -U --noconfirm /pkgs/*.pkg.tar.zst >/tmp/install.log 2>&1 || { tail -30 /tmp/install.log; fail "pacman -U"; finish; }
    pacman -Q elksmart-comm-git irremote
  elif [ "$KIND" = deb ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq && apt-get install -y -q --no-install-recommends /pkgs/*.deb >/tmp/install.log 2>&1 \
      || { tail -30 /tmp/install.log; fail "apt install"; finish; }
    grep -E '^Setting up ' /tmp/install.log | grep -c . | sed 's/^/packages set up incl. deps: /'
    for p in /pkgs/*.deb; do dpkg-deb -f "$p" Package Version Depends; done
  elif command -v dnf >/dev/null; then
    dnf -y -q install /pkgs/*.rpm >/tmp/install.log 2>&1 || { tail -30 /tmp/install.log; fail "dnf install"; finish; }
    rpm -q elksmart-comm irremote
  else
    zypper -n -q --no-gpg-checks install --allow-unsigned-rpm --no-recommends /pkgs/*.rpm >/tmp/install.log 2>&1 \
      || { tail -30 /tmp/install.log; fail "zypper install"; finish; }
    rpm -q elksmart-comm irremote
  fi
  echo "OK: installed with the distro package manager"
}
check_ldd() {
  command -v ldd >/dev/null || { echo "(no ldd in image, checking with ld.so)"; }
  for f in "$@"; do
    if command -v ldd >/dev/null; then out=$(ldd "$f" 2>&1); else out=$(/lib64/ld-linux-x86-64.so.2 --list "$f" 2>&1); fi
    if echo "$out" | grep -q 'not found'; then fail "ldd $f:"; echo "$out" | grep 'not found'; else echo "OK ldd: $f ($(echo "$out" | wc -l) libs, none missing)"; fi
  done
}
run_cmd() {  # run_cmd LABEL CMD...   (expects exit 0)
  local label=$1; shift
  out=$("$@" 2>&1 </dev/null); rc=$?
  echo "--- $label (exit $rc)"; echo "$out" | head -"${HEADN:-6}"
  [ $rc -eq 0 ] || fail "$label exit $rc"
}
finish() { if [ $FAILS -eq 0 ]; then echo "RESULT: PASS"; exit 0; else echo "RESULT: FAIL ($FAILS)"; exit 1; fi; }
