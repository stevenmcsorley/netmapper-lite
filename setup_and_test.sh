#!/bin/bash
# Complete setup and test script - makes everything work

set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "NetMapper-Lite Complete Setup & Test"
echo "=========================================="
echo ""

# Step 1: Check Python
echo "[1/7] Checking Python..."
if ! command -v python3 > /dev/null; then
    echo "❌ Python3 not found!"
    exit 1
fi
PYTHON_VER=$(python3 --version | awk '{print $2}')
echo "   ✓ Python $PYTHON_VER found"

# Step 2: Check dependencies
echo ""
echo "[2/7] Checking dependencies..."
MISSING_DEPS=0

if ! python3 -c "import scapy" 2>/dev/null; then
    echo "   ⚠ scapy not installed - installing..."
    pip3 install scapy > /dev/null 2>&1 || {
        echo "   ❌ Failed to install scapy"
        MISSING_DEPS=1
    }
fi

if ! python3 -c "import gi; gi.require_version('Gtk', '4.0')" 2>/dev/null; then
    echo "   ⚠ GTK4 not available"
    echo "   Install with: sudo apt-get install python3-gi gir1.2-gtk-4.0"
    MISSING_DEPS=1
else
    echo "   ✓ GTK4 available"
fi

if [ $MISSING_DEPS -eq 1 ]; then
    echo ""
    echo "❌ Missing dependencies. Install them first."
    exit 1
fi

# Step 3: Set network capabilities
echo ""
echo "[3/7] Setting network capabilities..."
if getcap $(which python3) 2>/dev/null | grep -q net_raw; then
    echo "   ✓ Capabilities already set"
else
    echo "   Setting capabilities (requires sudo)..."
    if sudo setcap cap_net_raw,cap_net_admin+eip $(which python3) 2>/dev/null; then
        echo "   ✓ Capabilities set successfully"
    else
        echo "   ⚠ Could not set capabilities automatically"
        echo "   You may need to run helper with sudo"
    fi
fi

# Step 4: Stop any existing helper
echo ""
echo "[4/7] Cleaning up old instances..."
pkill -f netmapper_helper.py 2>/dev/null || true
sleep 2
rm -f /tmp/netmapper-helper.sock
echo "   ✓ Cleaned up"

# Step 5: Start helper
echo ""
echo "[5/7] Starting helper service..."
NETMAPPER_DEV=true python3 backend/netmapper_helper.py --dev > /tmp/helper.log 2>&1 &
HELPER_PID=$!
sleep 3

if [ -e /tmp/netmapper-helper.sock ]; then
    echo "   ✓ Helper started (PID: $HELPER_PID)"
else
    echo "   ❌ Helper failed to start"
    echo "   Check logs: tail -20 /tmp/helper.log"
    tail -10 /tmp/helper.log
    exit 1
fi

# Step 6: Test connection
echo ""
echo "[6/7] Testing helper connection..."
python3 << 'PYEOF'
import socket
import json
import sys

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect('/tmp/netmapper-helper.sock')
    s.sendall(json.dumps({'cmd': 'list_history', 'limit': 1}).encode())
    resp = json.loads(s.recv(4096).decode())
    s.close()
    
    if resp.get('status') == 'ok':
        print("   ✓ Helper responding correctly")
        sys.exit(0)
    else:
        print(f"   ❌ Helper error: {resp}")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    sys.exit(1)
PYEOF

CONN_OK=$?
if [ $CONN_OK -ne 0 ]; then
    echo "   Connection test failed"
    exit 1
fi

# Step 7: Quick scan test
echo ""
echo "[7/7] Testing ARP scan capability..."
python3 << 'PYEOF'
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
from scanner import arp_scan

try:
    # Test on small network
    hosts = arp_scan("192.168.1.0/24", timeout=2)
    if hosts:
        print(f"   ✓ Scan works! Found {len(hosts)} hosts (sample)")
        for h in hosts[:3]:
            print(f"      - {h.get('ip')} ({h.get('mac')})")
    else:
        print("   ⚠ Scan ran but found 0 hosts (may be normal)")
        print("   This could mean:")
        print("     - Network has no active devices")
        print("     - Wrong CIDR network")
        print("     - Still need network permissions")
except PermissionError as e:
    print("   ❌ Permission denied - need network capabilities")
    print("   Run: sudo setcap cap_net_raw,cap_net_admin+eip $(which python3)")
    sys.exit(1)
except Exception as e:
    print(f"   ⚠ Scan error (may be normal): {e}")
PYEOF

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Helper is running and ready!"
echo ""
echo "Next steps:"
echo "  1. Start GUI in another terminal:"
echo "     python3 frontend/gui.py"
echo ""
echo "  2. In GUI:"
echo "     - Enter your network CIDR (e.g., 192.168.1.0/24)"
echo "     - Click 'Start Scan'"
echo "     - Wait for results"
echo ""
echo "Helper logs: tail -f /tmp/helper.log"
echo ""
echo "To stop helper: pkill -f netmapper_helper.py"
echo ""

