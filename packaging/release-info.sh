#!/bin/bash
# Small helper for the release workflow and build-all.sh. Run from anywhere.
#   release-info.sh version        print __version__ from irremote/__init__.py (the one place the version lives)
#   release-info.sh check TAG      fail unless TAG is "v" + __version__ and CHANGELOG.md has a "## VER" section
#   release-info.sh notes TAG      print the release notes: packaging/release-notes/TAG.md if it exists,
#                                  else the "## VER" section of CHANGELOG.md
#   release-info.sh title TAG      print the release title (first "# " line of the notes, else "IR Remote VER")
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
version() { sed -nE 's/^__version__ = "([^"]+)".*/\1/p' "$ROOT/irremote/__init__.py"; }
changelog_section() {  # text between "## VER" and the next "## " heading
  awk -v v="$1" '/^## / { if (on) exit; if ($2 == v || $2 == "v" v) { on = 1; next } } on' "$ROOT/CHANGELOG.md"
}
notes() {
  local ver=${1#v} f="$ROOT/packaging/release-notes/$1.md"
  if [ -f "$f" ]; then cat "$f"
  else
    echo "# IR Remote $ver"; echo
    changelog_section "$ver"
    echo; echo "Each package was built and install-tested in a clean container for its distro."
  fi
}
case ${1:-} in
  version) version ;;
  check)
    tag=${2:?tag}; ver=$(version)
    [ -n "$ver" ] || { echo "::error::could not read __version__ from irremote/__init__.py"; exit 1; }
    [ "$tag" = "v$ver" ] || { echo "::error::tag $tag does not match __version__ $ver in irremote/__init__.py (expected tag v$ver)"; exit 1; }
    grep -qE "^## v?$ver( |\$)" "$ROOT/CHANGELOG.md" || { echo "::error::CHANGELOG.md has no '## $ver - DATE' section"; exit 1; }
    if [ -n "$(changelog_section Unreleased | grep -v '^[[:space:]]*$' || true)" ]; then
      echo "::warning::CHANGELOG.md still has entries under '## Unreleased' (move them into '## $ver' before tagging)"
    fi
    echo "OK: tag $tag matches __version__ $ver" ;;
  notes) notes "${2:?tag}" ;;
  title)
    t=$(notes "${2:?tag}" | sed -n 's/^# //p' | head -1)
    echo "${t:-IR Remote ${2#v}}" ;;
  *) sed -n '2,8p' "$0"; exit 2 ;;
esac
