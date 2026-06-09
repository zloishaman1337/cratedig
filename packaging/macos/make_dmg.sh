#!/usr/bin/env bash
# Build a drag-to-Applications .dmg from the PyInstaller .app bundle.
# Run on macOS after: pyinstaller packaging/cratedig.spec --noconfirm
#
#   packaging/macos/make_dmg.sh [version]
#
# Output: dist/cratedig-<version>.dmg
set -euo pipefail

VERSION="${1:-0.1.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/dist/cratedig.app"
DMG="$ROOT/dist/cratedig-${VERSION}.dmg"

if [[ ! -d "$APP" ]]; then
  echo "error: $APP not found — run PyInstaller first" >&2
  exit 1
fi

rm -f "$DMG"

if command -v create-dmg >/dev/null 2>&1; then
  create-dmg \
    --volname "cratedig" \
    --app-drop-link 450 180 \
    --icon "cratedig.app" 150 180 \
    --window-size 600 360 \
    "$DMG" "$APP"
else
  # Fallback: plain hdiutil image (no fancy layout).
  echo "create-dmg not found; using hdiutil (brew install create-dmg for the nicer layout)" >&2
  STAGE="$(mktemp -d)"
  cp -R "$APP" "$STAGE/"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "cratedig" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
  rm -rf "$STAGE"
fi

echo "wrote $DMG"
