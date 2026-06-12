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

# Auto-load the minisign key password from a gitignored .env so signing never
# prompts. An already-exported MINISIGN_PASSWORD wins.
if [[ -z "${MINISIGN_PASSWORD:-}" && -f "$ROOT/.env" ]]; then
  _pw="$(sed -n 's/^[[:space:]]*MINISIGN_PASSWORD[[:space:]]*=[[:space:]]*//p' "$ROOT/.env" | head -n1)"
  [[ -n "$_pw" ]] && export MINISIGN_PASSWORD="$_pw"
fi

echo "==> Python venv"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[gui,analysis,download,metadata,convert,build]"

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

echo "==> Bundled minisign (update verifier)"
if [[ ! -x "packaging/bin/macos/minisign" ]]; then
  if command -v minisign >/dev/null 2>&1; then
    cp "$(command -v minisign)" packaging/bin/macos/minisign
    chmod +x packaging/bin/macos/minisign
    echo "    staged minisign from $(command -v minisign)"
  else
    echo "    WARNING: minisign not found — online update verification won't work."
    echo "    Install it first:  brew install minisign"
  fi
fi
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

# Auto-tier decides whether THIS release can also offer a delta. The full .dmg is
# ALWAYS built (fresh installs + the client's fallback); a delta .zip is built
# ALONGSIDE it when the diff is code-only (delta-over-the-wire).
TIER="full"
if [[ -n "$PREV" ]]; then
  DIFF_OUT="$(python packaging/make_manifest.py diff "$PREV" "$NEW_MANIFEST")"
  echo "$DIFF_OUT" | sed 's/^/    /'
  if echo "$DIFF_OUT" | grep -q 'tier=delta'; then TIER="delta"; fi
fi
WANT_DELTA=""
[[ "$TIER" == "delta" && -n "$PREV" ]] && WANT_DELTA=1

echo "==> DMG (full, v$VERSION)"
bash packaging/macos/make_dmg.sh "$VERSION"
FULL="dist/cratedig-${VERSION}.dmg"
ASSETS=("$FULL")

if [[ -n "$WANT_DELTA" ]]; then
  echo "==> macOS DELTA update zip (v$VERSION)"
  DELTA="dist/cratedig-update-${VERSION}-mac.zip"
  python packaging/make_manifest.py build-delta-zip "$PREV" "$NEW_MANIFEST" dist/cratedig.app "$DELTA"
  ASSETS+=("$DELTA")
fi

echo "==> Release meta (delta gate)"
META="dist/release-meta-${VERSION}.json"
if [[ -n "$WANT_DELTA" ]]; then
  python packaging/make_manifest.py emit-release-meta "$NEW_MANIFEST" "$META" --old "$PREV"
else
  python packaging/make_manifest.py emit-release-meta "$NEW_MANIFEST" "$META"
fi
ASSETS+=("$META")

if [[ -n "${SIGN:-}" || -n "${PUBLISH:-}" ]]; then
  echo "==> Sign assets (minisign)"
  : "${MINISIGN_PASSWORD:?set MINISIGN_PASSWORD (the minisign.key password) before signing}"
  [[ -f "$ROOT/minisign.key" ]] || { echo "minisign.key not found at $ROOT/minisign.key"; exit 1; }
  for a in "${ASSETS[@]}"; do
    printf '%s\n' "$MINISIGN_PASSWORD" | minisign -S -m "$a" -s "$ROOT/minisign.key" \
      -x "$a.minisig" -c "cratedig $VERSION" -t "cratedig $VERSION"
    echo "    signed: $a.minisig"
  done
fi

if [[ -n "${PUBLISH:-}" ]]; then
  echo "==> Publish to GitHub Releases (gh)"
  if ! gh release view "$VERSION" >/dev/null 2>&1; then
    gh release create "$VERSION" --title "CRATEDIG $VERSION" \
      --notes "cratedig $VERSION (online-update baseline)."
  fi
  UPLOADS=()
  for a in "${ASSETS[@]}"; do UPLOADS+=("$a" "$a.minisig"); done
  gh release upload "$VERSION" "${UPLOADS[@]}" --clobber
  echo "    published $VERSION"
fi

echo
echo "Done (tier=$TIER, delta=${WANT_DELTA:-0}):"
echo "  dist/cratedig.app"
echo "  $NEW_MANIFEST"
for a in "${ASSETS[@]}"; do echo "  $a"; done
echo
echo "Unsigned build. On the target Mac, first launch = right-click the app -> Open,"
echo "or run:  xattr -dr com.apple.quarantine /Applications/cratedig.app"
