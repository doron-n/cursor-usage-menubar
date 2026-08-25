#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
VENV="$ROOT/.venv"
PY="$VENV/bin/python"
DIST="${PKG_DIST_DIR:-$ROOT/dist}"
BUILD="${PKG_BUILD_DIR:-$ROOT/build}"
APP_NAME="Cursor Usage"
APP="$DIST/${APP_NAME}.app"
PAYLOAD="$BUILD/pkg-payload"
SCRIPTS="$ROOT/packaging/scripts"
IDENT="com.cursor-usage.menubar"
# GitHub download page + releases. Override with PKG_GITHUB_REPO if the remote differs.
GITHUB_REPO="${PKG_GITHUB_REPO:-doron-n/cursor-usage-menubar}"
PAGES_URL="https://doron-n.github.io/cursor-usage-menubar/"

if [[ ! -x "$PY" ]]; then
  python3 -m venv "$VENV"
fi
"$PY" -m pip install -q -r "$ROOT/requirements.txt" -r "$ROOT/requirements-build.txt"

if [[ "${PKG_SKIP_BUMP:-}" == "1" ]]; then
  VERSION="$("$PY" -m cursor_usage_menubar.app_version --current)"
else
  VERSION="$("$PY" -m cursor_usage_menubar.app_version --bump "${PKG_BUMP:-patch}")"
fi
export CURSOR_USAGE_VERSION="$VERSION"
PKG="$DIST/CursorUsage-${VERSION}-arm64.pkg"
STABLE_PKG="$DIST/CursorUsage-arm64.pkg"

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

cp -f "$PKG" "$STABLE_PKG"
"$PY" -m cursor_usage_menubar.app_version --write "$VERSION"

if [[ "${PKG_COPY_DESKTOP:-1}" == "1" && -d "$HOME/Desktop" ]]; then
  cp -f "$PKG" "$HOME/Desktop/"
fi

echo
echo "Built: $PKG"
echo "Version: $VERSION"
ls -lh "$PKG"
echo
echo "This package is Apple Silicon (arm64) and unsigned by Apple."
echo "Recipients: double-click the pkg, or right-click → Open if macOS blocks it."
echo "They must already be signed in to the Cursor desktop app."
echo "Download page: $PAGES_URL"

if [[ "${PKG_PUBLISH:-}" == "1" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "gh is required to publish a GitHub Release" >&2
    exit 1
  fi
  notes="$(cat <<EOF
Cursor Usage ${VERSION} for Apple Silicon.

Download and install notes: ${PAGES_URL}

- Already signed in to the Cursor desktop app
- Right-click the pkg → Open if macOS blocks it
- Unofficial Cursor APIs — they can change without notice
EOF
)"
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1 && git remote get-url origin >/dev/null 2>&1; then
    git add VERSION
    if ! git diff --cached --quiet; then
      git commit -m "Bump version to ${VERSION}"
    fi
    git push origin HEAD
  fi
  gh release create "v${VERSION}" \
    --repo "$GITHUB_REPO" \
    --title "Cursor Usage ${VERSION}" \
    --notes "$notes" \
    "$PKG" \
    "$STABLE_PKG"
  echo "Published: https://github.com/${GITHUB_REPO}/releases/tag/v${VERSION}"
fi
