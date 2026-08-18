#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
DIST="$ROOT/dist"
BUILD="${PKG_BUILD_DIR:-$ROOT/build}"
APP_NAME="Cursor Usage"
APP="$DIST/${APP_NAME}.app"
PAYLOAD="$BUILD/pkg-payload"
SCRIPTS="$ROOT/packaging/scripts"
IDENT="com.cursor-usage.menubar"
VERSION="1.0.0"
PKG="$DIST/CursorUsage-${VERSION}-arm64.pkg"

if [[ ! -x "$PY" ]]; then
  python3 -m venv "$VENV"
fi
"$PY" -m pip install -q -r "$ROOT/requirements.txt" -r "$ROOT/requirements-build.txt"

chmod -R u+w "$DIST" "$BUILD" 2>/dev/null || true
rm -rf "$DIST" "$BUILD"
mkdir -p "$DIST" "$BUILD"

"$PY" -m PyInstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST" \
  --workpath "$BUILD/pyinstaller" \
  "$ROOT/packaging/Cursor Usage.spec"

if [[ ! -d "$APP" ]]; then
  echo "expected app bundle at $APP" >&2
  exit 1
fi

# Ad-hoc sign so Gatekeeper treats it as a local app, not random unsigned bits.
codesign --force --deep --sign - "$APP"

mkdir -p "$PAYLOAD"
rm -rf "$PAYLOAD/${APP_NAME}.app"
cp -R "$APP" "$PAYLOAD/"

chmod +x "$SCRIPTS/postinstall"

pkgbuild \
  --root "$PAYLOAD" \
  --identifier "$IDENT" \
  --version "$VERSION" \
  --install-location /Applications \
  --scripts "$SCRIPTS" \
  "$PKG"

echo
echo "Built: $PKG"
ls -lh "$PKG"
echo
echo "This package is Apple Silicon (arm64) and unsigned by Apple."
echo "Recipients: double-click the pkg, or right-click → Open if macOS blocks it."
echo "They must already be signed in to the Cursor desktop app."
