#!/bin/bash
# Script to restart helper with proper network permissions

echo "=========================================="
echo "NetMapper Helper - Restart with Permissions"
echo "=========================================="
echo ""

# Stop any running helper
echo "Stopping current helper..."
pkill -f netmapper_helper.py 2>/dev/null
sleep 2

# Check if capabilities are set
if getcap $(which python3) 2>/dev/null | grep -q net_raw; then
    echo "✅ Network capabilities already set on Python"
    echo ""
    echo "Starting helper..."
    cd "$(dirname "$0")"
    NETMAPPER_DEV=true python3 backend/netmapper_helper.py --dev > /tmp/helper.log 2>&1 &
    sleep 2
    
    if [ -e /tmp/netmapper-helper.sock ]; then
        echo "✅ Helper started successfully!"
        echo ""
        echo "Test the scan now - it should find hosts!"
    else
        echo "❌ Helper failed to start. Check /tmp/helper.log"
        tail -5 /tmp/helper.log
    fi
else
    echo "❌ Network capabilities NOT set"
    echo ""
    echo "To fix, run (requires sudo password):"
    echo "  sudo setcap cap_net_raw,cap_net_admin+eip \$(which python3)"
    echo ""
    echo "Then run this script again, or start helper manually:"
    echo "  python3 backend/netmapper_helper.py --dev"
    echo ""
    echo "Alternative: Run helper with sudo (no capabilities needed):"
    echo "  sudo python3 backend/netmapper_helper.py --dev"
fi


