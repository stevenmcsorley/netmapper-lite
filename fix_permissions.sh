#!/bin/bash
# Script to fix network scanning permissions

echo "=========================================="
echo "NetMapper-Lite Permission Fix"
echo "=========================================="
echo ""

# Stop any running helper
pkill -f netmapper_helper.py 2>/dev/null
sleep 1

echo "Setting network capabilities on Python..."
echo "(This requires sudo password)"
echo ""

# Set capabilities
sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Capabilities set successfully!"
    echo ""
    echo "Verifying:"
    getcap $(which python3)
    echo ""
    echo "Now you can run helper WITHOUT sudo:"
    echo "  python3 backend/netmapper_helper.py --dev"
    echo ""
    echo "Starting helper with capabilities..."
    cd "$(dirname "$0")"
    NETMAPPER_DEV=true python3 backend/netmapper_helper.py --dev > /tmp/helper.log 2>&1 &
    sleep 2
    
    if [ -e /tmp/netmapper-helper.sock ]; then
        echo "✅ Helper started successfully!"
        echo ""
        echo "You can now run the GUI:"
        echo "  python3 frontend/gui.py"
    else
        echo "⚠️  Helper failed to start. Check /tmp/helper.log"
    fi
else
    echo ""
    echo "❌ Failed to set capabilities"
    echo ""
    echo "Alternative: Run helper with sudo:"
    echo "  sudo python3 backend/netmapper_helper.py --dev"
fi

