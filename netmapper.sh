#!/bin/bash
# Alternative launcher - installs to PATH

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing NetMapper launcher to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Create launcher script
cat > "$INSTALL_DIR/netmapper" << 'LAUNCHER'
#!/bin/bash
cd "$HOME/projects/software/netmapper-lite" || cd "/opt/netmapper-lite" || { echo "Cannot find netmapper-lite directory"; exit 1; }

# Stop any existing helper
pkill -f netmapper_helper.py 2>/dev/null || true
sleep 1
rm -f /tmp/netmapper-helper.sock

# Check if we need sudo
NEED_SUDO=0
if ! getcap $(which python3) 2>/dev/null | grep -q net_raw; then
    NEED_SUDO=1
fi

if [ $NEED_SUDO -eq 1 ]; then
    echo "Starting helper with sudo..."
    sudo -b python3 backend/netmapper_helper.py --dev > /tmp/helper.log 2>&1
else
    NETMAPPER_DEV=true python3 backend/netmapper_helper.py --dev > /tmp/helper.log 2>&1 &
fi

# Wait for helper
for i in {1..10}; do
    [ -e /tmp/netmapper-helper.sock ] && break
    sleep 0.5
done

if [ ! -e /tmp/netmapper-helper.sock ]; then
    echo "❌ Helper failed to start. Check: tail /tmp/helper.log"
    exit 1
fi

# Start GUI
python3 frontend/gui.py

# Cleanup on exit
pkill -f netmapper_helper.py 2>/dev/null || true
rm -f /tmp/netmapper-helper.sock
LAUNCHER

chmod +x "$INSTALL_DIR/netmapper"

if [ -d "$INSTALL_DIR" ] && [[ ":$PATH:" == *":$INSTALL_DIR:"* ]]; then
    echo "✅ Installed! Now you can run: netmapper"
elif [ -d "$INSTALL_DIR" ]; then
    echo "✅ Installed to $INSTALL_DIR"
    echo "Add to PATH: export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "Or run: $INSTALL_DIR/netmapper"
else
    echo "✅ Script ready. Run: $INSTALL_DIR/netmapper"
fi

