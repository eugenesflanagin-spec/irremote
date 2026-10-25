# SPDX-License-Identifier: MIT
# Maintainer: Eugene Flanagin <eflanagin@pm.me>
#
# Builds from this source tree (run makepkg in the repository root).
# Build and install packaging/elksmart-comm-git first.

pkgname=irremote
pkgver=1.0.0
pkgrel=1
pkgdesc="IR Remote - friendly desktop remote control for ELK Smart / OCRUSTAR USB infrared blasters"
arch=('any')
url="https://github.com/eugenesflanagin-spec/irremote"
license=('MIT')
depends=('python' 'python-pyqt6' 'python-dbus' 'elksmart-comm-git')
optdepends=('libnotify: notifications from "irremote send" (keyboard shortcuts)'
            'kconfig: kwriteconfig6, to save global shortcuts like System Settings does')

pkgver() {
	python -c 'import sys; sys.path.insert(0, sys.argv[1]); import irremote; print(irremote.__version__)' "$startdir"
}

prepare() {
	rm -rf "$srcdir/tree"
	mkdir -p "$srcdir/tree"
	cp -r "$startdir"/{irremote,tests,bin,data,README.md,LICENSE} "$srcdir/tree/"
	find "$srcdir/tree" -name __pycache__ -prune -exec rm -rf {} +
}

check() {
	cd tree
	QT_QPA_PLATFORM=offscreen HOME="$srcdir/home" XDG_CONFIG_HOME="$srcdir/home/.config" \
		XDG_DATA_HOME="$srcdir/home/.local/share" python -m unittest discover -s tests
}

package() {
	cd tree
	install -d "$pkgdir/usr/lib/irremote/irremote"
	install -m644 irremote/*.py "$pkgdir/usr/lib/irremote/irremote/"
	python -m compileall -q -d /usr/lib/irremote "$pkgdir/usr/lib/irremote"
	install -Dm755 bin/irremote "$pkgdir/usr/bin/irremote"
	install -Dm644 data/irremote.desktop "$pkgdir/usr/share/applications/irremote.desktop"
	install -Dm644 data/irremote.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/irremote.svg"
	install -Dm644 README.md "$pkgdir/usr/share/doc/irremote/README.md"
	install -Dm644 LICENSE "$pkgdir/usr/share/licenses/irremote/LICENSE"
}
