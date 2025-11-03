#!/bin/bash
# Quick start script for live network testing

echo "=========================================="
echo "NetMapper-Lite Live Network Test"
echo "=========================================="
echo ""

# Check if helper is running
if [ -e /tmp/netmapper-helper.sock ]; then
    echo "✅ Helper service is running"
else
    echo "⚠️  Helper service not running"
    echo ""
    echo "Starting helper service..."
    echo ""
    
    # Try to start with capabilities first
    if getcap $(which python3) 2>/dev/null | grep -q net_raw; then
        echo "✅ Python has network capabilities, starting helper..."
        cd "$(dirname "$0")"
        NETMAPPER_DEV=true python3 backend/netmapper_helper.py --dev > /tmp/helper.log 2>&1 &
        sleep 2
    else
        echo "⚠️  Python needs network capabilities for ARP scanning"
        echo ""
        echo "Option 1: Set capabilities (one-time, requires sudo):"
        echo "   sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)"
        echo ""
        echo "Option 2: Run helper with sudo (Terminal 1):"
        echo "   cd $(dirname "$0")"
        echo "   sudo python3 backend/netmapper_helper.py --dev"
        echo ""
        read -p "Press Enter after starting helper, or Ctrl+C to exit..."
    fi
fi

echo ""
echo "=========================================="
echo "Starting GUI..."
echo "=========================================="
echo ""

cd "$(dirname "$0")"

# Detect network
NETWORK_IP=$(python3 -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()" 2>/dev/null)
if [ -n "$NETWORK_IP" ]; then
    NETWORK_CIDR=$(echo "$NETWORK_IP" | awk -F. '{print $1"."$2"."$3".0/24"}')
    echo "📍 Detected network: $NETWORK_CIDR"
    echo ""
    echo "The GUI will open. Use this CIDR for scanning: $NETWORK_CIDR"
    echo ""
fi

python3 frontend/gui.py


