#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script must run on your Apple Silicon Mac, not on Windows."
  exit 1
fi
if [ "$(uname -m)" != "arm64" ]; then
  echo "Use a native Apple Silicon terminal and arm64 Python (not Rosetta)."
  exit 1
fi
PYTHON="${RF_PYTHON:-python3}"
"$PYTHON" -c 'import sys,platform,tkinter; assert sys.version_info >= (3,11); assert platform.machine()=="arm64", "Use arm64 Python"'
BUILD="$ROOT/.build-macos"
mkdir -p "$BUILD" "$ROOT/release-macos"
"$PYTHON" -m venv "$BUILD/venv"
PY="$BUILD/venv/bin/python"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r requirements-macos.txt
"$PY" tests_portable.py
"$PY" tests_macos_contract.py
"$PY" -m pip freeze > "$ROOT/release-macos/build-dependencies.txt"
"$PY" - "$BUILD" <<'PY'
import importlib.metadata as md, importlib.util, shutil,sys
from pathlib import Path
build=Path(sys.argv[1]); target=build/'licenses'
shutil.copytree('licenses',target,dirs_exist_ok=True)
for d in md.distributions():
    for f in d.files or []:
        if any('license' in s.lower() or 'copying' in s.lower() for s in f.parts):
            source=Path(d.locate_file(f))
            if source.is_file():
                name=(d.metadata['Name']+'-'+str(f).replace('/','_'))
                shutil.copyfile(source,target/name)
src=Path(importlib.util.find_spec('pynput').origin).parent
shutil.copytree(src,build/'third-party-source'/'pynput',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
PY
"$PY" -m PyInstaller --noconfirm --clean --windowed --name ResearchFlowAI \
  --osx-bundle-identifier com.researchflowai.desktop --target-architecture arm64 \
  --hidden-import pynput.keyboard._darwin --hidden-import pynput._util.darwin \
  --exclude-module windows_integration --exclude-module pystray \
  --add-data "$BUILD/licenses:licenses" --add-data "$BUILD/third-party-source:third-party-source" --add-data "README-macOS.md:." \
  --add-data "THIRD-PARTY-NOTICES.txt:." \
  --distpath "$BUILD/dist" --workpath "$BUILD/pyinstaller" --specpath "$BUILD" app.py
APP="$BUILD/dist/ResearchFlowAI.app"
"$PY" - "$APP/Contents/Info.plist" <<'PY'
import plistlib,sys
from pathlib import Path
p=Path(sys.argv[1]); d=plistlib.loads(p.read_bytes())
d.update(CFBundleShortVersionString='0.3.0', CFBundleVersion='0.3.0',
         LSMinimumSystemVersion='14.0', NSHighResolutionCapable=True)
p.write_bytes(plistlib.dumps(d))
PY
# Local ad-hoc signing makes the Apple Silicon bundle runnable. It is NOT a
# Developer ID signature or notarization and does not bypass Gatekeeper.
/usr/bin/codesign --force --deep --sign - "$APP"
"$APP/Contents/MacOS/ResearchFlowAI" --self-test "$ROOT/release-macos/runtime-self-test.json"
STAGE="$(mktemp -d "$BUILD/dmg-stage.XXXXXX")"
/usr/bin/ditto "$APP" "$STAGE/ResearchFlowAI.app"
/bin/ln -s /Applications "$STAGE/Applications"
/usr/bin/hdiutil create -volname ResearchFlowAI -srcfolder "$STAGE" -ov -format UDZO \
  "$ROOT/release-macos/ResearchFlowAI-macOS-arm64.dmg"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ROOT/release-macos/ResearchFlowAI-macOS-arm64.app.zip"
echo "Built: $ROOT/release-macos/ResearchFlowAI-macOS-arm64.dmg"
echo "Now test the installed app, Accessibility/Input Monitoring, selection and replacement on your Mac."
