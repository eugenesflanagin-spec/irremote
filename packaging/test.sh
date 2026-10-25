#!/bin/bash
# Fresh-container install + checks for irremote and elksmart-comm
# (run by test-in-container.sh as: docker run -e KIND=arch|deb|rpm -e VER=x.y.z
#  -v pkgs:/pkgs -v packaging:/pkg IMAGE bash /pkg/test.sh)
# There is no USB dongle in CI: nothing here talks to one (only --help/--version
# of elksmart-comm, and IRREMOTE_COMM points the app at a program that doesn't exist).
set -u
. /pkg/test-common.sh
. /pkg/elksmart-comm.sh
install_pkgs
for b in irremote elksmart-comm; do
  command -v $b >/dev/null && echo "OK installed: $(command -v $b)" || fail "missing $b"
done
check_ldd /usr/bin/elksmart-comm
case $KIND in
  deb) ev=$(dpkg-query -W -f '${Version}' elksmart-comm) iv=$(dpkg-query -W -f '${Version}' irremote) want=$ELK_VER ;;
  rpm) ev=$(rpm -q --qf '%{VERSION}-%{RELEASE}' elksmart-comm) iv=$(rpm -q --qf '%{VERSION}-%{RELEASE}' irremote) want=$ELK_VER ;;
  *)   ev=$(pacman -Q elksmart-comm-git | cut -d' ' -f2) iv=$(pacman -Q irremote | cut -d' ' -f2) want=$ELK_ARCH_PKGVER ;;
esac
[[ $ev == "$want"-* ]] && echo "OK elksmart-comm package version $ev" || fail "elksmart-comm package version $ev, expected $want-*"
[[ $iv == "$VER"-* ]] && echo "OK irremote package version $iv" || fail "irremote package version $iv, expected $VER-*"

echo "--- elksmart-comm"
run_cmd "elksmart-comm --help" elksmart-comm --help
run_cmd "elksmart-comm --version" elksmart-comm --version
# our 045c:0132 learn patch (packaging/elksmart-comm-git/0001-learn-skip-0132-ack.patch) is in
grep -qa 'learn/recv: skipping acknowledgement' /usr/bin/elksmart-comm && echo "OK learn patch is applied" || fail "elksmart-comm lacks the 045c:0132 learn patch"
rule=/usr/lib/udev/rules.d/70-elksmart-ir.rules
if [ -f $rule ] && grep -q 'ATTRS{idVendor}=="045c"' $rule && grep -q 'TAG+="uaccess"' $rule; then
  echo "OK udev rule: $rule"
else fail "udev rule $rule missing or wrong"; fi
lic=$(grep -l 'Janouch' /usr/share/licenses/elksmart-comm*/LICENSE* /usr/share/doc/elksmart-comm*/copyright 2>/dev/null | tr '\n' ' ')
[ -n "$lic" ] && echo "OK upstream licence (Přemysl Eric Janouch): $lic" || fail "no elksmart-comm licence naming Janouch"

echo "--- irremote command line"
T=$(mktemp -d); mkdir -m700 "$T/run"
export HOME=$T XDG_CONFIG_HOME=$T/.config XDG_DATA_HOME=$T/.local/share XDG_RUNTIME_DIR=$T/run
export IRREMOTE_COMM=/nonexistent/elksmart-comm   # never run the real tool against hardware
run_cmd "irremote --version" irremote --version
v=$(irremote --version 2>&1 | head -1)
[ "$v" = "irremote $VER" ] && echo "OK version $VER" || fail "--version says '$v', expected 'irremote $VER'"
run_cmd "irremote --help" irremote --help
HEADN=12 run_cmd "irremote layouts" irremote layouts
irremote layouts 2>&1 | grep -q 'vizio-onn-tv' && echo "OK built-in layouts found" || fail "built-in layouts missing"
run_cmd "irremote list" irremote list

echo "--- python import from the installed location"
run_cmd "import irremote" python3 -c '
import sys; sys.path.insert(0, "/usr/lib/irremote")
import irremote, irremote.cli, irremote.core, irremote.gui, dbus
from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
print(irremote.__file__, irremote.__version__, "PyQt", PYQT_VERSION_STR, "Qt", QT_VERSION_STR, "dbus-python", dbus.__version__)
assert irremote.__file__.startswith("/usr/lib/irremote/"), irremote.__file__
assert irremote.__version__ == sys.argv[1], irremote.__version__
' "$VER"
n=$(compgen -G '/usr/lib/irremote/irremote/__pycache__/*.pyc' | wc -l)   # (no find in every image)
[ "$n" -gt 0 ] && echo "OK byte-compiled: $n .pyc files" || fail "no .pyc files under /usr/lib/irremote"

echo "--- GUI starts and quits (offscreen, 3 s)"
out=$(QT_QPA_PLATFORM=offscreen IRREMOTE_SMOKE=3000 timeout 60 irremote 2>&1 </dev/null); rc=$?
echo "$out" | grep -v '^$' | head -10
[ $rc -eq 0 ] && echo "OK GUI ran and quit (exit 0)" || fail "GUI smoke run exit $rc (124 = timed out)"
[ -f "$XDG_CONFIG_HOME/irremote/irremote.conf" ] && echo "OK window settings saved on quit" || echo "(no irremote.conf written)"
rm -rf "$T"

echo "--- desktop entry + icon"
[ -f /usr/share/icons/hicolor/scalable/apps/irremote.svg ] && echo "OK icon" || fail "missing icon"
pkg_install desktop-file-utils
if command -v desktop-file-validate >/dev/null; then
  f=/usr/share/applications/irremote.desktop
  out=$(desktop-file-validate "$f" 2>&1); rc=$?
  [ $rc -eq 0 ] && echo "OK desktop-file-validate $(basename $f)${out:+ ($out)}" || { fail "desktop-file-validate $f"; echo "$out"; }
else fail "desktop-file-validate not available"; fi
finish
