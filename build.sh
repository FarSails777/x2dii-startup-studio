#!/bin/sh
set -eu
cd "$(dirname "$0")"
APP="${OUTPUT_APP:-dist/X2D II 开机工作室.app}"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
clang -fobjc-arc -mmacosx-version-min=13.0 App.m \
    -o "$APP/Contents/MacOS/X2DIIAnimationInstaller" \
    -framework Cocoa -framework UniformTypeIdentifiers
cp installer.py bootstrap.py studio.py x2dii_protocol.py rndis-up "$APP/Contents/Resources/"
mkdir -p "$APP/Contents/Resources/assets"
cp assets/AppIcon.png assets/phaseone-logo.bin assets/phaseone-preview.png "$APP/Contents/Resources/assets/"
cp assets/AppIcon.icns "$APP/Contents/Resources/"
cp THIRD_PARTY_NOTICES.txt "$APP/Contents/Resources/RNDIS-LICENSE.txt"
cat >"$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.x2dii.startup-studio</string>
<key>CFBundleName</key><string>X2D II 开机工作室</string>
<key>CFBundleDisplayName</key><string>X2D II 开机工作室</string>
<key>CFBundleExecutable</key><string>X2DIIAnimationInstaller</string>
<key>CFBundleIconFile</key><string>AppIcon.icns</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.3.1</string>
<key>CFBundleVersion</key><string>4</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
chmod +x "$APP/Contents/MacOS/X2DIIAnimationInstaller" "$APP/Contents/Resources/rndis-up"
codesign --force --deep --sign - "$APP"
echo "$APP"
