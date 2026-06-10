#!/usr/bin/env bash
# One-shot macOS build: venv -> deps -> ffmpeg -> icons -> .app -> .dmg
# Run from the repo root on a Mac:
#
#   bash packaging/macos/build_all.sh [version]
#
# Output: dist/cratedig.app  and  dist/cratedig-<version>.dmg
set -euo pipefail

VERSION="${1:-0.1.0}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "==> Python venv"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[gui,analysis,download,metadata,build]"

echo "==> Fetch ffmpeg/ffplay (static arm64 from osxexperts.net, FFmpeg 8.1)"
mkdir -p packaging/bin/macos
# osxexperts.net ships STATIC arm64 builds (evermeet.cx is x86_64-only -> Rosetta).
# URLs are version-pinned (ff*81arm = FFmpeg 8.1); bump the "81" when upgrading.
for tool in ffmpeg ffplay; do
  if [[ ! -x "packaging/bin/macos/$tool" ]]; then
    # the host can reset the connection mid-transfer; retry to survive it.
    curl -L --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 30 \
      "https://www.osxexperts.net/${tool}81arm.zip" -o "/tmp/$tool.zip"
    unzip -o "/tmp/$tool.zip" -d packaging/bin/macos
  fi
done
chmod +x packaging/bin/macos/ffmpeg packaging/bin/macos/ffplay
# Strip quarantine so the bundled tools run inside an unsigned app.
xattr -dr com.apple.quarantine packaging/bin/macos || true

echo "==> Render icons (.icns via iconutil)"
python packaging/render_icons.py

echo "==> PyInstaller (.app)"
pyinstaller packaging/cratedig.spec --noconfirm

echo "==> Release manifest (v$VERSION)"
MANIFEST_DIR="packaging/release-manifests"
mkdir -p "$MANIFEST_DIR"
NEW_MANIFEST="$MANIFEST_DIR/cratedig-$VERSION-mac.json"
python packaging/make_manifest.py generate dist/cratedig.app "$VERSION" mac "$NEW_MANIFEST"

# Pick the previous mac manifest (newest that isn't this one) to diff against.
PREV="$(ls "$MANIFEST_DIR"/cratedig-*-mac.json 2>/dev/null | grep -v "$NEW_MANIFEST" \
        | sort -V | tail -n 1 || true)"

TIER="full"
if [[ -n "$PREV" ]]; then
  DIFF_OUT="$(python packaging/make_manifest.py diff "$PREV" "$NEW_MANIFEST")"
  echo "$DIFF_OUT" | sed 's/^/    /'
  if echo "$DIFF_OUT" | grep -q 'tier=delta'; then TIER="delta"; fi
fi

if [[ "$TIER" == "delta" ]]; then
  echo "==> macOS DELTA update zip (v$VERSION)"
  OUT="dist/cratedig-update-${VERSION}-mac.zip"
  python packaging/make_manifest.py build-delta-zip "$PREV" "$NEW_MANIFEST" dist/cratedig.app "$OUT"
else
  echo "==> DMG (full, v$VERSION)"
  bash packaging/macos/make_dmg.sh "$VERSION"
  OUT="dist/cratedig-${VERSION}.dmg"
fi

echo
echo "Done ($TIER):"
echo "  dist/cratedig.app"
echo "  $NEW_MANIFEST"
echo "  $OUT"
echo
echo "Unsigned build. On the target Mac, first launch = right-click the app -> Open,"
echo "or run:  xattr -dr com.apple.quarantine /Applications/cratedig.app"
