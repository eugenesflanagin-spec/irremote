# elksmart-comm from usb-drivers by Přemysl Eric Janouch (0BSD).
# Version is set by packaging/build-rpm.sh from packaging/elksmart-comm.sh;
# Source0 is the pinned tarball made by packaging/fetch-elksmart-comm.sh.
Name:           elksmart-comm
Version:        1.2.0+git20260821.d48653a
Release:        1%{?dist}
Summary:        Command-line tool for ELK Smart / OCRUSTAR USB infrared blasters
License:        0BSD
URL:            https://git.janouch.name/p/usb-drivers
Source0:        %{name}-%{version}.tar.gz
Source1:        70-elksmart-ir.rules
# 045c:0132 replies "ff ff ff ff" to the learn command before any IR data;
# upstream treats that as "unexpected response" and gives up immediately.
Patch0:         0001-learn-skip-0132-ack.patch
ExclusiveArch:  x86_64

BuildRequires:  gcc
BuildRequires:  make
BuildRequires:  cmake
BuildRequires:  pkgconfig(libusb-1.0)
BuildRequires:  systemd-rpm-macros

%description
elksmart-comm talks to ELK Smart infrared dongles (EKX4S, EKX5S-T, the
OCRUSTAR "Smart IR Blaster" 045c:0132 and relatives). It can learn codes from
a remote control and transmit them.

It is part of usb-drivers by Přemysl Eric Janouch. This package adds a small
patch so learning works with the 045c:0132 dongle, and a udev rule
(70-elksmart-ir.rules) that lets the logged-in desktop user use the dongle
without root. IR Remote (package irremote) is a desktop front end for it.

%prep
%autosetup -p1 -n %{name}-%{version}

%build
%set_build_flags
export CFLAGS="$CFLAGS -fPIE" LDFLAGS="$LDFLAGS -pie"
cmake -S . -B build -DCMAKE_BUILD_TYPE=None -DCMAKE_INSTALL_PREFIX=%{_prefix} \
  -DWITH_HIDAPI=OFF -DWITH_LIBUSB=ON -DBUILD_TESTING=ON
# only elksmart-comm (usb-drivers also has other tools, not packaged here)
%make_build -C build elksmart-comm test-elksmart-comm
awk '/^elksmart-comm$/{p=1} p&&/^razer-bw-te-ctl$/{exit} p' README.adoc >README.elksmart-comm.adoc
cp -p liberty/LICENSE LICENSE.liberty

%install
install -Dm755 build/elksmart-comm %{buildroot}%{_bindir}/elksmart-comm
# keeps its name: IR Remote refers to it, and it must sort before 73-seat-late.rules (uaccess)
install -Dm644 %{SOURCE1} %{buildroot}%{_udevrulesdir}/70-elksmart-ir.rules

%check
./build/test-elksmart-comm

# apply the udev rule now, so a dongle that is already plugged in works
%post
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload >/dev/null 2>&1 || :
  udevadm trigger --action=add --subsystem-match=usb --attr-match=idVendor=045c >/dev/null 2>&1 || :
fi

%postun
if [ "$1" -eq 0 ] && command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload >/dev/null 2>&1 || :
fi

%files
%license LICENSE LICENSE.liberty
%doc README.elksmart-comm.adoc NEWS
%{_bindir}/elksmart-comm
%{_udevrulesdir}/70-elksmart-ir.rules

%changelog
* Sun Oct 25 2026 Eugene Flanagin <eflanagin@pm.me> - 1.2.0+git20260821.d48653a-1
- Package of usb-drivers commit d48653a (elksmart-comm only), with the
  045c:0132 learn patch and the 70-elksmart-ir.rules udev rule
