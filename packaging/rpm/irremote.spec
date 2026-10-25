# IR Remote. Version is set by packaging/build-rpm.sh from irremote/__init__.py.
Name:           irremote
Version:        1.1.0
Release:        1%{?dist}
Summary:        Friendly desktop remote control for USB infrared blasters
License:        MIT
URL:            https://github.com/eugenesflanagin-spec/irremote
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz
BuildArch:      noarch

%if 0%{?suse_version}
%global pyqt6 python3-PyQt6
%global pydbus python3-dbus-python
%else
%global pyqt6 python3-pyqt6
%global pydbus python3-dbus
%endif

BuildRequires:  python3 >= 3.11
BuildRequires:  %{pyqt6}
BuildRequires:  %{pydbus}
BuildRequires:  desktop-file-utils
Requires:       python3 >= 3.11
Requires:       %{pyqt6}
Requires:       %{pydbus}
Requires:       elksmart-comm
%if 0%{?suse_version}
Recommends:     libnotify-tools
%else
Requires:       hicolor-icon-theme
Recommends:     libnotify
%endif
Suggests:       kf6-kconfig

%description
IR Remote turns an ELK Smart / OCRUSTAR USB infrared blaster (045c:0132) into
a remote control on your desktop. Teach it the buttons of your real remotes
(TV, soundbar, fan, ...) once, then press them from the window, a picture of
your remote, the tray, a keyboard shortcut or a script.

The dongle itself is driven by elksmart-comm (package elksmart-comm).

%prep
%autosetup -n %{name}-%{version}

%build
# plain Python, nothing to build

%install
# same layout as the Arch package: a private module directory
install -d %{buildroot}%{_prefix}/lib/irremote/irremote
install -m644 irremote/*.py %{buildroot}%{_prefix}/lib/irremote/irremote/
install -Dm644 -t %{buildroot}%{_prefix}/lib/irremote/irremote/layouts irremote/layouts/*.json
python3 -m compileall -q -d %{_prefix}/lib/irremote %{buildroot}%{_prefix}/lib/irremote
install -Dm755 bin/irremote %{buildroot}%{_bindir}/irremote
install -Dm644 data/irremote.desktop %{buildroot}%{_datadir}/applications/irremote.desktop
install -Dm644 data/irremote.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/irremote.svg

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/irremote.desktop
T=$(mktemp -d)
QT_QPA_PLATFORM=offscreen HOME=$T XDG_CONFIG_HOME=$T/.config XDG_DATA_HOME=$T/.local/share \
  XDG_RUNTIME_DIR=$T python3 -m unittest discover -s tests
rm -rf "$T"

%files
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/irremote
%{_prefix}/lib/irremote/
%{_datadir}/applications/irremote.desktop
%{_datadir}/icons/hicolor/scalable/apps/irremote.svg

%changelog
* Sun Oct 25 2026 Eugene Flanagin <eflanagin@pm.me> - 1.1.0-1
- Package of upstream release 1.1.0 (see CHANGELOG.md)
