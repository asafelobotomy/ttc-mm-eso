#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
APPDIR="$BUILD_DIR/AppDir"
ARCH_NAME=${ARCH:-$(uname -m)}

APPIMAGETOOL_BIN=${APPIMAGETOOL:-}
if [[ -z "$APPIMAGETOOL_BIN" ]]; then
  if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL_BIN=$(command -v appimagetool)
  elif [[ -x "$BUILD_DIR/appimagetool-${ARCH_NAME}.AppImage" ]]; then
    APPIMAGETOOL_BIN="$BUILD_DIR/appimagetool-${ARCH_NAME}.AppImage"
  elif [[ -x "$BUILD_DIR/appimagetool.AppImage" ]]; then
    APPIMAGETOOL_BIN="$BUILD_DIR/appimagetool.AppImage"
  else
    echo "appimagetool is required to build the AppImage." >&2
    echo "Set APPIMAGETOOL=/path/to/appimagetool or place appimagetool-${ARCH_NAME}.AppImage in build/." >&2
    exit 1
  fi
fi

cd "$ROOT_DIR"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name ttc-mm-gui \
  --add-data "ttc_mm/compat:ttc_mm/compat" \
  ttc_mm/gui.py

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -r "$DIST_DIR/ttc-mm-gui/." "$APPDIR/usr/bin/"
cp "$ROOT_DIR/packaging/ttc-mm.desktop" "$APPDIR/ttc-mm.desktop"
cp "$ROOT_DIR/packaging/ttc-mm.desktop" "$APPDIR/usr/share/applications/"
cp "$ROOT_DIR/packaging/ttc-mm.svg" "$APPDIR/ttc-mm.svg"
cp "$ROOT_DIR/packaging/ttc-mm.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/ttc-mm.svg"
cp "$ROOT_DIR/packaging/ttc-mm.svg" "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
exec "$HERE/usr/bin/ttc-mm-gui" "$@"
EOF
chmod +x "$APPDIR/AppRun"

if [[ "$APPIMAGETOOL_BIN" == *.AppImage ]]; then
  "$APPIMAGETOOL_BIN" --appimage-extract-and-run "$APPDIR" "$DIST_DIR/ttc-mm-gui-${ARCH_NAME}.AppImage"
else
  "$APPIMAGETOOL_BIN" "$APPDIR" "$DIST_DIR/ttc-mm-gui-${ARCH_NAME}.AppImage"
fi
echo "Built $DIST_DIR/ttc-mm-gui-${ARCH_NAME}.AppImage"