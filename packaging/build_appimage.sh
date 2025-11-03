#!/bin/bash
# Build AppImage for NetMapper-Lite

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/appimage"
APPIMAGE_NAME="NetMapper-Lite-x86_64.AppImage"

echo "=========================================="
echo "Building NetMapper-Lite AppImage"
echo "=========================================="
echo ""

# Create build directory
mkdir -p "$BUILD_DIR/AppDir"

# AppDir structure
APPDIR="$BUILD_DIR/AppDir"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/lib/netmapper"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

echo "[1/6] Copying application files..."

# Copy backend
cp -r "$PROJECT_ROOT/backend/"* "$APPDIR/usr/lib/netmapper/"
chmod +x "$APPDIR/usr/lib/netmapper/netmapper_helper.py"
chmod +x "$APPDIR/usr/lib/netmapper/scanner.py"

# Copy frontend
cp "$PROJECT_ROOT/frontend/gui.py" "$APPDIR/usr/bin/netmapper-gui"
chmod +x "$APPDIR/usr/bin/netmapper-gui"

# Create launcher script
cat > "$APPDIR/AppRun" << 'LAUNCHER'
#!/bin/bash
# AppRun script for NetMapper-Lite AppImage

HERE="$(dirname "$(readlink -f "${0}")")"
cd "$HERE"

# Set environment
export PATH="$HERE/usr/bin:$PATH"
export PYTHONPATH="$HERE/usr/lib:$PYTHONPATH"

# Start helper with sudo (will prompt)
sudo "$HERE/usr/lib/netmapper/netmapper_helper.py" --dev > /tmp/netmapper-helper.log 2>&1 &
sleep 2

# Start GUI
exec "$HERE/usr/bin/netmapper-gui"
LAUNCHER

chmod +x "$APPDIR/AppRun"

echo "[2/6] Creating desktop entry..."

# Desktop entry
cat > "$APPDIR/usr/share/applications/netmapper-lite.desktop" << 'DESKTOP'
[Desktop Entry]
Type=Application
Name=NetMapper-Lite
Comment=Network mapping and device discovery tool
Exec=netmapper-gui
Icon=netmapper-lite
Categories=Network;System;
Terminal=false
DESKTOP

echo "[3/6] Creating icon (placeholder)..."
# Create a simple icon (256x256 placeholder)
# In production, replace with actual icon
convert -size 256x256 xc:transparent -fill '#2196F3' -draw 'circle 128,128 128,64' \
  -pointsize 72 -fill white -gravity center -annotate +0+0 'NM' \
  "$APPDIR/usr/share/icons/hicolor/256x256/apps/netmapper-lite.png" 2>/dev/null || \
  echo "⚠ Icon generation skipped (ImageMagick not installed)"

echo "[4/6] Downloading AppImageTool..."
cd "$BUILD_DIR"

# Download AppImageTool if not present
if [ ! -f "appimagetool-x86_64.AppImage" ]; then
    wget -q https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x appimagetool-x86_64.AppImage
fi

echo "[5/6] Creating AppImage..."
./appimagetool-x86_64.AppImage "$APPDIR"

echo "[6/6] Finalizing..."
mv NetMapper-Lite*.AppImage "$APPIMAGE_NAME" 2>/dev/null || true

if [ -f "$APPIMAGE_NAME" ]; then
    echo ""
    echo "✅ AppImage created successfully!"
    echo "   Location: $BUILD_DIR/$APPIMAGE_NAME"
    echo ""
    echo "To make executable and test:"
    echo "   chmod +x $BUILD_DIR/$APPIMAGE_NAME"
    echo "   $BUILD_DIR/$APPIMAGE_NAME"
else
    echo "❌ AppImage creation failed"
    exit 1
fi

