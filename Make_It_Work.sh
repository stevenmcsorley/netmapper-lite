#!/bin/bash
# Simple script - just makes it work

cd "$(dirname "$0")"

echo "=========================================="
echo "NetMapper-Lite - Simple Fix"
echo "=========================================="
echo ""

# Stop everything first
echo "Stopping any running instances..."
pkill -f netmapper_helper.py 2>/dev/null || true
sleep 2
rm -f /tmp/netmapper-helper.sock

echo ""
echo "Choose how to run the helper:"
echo ""
echo "Option 1: With sudo (easiest, recommended)"
echo "  Run: sudo python3 backend/netmapper_helper.py --dev"
echo ""
echo "Option 2: Set capabilities (one-time setup)"
echo "  Run: sudo setcap cap_net_raw,cap_net_admin+eip \$(which python3)"
echo "  Then: python3 backend/netmapper_helper.py --dev"
echo ""

read -p "Press Enter to try Option 1 (sudo), or Ctrl+C to exit..."

echo ""
echo "Starting helper with sudo..."
echo "(Enter your password when prompted)"
echo ""

sudo python3 backend/netmapper_helper.py --dev &
sleep 3

if [ -e /tmp/netmapper-helper.sock ]; then
    echo ""
    echo "✅ SUCCESS! Helper is running!"
    echo ""
    echo "Now in ANOTHER terminal, run:"
    echo "  cd $(pwd)"
    echo "  python3 frontend/gui.py"
    echo ""
    echo "Then scan your network - it should work now!"
else
    echo ""
    echo "❌ Helper failed to start"
    tail -10 /tmp/helper.log
fi

