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

echo "==> Fetch ffmpeg/ffplay (native arch from evermeet.cx)"
mkdir -p packaging/bin/macos
for tool in ffmpeg ffplay; do
  if [[ ! -x "packaging/bin/macos/$tool" ]]; then
    # evermeet.cx can reset the connection mid-transfer; retry to survive it.
    curl -L --retry 5 --retry-delay 3 --retry-all-errors --connect-timeout 30 \
      "https://evermeet.cx/ffmpeg/getrelease/$tool/zip" -o "/tmp/$tool.zip"
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

echo "==> DMG"
bash packaging/macos/make_dmg.sh "$VERSION"

echo
echo "Done:"
echo "  dist/cratedig.app"
echo "  dist/cratedig-${VERSION}.dmg"
echo
echo "Unsigned build. On the target Mac, first launch = right-click the app -> Open,"
echo "or run:  xattr -dr com.apple.quarantine /Applications/cratedig.app"
