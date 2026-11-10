#!/usr/bin/env bash
# Package the PyInstaller output as a .deb.
#   desktop/linux/build_deb.sh <pyinstaller-dist-dir> <version> <output-dir>
# Installs to /opt/productivity-suite, adds the `productivity-suite` command,
# a desktop menu entry and an icon. Data stays in ~/.productivity-suite.
# The window uses the distribution's GTK WebKit through its own Python (see desktop/app_window.py), so the
# package depends on python3-gi and gir1.2-webkit2-4.1; apt installs them with the package.
set -euo pipefail
DIST="${1:?pyinstaller dist folder (…/ProductivitySuite)}"
VERSION="${2:?version, e.g. 0.1.0}"
OUT="${3:?output folder}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ARCH="$(dpkg --print-architecture)"
PKG="$(mktemp -d)/productivity-suite_${VERSION}_${ARCH}"

mkdir -p "$PKG/DEBIAN" "$PKG/opt/productivity-suite" "$PKG/usr/bin" \
         "$PKG/usr/share/applications" "$PKG/usr/share/icons/hicolor/512x512/apps"
cp -a "$DIST"/. "$PKG/opt/productivity-suite/"
cat > "$PKG/usr/bin/productivity-suite" <<'SH'
#!/bin/sh
exec /opt/productivity-suite/ProductivitySuite "$@"
SH
chmod 0755 "$PKG/usr/bin/productivity-suite"
cp "$HERE/productivity-suite.desktop" "$PKG/usr/share/applications/"
cp "$HERE/../assets/icon.png" "$PKG/usr/share/icons/hicolor/512x512/apps/productivity-suite.png"
mkdir -p "$PKG/usr/share/doc/productivity-suite"
cat "$HERE/../../NOTICE" > "$PKG/usr/share/doc/productivity-suite/copyright"
printf '\n\n' >> "$PKG/usr/share/doc/productivity-suite/copyright"
cat "$HERE/../../LICENSE" >> "$PKG/usr/share/doc/productivity-suite/copyright"

SIZE_KB="$(du -sk "$PKG" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<CTRL
Package: productivity-suite
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Installed-Size: ${SIZE_KB}
Depends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1 | gir1.2-webkit2-4.0
Recommends: xdg-utils
Maintainer: Agentic Productivity Suite <noreply@users.noreply.github.com>
Homepage: https://github.com/albanc80/Agentic-Productivity-Suite
Description: Governed agent playbooks for daily work, management, product,
 engineering and upstream operations. Runs locally in its own window (the
 system's GTK WebKit); works offline with local models.
CTRL

# uv and Node.js for connectors (see backend/app/runtimes.py): checked and, if missing or too old, downloaded
# into /opt/productivity-suite/_internal/tools at the end of the install. A failed download never fails the
# install (the app downloads on first use instead). Removing the package deletes them; an upgrade keeps them.
cat > "$PKG/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
  /opt/productivity-suite/ProductivitySuite --install-tools || true
fi
SH
cat > "$PKG/DEBIAN/prerm" <<'SH'
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
  /opt/productivity-suite/ProductivitySuite --remove-tools || true
fi
SH
chmod 0755 "$PKG/DEBIAN/postinst" "$PKG/DEBIAN/prerm"

mkdir -p "$OUT"
dpkg-deb --root-owner-group --build "$PKG" "$OUT/productivity-suite_${VERSION}_${ARCH}.deb"
echo "Built $OUT/productivity-suite_${VERSION}_${ARCH}.deb"
