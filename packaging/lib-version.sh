# shellcheck shell=bash
# Version stamping helpers, sourced by the build scripts inside the build
# containers (needs only bash, sed, awk and GNU date).
#
# The committed debian/*/changelog and rpm/*.spec are templates: at build time
# the version (irremote: __version__ in irremote/__init__.py, checked against
# the git tag by the workflow; elksmart-comm: packaging/elksmart-comm.sh) is
# written into a copy of them. Nothing has to be edited by hand for a release.

PKG_MAINT="Eugene Flanagin <eflanagin@pm.me>"

# release_date VER CHANGELOG.md -> YYYY-MM-DD from the "## VER - YYYY-MM-DD"
# heading, or today's date (UTC) if there is no such heading yet.
release_date() {
  local d
  d=$(sed -nE "s/^## +v?$1 +- +([0-9]{4}-[0-9]{2}-[0-9]{2}).*/\1/p" "$2" | head -1)
  [ -n "$d" ] || d=$(date -u +%F)
  echo "$d"
}

# stamp_debian_changelog FILE NAME VER DATE MESSAGE: add a "VER-1" entry on
# top unless the top entry is already VER-1.
stamp_debian_changelog() {
  local f=$1 name=$2 ver=$3 date=$4 msg=$5 tmp
  head -1 "$f" | grep -qF "$name ($ver-1)" && return 0
  tmp=$(mktemp)
  {
    echo "$name ($ver-1) unstable; urgency=medium"
    echo
    echo "  * $msg"
    echo
    echo " -- $PKG_MAINT  $(LC_ALL=C date -u -R -d "$date 12:00:00")"
    echo
    cat "$f"
  } >"$tmp"
  cat "$tmp" >"$f"; rm -f "$tmp"
}

# stamp_spec FILE VER DATE MESSAGE: set Version: and add a %changelog entry
# for VER-1 unless one is there already.
stamp_spec() {
  local f=$1 ver=$2 date=$3 msg=$4 line
  sed -i -E "s/^(Version:[[:space:]]+).*/\1$ver/" "$f"
  grep -qF -- " - $ver-1" "$f" && return 0
  line="* $(LC_ALL=C date -u -d "$date" '+%a %b %d %Y') $PKG_MAINT - $ver-1"
  awk -v l1="$line" -v l2="- $msg" \
    '{ print } /^%changelog/ { print l1; print l2; print "" }' "$f" >"$f.new" && mv "$f.new" "$f"
}

# elk_date: ELK_DATE (YYYYMMDD) as YYYY-MM-DD
elk_date() { echo "${ELK_DATE:0:4}-${ELK_DATE:4:2}-${ELK_DATE:6:2}"; }
